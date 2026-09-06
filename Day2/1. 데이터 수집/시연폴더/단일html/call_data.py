"""
관세청_품목별 국가별 수출입실적(GW) API를 호출해서
2025년 국가별(AU/ID/US) 석탄(HS 2701) 수입 원자료를 CSV로 저장하는 스크립트.

load_data.py 의 "1) API 호출" 부분만 떼어내어, 결과를 dashboard_data.js 가 아닌
CSV 파일(raw_trade_data.csv)로 저장한다. 이후 분석/그래프는 data_analyse.py 에서 수행한다.

사용법:
    1. .env 파일에 API_KEY=발급받은_인증키(Decoding) 입력
    2. pip install requests python-dotenv pandas
    3. python call_data.py
"""

import os
import sys
import xml.etree.ElementTree as ET

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("API_KEY")
BASE_URL = "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList"

# ---- 조회 조건 ----
STRT_YYMM = "202501"
END_YYMM = "202512"
HS_SGN = "2701"
COUNTRY_NAMES = {
    "AU": "호주",
    "ID": "인도네시아",
    "US": "미국",
}

OUTPUT_CSV = "trade_stats_2701_2025.csv"


# ============================================================
# API 호출
# ============================================================
def fetch_trade_stats(strt_yymm: str, end_yymm: str, cnty_cd: str, hs_sgn: str | None = None):
    """국가별 품목별 수출입실적을 조회한다."""
    if not API_KEY:
        raise RuntimeError(".env 파일에 API_KEY가 설정되어 있지 않습니다.")

    params = {
        "serviceKey": API_KEY,
        "strtYymm": strt_yymm,
        "endYymm": end_yymm,
        "cntyCd": cnty_cd,
    }
    if hs_sgn:
        params["hsSgn"] = hs_sgn

    response = requests.get(BASE_URL, params=params, timeout=10)
    response.raise_for_status()

    root = ET.fromstring(response.content)

    result_code = root.findtext(".//resultCode")
    result_msg = root.findtext(".//resultMsg")
    if result_code not in (None, "00", "0"):
        raise RuntimeError(f"API 오류 [{result_code}]: {result_msg}")

    rows = []
    for item in root.findall(".//item"):
        rows.append({child.tag: child.text for child in item})

    return rows


def main():
    all_rows = []
    for cnty_cd in COUNTRY_NAMES:
        try:
            rows = fetch_trade_stats(STRT_YYMM, END_YYMM, cnty_cd, HS_SGN)
            all_rows.extend(rows)
        except Exception as e:
            print(f"[{cnty_cd}] 조회 실패: {e}", file=sys.stderr)

    df = pd.DataFrame(all_rows)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"저장 완료: {OUTPUT_CSV} ({len(df)} rows)")


if __name__ == "__main__":
    main()
