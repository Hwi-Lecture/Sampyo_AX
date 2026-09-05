"""
사용자가 입력한 두 문장 사이의 유사도를 두 가지 방식으로 비교하는 Streamlit 앱.

- BM25 유사도: chunks/ 안의 60개 청크로 만든 말뭉치의 IDF 통계를 배경으로 사용해,
  두 문장을 서로 질의/문서로 놓고 BM25 점수를 계산 (비대칭이므로 양방향 + 평균 제공)
- Dense 유사도: ollama/embeddinggemma로 두 문장을 새로 임베딩한 뒤 코사인 유사도

기존 청크의 사전 계산 벡터(embeddings/)는 사용하지 않는다 — 사용자가 입력하는
두 문장은 말뭉치 밖의 임의의 텍스트이기 때문에, BM25는 배경 통계만 재사용하고
dense는 그때그때 새로 계산한다.

실행: streamlit run score_app.py
"""

import re
from pathlib import Path

import numpy as np
import requests
import streamlit as st
from rank_bm25 import BM25Okapi

BASE_DIR = Path(__file__).parent
CHUNKS_DIR = BASE_DIR / "chunks"

OLLAMA_URL = "http://localhost:11434/api/embed"
OLLAMA_MODEL = "embeddinggemma"

TOKEN_RE = re.compile(r"[가-힣]+|[A-Za-z]+|[0-9]+(?:\.[0-9]+)?")


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


@st.cache_resource
def load_bm25():
    chunk_files = sorted(CHUNKS_DIR.glob("*/chunk_*.md"))
    texts = [f.read_text(encoding="utf-8") for f in chunk_files]
    tokenized_corpus = [tokenize(t) for t in texts]
    bm25 = BM25Okapi(tokenized_corpus)
    return bm25, len(chunk_files)


def bm25_pair_score(query_tokens: list[str], doc_tokens: list[str], bm25: BM25Okapi) -> float:
    """query 문장을 기준으로, doc 문장을 하나의 (말뭉치 밖) 문서로 보고 BM25 점수를 계산."""
    if not query_tokens or not doc_tokens:
        return 0.0

    term_freq: dict[str, int] = {}
    for tok in doc_tokens:
        term_freq[tok] = term_freq.get(tok, 0) + 1

    doc_len = len(doc_tokens)
    k1, b, avgdl = bm25.k1, bm25.b, bm25.avgdl

    score = 0.0
    for tok in set(query_tokens):
        idf = bm25.idf.get(tok, 0.0)
        if idf <= 0:
            continue
        freq = term_freq.get(tok, 0)
        if freq == 0:
            continue
        denom = freq + k1 * (1 - b + b * doc_len / avgdl)
        score += idf * (freq * (k1 + 1)) / denom
    return score


def embed(text: str) -> np.ndarray:
    resp = requests.post(
        OLLAMA_URL,
        json={"model": OLLAMA_MODEL, "input": text},
        timeout=60,
    )
    resp.raise_for_status()
    vec = np.array(resp.json()["embeddings"][0], dtype=np.float64)
    return vec


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def main():
    st.set_page_config(page_title="문장 유사도 비교", layout="centered")
    st.title("두 문장 유사도 비교")
    st.caption(
        "두 문장을 입력하면 BM25 유사도와 embeddinggemma 코사인 유사도를 비교합니다. "
        "BM25의 IDF 통계는 chunks/ 폴더의 60개 청크 말뭉치를 배경으로 사용합니다."
    )

    bm25, n_docs = load_bm25()

    col1, col2 = st.columns(2)
    with col1:
        sent1 = st.text_area("문장 1", placeholder="예: 지게차는 안전인증을 받아야 한다", height=100)
    with col2:
        sent2 = st.text_area("문장 2", placeholder="예: 위험기계는 안전검사를 통과해야 한다", height=100)

    if not sent1 or not sent2:
        st.info("두 문장을 모두 입력하면 결과가 나타납니다.")
        return

    tokens1, tokens2 = tokenize(sent1), tokenize(sent2)

    with st.expander("토큰화 결과 보기"):
        st.write("문장 1:", tokens1)
        st.write("문장 2:", tokens2)

    st.divider()

    # ---- BM25 ----
    st.subheader("BM25 유사도")
    st.caption(f"배경 말뭉치: chunks/ 청크 {n_docs}개 (IDF 통계용, 이 청크들과 직접 비교하는 것이 아님)")

    score_1to2 = bm25_pair_score(tokens1, tokens2, bm25)
    score_2to1 = bm25_pair_score(tokens2, tokens1, bm25)
    avg_score = (score_1to2 + score_2to1) / 2

    b1, b2, b3 = st.columns(3)
    b1.metric("문장1 → 문장2", f"{score_1to2:.3f}")
    b2.metric("문장2 → 문장1", f"{score_2to1:.3f}")
    b3.metric("평균 (양방향)", f"{avg_score:.3f}")
    st.caption(
        "BM25는 원래 '질의 → 문서' 방향으로 비대칭입니다. 화살표 왼쪽 문장을 질의, "
        "오른쪽 문장을 문서로 보고 점수를 계산했습니다."
    )

    st.divider()

    # ---- Dense ----
    st.subheader("Dense 유사도 (embeddinggemma)")
    try:
        vec1 = embed(sent1)
        vec2 = embed(sent2)
        dense_sim = cosine(vec1, vec2)
        st.metric("코사인 유사도", f"{dense_sim:.4f}")
    except requests.exceptions.RequestException as e:
        st.error(f"Ollama 호출 실패: {e}\nOllama가 localhost:11434에서 실행 중인지 확인하세요.")


if __name__ == "__main__":
    main()
