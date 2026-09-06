import base64
import io

import pandas as pd
import requests
import streamlit as st
from PIL import Image

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen3-vl:4b-instruct"
UPSCALE_FACTOR = 3

BASIC_PROMPT = (
    "이 이미지는 차량 번호판이다. 번호판에 적힌 문자와 숫자를 그대로 읽어서 출력해줘. "
    "다른 설명은 하지 말고 번호판 텍스트만 출력해."
)

REGIONS = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
]

ALLOWED_HANGUL = [
    "가", "나", "다", "라", "마",
    "거", "너", "더", "러", "머", "버", "서", "어", "저",
    "고", "노", "도", "로", "모", "보", "소", "오", "조",
    "구", "누", "두", "루", "무", "부", "수", "우", "주",
    "바", "사", "아", "자", "하", "허", "호",
]
DIPLOMATIC_HANGUL = ["외교", "영사", "준영", "준외", "국기", "협정"]

REFINE_PROMPT_TEMPLATE = """다음은 차량 번호판 이미지와 해당 번호판의 텍스트를 추출한 텍스트이다.
아래 조건들을 참고하여 텍스트를 다시 작성할 것.

1. 번호판의 문자는 한글과 숫자로만 구성된다.
2. 번호판의 맨 앞에는 다음과 같은 지역명들이 들어갈 수 있다.
{regions}
   단, 원래 추출된 텍스트에 지역명이 없다면 임의로 지역명을 추가하지 말 것.
3. 일반적인 한국차의 번호판 형식은 다음과 같다. 이 패턴과 일치하도록 다시 작성할 것.
- 87나2135
- 123가4567
- 경기36바5142
4. 번호판에 허용되는 한글 문자는 아래 목록뿐이다.
   - 일반/대여/영업용: {allowed_hangul}
   - 외교용: {diplomatic_hangul}
   위 목록에 없는 한글(예: 뱌, 댜 등)이 추출되었다면, 시각적으로 가장 유사한 허용 한글로 교정할 것.

추출된 텍스트: {ocr_text}

최종적으로 교정된 최종 번호판 텍스트만 출력할 것."""


def build_refine_prompt(ocr_text: str) -> str:
    return REFINE_PROMPT_TEMPLATE.format(
        regions=REGIONS,
        allowed_hangul=", ".join(ALLOWED_HANGUL),
        diplomatic_hangul=", ".join(DIPLOMATIC_HANGUL),
        ocr_text=ocr_text,
    )


def upscale_bytes(image_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = img.size
    upscaled = img.resize((w * UPSCALE_FACTOR, h * UPSCALE_FACTOR), Image.LANCZOS)
    buf = io.BytesIO()
    upscaled.save(buf, format="PNG")
    return buf.getvalue()


def run_ocr_with_prompt(image_bytes: bytes, prompt: str) -> str:
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False,
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json().get("response", "").strip()


def process_image(image_bytes: bytes) -> str:
    upscaled_bytes = upscale_bytes(image_bytes)
    ocr_basic = run_ocr_with_prompt(upscaled_bytes, BASIC_PROMPT)
    refine_prompt = build_refine_prompt(ocr_basic)
    ocr_refined = run_ocr_with_prompt(upscaled_bytes, refine_prompt)
    return ocr_refined


st.set_page_config(page_title="차량 번호판 OCR", layout="centered")
st.title("차량 번호판 OCR")
st.caption("이미지를 업로드하면 업스케일 + LLM 재검토를 거쳐 번호판 텍스트를 추출합니다.")

uploaded_files = st.file_uploader(
    "차량 번호판 이미지 업로드 (여러 장 가능)",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True,
)

if uploaded_files:
    st.write(f"업로드된 이미지: {len(uploaded_files)}개")

if st.button("OCR 실행", disabled=not uploaded_files):
    results = []
    progress = st.progress(0.0)
    status = st.empty()

    for i, file in enumerate(uploaded_files, 1):
        status.text(f"[{i}/{len(uploaded_files)}] {file.name} 처리 중...")
        image_bytes = file.getvalue()
        try:
            ocr_result = process_image(image_bytes)
        except Exception as e:
            ocr_result = f"ERROR: {e}"
        results.append({"filename": file.name, "ocr_result": ocr_result})
        progress.progress(i / len(uploaded_files))

    status.text("완료")
    df = pd.DataFrame(results)
    st.session_state["ocr_df"] = df

if "ocr_df" in st.session_state:
    df = st.session_state["ocr_df"]
    st.subheader("결과")
    st.dataframe(df, use_container_width=True)

    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False, encoding="utf-8-sig")
    st.download_button(
        "결과 CSV 다운로드",
        data=csv_buffer.getvalue().encode("utf-8-sig"),
        file_name="ocr_results.csv",
        mime="text/csv",
    )
