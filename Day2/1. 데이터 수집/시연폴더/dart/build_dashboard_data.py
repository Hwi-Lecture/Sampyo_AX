"""
DART Open API에서 대시보드에 필요한 모든 수치를 직접 조회해서
dashboard_data.json 하나로 저장한다.

cement_dashboard.html은 이 JSON을 fetch로 그대로 불러와 렌더링하므로,
스크립트가 뽑아낸 값과 화면에 찍히는 값 사이에 수기 전사로 인한 오차가 없다.
"""
import json
import os
import requests

BASE_DIR = os.path.dirname(__file__)

API_KEY = None
with open(os.path.join(BASE_DIR, ".env"), encoding="utf-8") as f:
    for line in f:
        if line.startswith("API_KEY="):
            API_KEY = line.strip().split("=", 1)[1]

COMPANIES = [
    {"key": "ssangyong", "name": "쌍용씨앤이",  "corp_code": "00138224"},
    {"key": "hanil",     "name": "한일시멘트",  "corp_code": "01319808"},
    {"key": "asia",      "name": "아세아시멘트", "corp_code": "00990165"},
    {"key": "sungshin",  "name": "성신양회",    "corp_code": "00132804"},
]

YEARS = list(range(2020, 2026))

REVENUE_NAMES = ["매출액", "매출", "수익(매출액)", "수익"]
OP_INCOME_NAMES = ["영업이익", "영업이익(손실)"]
NET_INCOME_NAMES = ["당기순이익(손실)", "당기순이익", "반기순이익(손실)", "반기순이익"]
LIABILITIES_NAMES = ["부채총계"]
EQUITY_NAMES = ["자본총계"]
CAPEX_AGGREGATE_NAMES = ["유형자산의 취득"]
CAPEX_SUBITEM_NAMES = [
    "토지의 취득", "건물의 취득", "구축물의 취득", "기계장치의 취득",
    "차량운반구의 취득", "기타의유형자산의 취득", "기타유형자산의 취득",
    "건설중인자산의 취득", "리스기계장치의 취득",
]


def fetch_acnt_all(corp_code, year, reprt_code, fs_div):
    url = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
    params = {
        "crtfc_key": API_KEY, "corp_code": corp_code, "bsns_year": str(year),
        "reprt_code": reprt_code, "fs_div": fs_div,
    }
    return requests.get(url, params=params, timeout=15).json()


def fetch_acnt_all_with_fallback(corp_code, year, reprt_code):
    data = fetch_acnt_all(corp_code, year, reprt_code, "CFS")
    if data.get("status") != "000":
        data = fetch_acnt_all(corp_code, year, reprt_code, "OFS")
    return data


def fetch_filings(corp_code, bgn_de, end_de):
    url = "https://opendart.fss.or.kr/api/list.json"
    params = {
        "crtfc_key": API_KEY, "corp_code": corp_code, "bgn_de": bgn_de,
        "end_de": end_de, "pblntf_ty": "B", "page_no": "1", "page_count": "100",
        "last_reprt_at": "N",
    }
    return requests.get(url, params=params, timeout=15).json()


def to_eok(amount_str):
    """원 -> 억원(1e8)"""
    try:
        return round(int(amount_str) / 100_000_000, 1)
    except (TypeError, ValueError):
        return None


def group_by_sj(items, keys):
    grouped = {k: [] for k in keys}
    for item in items:
        if item["sj_div"] in grouped:
            grouped[item["sj_div"]].append(item)
    return grouped


def find_by_names(items, names):
    for item in items:
        if item["account_nm"] in names:
            return item
    return None


def find_across(grouped, sj_order, names):
    for sj in sj_order:
        hit = find_by_names(grouped.get(sj, []), names)
        if hit:
            return hit
    return None


def get_capex_eok(grouped_cf):
    agg = find_by_names(grouped_cf, CAPEX_AGGREGATE_NAMES)
    if agg and agg.get("thstrm_amount"):
        return to_eok(agg["thstrm_amount"])
    total, found = 0.0, False
    for item in grouped_cf:
        if item["account_nm"] in CAPEX_SUBITEM_NAMES and item.get("thstrm_amount"):
            amt = to_eok(item["thstrm_amount"])
            if amt is not None:
                total += amt
                found = True
    return round(abs(total), 1) if found else None


# ---------------------------------------------------------------- H1 실적
half_year = {}
for c in COMPANIES:
    data = fetch_acnt_all_with_fallback(c["corp_code"], 2026, "11012")
    if data.get("status") != "000":
        half_year[c["key"]] = {"error": data.get("message")}
        continue
    grouped = group_by_sj(data["list"], ["IS", "CIS"])
    all_items = grouped["IS"] + grouped["CIS"]

    revenue = find_across(grouped, ("IS", "CIS"), REVENUE_NAMES)
    op_income = find_across(grouped, ("IS", "CIS"), OP_INCOME_NAMES)
    net_income = find_across(grouped, ("IS", "CIS"), NET_INCOME_NAMES)

    def cur_prev(item):
        if not item:
            return None, None
        return to_eok(item["thstrm_amount"]), to_eok(item.get("frmtrm_q_amount"))

    rev_cur, rev_prev = cur_prev(revenue)
    op_cur, op_prev = cur_prev(op_income)
    ni_cur, ni_prev = cur_prev(net_income)

    margin_cur = round(op_cur / rev_cur * 100, 1) if rev_cur else None
    margin_prev = round(op_prev / rev_prev * 100, 1) if rev_prev else None

    half_year[c["key"]] = {
        "revenue": {"h1_2026": rev_cur, "h1_2025": rev_prev},
        "op_income": {"h1_2026": op_cur, "h1_2025": op_prev},
        "net_income": {"h1_2026": ni_cur, "h1_2025": ni_prev},
        "op_margin": {"h1_2026": margin_cur, "h1_2025": margin_prev},
    }

# 쌍용씨앤이 2025H1 순이익: 2026반기보고서의 비교(frmtrm_q) 수치가
# 2025년에 실제 제출된 반기보고서 원본과 다른지 직접 재조회해서 검증하고 기록해둔다.
orig_2025h1 = fetch_acnt_all_with_fallback("00138224", 2025, "11012")
restated_note = None
if orig_2025h1.get("status") == "000":
    grouped = group_by_sj(orig_2025h1["list"], ["IS", "CIS"])
    ni_orig_item = find_across(grouped, ("IS", "CIS"), NET_INCOME_NAMES)
    if ni_orig_item:
        ni_orig = to_eok(ni_orig_item["thstrm_amount"])
        ni_restated = half_year["ssangyong"]["net_income"]["h1_2025"]
        if ni_orig is not None and ni_restated is not None and abs(ni_orig - ni_restated) > 1:
            restated_note = {
                "company": "ssangyong",
                "metric": "net_income",
                "period": "h1_2025",
                "originally_filed": ni_orig,
                "restated_in_2026_report": ni_restated,
                "reason": "2025-10-27 공시 \"주요사항보고서(회사합병결정)\" 이후 동일지배하 합병으로 비교재무제표가 소급재작성된 것으로 추정",
            }

# ---------------------------------------------------------------- 연간(2020-2025) 추이
annual = {c["key"]: {"revenue": [], "op_margin": [], "capex": [], "debt_ratio": []} for c in COMPANIES}
for c in COMPANIES:
    for year in YEARS:
        data = fetch_acnt_all_with_fallback(c["corp_code"], year, "11011")
        if data.get("status") != "000":
            for k in ("revenue", "op_margin", "capex", "debt_ratio"):
                annual[c["key"]][k].append(None)
            continue
        grouped = group_by_sj(data["list"], ["IS", "CIS", "CF", "BS"])

        revenue = find_across(grouped, ("IS", "CIS"), REVENUE_NAMES)
        op_income = find_across(grouped, ("IS", "CIS"), OP_INCOME_NAMES)
        liab = find_by_names(grouped["BS"], LIABILITIES_NAMES)
        equity = find_by_names(grouped["BS"], EQUITY_NAMES)

        rev_amt = to_eok(revenue["thstrm_amount"]) if revenue else None
        op_amt = to_eok(op_income["thstrm_amount"]) if op_income else None
        liab_amt = to_eok(liab["thstrm_amount"]) if liab else None
        equity_amt = to_eok(equity["thstrm_amount"]) if equity else None
        capex_amt = get_capex_eok(grouped["CF"])

        margin = round(op_amt / rev_amt * 100, 1) if rev_amt else None
        debt_ratio = round(liab_amt / equity_amt * 100, 1) if (liab_amt is not None and equity_amt) else None

        annual[c["key"]]["revenue"].append(rev_amt)
        annual[c["key"]]["op_margin"].append(margin)
        annual[c["key"]]["capex"].append(capex_amt)
        annual[c["key"]]["debt_ratio"].append(debt_ratio)

# ---------------------------------------------------------------- 주요사항보고서
filings = []
for c in COMPANIES:
    res = fetch_filings(c["corp_code"], "20200101", "20260906")
    if res.get("status") != "000":
        continue
    for item in res.get("list", []):
        raw_title = item["report_nm"]
        amend = raw_title.startswith("[") and "정정" in raw_title.split("]")[0]
        title = raw_title.split("]", 1)[1] if amend and "]" in raw_title else raw_title
        filings.append({
            "co": c["key"],
            "date": item["rcept_dt"][:4] + "-" + item["rcept_dt"][4:6] + "-" + item["rcept_dt"][6:8],
            "title": title,
            "amend": amend,
            "rcept_no": item["rcept_no"],
        })
filings.sort(key=lambda f: f["date"], reverse=True)

# ---------------------------------------------------------------- 저장
output = {
    "meta": {
        "generated_at": "2026-09-07",
        "source": "opendart.fss.or.kr Open API (fnlttSinglAcntAll, list.json)",
        "unit": "억원 (=100,000,000원), 비율은 % 별도 표기",
        "fs_basis": "CFS(연결재무제표) 우선, 조회 불가 시 OFS(개별재무제표)",
    },
    "companies": [{"key": c["key"], "name": c["name"]} for c in COMPANIES],
    "years": YEARS,
    "half_year": half_year,
    "annual": annual,
    "filings": filings,
    "notes": [restated_note] if restated_note else [],
}

json_path = os.path.join(BASE_DIR, "dashboard_data.json")
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

# dashboard_template.html의 플레이스홀더에 위 JSON을 그대로 주입해
# cement_dashboard.html을 생성한다. 화면에 찍히는 모든 수치는
# 이 JSON에서만 나오므로 템플릿에 수기로 옮겨 적을 일이 없다.
template_path = os.path.join(BASE_DIR, "dashboard_template.html")
html_path = os.path.join(BASE_DIR, "cement_dashboard.html")
with open(template_path, encoding="utf-8") as f:
    template = f.read()
injected = template.replace(
    "/*__DASHBOARD_DATA__*/{}",
    json.dumps(output, ensure_ascii=False)
)
with open(html_path, "w", encoding="utf-8") as f:
    f.write(injected)

print("Saved:", json_path)
print("Saved:", html_path)
print("half_year keys:", list(half_year.keys()))
print("restated_note:", restated_note)
print("filings count:", len(filings))
