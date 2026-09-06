import os
import requests
import pandas as pd

API_KEY = None
with open(os.path.join(os.path.dirname(__file__), ".env"), encoding="utf-8") as f:
    for line in f:
        if line.startswith("API_KEY="):
            API_KEY = line.strip().split("=", 1)[1]

COMPANIES = {
    "쌍용씨앤이": "00138224",
    "한일시멘트": "01319808",
    "아세아시멘트": "00990165",
    "성신양회": "00132804",
}

BSNS_YEAR = "2026"
REPRT_CODE = "11012"  # 반기보고서
FS_DIV = "CFS"  # 연결재무제표 (없으면 OFS로 재시도)

REVENUE_NAMES = ["매출액", "매출", "수익(매출액)", "수익"]
OP_INCOME_NAMES = ["영업이익", "영업이익(손실)"]
NET_INCOME_NAMES = ["당기순이익(손실)", "당기순이익", "반기순이익(손실)", "반기순이익"]


def find_item(items_by_sj, names):
    for sj in ("IS", "CIS"):
        for item in items_by_sj.get(sj, []):
            if item["account_nm"] in names:
                return item
    return None


def fetch_financials(corp_code, fs_div):
    url = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
    params = {
        "crtfc_key": API_KEY,
        "corp_code": corp_code,
        "bsns_year": BSNS_YEAR,
        "reprt_code": REPRT_CODE,
        "fs_div": fs_div,
    }
    res = requests.get(url, params=params, timeout=10).json()
    return res


def to_won_100m(amount_str):
    try:
        return round(int(amount_str) / 100_000_000, 1)  # 억원 단위
    except (TypeError, ValueError):
        return None


rows = []
for name, corp_code in COMPANIES.items():
    data = fetch_financials(corp_code, FS_DIV)
    if data.get("status") != "000":
        # CFS 실패 시 OFS(개별)로 재시도
        data = fetch_financials(corp_code, "OFS")

    if data.get("status") != "000":
        rows.append({
            "회사명": name,
            "비고": f"조회 실패: {data.get('message')}",
        })
        continue

    items_by_sj = {"IS": [], "CIS": []}
    for item in data["list"]:
        if item["sj_div"] in items_by_sj:
            items_by_sj[item["sj_div"]].append(item)

    revenue = find_item(items_by_sj, REVENUE_NAMES)
    op_income = find_item(items_by_sj, OP_INCOME_NAMES)
    net_income = find_item(items_by_sj, NET_INCOME_NAMES)

    revenue_amt = to_won_100m(revenue["thstrm_amount"]) if revenue else None
    op_income_amt = to_won_100m(op_income["thstrm_amount"]) if op_income else None
    net_income_amt = to_won_100m(net_income["thstrm_amount"]) if net_income else None

    # frmtrm_q_amount = 전년동기(2025년 반기) 금액
    revenue_prev = to_won_100m(revenue["frmtrm_q_amount"]) if revenue else None
    op_income_prev = to_won_100m(op_income["frmtrm_q_amount"]) if op_income else None
    net_income_prev = to_won_100m(net_income["frmtrm_q_amount"]) if net_income else None

    def yoy(cur, prev):
        if cur is None or prev is None or prev == 0:
            return None
        return round((cur - prev) / abs(prev) * 100, 1)

    op_margin = None
    if revenue_amt and op_income_amt is not None and revenue_amt != 0:
        op_margin = round(op_income_amt / revenue_amt * 100, 1)

    op_margin_prev = None
    if revenue_prev and op_income_prev is not None and revenue_prev != 0:
        op_margin_prev = round(op_income_prev / revenue_prev * 100, 1)

    rows.append({
        "회사명": name,
        "매출액(억원)_26H1": revenue_amt,
        "매출액(억원)_25H1": revenue_prev,
        "매출액 YoY(%)": yoy(revenue_amt, revenue_prev),
        "영업이익(억원)_26H1": op_income_amt,
        "영업이익(억원)_25H1": op_income_prev,
        "영업이익 YoY(%)": yoy(op_income_amt, op_income_prev),
        "당기순이익(억원)_26H1": net_income_amt,
        "당기순이익(억원)_25H1": net_income_prev,
        "당기순이익 YoY(%)": yoy(net_income_amt, net_income_prev),
        "영업이익률(%)_26H1": op_margin,
        "영업이익률(%)_25H1": op_margin_prev,
        "비고": "",
    })

df = pd.DataFrame(rows)
print(df.to_string(index=False))
df.to_csv(os.path.join(os.path.dirname(__file__), "dart_financials_2026h1_vs_2025h1.csv"), index=False, encoding="utf-8-sig")
