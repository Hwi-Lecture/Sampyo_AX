import os
import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

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

YEARS = list(range(2020, 2026))
REPRT_CODE = "11011"  # 사업보고서(연간)

CAPEX_AGGREGATE_NAMES = ["유형자산의 취득"]
# 성신양회처럼 유형자산 취득이 세부 계정으로 쪼개져 나오는 경우 합산할 항목들
CAPEX_SUBITEM_NAMES = [
    "토지의 취득", "건물의 취득", "구축물의 취득", "기계장치의 취득",
    "차량운반구의 취득", "기타의유형자산의 취득", "기타유형자산의 취득",
    "건설중인자산의 취득", "리스기계장치의 취득",
]
LIABILITIES_NAMES = ["부채총계"]
EQUITY_NAMES = ["자본총계"]


def find_item(items_by_sj, sj_key, names):
    for item in items_by_sj.get(sj_key, []):
        if item["account_nm"] in names:
            return item
    return None


def get_capex_amount(items_by_sj):
    aggregate = find_item(items_by_sj, "CF", CAPEX_AGGREGATE_NAMES)
    if aggregate and aggregate["thstrm_amount"]:
        return to_won_100m(aggregate["thstrm_amount"])

    total = 0
    found = False
    for item in items_by_sj.get("CF", []):
        if item["account_nm"] in CAPEX_SUBITEM_NAMES and item["thstrm_amount"]:
            amt = to_won_100m(item["thstrm_amount"])
            if amt is not None:
                total += amt
                found = True
    return total if found else None


def fetch_financials(corp_code, year, fs_div):
    url = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
    params = {
        "crtfc_key": API_KEY,
        "corp_code": corp_code,
        "bsns_year": str(year),
        "reprt_code": REPRT_CODE,
        "fs_div": fs_div,
    }
    return requests.get(url, params=params, timeout=10).json()


def to_won_100m(amount_str):
    try:
        return int(amount_str) / 100_000_000
    except (TypeError, ValueError):
        return None


records = []
for name, corp_code in COMPANIES.items():
    for year in YEARS:
        data = fetch_financials(corp_code, year, "CFS")
        if data.get("status") != "000":
            data = fetch_financials(corp_code, year, "OFS")
        if data.get("status") != "000":
            records.append({"회사명": name, "연도": year, "유형자산취득액(억원)": None, "부채비율(%)": None})
            continue

        items_by_sj = {"CF": [], "BS": []}
        for item in data["list"]:
            if item["sj_div"] in items_by_sj:
                items_by_sj[item["sj_div"]].append(item)

        liab_item = find_item(items_by_sj, "BS", LIABILITIES_NAMES)
        equity_item = find_item(items_by_sj, "BS", EQUITY_NAMES)

        # 유형자산 취득은 현금유출이라 음수(-)로 표기되는 경우가 많아 절대값 사용
        capex_amt = get_capex_amount(items_by_sj)
        if capex_amt is not None:
            capex_amt = abs(capex_amt)

        liab_amt = to_won_100m(liab_item["thstrm_amount"]) if liab_item else None
        equity_amt = to_won_100m(equity_item["thstrm_amount"]) if equity_item else None

        debt_ratio = None
        if liab_amt is not None and equity_amt:
            debt_ratio = round(liab_amt / equity_amt * 100, 1)

        records.append({
            "회사명": name,
            "연도": year,
            "유형자산취득액(억원)": round(capex_amt, 1) if capex_amt is not None else None,
            "부채비율(%)": debt_ratio,
        })

df = pd.DataFrame(records)
print(df.to_string(index=False))
df.to_csv(os.path.join(os.path.dirname(__file__), "dart_capex_debt_2020_2025.csv"), index=False, encoding="utf-8-sig")

for font_path in [r"C:\Windows\Fonts\malgun.ttf"]:
    if os.path.exists(font_path):
        fm.fontManager.addfont(font_path)
        plt.rcParams["font.family"] = fm.FontProperties(fname=font_path).get_name()
        break
plt.rcParams["axes.unicode_minus"] = False

fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))

n_companies = len(COMPANIES)
bar_width = 0.8 / n_companies
x = list(range(len(YEARS)))

for idx, name in enumerate(COMPANIES):
    sub = df[df["회사명"] == name].sort_values("연도")
    offsets = [xi + (idx - (n_companies - 1) / 2) * bar_width for xi in x]
    axes[0].bar(offsets, sub["유형자산취득액(억원)"], width=bar_width, label=name)
    axes[1].plot(sub["연도"], sub["부채비율(%)"], marker="o", label=name)

axes[0].set_title("유형자산 취득액 추이 (2020-2025)")
axes[0].set_xlabel("연도")
axes[0].set_ylabel("유형자산 취득액 (억원)")
axes[0].set_xticks(x)
axes[0].set_xticklabels(YEARS)
axes[0].grid(alpha=0.3, axis="y")
axes[0].legend()

axes[1].set_title("부채비율 추이 (2020-2025)")
axes[1].set_xlabel("연도")
axes[1].set_ylabel("부채비율 (%)")
axes[1].set_xticks(YEARS)
axes[1].grid(alpha=0.3)
axes[1].legend()

fig.tight_layout()
out_path = os.path.join(os.path.dirname(__file__), "dart_capex_debt_2020_2025.png")
fig.savefig(out_path, dpi=150)
print("Saved:", out_path)
