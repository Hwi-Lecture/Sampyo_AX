"""
PDF 3페이지를 이미지로 변환한 뒤, Ollama의 qwen3-vl:4b-instruct 모델에게
해당 이미지에 있는 텍스트를 그대로(변형 없이) 추출해 달라고 요청하고
결과를 result.txt로 저장하는 스크립트.
"""

import base64
import requests
import fitz  # PyMuPDF

PDF_PATH = r"images\산업안전보건법 주요 개정내용(제조업).pdf"
PAGE_NUMBER = 3  # 사람이 세는 페이지 번호 (1부터 시작)
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen3-vl:4b-instruct"
OUTPUT_PATH = "result.txt"

PROMPT = (
    "이 이미지는 문서의 한 페이지입니다. "
    "이미지에 보이는 텍스트를 하나도 빠짐없이, 원문 그대로(요약하거나 재구성하지 말고) "
    "추출해서 출력해줘."
)


def render_page_to_png_bytes(pdf_path: str, page_number: int, zoom: float = 2.0) -> bytes:
    doc = fitz.open(pdf_path)
    page = doc.load_page(page_number - 1)
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix)
    png_bytes = pix.tobytes("png")
    doc.close()
    return png_bytes


def ask_ollama(image_bytes: bytes) -> str:
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "model": MODEL_NAME,
        "prompt": PROMPT,
        "images": [image_b64],
        "stream": False,
    }
    response = requests.post(OLLAMA_URL, json=payload, timeout=300)
    response.raise_for_status()
    return response.json()["response"]


def main():
    image_bytes = render_page_to_png_bytes(PDF_PATH, PAGE_NUMBER)
    result_text = ask_ollama(image_bytes)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(result_text)

    print(f"완료: {OUTPUT_PATH} 에 저장되었습니다.")


if __name__ == "__main__":
    main()
