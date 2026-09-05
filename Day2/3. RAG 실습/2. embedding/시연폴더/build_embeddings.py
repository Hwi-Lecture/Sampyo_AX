"""
chunks 폴더의 문서 청크들을 임베딩 벡터로 변환하여 embeddings 폴더에 저장한다.

- Sparse vector: BM25 (rank_bm25)
- Dense vector: Ollama의 embeddinggemma 모델

출력 (embeddings/):
  - dense.jsonl   : 청크별 dense 임베딩 벡터
  - sparse.jsonl  : 청크별 BM25 sparse 벡터 (term_id -> weight)
  - vocab.json    : BM25 sparse 벡터의 term_id -> token 매핑
  - bm25_meta.json: BM25 파라미터(k1, b, 평균 문서 길이 등)
"""

import json
import re
from pathlib import Path

import requests
from rank_bm25 import BM25Okapi

BASE_DIR = Path(__file__).parent
CHUNKS_DIR = BASE_DIR / "chunks"
MANIFEST_PATH = CHUNKS_DIR / "manifest.jsonl"
EMBEDDINGS_DIR = BASE_DIR / "embeddings"

OLLAMA_URL = "http://localhost:11434/api/embed"
OLLAMA_MODEL = "embeddinggemma"

TOKEN_RE = re.compile(r"[가-힣]+|[A-Za-z]+|[0-9]+(?:\.[0-9]+)?")


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def load_manifest() -> list[dict]:
    entries = []
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def load_chunk_text(chunk_file: str) -> str:
    path = CHUNKS_DIR / chunk_file
    return path.read_text(encoding="utf-8")


def embed_dense(text: str) -> list[float]:
    resp = requests.post(
        OLLAMA_URL,
        json={"model": OLLAMA_MODEL, "input": text},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["embeddings"][0]


def main():
    EMBEDDINGS_DIR.mkdir(exist_ok=True)

    manifest = load_manifest()
    print(f"총 {len(manifest)}개 청크를 로드합니다.")

    texts = []
    for entry in manifest:
        text = load_chunk_text(entry["chunk_file"])
        entry["text"] = text
        texts.append(text)

    # ---- Sparse vector (BM25) ----
    print("BM25 sparse 벡터를 계산합니다...")
    tokenized_corpus = [tokenize(t) for t in texts]
    bm25 = BM25Okapi(tokenized_corpus)

    vocab: dict[str, int] = {}

    def token_id(tok: str) -> int:
        if tok not in vocab:
            vocab[tok] = len(vocab)
        return vocab[tok]

    sparse_records = []
    for entry, doc_tokens in zip(manifest, tokenized_corpus):
        if not doc_tokens:
            sparse_records.append({
                "chunk_file": entry["chunk_file"],
                "source_file": entry["source_file"],
                "chunk_index": entry["chunk_index"],
                "indices": [],
                "values": [],
            })
            continue

        term_freq: dict[str, int] = {}
        for tok in doc_tokens:
            term_freq[tok] = term_freq.get(tok, 0) + 1

        doc_len = len(doc_tokens)
        idf = bm25.idf
        avgdl = bm25.avgdl
        k1 = bm25.k1
        b = bm25.b

        indices = []
        values = []
        for tok, freq in term_freq.items():
            tok_idf = idf.get(tok, 0.0)
            if tok_idf == 0.0:
                continue
            denom = freq + k1 * (1 - b + b * doc_len / avgdl)
            score = tok_idf * (freq * (k1 + 1)) / denom
            if score <= 0:
                continue
            indices.append(token_id(tok))
            values.append(round(float(score), 6))

        sparse_records.append({
            "chunk_file": entry["chunk_file"],
            "source_file": entry["source_file"],
            "chunk_index": entry["chunk_index"],
            "indices": indices,
            "values": values,
        })

    sparse_path = EMBEDDINGS_DIR / "sparse.jsonl"
    with open(sparse_path, "w", encoding="utf-8") as f:
        for rec in sparse_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"저장 완료: {sparse_path} ({len(sparse_records)}개)")

    vocab_path = EMBEDDINGS_DIR / "vocab.json"
    id_to_token = [None] * len(vocab)
    for tok, idx in vocab.items():
        id_to_token[idx] = tok
    with open(vocab_path, "w", encoding="utf-8") as f:
        json.dump(id_to_token, f, ensure_ascii=False, indent=2)
    print(f"저장 완료: {vocab_path} (vocab size={len(vocab)})")

    meta_path = EMBEDDINGS_DIR / "bm25_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "k1": bm25.k1,
            "b": bm25.b,
            "avgdl": bm25.avgdl,
            "doc_count": bm25.corpus_size,
            "vocab_size": len(vocab),
            "tokenizer": "regex: 한글/영문/숫자 단위",
        }, f, ensure_ascii=False, indent=2)
    print(f"저장 완료: {meta_path}")

    # ---- Dense vector (Ollama embeddinggemma) ----
    print(f"Ollama({OLLAMA_MODEL})로 dense 임베딩을 계산합니다...")
    dense_path = EMBEDDINGS_DIR / "dense.jsonl"
    with open(dense_path, "w", encoding="utf-8") as f:
        for i, entry in enumerate(manifest, 1):
            vector = embed_dense(entry["text"])
            record = {
                "chunk_file": entry["chunk_file"],
                "source_file": entry["source_file"],
                "chunk_index": entry["chunk_index"],
                "model": OLLAMA_MODEL,
                "dim": len(vector),
                "embedding": vector,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"  [{i}/{len(manifest)}] {entry['chunk_file']} -> dim={len(vector)}")
    print(f"저장 완료: {dense_path}")

    print("\n모든 임베딩 생성이 완료되었습니다.")


if __name__ == "__main__":
    main()
