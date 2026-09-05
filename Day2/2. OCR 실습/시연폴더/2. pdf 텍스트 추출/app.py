"""
PDF를 업로드하면 모든 페이지를 이미지로 변환해 Ollama의 비전 모델로 OCR을 수행하고
(마크다운 문법으로 구조를 유지), 추출된 내용을 바탕으로 문서에 대해 대화할 수 있는
Streamlit 챗봇.

실행: streamlit run app.py
사전 요구사항: Ollama가 로컬에서 실행 중이어야 함 (http://localhost:11434)
"""

import base64
import re

import fitz  # PyMuPDF
import requests
import streamlit as st

CODE_FENCE_PATTERN = re.compile(r"^```(?:markdown|md)?\s*\n(.*)\n```\s*$", re.DOTALL)


def strip_code_fence(text: str) -> str:
    """모델이 응답을 ```markdown ... ``` 코드블록으로 감싸는 경우 벗겨낸다."""
    match = CODE_FENCE_PATTERN.match(text.strip())
    return match.group(1) if match else text

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
    return strip_code_fence(res.json()["response"])


def get_pdf_page_count(pdf_bytes: bytes) -> int:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    count = len(doc)
    doc.close()
    return count


def extract_single_page(pdf_bytes: bytes, page_number: int, ocr_model: str) -> str:
    """지정한 페이지(1부터 시작) 하나만 이미지로 렌더링해 Ollama 비전 모델로 OCR."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    image_bytes = render_page_to_png_bytes(doc, page_number - 1)
    doc.close()
    return ocr_page_with_ollama(image_bytes, ocr_model)


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
    st.session_state.page_texts = {}  # {페이지번호: 텍스트}
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
            st.session_state.page_texts = {}
            st.session_state.messages = []
            st.session_state.file_name = uploaded_file.name

        pdf_bytes = uploaded_file.getvalue()
        page_count = get_pdf_page_count(pdf_bytes)
        page_number = st.number_input(
            "OCR 수행할 페이지 번호", min_value=1, max_value=page_count, value=1, step=1
        )
        st.caption(f"전체 {page_count}페이지")

        if st.button("해당 페이지 OCR 실행", type="primary"):
            page_number = int(page_number)
            with st.spinner(f"{page_number}페이지 OCR 처리 중..."):
                st.session_state.page_texts[page_number] = extract_single_page(
                    pdf_bytes, page_number, ocr_model
                )
            st.success(f"{page_number}페이지 추출 완료")

# ---------- 본문: 추출 결과 + 채팅 ----------

col_doc, col_chat = st.columns([1, 1])

with col_doc:
    st.subheader("추출된 문서")
    if not st.session_state.page_texts:
        st.info("왼쪽에서 PDF를 업로드하고 페이지 번호를 지정한 뒤 'OCR 실행'을 눌러주세요.")
    else:
        sorted_pages = sorted(st.session_state.page_texts.items())
        for page_num, text in sorted_pages:
            with st.expander(f"{page_num} 페이지", expanded=True):
                st.markdown(text)

        full_text = "\n\n".join(
            f"## {page_num}페이지\n{text}" for page_num, text in sorted_pages
        )
        st.download_button(
            "추출된 텍스트 다운로드 (result.txt)",
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
            f"[{page_num}페이지]\n{text}"
            for page_num, text in sorted(st.session_state.page_texts.items())
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
