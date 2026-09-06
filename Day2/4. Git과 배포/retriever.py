"""
embeddings 폴더(dense.jsonl, sparse.jsonl, vocab.json)에 저장된 문서 벡터를 이용해
dense retrieval과 sparse(BM25) retrieval 결과를 절반씩 반영한 hybrid retrieval을 수행한다.
"""

import json
import re
from pathlib import Path

import numpy as np
import requests

BASE_DIR = Path(__file__).parent
EMBEDDINGS_DIR = BASE_DIR / "embeddings"

OLLAMA_URL = "http://localhost:11434/api/embed"
OLLAMA_MODEL = "embeddinggemma"

TOKEN_RE = re.compile(r"[가-힣]+|[A-Za-z]+|[0-9]+(?:\.[0-9]+)?")


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def _load_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _embed_query_dense(query: str) -> np.ndarray:
    resp = requests.post(
        OLLAMA_URL,
        json={"model": OLLAMA_MODEL, "input": query},
        timeout=120,
    )
    resp.raise_for_status()
    vector = resp.json()["embeddings"][0]
    return np.array(vector, dtype=np.float32)


def _cosine_similarity(query_vec: np.ndarray, doc_vecs: np.ndarray) -> np.ndarray:
    query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
    doc_norms = doc_vecs / (np.linalg.norm(doc_vecs, axis=1, keepdims=True) + 1e-10)
    return doc_norms @ query_norm


def _min_max_normalize(scores: np.ndarray) -> np.ndarray:
    lo, hi = float(scores.min()), float(scores.max())
    if hi - lo < 1e-10:
        return np.zeros_like(scores)
    return (scores - lo) / (hi - lo)


def retrieve(query: str, top_k: int = 5, dense_weight: float = 0.5,
             embeddings_dir: Path = EMBEDDINGS_DIR) -> list[dict]:
    """
    사용자 입력 문장(query)에 대해 embeddings 폴더의 문서 벡터를 검색하여
    dense retrieval과 sparse(BM25) retrieval 결과를 각각 dense_weight : (1-dense_weight)
    비율로 반영한 hybrid retrieval 결과를 반환한다. (기본값: 5:5)

    Returns
    -------
    list[dict]: hybrid_score 내림차순으로 정렬된 top_k개의 검색 결과.
        각 dict는 chunk_file, source_file, chunk_index,
        hybrid_score, dense_score(cosine 유사도), sparse_score(BM25 원점수)를 포함한다.
    """
    embeddings_dir = Path(embeddings_dir)

    dense_records = _load_jsonl(embeddings_dir / "dense.jsonl")
    sparse_records = _load_jsonl(embeddings_dir / "sparse.jsonl")
    with open(embeddings_dir / "vocab.json", "r", encoding="utf-8") as f:
        vocab: list[str] = json.load(f)
    token_to_id = {tok: idx for idx, tok in enumerate(vocab)}

    # ---- Dense retrieval: 쿼리 임베딩과 문서 임베딩 간 cosine 유사도 ----
    query_dense = _embed_query_dense(query)
    doc_dense = np.array([rec["embedding"] for rec in dense_records], dtype=np.float32)
    dense_scores = _cosine_similarity(query_dense, doc_dense)

    # ---- Sparse retrieval: 쿼리 토큰과 겹치는 문서의 BM25 가중치 합산 ----
    # (sparse.jsonl에는 문서별로 이미 계산된 BM25 term weight가 저장되어 있으므로,
    #  표준 BM25 스코어링 방식대로 쿼리에 등장한 term의 weight만 합산하면 된다.)
    query_term_ids = {token_to_id[tok] for tok in tokenize(query) if tok in token_to_id}

    sparse_scores = np.zeros(len(sparse_records), dtype=np.float32)
    for i, rec in enumerate(sparse_records):
        score = 0.0
        for idx, val in zip(rec["indices"], rec["values"]):
            if idx in query_term_ids:
                score += val
        sparse_scores[i] = score

    # ---- 정규화 후 hybrid 결합 ----
    dense_norm = _min_max_normalize(dense_scores)
    sparse_norm = _min_max_normalize(sparse_scores)
    hybrid_scores = dense_weight * dense_norm + (1 - dense_weight) * sparse_norm

    order = np.argsort(-hybrid_scores)[:top_k]

    results = []
    for rank, i in enumerate(order, start=1):
        rec = dense_records[i]
        results.append({
            "rank": rank,
            "chunk_file": rec["chunk_file"],
            "source_file": rec["source_file"],
            "chunk_index": rec["chunk_index"],
            "hybrid_score": float(hybrid_scores[i]),
            "dense_score": float(dense_scores[i]),
            "sparse_score": float(sparse_scores[i]),
        })
    return results


if __name__ == "__main__":
    test_queries = [
        "콘크리트 단위수량 측정 방법",
        "산업안전보건법 개정 내용",
    ]

    for test_query in test_queries:
        print(f"\n[테스트 질의] {test_query}")
        results = retrieve(test_query, top_k=5)
        for r in results:
            print(
                f"  {r['rank']}. {r['chunk_file']} "
                f"(hybrid={r['hybrid_score']:.4f}, "
                f"dense={r['dense_score']:.4f}, sparse={r['sparse_score']:.4f})"
            )
