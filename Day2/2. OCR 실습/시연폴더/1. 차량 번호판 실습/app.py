import base64
import json

import streamlit as st
import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen3-vl:4b-instruct"

st.set_page_config(page_title="Qwen3 Chatbot", page_icon="💬")
st.title("💬 Qwen3-VL Chatbot (Ollama)")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        for img in msg.get("images", []):
            st.image(base64.b64decode(img), width=200)
        st.markdown(msg["content"])

uploaded_image = st.file_uploader(
    "이미지 첨부 (선택)", type=["png", "jpg", "jpeg", "webp"]
)
if uploaded_image:
    st.image(uploaded_image, caption="첨부된 이미지", width=200)

prompt = st.chat_input("메시지를 입력하세요")

if prompt:
    user_message = {"role": "user", "content": prompt}
    if uploaded_image:
        image_b64 = base64.b64encode(uploaded_image.getvalue()).decode("utf-8")
        user_message["images"] = [image_b64]

    st.session_state.messages.append(user_message)
    with st.chat_message("user"):
        if uploaded_image:
            st.image(uploaded_image, width=200)
        st.markdown(prompt)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        full_response = ""
        try:
            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": MODEL_NAME,
                    "messages": st.session_state.messages,
                    "stream": True,
                },
                stream=True,
                timeout=120,
            )
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                content = chunk.get("message", {}).get("content", "")
                full_response += content
                placeholder.markdown(full_response)
                if chunk.get("done"):
                    break
        except requests.exceptions.RequestException as e:
            full_response = f"오류: Ollama 서버에 연결할 수 없습니다. ({e})"
            placeholder.markdown(full_response)

    st.session_state.messages.append({"role": "assistant", "content": full_response})
