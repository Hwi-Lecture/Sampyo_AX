# -*- coding: utf-8 -*-
"""
날씨 데이터 수집 → 가공 → 저장 파이프라인

주피터 노트북(실습_날씨데이터_분석.ipynb)에서 한 셀씩 확인했던 작업을
하나의 파일로 묶은 것입니다. 이 파일 하나만 실행하면 전체가 순서대로 돕니다.

    python weather_report.py

실행하면 같은 폴더에 아래 파일들이 만들어집니다.

    raw_weather.json        API가 준 원본 데이터
    weather_hourly.csv      시간별 표 (엑셀에서 바로 열림)
    weather_processed.json  가공 결과 (대시보드가 읽어갈 데이터)
    charts/*.png            그래프 4장

필요한 것: pandas, matplotlib
    pip install pandas matplotlib
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import matplotlib

matplotlib.use("Agg")   # 화면 없이 파일로만 그래프를 저장하는 방식
                        # (예약 실행처럼 창을 띄울 수 없는 환경에서도 동작합니다)

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import font_manager


# ============================================================
# 설정 — 여기만 고치면 됩니다
# ============================================================

REGION = "서울"
LATITUDE = 37.5665
LONGITUDE = 126.9780

PAST_DAYS = 7        # 지난 며칠 실측치까지 (최대 92)
FORECAST_DAYS = 7    # 앞으로 며칠 예보까지 (최대 16)

# 작업 가능 여부를 가르는 기준값 — 현장 사정에 맞게 조정하세요
STOP_PRECIP_PROB = 60    # 강수확률이 이 % 이상이면 중단
STOP_PRECIP = 1.0        # 강수량이 이 mm 이상이면 중단
STOP_WIND = 36           # 풍속이 이 km/h 이상이면 중단 (약 10 m/s)

WARN_PRECIP_PROB = 30    # 강수확률이 이 % 이상이면 주의
WARN_HOT = 33            # 기온이 이 °C 이상이면 주의 (혹서기)
WARN_COLD = 5            # 기온이 이 °C 이하면 주의 (한중 양생)

# 결과를 저장할 위치 (이 파일이 있는 폴더 기준)
OUTPUT_DIR = Path(__file__).parent
CHART_DIR = OUTPUT_DIR / "charts"


# ============================================================
# 아래부터는 그대로 두고 실행하면 됩니다
# ============================================================

API_URL = "https://api.open-meteo.com/v1/forecast"

STATUS_OK = "작업가능"
STATUS_WARN = "주의"
STATUS_STOP = "중단"
STATUS_ORDER = [STATUS_OK, STATUS_WARN, STATUS_STOP]
STATUS_COLOR = {
    STATUS_OK: "tab:green",
    STATUS_WARN: "tab:orange",
    STATUS_STOP: "tab:red",
}

COLUMN_LABELS = {
    "time": "시각",
    "temp": "기온",
    "feels_like": "체감온도",
    "humidity": "습도",
    "precip": "강수량",
    "precip_prob": "강수확률",
    "wind": "풍속",
    "kind": "구분",
    "status": "상태",
}


def setup_matplotlib():
    """그래프의 한글이 깨지지 않게 폰트를 지정합니다."""
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for candidate in ["Malgun Gothic", "AppleGothic", "NanumGothic", "Gulim"]:
        if candidate in installed:
            plt.rcParams["font.family"] = candidate
            break
    else:
        print("  (참고) 한글 폰트를 못 찾아 그래프의 한글이 네모로 보일 수 있습니다.")

    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.figsize"] = (11, 4)
    plt.rcParams["axes.grid"] = True
    plt.rcParams["grid.alpha"] = 0.3


# ------------------------------------------------------------
# 1. API 호출
# ------------------------------------------------------------

def fetch_weather():
    """Open-Meteo API를 호출해서 원본 데이터를 받아옵니다."""
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                  "precipitation,precipitation_probability,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,"
                 "precipitation_sum,wind_speed_10m_max",
        "past_days": PAST_DAYS,
        "forecast_days": FORECAST_DAYS,
        "timezone": "auto",
    }
    url = API_URL + "?" + urllib.parse.urlencode(params)

    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print("API 호출에 실패했습니다.")
        print("  인터넷 연결이나 사내 네트워크 차단 여부를 확인해주세요.")
        print("  자세한 원인:", e)
        sys.exit(1)

    print(f"  {REGION} 데이터 수신 — "
          f"시간별 {len(raw['hourly']['time'])}건 / "
          f"일별 {len(raw['daily']['time'])}건 ({raw['timezone']})")
    return raw, params


# ------------------------------------------------------------
# 2. 표로 정리하기
# ------------------------------------------------------------

def build_dataframe(raw, params):
    """받은 JSON을 다루기 쉬운 표(DataFrame)로 바꿉니다."""
    df = pd.DataFrame(raw["hourly"]).rename(columns={
        "temperature_2m": "temp",
        "apparent_temperature": "feels_like",
        "relative_humidity_2m": "humidity",
        "precipitation": "precip",
        "precipitation_probability": "precip_prob",
        "wind_speed_10m": "wind",
    })
    df["time"] = pd.to_datetime(df["time"])

    # 지난 며칠은 '실측', 그 뒤는 '예보'로 표시합니다
    last_past_day = pd.to_datetime(raw["daily"]["time"][params["past_days"] - 1])
    forecast_start = last_past_day + pd.Timedelta(days=1)
    df["kind"] = df["time"].apply(
        lambda t: "실측" if t < forecast_start else "예보"
    )
    df["date"] = df["time"].dt.date

    print(f"  표 생성 — {len(df)}줄 "
          f"(실측 {(df['kind'] == '실측').sum()} / 예보 {(df['kind'] == '예보').sum()})")
    return df, forecast_start


# ------------------------------------------------------------
# 3. 업무 기준 적용
# ------------------------------------------------------------

def judge(row):
    """한 시간치 데이터를 '중단' / '주의' / '작업가능' 으로 판정합니다."""
    if (row["precip_prob"] >= STOP_PRECIP_PROB
            or row["precip"] >= STOP_PRECIP
            or row["wind"] >= STOP_WIND):
        return STATUS_STOP
    if (row["precip_prob"] >= WARN_PRECIP_PROB
            or row["temp"] >= WARN_HOT
            or row["temp"] <= WARN_COLD):
        return STATUS_WARN
    return STATUS_OK


def apply_status(df):
    df["status"] = df.apply(judge, axis=1)

    counts = df["status"].value_counts()
    parts = [f"{s} {counts.get(s, 0)}h" for s in STATUS_ORDER]
    print("  상태 판정 — " + " / ".join(parts))
    return df, counts


# ------------------------------------------------------------
# 4. 집계
# ------------------------------------------------------------

def summarize_by_date(df):
    """날짜별로 상태를 묶어서 작업가능률을 계산합니다."""
    by_date = df.groupby(["date", "status"]).size().unstack(fill_value=0)
    for s in STATUS_ORDER:
        if s not in by_date.columns:
            by_date[s] = 0
    by_date = by_date[STATUS_ORDER]
    by_date["workable_rate"] = (
        by_date[STATUS_OK] / by_date.sum(axis=1) * 100
    ).round(1)
    return by_date


def find_workable_blocks(df):
    """작업가능 상태가 연속으로 이어지는 구간을 찾습니다."""
    block_id = (df["status"] != df["status"].shift()).cumsum()
    blocks = df.groupby(block_id).agg(
        status=("status", "first"),
        start=("time", "first"),
        end=("time", "last"),
        hours=("time", "size"),
    )
    workable = blocks[blocks["status"] == STATUS_OK]
    return workable.sort_values("hours", ascending=False)


def compare_actual_forecast(df):
    """실측 기간과 예보 기간을 나란히 비교합니다."""
    compare = df.groupby("kind").agg(
        hours=("temp", "size"),
        temp_mean=("temp", "mean"),
        temp_max=("temp", "max"),
        precip_total=("precip", "sum"),
        humidity_mean=("humidity", "mean"),
        wind_max=("wind", "max"),
    ).round(1)
    compare["workable_hours"] = (
        df[df["status"] == STATUS_OK].groupby("kind").size()
    )
    compare["workable_rate"] = (
        compare["workable_hours"] / compare["hours"] * 100
    ).round(1)
    return compare.reindex([k for k in ["실측", "예보"] if k in compare.index])


# ------------------------------------------------------------
# 5. 그래프 그리기
# ------------------------------------------------------------

def draw_charts(df, by_date, counts, forecast_start):
    """그래프 4장을 PNG 파일로 저장합니다."""
    CHART_DIR.mkdir(exist_ok=True)
    saved = []

    # (1) 기온 흐름 — 실측은 실선, 예보는 점선
    actual = df[df["kind"] == "실측"]
    forecast = df[df["kind"] == "예보"]

    fig, ax = plt.subplots()
    ax.plot(actual["time"], actual["temp"],
            label="기온 (실측)", color="tab:red", linewidth=1.6)
    ax.plot(forecast["time"], forecast["temp"],
            label="기온 (예보)", color="tab:red", linewidth=1.6,
            linestyle="--", alpha=0.7)
    ax.plot(df["time"], df["feels_like"],
            label="체감온도", color="tab:orange", linewidth=1, alpha=0.5)
    ax.axvline(forecast_start, color="gray", linestyle=":", linewidth=1.5)
    ax.text(forecast_start, ax.get_ylim()[1], " 오늘부터 예보",
            va="top", fontsize=9, color="gray")
    ax.set_title(f"{REGION} 기온 변화 (지난 {PAST_DAYS}일 + 앞으로 {FORECAST_DAYS}일)")
    ax.set_ylabel("기온 (°C)")
    ax.legend(loc="lower left")
    fig.autofmt_xdate()
    saved.append(_save(fig, "1_기온흐름.png"))

    # (2) 강수량(막대) 과 강수확률(선) — 단위가 달라 축을 두 개 씁니다
    fig, ax1 = plt.subplots()
    ax1.bar(df["time"], df["precip"], width=0.04,
            color="tab:blue", label="강수량 (mm)")
    ax1.set_ylabel("강수량 (mm)", color="tab:blue")
    ax1.tick_params(axis="y", labelcolor="tab:blue")

    ax2 = ax1.twinx()
    ax2.plot(df["time"], df["precip_prob"], color="tab:green",
             linewidth=1.2, alpha=0.8)
    ax2.set_ylabel("강수확률 (%)", color="tab:green")
    ax2.tick_params(axis="y", labelcolor="tab:green")
    ax2.set_ylim(0, 105)
    ax2.grid(False)

    ax1.axvline(forecast_start, color="gray", linestyle=":", linewidth=1.5)
    ax1.set_title(f"{REGION} 강수량(막대) 과 강수확률(선)")
    fig.autofmt_xdate()
    saved.append(_save(fig, "2_강수.png"))

    # (3) 상태별 분포
    total = len(df)
    fig, ax = plt.subplots(figsize=(6, 3.5))
    values = [counts.get(s, 0) for s in STATUS_ORDER]
    ax.bar(STATUS_ORDER, values, color=[STATUS_COLOR[s] for s in STATUS_ORDER])
    for i, value in enumerate(values):
        ax.text(i, value, f"{value}시간\n({value / total * 100:.1f}%)",
                ha="center", va="bottom")
    ax.set_title(f"전체 {total}시간 중 상태별 분포")
    ax.set_ylabel("시간")
    ax.set_ylim(0, max(values) * 1.25)
    saved.append(_save(fig, "3_상태분포.png"))

    # (4) 날짜별 작업 가능 시간
    chart_data = by_date[STATUS_ORDER]
    labels = [str(d)[5:] for d in chart_data.index]

    fig, ax = plt.subplots(figsize=(11, 4))
    bottom = [0] * len(chart_data)
    for s in STATUS_ORDER:
        ax.bar(labels, chart_data[s], bottom=bottom,
               label=s, color=STATUS_COLOR[s])
        bottom = [a + b for a, b in zip(bottom, chart_data[s])]
    ax.set_title(f"{REGION} 날짜별 작업 가능 시간 (하루 24시간 기준)")
    ax.set_ylabel("시간")
    ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    saved.append(_save(fig, "4_날짜별작업가능.png"))

    print(f"  그래프 {len(saved)}장 저장 — charts/ 폴더")
    return saved


def _save(fig, filename):
    path = CHART_DIR / filename
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return path


# ------------------------------------------------------------
# 6. 파일로 저장
# ------------------------------------------------------------

def save_outputs(raw, df, by_date, counts, workable):
    """원본·표·가공결과를 파일로 남깁니다."""
    # 원본 그대로
    with open(OUTPUT_DIR / "raw_weather.json", "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)

    # 엑셀에서 열 수 있는 CSV (utf-8-sig 라야 한글이 안 깨집니다)
    export_cols = ["time", "temp", "feels_like", "humidity",
                   "precip", "precip_prob", "wind", "kind", "status"]
    export = df[export_cols]
    export.to_csv(OUTPUT_DIR / "weather_hourly.csv",
                  index=False, encoding="utf-8-sig")

    # 대시보드가 읽어갈 JSON
    result = {
        "region": REGION,
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "timezone": raw["timezone"],
        "generated_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "column_labels": COLUMN_LABELS,
        "thresholds": {
            "stop_precip_prob": STOP_PRECIP_PROB,
            "stop_precip": STOP_PRECIP,
            "stop_wind": STOP_WIND,
            "warn_precip_prob": WARN_PRECIP_PROB,
            "warn_hot": WARN_HOT,
            "warn_cold": WARN_COLD,
        },
        "summary": {
            "temp_min": float(df["temp"].min()),
            "temp_mean": round(float(df["temp"].mean()), 1),
            "temp_max": float(df["temp"].max()),
            "precip_total": round(float(df["precip"].sum()), 1),
            "wind_max": float(df["wind"].max()),
            "status_counts": {s: int(counts.get(s, 0)) for s in STATUS_ORDER},
        },
        "daily": by_date.reset_index().assign(
            date=lambda x: x["date"].astype(str)
        ).to_dict(orient="records"),
        "hourly": export.assign(
            time=lambda x: x["time"].dt.strftime("%Y-%m-%dT%H:%M")
        ).to_dict(orient="records"),
        "workable_blocks": [
            {
                "start": row["start"].strftime("%Y-%m-%dT%H:%M"),
                "end": row["end"].strftime("%Y-%m-%dT%H:%M"),
                "hours": int(row["hours"]),
            }
            for _, row in workable.head(10).iterrows()
        ],
    }
    with open(OUTPUT_DIR / "weather_processed.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 대시보드(dashboard.html)가 읽어갈 JS 파일.
    # JSON을 fetch로 읽으면 파일을 더블클릭해서 열었을 때 브라우저가 막기 때문에,
    # <script src="..."> 로 불러올 수 있게 JS 형태로 한 번 더 저장합니다.
    with open(OUTPUT_DIR / "weather_data.js", "w", encoding="utf-8") as f:
        f.write("// 이 파일은 weather_report.py 가 자동으로 만듭니다. 직접 고치지 마세요.\n")
        f.write("const WEATHER_DATA = ")
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write(";\n")

    print("  raw_weather.json / weather_hourly.csv / "
          "weather_processed.json / weather_data.js 저장")


# ------------------------------------------------------------
# 7. 사람이 읽는 요약 출력
# ------------------------------------------------------------

def print_report(df, by_date, counts, workable, compare):
    total = len(df)
    line = "-" * 58

    print()
    print("=" * 58)
    print(f"  {REGION} 작업 여건 요약  "
          f"({df['time'].min():%m/%d} ~ {df['time'].max():%m/%d})")
    print("=" * 58)

    print()
    print("[ 기간 전체 ]")
    print(f"  기온      최저 {df['temp'].min()}°C / "
          f"평균 {df['temp'].mean():.1f}°C / 최고 {df['temp'].max()}°C")
    print(f"  강수량    합계 {df['precip'].sum():.1f} mm")
    print(f"  최대풍속  {df['wind'].max()} km/h")

    print()
    print("[ 상태별 시간 ]")
    for s in STATUS_ORDER:
        n = counts.get(s, 0)
        ratio = n / total * 100
        print(f"  {s:<6}{n:>4}시간 ({ratio:>5.1f}%)  {'█' * int(ratio / 2)}")

    print()
    print("[ 날짜별 작업가능률 ]")
    print(line)
    for date, row in by_date.iterrows():
        rate = row["workable_rate"]
        print(f"  {date}   {int(row[STATUS_OK]):>2}h 가능 / "
              f"{int(row[STATUS_WARN]):>2}h 주의 / {int(row[STATUS_STOP]):>2}h 중단   "
              f"{rate:>5.1f}% {'█' * int(rate / 5)}")

    print()
    print("[ 연속 작업가능 구간 상위 5개 ]")
    print(line)
    if len(workable) == 0:
        print("  없습니다. 기준값을 조정해보세요.")
    else:
        for _, row in workable.head(5).iterrows():
            print(f"  {row['start']:%m/%d %H시}  ~  {row['end']:%m/%d %H시}"
                  f"   ({row['hours']}시간 연속)")

    print()
    print("[ 실측 vs 예보 ]")
    print(line)
    for kind, row in compare.iterrows():
        print(f"  {kind}   평균 {row['temp_mean']}°C / "
              f"강수 {row['precip_total']}mm / "
              f"작업가능 {int(row['workable_hours'])}h ({row['workable_rate']}%)")
    print()


# ------------------------------------------------------------
# 전체 흐름
# ------------------------------------------------------------

def main():
    print()
    print(f"[1/6] API 호출 — {REGION} (위도 {LATITUDE}, 경도 {LONGITUDE})")
    raw, params = fetch_weather()

    print("[2/6] 표로 정리")
    df, forecast_start = build_dataframe(raw, params)

    print("[3/6] 업무 기준 적용")
    df, counts = apply_status(df)

    print("[4/6] 집계")
    by_date = summarize_by_date(df)
    workable = find_workable_blocks(df)
    compare = compare_actual_forecast(df)
    print(f"  날짜별 {len(by_date)}일 / 연속 작업가능 구간 {len(workable)}개")

    print("[5/6] 그래프 생성")
    setup_matplotlib()
    draw_charts(df, by_date, counts, forecast_start)

    print("[6/6] 파일 저장")
    save_outputs(raw, df, by_date, counts, workable)

    print_report(df, by_date, counts, workable, compare)
    print(f"완료 — 결과물은 {OUTPUT_DIR} 폴더에 있습니다.")


if __name__ == "__main__":
    # 윈도우 명령창에서 한글이 깨지지 않게 출력 방식을 UTF-8로 맞춥니다
    sys.stdout.reconfigure(encoding="utf-8")
    main()
