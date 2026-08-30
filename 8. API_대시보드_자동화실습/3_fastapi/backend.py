# -*- coding: utf-8 -*-
"""
날씨 대시보드 — FastAPI 버전 (PPT 122p, 3번 방법)

백엔드(이 파일)는 "API 호출 + 데이터 가공"만 담당하고, 화면(static/index.html)은
따로 분리되어 있습니다. 화면은 fetch()로 백엔드에 데이터를 요청(=API 통신)해서
그림을 그립니다. 1_python_html이 파일(js)로 데이터를 건네줬다면, 여기서는
실시간 요청/응답으로 데이터를 건네준다는 점이 다릅니다.

실행 방법
    pip install fastapi uvicorn requests
    uvicorn backend:app --reload --port 8000

브라우저에서 http://localhost:8000 접속 (화면) → 화면이 내부적으로
http://localhost:8000/api/weather 를 호출해서 데이터를 받아갑니다.
"""

import requests
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="날씨 대시보드 API")

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

API_URL = "https://api.open-meteo.com/v1/forecast"


def judge(temp, precip, precip_prob, wind):
    """한 시간치 값을 작업가능/주의/중단으로 판정합니다."""
    if precip_prob >= STOP_PRECIP_PROB or precip >= STOP_PRECIP or wind >= STOP_WIND:
        return STATUS_STOP
    if precip_prob >= WARN_PRECIP_PROB or temp >= WARN_HOT or temp <= WARN_COLD:
        return STATUS_WARN
    return STATUS_OK


@app.get("/api/weather")
def get_weather():
    """프론트엔드(index.html)가 fetch()로 호출하는 API. 매 호출마다 최신 데이터를 받아옵니다."""
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

    times = raw["hourly"]["time"]
    temps = raw["hourly"]["temperature_2m"]
    feels = raw["hourly"]["apparent_temperature"]
    precs = raw["hourly"]["precipitation"]
    prob = raw["hourly"]["precipitation_probability"]
    wind = raw["hourly"]["wind_speed_10m"]

    forecast_start_index = len(times) - FORECAST_DAYS * 24

    hourly = []
    status_counts = {STATUS_OK: 0, STATUS_WARN: 0, STATUS_STOP: 0}
    for i, t in enumerate(times):
        status = judge(temps[i], precs[i], prob[i], wind[i])
        status_counts[status] += 1
        hourly.append({
            "time": t,
            "temp": temps[i],
            "feels_like": feels[i],
            "precip": precs[i],
            "precip_prob": prob[i],
            "wind": wind[i],
            "kind": "실측" if i < forecast_start_index else "예보",
            "status": status,
        })

    return {
        "region": REGION,
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "timezone": raw["timezone"],
        "summary": {
            "temp_mean": round(sum(temps) / len(temps), 1),
            "precip_total": round(sum(precs), 1),
            "wind_max": max(wind),
            "status_counts": status_counts,
            "workable_rate": round(status_counts[STATUS_OK] / len(times) * 100, 1),
        },
        "hourly": hourly,
    }


# index.html, style, script 등 화면 파일을 그대로 내려주는 부분
# (별도 웹서버 없이 FastAPI 하나로 화면+API를 동시에 서비스합니다)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
