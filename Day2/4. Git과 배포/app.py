"""
retriever.py의 hybrid retrieve()를 이용해 관련 문서를 검색하고,
ollama의 qwen3-vl:4b-instruct 모델로 답변을 생성하는 Streamlit RAG 챗봇.
"""

import json
from pathlib import Path

import requests
import streamlit as st

from retriever import retrieve

BASE_DIR = Path(__file__).parent
CHUNKS_DIR = BASE_DIR / "chunks"

OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
LLM_MODEL = "qwen3-vl:4b-instruct"

TOP_K = 5

SYSTEM_PROMPT = (
    "당신은 주어진 참고 문서를 바탕으로 사용자의 질문에 답하는 한국어 어시스턴트입니다. "
    "반드시 아래 참고 문서의 내용에 근거하여 답변하고, 문서에 없는 내용은 모른다고 답하세요."
)


def load_chunk_text(chunk_file: str) -> str:
    path = CHUNKS_DIR / chunk_file
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "(문서 내용을 불러올 수 없습니다.)"


def build_context(results: list[dict]) -> str:
    parts = []
    for r in results:
        text = load_chunk_text(r["chunk_file"])
        parts.append(
            f"[문서 {r['rank']}] (출처: {r['source_file']})\n{text}"
        )
    return "\n\n".join(parts)


def stream_answer(query: str, context: str, history: list[dict]):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append(
        {
            "role": "user",
            "content": f"[참고 문서]\n{context}\n\n[질문]\n{query}",
        }
    )

    with requests.post(
        OLLAMA_CHAT_URL,
        json={"model": LLM_MODEL, "messages": messages, "stream": True},
        stream=True,
        timeout=300,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            if chunk.get("done"):
                break
            content = chunk.get("message", {}).get("content", "")
            if content:
                yield content


st.set_page_config(page_title="문서 기반 RAG 챗봇", page_icon="📚", layout="wide")
st.title("📚 문서 기반 RAG 챗봇")
st.caption(f"LLM: ollama/{LLM_MODEL} · Retriever: hybrid (dense + sparse)")

if "messages" not in st.session_state:
    st.session_state.messages = []  # [{role, content}]
if "sources" not in st.session_state:
    st.session_state.sources = {}  # message index -> results

for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and i in st.session_state.sources:
            with st.expander("🔎 참고한 관련 문서"):
                for r in st.session_state.sources[i]:
                    st.markdown(
                        f"**{r['rank']}. {r['source_file']}** "
                        f"(hybrid={r['hybrid_score']:.3f}, "
                        f"dense={r['dense_score']:.3f}, sparse={r['sparse_score']:.3f})"
                    )
                    st.text(load_chunk_text(r["chunk_file"]))

query = st.chat_input("질문을 입력하세요")

if query:
    st.session_state.messages.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)

    with st.chat_message("assistant"):
        with st.spinner("관련 문서 검색 중..."):
            try:
                results = retrieve(query, top_k=TOP_K)
            except Exception as e:
                results = []
                st.error(f"검색 중 오류가 발생했습니다: {e}")

        context = build_context(results) if results else "(관련 문서를 찾지 못했습니다.)"

        history = [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.messages[:-1]
        ]

        answer_box = st.empty()
        answer = ""
        try:
            for piece in stream_answer(query, context, history):
                answer += piece
                answer_box.markdown(answer + "▌")
            answer_box.markdown(answer)
        except Exception as e:
            answer = f"LLM 호출 중 오류가 발생했습니다: {e}"
            answer_box.markdown(answer)

        if results:
            with st.expander("🔎 참고한 관련 문서"):
                for r in results:
                    st.markdown(
                        f"**{r['rank']}. {r['source_file']}** "
                        f"(hybrid={r['hybrid_score']:.3f}, "
                        f"dense={r['dense_score']:.3f}, sparse={r['sparse_score']:.3f})"
                    )
                    st.text(load_chunk_text(r["chunk_file"]))

    st.session_state.messages.append({"role": "assistant", "content": answer})
    st.session_state.sources[len(st.session_state.messages) - 1] = results
