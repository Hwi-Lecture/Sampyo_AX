"""
PDF에 텍스트 레이어가 있는 경우, Ollama/VLM 없이 PyMuPDF의 get_text()만으로
3페이지 텍스트를 그대로 추출해 result.txt로 저장하는 스크립트.
"""

import fitz  # PyMuPDF

PDF_PATH = r"images\산업안전보건법 주요 개정내용(제조업).pdf"
PAGE_NUMBER = 3  # 사람이 세는 페이지 번호 (1부터 시작)
OUTPUT_PATH = "result.txt"


def extract_page_text(pdf_path: str, page_number: int) -> str:
    doc = fitz.open(pdf_path)
    page = doc.load_page(page_number - 1)
    text = page.get_text()
    doc.close()
    return text


def main():
    text = extract_page_text(PDF_PATH, PAGE_NUMBER)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"완료: {OUTPUT_PATH} 에 저장되었습니다.")


if __name__ == "__main__":
    main()
