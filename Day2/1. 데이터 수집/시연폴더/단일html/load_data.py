"""
관세청_품목별 국가별 수출입실적(GW) API를 호출해서
2025년 국가별(AU/ID/US) 석탄(HS 2701) 수입 통계를 계산하고,
dashboard.html이 그대로 읽어들일 dashboard_data.js 를 생성하는 단일 스크립트.

흐름:
    1) API 호출 (국가별로 월별 원자료 조회)
    2) 월별/국가별 집계 (수입중량, 수입금액, 단가)
    3) 국가별 연간 요약 통계 계산 (총중량, 평균단가, 수입의존도)
    4) 결과를 dashboard_data.js 로 저장
       -> <script src="dashboard_data.js">로 불러오기 때문에
          dashboard.html은 서버 없이 더블클릭으로 열어도 정상 동작합니다.

사용법:
    1. .env 파일에 API_KEY=발급받은_인증키(Decoding) 입력
    2. pip install requests python-dotenv
    3. python load_data.py
"""

import json
import os
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone

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

OUTPUT_JS = "dashboard_data.js"


# ============================================================
# 1) API 호출
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


# ============================================================
# 2) 월별/국가별 집계
# ============================================================
def aggregate_monthly(rows_by_country):
    """{cnty: [row, ...]} -> {(cnty, year_month): [impDlr_sum, impWgt_sum]}"""
    monthly_totals = defaultdict(lambda: [0, 0])

    for cnty, rows in rows_by_country.items():
        for row in rows:
            stat_cd = row.get("statCd")
            if stat_cd != cnty:
                continue  # '총계' 등 합계 행 제외

            year_month = row["year"]
            monthly_totals[(cnty, year_month)][0] += int(row["impDlr"])
            monthly_totals[(cnty, year_month)][1] += int(row["impWgt"])

    return monthly_totals


# ============================================================
# 3) 국가별 연간 요약 통계
# ============================================================
def build_summary(monthly_totals):
    by_country = defaultdict(list)
    for (cnty, year_month), (dlr, wgt) in monthly_totals.items():
        by_country[cnty].append((year_month, dlr, wgt))
    for cnty in by_country:
        by_country[cnty].sort()

    months = [m for m, _, _ in next(iter(by_country.values()))]

    monthly_out = {}
    summary_out = {}
    grand_total_wgt = 0

    for cnty in COUNTRY_NAMES:
        cnty_rows = by_country.get(cnty, [])
        imp_dlr = [d for _, d, _ in cnty_rows]
        imp_wgt = [w for _, _, w in cnty_rows]
        unit_price = [(d / w) if w else 0 for d, w in zip(imp_dlr, imp_wgt)]

        monthly_out[cnty] = {
            "impDlr": imp_dlr,
            "impWgt": imp_wgt,
            "unitPrice": unit_price,
        }

        total_wgt = sum(imp_wgt)
        total_dlr = sum(imp_dlr)
        summary_out[cnty] = {
            "totalImpWgt": total_wgt,
            "totalImpDlr": total_dlr,
            "avgUnitPrice": (total_dlr / total_wgt) if total_wgt else 0,
        }
        grand_total_wgt += total_wgt

    for cnty in COUNTRY_NAMES:
        summary_out[cnty]["importSharePercent"] = (
            summary_out[cnty]["totalImpWgt"] / grand_total_wgt * 100
            if grand_total_wgt else 0
        )

    return months, monthly_out, summary_out, grand_total_wgt


# ============================================================
# 4) dashboard_data.js 저장
# ============================================================
def save_dashboard_js(months, monthly_out, summary_out, grand_total_wgt):
    result = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hsCode": HS_SGN,
        "period": {"start": months[0], "end": months[-1]},
        "countries": COUNTRY_NAMES,
        "months": months,
        "monthly": monthly_out,
        "summary": summary_out,
        "grandTotalImpWgt": grand_total_wgt,
    }

    with open(OUTPUT_JS, "w", encoding="utf-8") as f:
        f.write("// 이 파일은 load_data.py 가 자동 생성합니다. 직접 수정하지 마세요.\n")
        f.write("const DASHBOARD_DATA = ")
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write(";\n")


def main():
    rows_by_country = {}
    for cnty_cd in COUNTRY_NAMES:
        try:
            rows_by_country[cnty_cd] = fetch_trade_stats(STRT_YYMM, END_YYMM, cnty_cd, HS_SGN)
        except Exception as e:
            print(f"[{cnty_cd}] 조회 실패: {e}", file=sys.stderr)
            rows_by_country[cnty_cd] = []

    monthly_totals = aggregate_monthly(rows_by_country)
    months, monthly_out, summary_out, grand_total_wgt = build_summary(monthly_totals)
    save_dashboard_js(months, monthly_out, summary_out, grand_total_wgt)

    print(f"저장 완료: {OUTPUT_JS}")
    for cnty, name in COUNTRY_NAMES.items():
        s = summary_out[cnty]
        print(
            f"  {name}({cnty}): 총중량 {s['totalImpWgt']:,}kg, "
            f"평균단가 {s['avgUnitPrice']:.4f}원/kg, "
            f"의존도 {s['importSharePercent']:.2f}%"
        )


if __name__ == "__main__":
    main()
