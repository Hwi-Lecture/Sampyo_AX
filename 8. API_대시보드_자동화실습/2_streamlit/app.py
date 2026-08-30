# -*- coding: utf-8 -*-
"""
날씨 대시보드 — Streamlit 버전 (PPT 121p, 2번 방법)

이 파일 하나로 "API 호출 → 데이터 가공 → 화면 표시"가 전부 끝납니다.
1_python_html 폴더처럼 별도 HTML/CSS/JS 파일이 없고, 파이썬 코드가
곧 화면입니다.

실행 방법
    pip install streamlit pandas requests
    streamlit run app.py

실행하면 브라우저가 자동으로 열리고, 코드를 고쳐서 저장하면
화면이 바로 갱신됩니다(서버가 계속 떠 있어야 함).
"""

import pandas as pd
import requests
import streamlit as st

# ============================================================
# 설정 — 1_python_html/weather_report.py 와 동일한 값
# ============================================================

REGION = "서울"
LATITUDE = 37.5665
LONGITUDE = 126.9780

PAST_DAYS = 7
FORECAST_DAYS = 7

STOP_PRECIP_PROB = 60
STOP_PRECIP = 1.0
STOP_WIND = 36

WARN_PRECIP_PROB = 30
WARN_HOT = 33
WARN_COLD = 5

STATUS_OK, STATUS_WARN, STATUS_STOP = "작업가능", "주의", "중단"
STATUS_ORDER = [STATUS_OK, STATUS_WARN, STATUS_STOP]
STATUS_COLOR = {STATUS_OK: "#2e7d32", STATUS_WARN: "#ef6c00", STATUS_STOP: "#c62828"}

API_URL = "https://api.open-meteo.com/v1/forecast"


# ------------------------------------------------------------
# 데이터 가져오기 + 가공 (캐시를 걸어서, 화면을 조작할 때마다
# API를 다시 부르지 않고 10분에 한 번만 새로 받아옵니다)
# ------------------------------------------------------------

@st.cache_data(ttl=600)
def load_weather() -> pd.DataFrame:
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                  "precipitation,precipitation_probability,wind_speed_10m",
        "past_days": PAST_DAYS,
        "forecast_days": FORECAST_DAYS,
        "timezone": "auto",
    }
    raw = requests.get(API_URL, params=params, timeout=30).json()

    df = pd.DataFrame(raw["hourly"]).rename(columns={
        "temperature_2m": "temp",
        "apparent_temperature": "feels_like",
        "relative_humidity_2m": "humidity",
        "precipitation": "precip",
        "precipitation_probability": "precip_prob",
        "wind_speed_10m": "wind",
    })
    df["time"] = pd.to_datetime(df["time"])
    forecast_start = df["time"].iloc[len(df) - FORECAST_DAYS * 24]
    df["kind"] = df["time"].apply(lambda t: "실측" if t < forecast_start else "예보")
    df["date"] = df["time"].dt.date

    def judge(row):
        if (row["precip_prob"] >= STOP_PRECIP_PROB
                or row["precip"] >= STOP_PRECIP
                or row["wind"] >= STOP_WIND):
            return STATUS_STOP
        if (row["precip_prob"] >= WARN_PRECIP_PROB
                or row["temp"] >= WARN_HOT
                or row["temp"] <= WARN_COLD):
            return STATUS_WARN
        return STATUS_OK

    df["status"] = df.apply(judge, axis=1)
    return df


# ------------------------------------------------------------
# 화면 구성
# ------------------------------------------------------------

st.set_page_config(page_title=f"{REGION} 현장 작업 여건", layout="wide")
st.title(f"🏗️ {REGION} 현장 작업 여건 대시보드")
st.caption("Streamlit 버전 — 파이썬 코드 하나로 데이터 처리부터 화면까지")

with st.spinner("날씨 데이터를 불러오는 중..."):
    df = load_weather()

counts = df["status"].value_counts()
total = len(df)

col1, col2, col3, col4 = st.columns(4)
col1.metric("평균 기온", f"{df['temp'].mean():.1f} °C")
col2.metric("누적 강수량", f"{df['precip'].sum():.1f} mm")
col3.metric("최대 풍속", f"{df['wind'].max():.1f} km/h")
col4.metric("작업가능 비율", f"{counts.get(STATUS_OK, 0) / total * 100:.1f} %")

st.subheader("기온 흐름 (실측 vs 예보)")
st.line_chart(df.set_index("time")[["temp", "feels_like"]])

st.subheader("강수확률 흐름")
st.area_chart(df.set_index("time")[["precip_prob"]])

st.subheader("날짜별 작업가능 시간")
by_date = df.groupby(["date", "status"]).size().unstack(fill_value=0)
for s in STATUS_ORDER:
    if s not in by_date.columns:
        by_date[s] = 0
st.bar_chart(by_date[STATUS_ORDER])

st.subheader("시간별 상세 표")
st.dataframe(
    df[["time", "temp", "feels_like", "precip", "precip_prob", "wind", "kind", "status"]],
    use_container_width=True,
    height=300,
)

st.caption(
    "장점: 파이썬 코드 하나로 데이터 처리+화면 구성 끝 (진입장벽 낮음) · "
    "단점: 이 화면을 보려면 `streamlit run app.py` 서버가 계속 떠 있어야 하고, "
    "레이아웃/디자인은 Streamlit이 제공하는 범위 안에서만 꾸밀 수 있음(자유도 낮음)."
)
