"""
call_data.py 가 생성한 raw_trade_data.csv 를 읽어
월별/국가별 수입 통계를 집계하고 그래프로 시각화하는 스크립트.

load_data.py 의 "2) 월별/국가별 집계", "3) 국가별 연간 요약 통계 계산" 부분을 재사용하고,
matplotlib 그래프 출력 기능을 추가했다.

사용법:
    1. python call_data.py 를 먼저 실행해 raw_trade_data.csv 를 생성
    2. pip install pandas matplotlib
    3. python data_analyse.py
"""

import sys
from collections import defaultdict

import matplotlib.pyplot as plt
import pandas as pd

INPUT_CSV = "trade_stats_2701_2025.csv"

COUNTRY_NAMES = {
    "AU": "호주",
    "ID": "인도네시아",
    "US": "미국",
}


# ============================================================
# 1) 월별/국가별 집계
# ============================================================
def aggregate_monthly(df):
    """DataFrame -> {(cnty, year_month): [impDlr_sum, impWgt_sum]}"""
    monthly_totals = defaultdict(lambda: [0, 0])

    for _, row in df.iterrows():
        cnty = row["statCd"]
        if cnty not in COUNTRY_NAMES:
            continue  # '총계' 등 합계 행 제외

        year_month = row["year"]
        monthly_totals[(cnty, year_month)][0] += int(row["impDlr"])
        monthly_totals[(cnty, year_month)][1] += int(row["impWgt"])

    return monthly_totals


# ============================================================
# 2) 국가별 연간 요약 통계
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
# 3) 그래프
# ============================================================
def plot_monthly_weight(months, monthly_out):
    plt.figure(figsize=(10, 5))
    for cnty, name in COUNTRY_NAMES.items():
        plt.plot(months, monthly_out[cnty]["impWgt"], marker="o", label=name)
    plt.title("월별 국가별 수입중량 추이")
    plt.xlabel("년월")
    plt.ylabel("수입중량 (kg)")
    plt.xticks(rotation=45)
    plt.legend()
    plt.tight_layout()
    plt.savefig("monthly_weight.png")
    plt.close()


def plot_monthly_unit_price(months, monthly_out):
    plt.figure(figsize=(10, 5))
    for cnty, name in COUNTRY_NAMES.items():
        plt.plot(months, monthly_out[cnty]["unitPrice"], marker="o", label=name)
    plt.title("월별 국가별 단가 추이")
    plt.xlabel("년월")
    plt.ylabel("단가 (원/kg)")
    plt.xticks(rotation=45)
    plt.legend()
    plt.tight_layout()
    plt.savefig("monthly_unit_price.png")
    plt.close()


def plot_import_share(summary_out):
    labels = [COUNTRY_NAMES[cnty] for cnty in COUNTRY_NAMES]
    shares = [summary_out[cnty]["importSharePercent"] for cnty in COUNTRY_NAMES]

    plt.figure(figsize=(6, 6))
    plt.pie(shares, labels=labels, autopct="%.1f%%")
    plt.title("국가별 수입의존도")
    plt.tight_layout()
    plt.savefig("import_share.png")
    plt.close()


def main():
    try:
        df = pd.read_csv(INPUT_CSV)
    except FileNotFoundError:
        print(f"{INPUT_CSV} 가 없습니다. call_data.py 를 먼저 실행하세요.", file=sys.stderr)
        sys.exit(1)

    monthly_totals = aggregate_monthly(df)
    months, monthly_out, summary_out, grand_total_wgt = build_summary(monthly_totals)

    print("=== 국가별 연간 요약 ===")
    for cnty, name in COUNTRY_NAMES.items():
        s = summary_out[cnty]
        print(
            f"  {name}({cnty}): 총중량 {s['totalImpWgt']:,}kg, "
            f"평균단가 {s['avgUnitPrice']:.4f}원/kg, "
            f"의존도 {s['importSharePercent']:.2f}%"
        )

    plot_monthly_weight(months, monthly_out)
    plot_monthly_unit_price(months, monthly_out)
    plot_import_share(summary_out)
    print("그래프 저장 완료: monthly_weight.png, monthly_unit_price.png, import_share.png")


if __name__ == "__main__":
    main()
