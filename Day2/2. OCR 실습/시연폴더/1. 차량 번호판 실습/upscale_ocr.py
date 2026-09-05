import base64
import csv
import re
from pathlib import Path

import cv2
import numpy as np
import requests

IMAGE_DIR = Path("images/vehicle_number")
BASIC_CSV = Path("ocr_results") / "basic.csv"
OUTPUT_DIR = Path("ocr_results")
OUTPUT_CSV = OUTPUT_DIR / "upscale_result.csv"

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen3-vl:4b-instruct"
PROMPT = (
    "이 이미지는 차량 번호판이다. 번호판에 적힌 문자와 숫자를 그대로 읽어서 출력해줘. "
    "다른 설명은 하지 말고 번호판 텍스트만 출력해."
)

UPSCALE_FACTOR = 3


def normalize(text: str) -> str:
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


def cer_of(gt: str, pred: str) -> float:
    gt_norm, pred_norm = normalize(gt), normalize(pred)
    return edit_distance(gt_norm, pred_norm) / len(gt_norm) if gt_norm else 0.0


def upscale_bytes(image_path: Path) -> bytes:
    # cv2.imread는 한글 등 비ASCII 경로를 못 읽으므로 numpy 버퍼를 거쳐 디코딩
    file_bytes = np.fromfile(str(image_path), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    upscaled = cv2.resize(
        img, (w * UPSCALE_FACTOR, h * UPSCALE_FACTOR), interpolation=cv2.INTER_LANCZOS4
    )
    ok, buf = cv2.imencode(".png", upscaled)
    return buf.tobytes()


def run_ocr(image_bytes: bytes) -> str:
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
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


def load_before_results() -> dict:
    with open(BASIC_CSV, encoding="utf-8-sig") as f:
        lines = f.readlines()
    header_idx = next(i for i, line in enumerate(lines) if line.startswith("filename,"))
    reader = csv.DictReader(lines[header_idx:])
    return {row["filename"]: row for row in reader}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    before_results = load_before_results()

    image_paths = sorted(
        p for p in IMAGE_DIR.iterdir() if p.name in before_results
    )

    rows = []
    for i, image_path in enumerate(image_paths, 1):
        before = before_results[image_path.name]
        gt = before["ground_truth"]
        ocr_before = before["ocr_result"]

        print(f"[{i}/{len(image_paths)}] {image_path.name} 업스케일 OCR 처리 중...")
        try:
            ocr_after = run_ocr(upscale_bytes(image_path))
        except Exception as e:
            ocr_after = f"ERROR: {e}"

        match_before = normalize(gt) == normalize(ocr_before)
        match_after = normalize(gt) == normalize(ocr_after)
        cer_before = cer_of(gt, ocr_before)
        cer_after = cer_of(gt, ocr_after)

        rows.append(
            {
                "filename": image_path.name,
                "ground_truth": gt,
                "ocr_before": ocr_before,
                "ocr_after_upscale": ocr_after,
                "match_before": match_before,
                "match_after": match_after,
                "cer_before": round(cer_before, 4),
                "cer_after": round(cer_after, 4),
            }
        )
        print(
            f"  정답: {gt} | 이전: {ocr_before} (CER {cer_before:.4f}) | "
            f"업스케일 후: {ocr_after} (CER {cer_after:.4f})"
        )

    total = len(rows)
    em_before = sum(1 for r in rows if r["match_before"]) / total if total else 0.0
    em_after = sum(1 for r in rows if r["match_after"]) / total if total else 0.0

    total_gt_chars = sum(len(normalize(r["ground_truth"])) for r in rows)
    total_edits_before = sum(
        edit_distance(normalize(r["ground_truth"]), normalize(r["ocr_before"])) for r in rows
    )
    total_edits_after = sum(
        edit_distance(normalize(r["ground_truth"]), normalize(r["ocr_after_upscale"])) for r in rows
    )
    cer_before_score = total_edits_before / total_gt_chars if total_gt_chars else 0.0
    cer_after_score = total_edits_after / total_gt_chars if total_gt_chars else 0.0

    fieldnames = [
        "filename",
        "ground_truth",
        "ocr_before",
        "ocr_after_upscale",
        "match_before",
        "match_after",
        "cer_before",
        "cer_after",
    ]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["EM_before", f"{em_before:.4f}"])
        writer.writerow(["EM_after_upscale", f"{em_after:.4f}"])
        writer.writerow(["CER_before", f"{cer_before_score:.4f}"])
        writer.writerow(["CER_after_upscale", f"{cer_after_score:.4f}"])
        writer.writerow([])
        dict_writer = csv.DictWriter(f, fieldnames=fieldnames)
        dict_writer.writeheader()
        dict_writer.writerows(rows)

    print(f"\n=== 결과 비교 (업스케일 {UPSCALE_FACTOR}x) ===")
    print(f"EM  : {em_before:.4f} -> {em_after:.4f}")
    print(f"CER : {cer_before_score:.4f} -> {cer_after_score:.4f}")
    print(f"결과 저장: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
