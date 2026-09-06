import base64
import csv
import re
from pathlib import Path

import requests

IMAGE_DIR = Path("images/vehicle_number")
OUTPUT_DIR = Path("ocr_results")
OUTPUT_CSV = OUTPUT_DIR / "basic.csv"

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen3-vl:4b-instruct"
PROMPT = (
    "이 이미지는 차량 번호판이다. 번호판에 적힌 문자와 숫자를 그대로 읽어서 출력해줘. "
    "다른 설명은 하지 말고 번호판 텍스트만 출력해."
)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def ground_truth_from_filename(path: Path) -> str:
    stem = path.stem
    # drop trailing "-숫자" style suffixes (duplicate/version markers), e.g. "58호0205-3" -> "58호0205"
    stem = re.sub(r"-\d+$", "", stem)
    return stem


def normalize(text: str) -> str:
    # 공백류 문자 제거 후 비교 (모델이 넣는 띄어쓰기 차이를 무시하기 위한 후처리)
    return re.sub(r"\s+", "", text)


def edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[-1]


def run_ocr(image_path: Path) -> str:
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "prompt": PROMPT,
            "images": [image_b64],
            "stream": False,
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json().get("response", "").strip()


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    image_paths = sorted(
        p for p in IMAGE_DIR.iterdir() if p.suffix.lower() in IMAGE_EXTS
    )

    rows = []
    for i, image_path in enumerate(image_paths, 1):
        gt = ground_truth_from_filename(image_path)
        print(f"[{i}/{len(image_paths)}] {image_path.name} 처리 중...")
        try:
            ocr_text = run_ocr(image_path)
        except Exception as e:
            ocr_text = f"ERROR: {e}"

        gt_norm = normalize(gt)
        ocr_norm = normalize(ocr_text)
        match = (gt_norm == ocr_norm)
        cer = edit_distance(gt_norm, ocr_norm) / len(gt_norm) if gt_norm else 0.0

        rows.append(
            {
                "filename": image_path.name,
                "ground_truth": gt,
                "ocr_result": ocr_text,
                "match": match,
                "cer": round(cer, 4),
            }
        )
        print(f"  정답: {gt} | OCR: {ocr_text} | 일치: {match} | CER: {cer:.4f}")

    total = len(rows)
    em_score = sum(1 for r in rows if r["match"]) / total if total else 0.0
    total_edits = sum(
        edit_distance(normalize(r["ground_truth"]), normalize(r["ocr_result"]))
        for r in rows
    )
    total_gt_chars = sum(len(normalize(r["ground_truth"])) for r in rows)
    cer_score = total_edits / total_gt_chars if total_gt_chars else 0.0

    fieldnames = ["filename", "ground_truth", "ocr_result", "match", "cer"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["EM", f"{em_score:.4f}"])
        writer.writerow(["CER", f"{cer_score:.4f}"])
        writer.writerow([])
        dict_writer = csv.DictWriter(f, fieldnames=fieldnames)
        dict_writer.writeheader()
        dict_writer.writerows(rows)

    print(f"\n완료: {total}건 중 {sum(1 for r in rows if r['match'])}건 일치")
    print(f"EM: {em_score:.4f} | CER: {cer_score:.4f}")
    print(f"결과 저장: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
