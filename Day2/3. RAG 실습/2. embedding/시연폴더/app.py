"""
저장된 임베딩(dense/sparse)을 이용해 dense retrieval과 sparse retrieval(BM25)을
나란히 비교해보는 Streamlit 앱.

실행: streamlit run search_app.py
"""

import json
import re
from pathlib import Path

import numpy as np
import requests
import streamlit as st

BASE_DIR = Path(__file__).parent
CHUNKS_DIR = BASE_DIR / "chunks"
EMB_DIR = BASE_DIR / "embeddings"

OLLAMA_URL = "http://localhost:11434/api/embed"
OLLAMA_MODEL = "embeddinggemma"

TOKEN_RE = re.compile(r"[가-힣]+|[A-Za-z]+|[0-9]+(?:\.[0-9]+)?")


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def load_jsonl(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


@st.cache_resource
def load_index():
    manifest = {m["chunk_file"]: m for m in load_jsonl(CHUNKS_DIR / "manifest.jsonl")}
    dense = load_jsonl(EMB_DIR / "dense.jsonl")
    sparse = load_jsonl(EMB_DIR / "sparse.jsonl")
    with open(EMB_DIR / "vocab.json", "r", encoding="utf-8") as f:
        vocab: list[str] = json.load(f)
    with open(EMB_DIR / "bm25_meta.json", "r", encoding="utf-8") as f:
        bm25_meta = json.load(f)

    token_to_id = {tok: i for i, tok in enumerate(vocab)}

    order = [d["chunk_file"] for d in dense]
    dense_matrix = np.array([d["embedding"] for d in dense], dtype=np.float64)
    dense_norms = np.linalg.norm(dense_matrix, axis=1, keepdims=True)
    dense_unit = dense_matrix / np.where(dense_norms == 0, 1, dense_norms)

    sparse_by_file = {s["chunk_file"]: s for s in sparse}
    sparse_vecs = []
    for cf in order:
        s = sparse_by_file[cf]
        d = dict(zip(s["indices"], s["values"]))
        sparse_vecs.append(d)

    texts = {}
    for cf in order:
        texts[cf] = (CHUNKS_DIR / cf).read_text(encoding="utf-8")

    meta = []
    for cf in order:
        m = manifest[cf]
        heading_path = m.get("heading_path", [])
        heading_str = " > ".join(h["title"] for h in heading_path) if heading_path else "(제목 없음)"
        meta.append({
            "chunk_file": cf,
            "source_file": m["source_file"],
            "chunk_index": m["chunk_index"],
            "heading_path": heading_str,
        })

    return {
        "order": order,
        "meta": meta,
        "dense_unit": dense_unit,
        "sparse_vecs": sparse_vecs,
        "token_to_id": token_to_id,
        "idf": bm25_meta,
        "texts": texts,
    }


def embed_query(text: str) -> np.ndarray:
    resp = requests.post(
        OLLAMA_URL,
        json={"model": OLLAMA_MODEL, "input": text},
        timeout=60,
    )
    resp.raise_for_status()
    vec = np.array(resp.json()["embeddings"][0], dtype=np.float64)
    return vec / (np.linalg.norm(vec) or 1)


def dense_search(query: str, index: dict, top_k: int = 5):
    qvec = embed_query(query)
    sims = index["dense_unit"] @ qvec
    top_idx = np.argsort(-sims)[:top_k]
    return [(int(i), float(sims[i])) for i in top_idx]


def sparse_search(query: str, index: dict, top_k: int = 5):
    q_tokens = tokenize(query)
    q_ids = {index["token_to_id"][t] for t in q_tokens if t in index["token_to_id"]}
    scores = []
    for i, vec in enumerate(index["sparse_vecs"]):
        score = sum(vec.get(tid, 0.0) for tid in q_ids)
        scores.append(score)
    scores = np.array(scores)
    top_idx = np.argsort(-scores)[:top_k]
    return [(int(i), float(scores[i])) for i in top_idx if scores[i] > 0] or \
           [(int(i), float(scores[i])) for i in top_idx]


def render_result_card(rank: int, idx: int, score: float, index: dict, overlap: bool):
    m = index["meta"][idx]
    text = index["texts"][m["chunk_file"]]
    text = re.sub(r"^#{1,6}\s*", "", text.strip(), flags=re.MULTILINE)
    snippet = text.strip().replace("\n", " ")
    if len(snippet) > 160:
        snippet = snippet[:160] + "…"
    badge = " 🔗 공통" if overlap else ""
    st.markdown(f"**{rank}. {m['heading_path']}**{badge}")
    st.caption(f"score={score:.4f} · {m['source_file']} · {m['chunk_file']}")
    st.write(snippet)
    st.divider()


def main():
    st.set_page_config(page_title="Dense vs Sparse Retrieval", layout="wide")
    st.title("Dense vs Sparse Retrieval 비교")
    st.caption(
        "문장을 입력하면 dense(ollama/embeddinggemma, 코사인 유사도)와 "
        "sparse(BM25) 검색 결과를 나란히 비교합니다. "
    )

    index = load_index()

    query = st.text_input("검색할 문장을 입력하세요", placeholder="예: 지게차 안전 점검 방법")
    top_k = st.slider("표시할 결과 수", 1, 10, 5)

    if not query:
        st.info("문장을 입력하고 Enter를 누르면 검색 결과가 나타납니다.")
        return

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Dense (embeddinggemma)")
        try:
            dense_results = dense_search(query, index, top_k)
        except requests.exceptions.RequestException as e:
            st.error(f"Ollama 호출 실패: {e}\nOllama가 localhost:11434에서 실행 중인지 확인하세요.")
            dense_results = []

    with col2:
        st.subheader("Sparse (BM25)")
        sparse_results = sparse_search(query, index, top_k)

    dense_idxs = {i for i, _ in dense_results}
    sparse_idxs = {i for i, _ in sparse_results}

    with col1:
        for rank, (idx, score) in enumerate(dense_results, 1):
            render_result_card(rank, idx, score, index, overlap=idx in sparse_idxs)

    with col2:
        for rank, (idx, score) in enumerate(sparse_results, 1):
            render_result_card(rank, idx, score, index, overlap=idx in dense_idxs)


if __name__ == "__main__":
    main()
