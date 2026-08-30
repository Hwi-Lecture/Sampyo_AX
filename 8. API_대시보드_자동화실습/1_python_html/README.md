# 1. Python이 데이터를 만들고, HTML이 읽어서 보여주기

교안 PPT 120p의 1번 방법입니다.
**파이썬이 데이터를 파일로 저장해두면, HTML 페이지가 그 파일을 읽어서 화면에 그립니다.**

```
weather_report.py   →   weather_data.js   →   dashboard.html
   (데이터 수집·가공)        (저장된 데이터)        (브라우저에서 보기)
```

## 실행 방법

```bash
pip install pandas matplotlib      # 처음 한 번만
python weather_report.py           # 데이터를 받아와 파일로 저장
```

그다음 `dashboard.html` 을 더블클릭하면 브라우저에 대시보드가 뜹니다.
서버가 필요 없어서, 이 폴더를 통째로 압축해 메일로 보내도 상대방이 바로 열어볼 수 있습니다.

## 파일 구성

| 파일 | 역할 | 지워도 되나 |
|---|---|---|
| `weather_report.py` | API 호출 → 판정 → 저장까지 전 과정. **여기 위쪽 설정값만 고치면 됩니다** | ❌ 본체 |
| `dashboard.html` | 화면. Chart.js로 그래프를 그립니다 | ❌ 본체 |
| `weather_data.js` | `weather_report.py` 가 만든 데이터. 대시보드가 읽는 **유일한** 데이터 파일 | ⭕ 다시 실행하면 생김 |
| `.claude/` | 도구 설정 (아래 설명) | ⭕ 없어도 실습은 됩니다 |

`weather_report.py` 를 실행하면 `raw_weather.json`, `weather_hourly.csv`,
`weather_processed.json`, `charts/*.png` 도 함께 생깁니다.
**대시보드는 이 파일들을 읽지 않습니다.** 엑셀로 열어보거나 보고서에 붙이는 용도이며,
지워도 다시 실행하면 그대로 다시 만들어집니다.

## `.claude/` 폴더는 왜 있나

이 폴더는 **Claude Code로 실습할 때만** 쓰이는 설정입니다.
파이썬이나 브라우저와는 무관해서, 지워도 위 실행 방법은 똑같이 동작합니다.

- **`launch.json`** — 대시보드를 로컬 서버(`localhost:8931`)로 띄우는 설정입니다.
  `dashboard.html` 은 더블클릭으로도 열리지만, 브라우저 보안 정책 때문에
  일부 환경에서는 `file://` 로 열 때 데이터를 못 읽는 경우가 있습니다.
  그럴 때 서버로 띄우면 해결됩니다.
- **`settings.local.json`** — `python weather_report.py` 실행을 미리 허용해둔 것입니다.
  이게 없으면 Claude Code가 스크립트를 돌릴 때마다 "실행해도 되나요?" 하고 매번 묻습니다.

## 다른 두 방법과 비교

| | 이 방법 (1번) | Streamlit (2번) | FastAPI (3번) |
|---|---|---|---|
| 서버 | 필요 없음 | 필요 | 필요 |
| 파일로 전달 | ⭕ 압축해서 메일 발송 가능 | ❌ | ❌ |
| 데이터 갱신 | 스크립트를 다시 실행해야 함 | 새로고침하면 갱신 | 새로고침하면 갱신 |
| 화면 자유도 | 높음 (HTML/CSS 직접 작성) | 낮음 (정해진 부품 조합) | 높음 |
