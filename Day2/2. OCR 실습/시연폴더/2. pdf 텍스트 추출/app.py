"""
PDF를 업로드하면 모든 페이지를 이미지로 변환해 Ollama의 비전 모델로 OCR을 수행하고
(마크다운 문법으로 구조를 유지), 추출된 내용을 바탕으로 문서에 대해 대화할 수 있는
Streamlit 챗봇.

실행: streamlit run app.py
사전 요구사항: Ollama가 로컬에서 실행 중이어야 함 (http://localhost:11434)
"""

import base64

import fitz  # PyMuPDF
import requests
import streamlit as st

OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OCR_MODEL = "qwen3-vl:4b-instruct"
DEFAULT_CHAT_MODEL = "qwen3-vl:4b-instruct"

OCR_PROMPT = (
    "이 이미지는 문서의 한 페이지입니다. "
    "이미지에 보이는 텍스트를 하나도 빠짐없이 원문 그대로 추출하되, "
    "원본의 구조를 마크다운 문법으로 표현해줘. "
    "제목/소제목은 #, ##, ### 같은 헤딩으로, 표는 마크다운 표(|---|) 형식으로, "
    "목록은 -, 1. 같은 목록 문법으로 나타내고, 강조된 텍스트는 **굵게** 표시해줘. "
    "텍스트를 요약하거나 재구성하지 말고, 내용은 그대로 유지한 채 구조만 마크다운으로 옮겨줘."
)


# ---------- Ollama 연동 ----------

def get_installed_models() -> list[str]:
    try:
        res = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        res.raise_for_status()
        return [m["name"] for m in res.json().get("models", [])]
    except requests.RequestException:
        return []


def render_page_to_png_bytes(doc: fitz.Document, page_index: int, zoom: float = 2.0) -> bytes:
    page = doc.load_page(page_index)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    return pix.tobytes("png")


def ocr_page_with_ollama(image_bytes: bytes, model: str) -> str:
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "model": model,
        "prompt": OCR_PROMPT,
        "images": [image_b64],
        "stream": False,
    }
    res = requests.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload, timeout=300)
    res.raise_for_status()
    return res.json()["response"]


def extract_pdf_text(pdf_bytes: bytes, ocr_model: str, progress_callback=None) -> list[str]:
    """모든 페이지를 이미지로 렌더링해 Ollama 비전 모델로 OCR, 마크다운으로 반환."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_texts = []
    for i in range(len(doc)):
        image_bytes = render_page_to_png_bytes(doc, i)
        ocr_text = ocr_page_with_ollama(image_bytes, ocr_model)
        page_texts.append(ocr_text)
        if progress_callback:
            progress_callback(i + 1, len(doc))
    doc.close()
    return page_texts


def chat_with_ollama(messages: list[dict], model: str) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    res = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=300)
    res.raise_for_status()
    return res.json()["message"]["content"]


# ---------- Streamlit UI ----------

st.set_page_config(page_title="PDF OCR 챗봇", page_icon="📄", layout="wide")
st.title("📄 PDF OCR 챗봇")
st.caption("PDF를 업로드하면 텍스트를 추출하고, 문서 내용에 대해 대화할 수 있습니다.")

if "page_texts" not in st.session_state:
    st.session_state.page_texts = []
if "file_name" not in st.session_state:
    st.session_state.file_name = None
if "messages" not in st.session_state:
    st.session_state.messages = []

installed_models = get_installed_models()


def default_index(options: list[str], preferred: str) -> int:
    return options.index(preferred) if preferred in options else 0


with st.sidebar:
    st.header("설정")
    if not installed_models:
        st.error("Ollama에 연결할 수 없습니다. `ollama serve`가 실행 중인지 확인하세요.")
    ocr_options = installed_models or [DEFAULT_OCR_MODEL]
    chat_options = installed_models or [DEFAULT_CHAT_MODEL]
    ocr_model = st.selectbox(
        "OCR(비전) 모델",
        options=ocr_options,
        index=default_index(ocr_options, DEFAULT_OCR_MODEL),
    )
    chat_model = st.selectbox(
        "채팅 모델",
        options=chat_options,
        index=default_index(chat_options, DEFAULT_CHAT_MODEL),
    )

    st.divider()
    uploaded_file = st.file_uploader("PDF 파일 업로드", type=["pdf"])

    if uploaded_file is not None:
        is_new_file = uploaded_file.name != st.session_state.file_name
        if is_new_file:
            st.session_state.page_texts = []
            st.session_state.messages = []
            st.session_state.file_name = uploaded_file.name

        if st.button("텍스트 추출 실행", type="primary"):
            pdf_bytes = uploaded_file.getvalue()
            progress_bar = st.progress(0.0, text="추출 준비 중...")

            def on_progress(done, total):
                progress_bar.progress(done / total, text=f"{done}/{total} 페이지 처리 중...")

            st.session_state.page_texts = extract_pdf_text(pdf_bytes, ocr_model, on_progress)
            progress_bar.empty()
            st.success(f"{len(st.session_state.page_texts)}페이지 추출 완료")

# ---------- 본문: 추출 결과 + 채팅 ----------

col_doc, col_chat = st.columns([1, 1])

with col_doc:
    st.subheader("추출된 문서")
    if not st.session_state.page_texts:
        st.info("왼쪽에서 PDF를 업로드하고 '텍스트 추출 실행'을 눌러주세요.")
    else:
        for idx, text in enumerate(st.session_state.page_texts, start=1):
            with st.expander(f"{idx} 페이지", expanded=(idx == 1)):
                st.markdown(text)

        full_text = "\n\n".join(
            f"## {i}페이지\n{t}" for i, t in enumerate(st.session_state.page_texts, start=1)
        )
        st.download_button(
            "전체 텍스트 다운로드 (result.txt)",
            data=full_text,
            file_name="result.txt",
            mime="text/plain",
        )

with col_chat:
    st.subheader("문서와 대화하기")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input(
        "문서 내용에 대해 질문해보세요",
        disabled=not st.session_state.page_texts,
    )

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        document_context = "\n\n".join(
            f"[{i}페이지]\n{t}" for i, t in enumerate(st.session_state.page_texts, start=1)
        )
        system_message = {
            "role": "system",
            "content": (
                "너는 아래 문서 내용을 바탕으로 사용자의 질문에 답하는 어시스턴트야. "
                "문서에 없는 내용은 추측하지 말고 모른다고 답해.\n\n"
                f"--- 문서 내용 시작 ---\n{document_context}\n--- 문서 내용 끝 ---"
            ),
        }

        with st.chat_message("assistant"):
            with st.spinner("답변 생성 중..."):
                reply = chat_with_ollama(
                    [system_message] + st.session_state.messages, chat_model
                )
                st.markdown(reply)

        st.session_state.messages.append({"role": "assistant", "content": reply})
