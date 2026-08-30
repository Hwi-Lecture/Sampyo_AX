# 대시보드 제작 방법 3가지 비교 (PPT 120~122p)

교안 "대시보드 이론 03 — 제작 방법" 슬라이드(120~122p)에서 소개하는 세 가지
방법을 같은 날씨 데이터(Open-Meteo, 서울 기준 작업가능/주의/중단 판정)로
각각 완성해서 비교할 수 있게 만든 폴더입니다.

| 폴더 | PPT | 방법 | 실행 방법 |
|---|---|---|---|
| `1_python_html/` | 120p, 1번 | Python이 데이터를 저장 → HTML이 불러와서 표시 | `python weather_report.py` 실행 후 `dashboard.html` 더블클릭 |
| `2_streamlit/` | 121p, 2번 | Streamlit — 파이썬 코드 하나로 처리+화면 | `streamlit run app.py` |
| `3_fastapi/` | 122p, 3번 | FastAPI 백엔드 + HTML 프론트엔드(API 통신) | `uvicorn backend:app --reload` |

각 폴더 안 README.md에 실행 방법과 다른 두 방법과의 비교 포인트를 정리해
두었습니다.