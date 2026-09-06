"""
표 구조(행 이름, 1~12월 열)를 하드코딩해두고, Ollama 비전 모델에게는
월별 숫자값만 JSON으로 추출하게 한 뒤, 소계/합계는 코드로 직접 계산해서
엑셀로 저장하는 테스트 스크립트.

기존 방식(모델이 마크다운 표 전체를 다시 그리는 방식)과 달리
- 표 구조(행/열 이름)를 모델이 틀릴 가능성을 제거
- 소계/합계처럼 계산으로 나오는 값은 OCR하지 않고 코드로 계산 -> 오인식 리스크 제거
- 모델은 "숫자만" 뽑으면 되므로 정확도가 더 높아질 것으로 기대

실행: python extract_table_fixed.py
사전 요구사항: Ollama가 로컬에서 실행 중이어야 함 (http://localhost:11434)
"""

import base64
import json
import re

import pandas as pd
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen3-vl:4b-instruct"

IMAGE_PATH = r"images\2024년_월별_시멘트_수급.png"
OUTPUT_XLSX = "table_result.xlsx"

# 표 구조: 행 이름(구분)과, 소계/합계를 계산하지 않을 행(재고처럼 flow가 아닌 stock 값)
ROW_LABELS = ["생산", "수입", "출하", "국내출하", "수출", "재고"]
SKIP_TOTAL_ROWS = {"재고"}
MONTHS = list(range(1, 13))


def build_prompt(row_labels: list[str]) -> str:
    labels_str = ", ".join(f'"{label}"' for label in row_labels)
    return (
        "이 이미지는 월별 수급 표입니다. 표에는 1월부터 12월까지의 숫자 값이 있습니다. "
        f"다음 행에 대해서만 1월부터 12월까지의 숫자를 순서대로 추출해줘: {labels_str}. "
        "소계나 합계 열은 무시하고 1~12월 값만 추출해. "
        "쉼표(,)나 천 단위 구분기호는 빼고 정수로만 출력해. "
        "다른 설명 없이 아래 JSON 형식으로만 출력해:\n"
        "{\n"
        + ",\n".join(f'  "{label}": [1월값, 2월값, ..., 12월값]' for label in row_labels)
        + "\n}"
    )


def ask_ollama_for_values(image_bytes: bytes, prompt: str) -> str:
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
    }
    res = requests.post(OLLAMA_URL, json=payload, timeout=300)
    res.raise_for_status()
    return res.json()["response"]


def parse_json_response(raw_text: str) -> dict:
    """모델 응답에서 JSON 블록만 뽑아 dict로 변환한다."""
    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if not match:
        raise ValueError(f"응답에서 JSON을 찾지 못했습니다:\n{raw_text}")
    json_text = match.group(0)
    return json.loads(json_text)


def clean_number(value) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^\d-]", "", str(value))
    return int(digits) if digits else 0


def build_dataframe(row_values: dict, row_labels: list[str]) -> pd.DataFrame:
    records = []
    for label in row_labels:
        months = [clean_number(v) for v in row_values.get(label, [None] * 12)]
        if len(months) != 12:
            raise ValueError(f"'{label}' 행의 값 개수가 12개가 아닙니다: {months}")

        row = {"구분": label}
        for month, value in zip(MONTHS, months):
            row[f"{month}월"] = value

        if label not in SKIP_TOTAL_ROWS:
            row["소계(1~6월)"] = sum(months[0:6])
            row["합계(1~12월)"] = sum(months)
        else:
            row["소계(1~6월)"] = None
            row["합계(1~12월)"] = None

        records.append(row)

    columns = ["구분"] + [f"{m}월" for m in MONTHS] + ["소계(1~6월)", "합계(1~12월)"]
    return pd.DataFrame(records, columns=columns)


def main():
    with open(IMAGE_PATH, "rb") as f:
        image_bytes = f.read()

    prompt = build_prompt(ROW_LABELS)
    raw_response = ask_ollama_for_values(image_bytes, prompt)
    print("=== 모델 원본 응답 ===")
    print(raw_response)
    print()

    row_values = parse_json_response(raw_response)
    df = build_dataframe(row_values, ROW_LABELS)

    print("=== 최종 표 ===")
    print(df.to_string(index=False))

    df.to_excel(OUTPUT_XLSX, index=False)
    print(f"\n완료: {OUTPUT_XLSX} 에 저장되었습니다.")


if __name__ == "__main__":
    main()
