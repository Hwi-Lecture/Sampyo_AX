"""
두 가지 기능을 하나로 합친 Streamlit 챗봇.

1. 국가별 석탄 수출입 통계(df_all.csv) 관련 질문
   -> csv_chatbot.py의 ollama tool-calling(pandas 코드 실행)으로 답변.
2. 산업안전보건법 개정내용 / 단위수량시험 제규격 등 문서 관련 질문
   -> retriever.py의 hybrid retrieve()로 관련 문서를 찾아 RAG로 답변.

질문 내용에 따라 두 기능 중 어느 것을 사용할지 자동으로 판별하며,
사이드바에서 판별 방식을 수동으로 고정할 수도 있다.
"""

import json
from pathlib import Path

import requests
import streamlit as st

from csv_chatbot import (
    MODEL as CSV_MODEL,
    SYSTEM_PROMPT as CSV_SYSTEM_PROMPT,
    TOOL_IMPL,
    TOOLS,
    build_pandas_query,
    chat,
)
from retriever import retrieve

BASE_DIR = Path(__file__).parent
CHUNKS_DIR = BASE_DIR / "chunks"

OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
RAG_LLM_MODEL = "qwen3-vl:4b-instruct"

TOP_K = 5

RAG_SYSTEM_PROMPT = (
    "당신은 주어진 참고 문서를 바탕으로 사용자의 질문에 답하는 한국어 어시스턴트입니다. "
    "반드시 아래 참고 문서의 내용에 근거하여 답변하고, 문서에 없는 내용은 모른다고 답하세요."
)

# ---- 질문 유형 자동 판별을 위한 키워드 ----
CSV_KEYWORDS = [
    "수입", "수출", "무역수지", "통계", "석탄", "무연탄", "유연탄",
    "호주", "인도네시아", "미국", "중량", "금액", "톤", "달러", "물량",
]
RAG_KEYWORDS = [
    "산업안전보건법", "안전보건", "산업안전", "개정", "법", "규정",
    "단위수량", "콘크리트", "제규격", "규격", "시험", "골재", "kcs",
]


def classify_query(query: str) -> str:
    """질문 내용을 보고 'csv' 또는 'rag' 중 어떤 기능을 사용할지 정한다."""
    q = query.lower()
    csv_hit = any(k.lower() in q for k in CSV_KEYWORDS)
    rag_hit = any(k.lower() in q for k in RAG_KEYWORDS)
    if csv_hit and not rag_hit:
        return "csv"
    if rag_hit and not csv_hit:
        return "rag"
    if csv_hit and rag_hit:
        # 둘 다 걸리면 더 구체적인(개수가 많은) 쪽을 우선한다.
        csv_count = sum(k.lower() in q for k in CSV_KEYWORDS)
        rag_count = sum(k.lower() in q for k in RAG_KEYWORDS)
        return "csv" if csv_count >= rag_count else "rag"
    return "rag"  # 판별 불가 시 문서 검색을 기본으로 사용


# ==================== CSV(통계) 챗봇 로직 ====================

def run_csv_turn(user_input: str):
    """국가별 수입 통계 질문을 pandas tool-calling으로 처리한다."""
    snapshot_len = len(st.session_state.csv_messages)
    st.session_state.csv_messages.append({"role": "user", "content": user_input})
    steps = []

    try:
        response = chat(model=CSV_MODEL, messages=st.session_state.csv_messages, tools=TOOLS)
        msg = response["message"]
        st.session_state.csv_messages.append(msg)

        while msg.get("tool_calls"):
            for tool_call in msg["tool_calls"]:
                fn_name = tool_call["function"]["name"]
                fn_args = tool_call["function"]["arguments"] or {}

                step = {"name": fn_name, "args": fn_args, "query": None, "result": None}
                if fn_name == "filter_and_aggregate":
                    step["query"] = build_pandas_query(**fn_args)

                impl = TOOL_IMPL.get(fn_name)
                if impl is None:
                    result = f"오류: 알 수 없는 도구 '{fn_name}'"
                else:
                    try:
                        result = impl(**fn_args)
                    except Exception as e:
                        result = f"오류: 도구 실행 중 예외 발생 - {e}"
                step["result"] = result
                steps.append(step)
                st.session_state.csv_messages.append({"role": "tool", "content": str(result)})

            response = chat(model=CSV_MODEL, messages=st.session_state.csv_messages, tools=TOOLS)
            msg = response["message"]
            st.session_state.csv_messages.append(msg)

        return steps, msg.get("content", ""), None

    except Exception as e:
        del st.session_state.csv_messages[snapshot_len:]
        return steps, None, str(e)


def render_csv_steps(steps):
    if not steps:
        return
    with st.expander(f"실행 과정 보기 ({len(steps)}단계)", expanded=False):
        for i, step in enumerate(steps, start=1):
            args_str = ", ".join(f"{k}={v!r}" for k, v in step["args"].items())
            st.markdown(f"**{i}. `{step['name']}({args_str})`**")
            if step["query"]:
                st.code(step["query"], language="python")
            st.text(f"결과: {step['result']}")


# ==================== 문서(RAG) 챗봇 로직 ====================

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
        parts.append(f"[문서 {r['rank']}] (출처: {r['source_file']})\n{text}")
    return "\n\n".join(parts)


def run_rag_turn(query: str, history: list[dict]):
    try:
        results = retrieve(query, top_k=TOP_K)
    except Exception as e:
        return [], f"검색 중 오류가 발생했습니다: {e}", None

    context = build_context(results) if results else "(관련 문서를 찾지 못했습니다.)"

    messages = [{"role": "system", "content": RAG_SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": f"[참고 문서]\n{context}\n\n[질문]\n{query}"})

    try:
        resp = requests.post(
            OLLAMA_CHAT_URL,
            json={"model": RAG_LLM_MODEL, "messages": messages, "stream": False},
            timeout=300,
        )
        resp.raise_for_status()
        answer = resp.json().get("message", {}).get("content", "")
        return results, answer, None
    except Exception as e:
        return results, None, str(e)


def render_rag_sources(results):
    if not results:
        return
    with st.expander("🔎 참고한 관련 문서"):
        for r in results:
            st.markdown(
                f"**{r['rank']}. {r['source_file']}** "
                f"(hybrid={r['hybrid_score']:.3f}, "
                f"dense={r['dense_score']:.3f}, sparse={r['sparse_score']:.3f})"
            )
            st.text(load_chunk_text(r["chunk_file"]))


# ==================== Streamlit UI ====================

st.set_page_config(page_title="통합 챗봇", page_icon="🤖", layout="wide")
st.title("🤖 통합 챗봇")
st.caption(
    "국가별 석탄 수출입 통계 질문은 pandas 코드 실행으로, "
    "산업안전보건법·단위수량시험 규격 관련 질문은 문서 검색(RAG)으로 답변합니다."
)

with st.sidebar:
    st.header("설정")
    mode_choice = st.radio(
        "질문 유형 판별 방식",
        ["자동 판별", "통계 데이터(CSV)로 고정", "문서 검색(RAG)으로 고정"],
        index=0,
    )

if "csv_messages" not in st.session_state:
    st.session_state.csv_messages = [{"role": "system", "content": CSV_SYSTEM_PROMPT}]
if "history" not in st.session_state:
    st.session_state.history = []

for turn in st.session_state.history:
    if turn["role"] == "user":
        with st.chat_message("user"):
            st.markdown(turn["content"])
    else:
        with st.chat_message("assistant"):
            st.caption(f"모드: {'📊 통계 데이터' if turn['mode'] == 'csv' else '📚 문서 검색'}")
            if turn["mode"] == "csv":
                render_csv_steps(turn.get("steps"))
            else:
                render_rag_sources(turn.get("sources"))
            if turn.get("error"):
                st.error(f"처리 중 문제가 발생했습니다: {turn['error']}")
            else:
                st.markdown(turn["content"])

user_input = st.chat_input("석탄 수출입 통계나 법령/규격 문서에 대해 물어보세요")
if user_input:
    if mode_choice == "통계 데이터(CSV)로 고정":
        mode = "csv"
    elif mode_choice == "문서 검색(RAG)으로 고정":
        mode = "rag"
    else:
        mode = classify_query(user_input)

    st.session_state.history.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        st.caption(f"모드: {'📊 통계 데이터' if mode == 'csv' else '📚 문서 검색'}")
        if mode == "csv":
            with st.spinner("데이터 조회 중..."):
                steps, answer, error = run_csv_turn(user_input)
            render_csv_steps(steps)
            if error:
                st.error(f"처리 중 문제가 발생했습니다: {error}")
            else:
                st.markdown(answer)
            st.session_state.history.append({
                "role": "assistant", "content": answer or "", "mode": mode,
                "steps": steps, "error": error,
            })
        else:
            with st.spinner("관련 문서 검색 중..."):
                rag_history = [
                    {"role": t["role"], "content": t["content"]}
                    for t in st.session_state.history[:-1]
                    if t["role"] in ("user", "assistant")
                ]
                results, answer, error = run_rag_turn(user_input, rag_history)
            render_rag_sources(results)
            if error:
                st.error(f"처리 중 문제가 발생했습니다: {error}")
            else:
                st.markdown(answer)
            st.session_state.history.append({
                "role": "assistant", "content": answer or "", "mode": mode,
                "sources": results, "error": error,
            })
