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

YEARS = list(range(2020, 2026))  # 2020~2025
REPRT_CODE = "11011"  # 사업보고서(연간)

REVENUE_NAMES = ["매출액", "매출", "수익(매출액)", "수익"]
OP_INCOME_NAMES = ["영업이익", "영업이익(손실)"]


def find_item(items_by_sj, names):
    for sj in ("IS", "CIS"):
        for item in items_by_sj.get(sj, []):
            if item["account_nm"] in names:
                return item
    return None


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
            records.append({"회사명": name, "연도": year, "매출액(억원)": None, "영업이익률(%)": None})
            continue

        items_by_sj = {"IS": [], "CIS": []}
        for item in data["list"]:
            if item["sj_div"] in items_by_sj:
                items_by_sj[item["sj_div"]].append(item)

        revenue = find_item(items_by_sj, REVENUE_NAMES)
        op_income = find_item(items_by_sj, OP_INCOME_NAMES)

        revenue_amt = to_won_100m(revenue["thstrm_amount"]) if revenue else None
        op_income_amt = to_won_100m(op_income["thstrm_amount"]) if op_income else None

        op_margin = None
        if revenue_amt and op_income_amt is not None and revenue_amt != 0:
            op_margin = round(op_income_amt / revenue_amt * 100, 1)

        records.append({
            "회사명": name,
            "연도": year,
            "매출액(억원)": round(revenue_amt, 1) if revenue_amt is not None else None,
            "영업이익률(%)": op_margin,
        })

df = pd.DataFrame(records)
print(df.to_string(index=False))
df.to_csv(os.path.join(os.path.dirname(__file__), "dart_annual_trends_2020_2025.csv"), index=False, encoding="utf-8-sig")

# 한글 폰트 설정 (Windows 맑은 고딕)
for font_path in [r"C:\Windows\Fonts\malgun.ttf"]:
    if os.path.exists(font_path):
        fm.fontManager.addfont(font_path)
        plt.rcParams["font.family"] = fm.FontProperties(fname=font_path).get_name()
        break
plt.rcParams["axes.unicode_minus"] = False

fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))

for name in COMPANIES:
    sub = df[df["회사명"] == name].sort_values("연도")
    axes[0].plot(sub["연도"], sub["매출액(억원)"], marker="o", label=name)
    axes[1].plot(sub["연도"], sub["영업이익률(%)"], marker="o", label=name)

axes[0].set_title("연간 매출액 추이 (2020-2025)")
axes[0].set_xlabel("연도")
axes[0].set_ylabel("매출액 (억원)")
axes[0].grid(alpha=0.3)
axes[0].legend()

axes[1].set_title("연간 영업이익률 추이 (2020-2025)")
axes[1].set_xlabel("연도")
axes[1].set_ylabel("영업이익률 (%)")
axes[1].grid(alpha=0.3)
axes[1].legend()

for ax in axes:
    ax.set_xticks(YEARS)

fig.tight_layout()
out_path = os.path.join(os.path.dirname(__file__), "dart_annual_trends_2020_2025.png")
fig.savefig(out_path, dpi=150)
print("Saved:", out_path)
