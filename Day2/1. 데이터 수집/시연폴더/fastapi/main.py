"""
load_data.py의 수집/집계 로직을 감싸는 FastAPI 백엔드.

GET  /                     -> dashboard.html 반환
GET  /api/dashboard-data   -> 석탄 수입 통계 JSON (캐시됨, ?refresh=true 로 강제 재조회)

실행:
    pip install -r requirements.txt
    uvicorn main:app --reload
    브라우저에서 http://127.0.0.1:8000/ 접속
"""

import sys
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from load_data import (
    COUNTRY_NAMES,
    END_YYMM,
    HS_SGN,
    STRT_YYMM,
    aggregate_monthly,
    build_summary,
    fetch_trade_stats,
)

BASE_DIR = Path(__file__).parent
DASHBOARD_HTML = BASE_DIR / "dashboard.html"

CACHE_TTL_SECONDS = 10 * 60  # 10분
_cache = {"data": None, "fetched_at": 0.0}

app = FastAPI(title="석탄 수입 동향 API")


def _collect_dashboard_data():
    rows_by_country = {}
    for cnty_cd in COUNTRY_NAMES:
        try:
            rows_by_country[cnty_cd] = fetch_trade_stats(STRT_YYMM, END_YYMM, cnty_cd, HS_SGN)
        except Exception as e:
            print(f"[{cnty_cd}] 조회 실패: {e}", file=sys.stderr)
            rows_by_country[cnty_cd] = []

    if all(not rows for rows in rows_by_country.values()):
        raise HTTPException(status_code=502, detail="관세청 API 조회에 실패했습니다.")

    monthly_totals = aggregate_monthly(rows_by_country)
    months, monthly_out, summary_out, grand_total_wgt = build_summary(monthly_totals)

    return {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "hsCode": HS_SGN,
        "period": {"start": months[0], "end": months[-1]},
        "countries": COUNTRY_NAMES,
        "months": months,
        "monthly": monthly_out,
        "summary": summary_out,
        "grandTotalImpWgt": grand_total_wgt,
    }


@app.get("/", response_class=HTMLResponse)
def index():
    return DASHBOARD_HTML.read_text(encoding="utf-8")


@app.get("/api/dashboard-data")
def dashboard_data(refresh: bool = Query(False)):
    now = time.time()
    is_stale = (_cache["data"] is None) or (now - _cache["fetched_at"] > CACHE_TTL_SECONDS)

    if refresh or is_stale:
        _cache["data"] = _collect_dashboard_data()
        _cache["fetched_at"] = now

    return {**_cache["data"], "cached": not (refresh or is_stale)}
