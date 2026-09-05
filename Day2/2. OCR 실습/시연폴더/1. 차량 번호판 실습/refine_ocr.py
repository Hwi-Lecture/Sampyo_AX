import base64
import csv
from pathlib import Path

import requests

from upscale_ocr import IMAGE_DIR, MODEL, OLLAMA_URL, cer_of, edit_distance, normalize, upscale_bytes

UPSCALE_RESULT_CSV = Path("ocr_results") / "upscale_result.csv"
OUTPUT_CSV = Path("ocr_results") / "refined_result.csv"

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


def build_prompt(ocr_text: str) -> str:
    return REFINE_PROMPT_TEMPLATE.format(
        regions=REGIONS,
        allowed_hangul=", ".join(ALLOWED_HANGUL),
        diplomatic_hangul=", ".join(DIPLOMATIC_HANGUL),
        ocr_text=ocr_text,
    )


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


def load_upscale_results() -> list[dict]:
    with open(UPSCALE_RESULT_CSV, encoding="utf-8-sig") as f:
        lines = f.readlines()
    header_idx = next(i for i, line in enumerate(lines) if line.startswith("filename,"))
    reader = csv.DictReader(lines[header_idx:])
    return list(reader)


def main():
    before_rows = load_upscale_results()

    rows = []
    for i, before in enumerate(before_rows, 1):
        filename = before["filename"]
        gt = before["ground_truth"]
        ocr_before = before["ocr_after_upscale"]
        image_path = IMAGE_DIR / filename

        print(f"[{i}/{len(before_rows)}] {filename} 2차 검토 중...")
        try:
            image_bytes = upscale_bytes(image_path)
            prompt = build_prompt(ocr_before)
            ocr_after = run_ocr_with_prompt(image_bytes, prompt)
        except Exception as e:
            ocr_after = f"ERROR: {e}"

        match_before = normalize(gt) == normalize(ocr_before)
        match_after = normalize(gt) == normalize(ocr_after)
        cer_before = cer_of(gt, ocr_before)
        cer_after = cer_of(gt, ocr_after)

        rows.append(
            {
                "filename": filename,
                "ground_truth": gt,
                "ocr_before": ocr_before,
                "ocr_after_refine": ocr_after,
                "match_before": match_before,
                "match_after": match_after,
                "cer_before": round(cer_before, 4),
                "cer_after": round(cer_after, 4),
            }
        )
        print(
            f"  정답: {gt} | 이전: {ocr_before} (CER {cer_before:.4f}) | "
            f"검토 후: {ocr_after} (CER {cer_after:.4f})"
        )

    total = len(rows)
    em_before = sum(1 for r in rows if r["match_before"]) / total if total else 0.0
    em_after = sum(1 for r in rows if r["match_after"]) / total if total else 0.0

    total_gt_chars = sum(len(normalize(r["ground_truth"])) for r in rows)
    total_edits_before = sum(
        edit_distance(normalize(r["ground_truth"]), normalize(r["ocr_before"])) for r in rows
    )
    total_edits_after = sum(
        edit_distance(normalize(r["ground_truth"]), normalize(r["ocr_after_refine"])) for r in rows
    )
    cer_before_score = total_edits_before / total_gt_chars if total_gt_chars else 0.0
    cer_after_score = total_edits_after / total_gt_chars if total_gt_chars else 0.0

    fieldnames = [
        "filename",
        "ground_truth",
        "ocr_before",
        "ocr_after_refine",
        "match_before",
        "match_after",
        "cer_before",
        "cer_after",
    ]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["EM_before", f"{em_before:.4f}"])
        writer.writerow(["EM_after_refine", f"{em_after:.4f}"])
        writer.writerow(["CER_before", f"{cer_before_score:.4f}"])
        writer.writerow(["CER_after_refine", f"{cer_after_score:.4f}"])
        writer.writerow([])
        dict_writer = csv.DictWriter(f, fieldnames=fieldnames)
        dict_writer.writeheader()
        dict_writer.writerows(rows)

    print(f"\n=== 결과 비교 (2차 검토 필터링) ===")
    print(f"EM  : {em_before:.4f} -> {em_after:.4f}")
    print(f"CER : {cer_before_score:.4f} -> {cer_after_score:.4f}")
    print(f"결과 저장: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
