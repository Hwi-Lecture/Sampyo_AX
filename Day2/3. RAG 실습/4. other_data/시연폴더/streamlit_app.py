"""
df_all.csv 챗봇의 Streamlit 웹 UI.

csv_chatbot.py의 도구 정의/실행 로직을 그대로 재사용하고, 여기서는
대화 UI와 "실행된 pandas 쿼리 + 결과"를 답변과 함께 보여주는 부분만 담당한다.

사용법:
    pip install streamlit
    streamlit run streamlit_app.py
"""

import streamlit as st

from csv_chatbot import (
    MODEL,
    SYSTEM_PROMPT,
    TOOL_IMPL,
    TOOLS,
    build_pandas_query,
    chat,
)

st.set_page_config(page_title="df_all.csv 챗봇", page_icon="🪨")
st.title("🪨 석탄 수출입 통계 챗봇")
st.caption(f"모델: {MODEL} (로컬 Ollama)")

if "messages" not in st.session_state:
    # 모델에게 실제로 보내는 대화 기록 (system 포함)
    st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
if "history" not in st.session_state:
    # 화면에 렌더링할 기록 (user / assistant + 중간 도구 실행 단계)
    st.session_state.history = []


def run_tool_calling_turn(user_input: str):
    """사용자 입력 하나를 처리하고 (steps, answer)를 반환. 실패 시 상태를 롤백한다."""
    snapshot_len = len(st.session_state.messages)
    st.session_state.messages.append({"role": "user", "content": user_input})
    steps = []

    try:
        response = chat(model=MODEL, messages=st.session_state.messages, tools=TOOLS)
        msg = response["message"]
        st.session_state.messages.append(msg)

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
                st.session_state.messages.append({"role": "tool", "content": str(result)})

            response = chat(model=MODEL, messages=st.session_state.messages, tools=TOOLS)
            msg = response["message"]
            st.session_state.messages.append(msg)

        return steps, msg.get("content", ""), None

    except Exception as e:
        del st.session_state.messages[snapshot_len:]
        return steps, None, str(e)


def render_steps(steps):
    if not steps:
        return
    with st.expander(f"실행 과정 보기 ({len(steps)}단계)", expanded=False):
        for i, step in enumerate(steps, start=1):
            args_str = ", ".join(f"{k}={v!r}" for k, v in step["args"].items())
            st.markdown(f"**{i}. `{step['name']}({args_str})`**")
            if step["query"]:
                st.code(step["query"], language="python")
            st.text(f"결과: {step['result']}")


# 이전 대화 렌더링
for turn in st.session_state.history:
    if turn["role"] == "user":
        with st.chat_message("user"):
            st.markdown(turn["content"])
    else:
        with st.chat_message("assistant"):
            render_steps(turn.get("steps"))
            if turn.get("error"):
                st.error(f"모델 호출 중 문제가 발생했습니다: {turn['error']}")
            else:
                st.markdown(turn["content"])

# 새 입력
user_input = st.chat_input("석탄 수출입 데이터에 대해 물어보세요")
if user_input:
    st.session_state.history.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("데이터 조회 중..."):
            steps, answer, error = run_tool_calling_turn(user_input)
        render_steps(steps)
        if error:
            st.error(f"모델 호출 중 문제가 발생했습니다: {error}")
            st.session_state.history.append(
                {"role": "assistant", "content": "", "steps": steps, "error": error}
            )
        else:
            st.markdown(answer)
            st.session_state.history.append(
                {"role": "assistant", "content": answer, "steps": steps}
            )
