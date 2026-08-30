# 2번 방법 — Streamlit (PPT 121p)

같은 날씨 대시보드를 **Streamlit**으로 만든 완성 예시입니다. 1_python_html과
비교했을 때 "파이썬 코드 하나로 데이터 처리부터 화면 구성까지" 방식이 실제로
어떻게 다른지 보여주는 용도입니다. (별도 다단계 실습이 아니라, 이론 설명 중
보여주는 완성본입니다.)

## 실행 방법

```
pip install streamlit pandas requests
streamlit run app.py
```

실행하면 브라우저가 자동으로 열립니다 (`http://localhost:8501`).

## 1_python_html과 비교 포인트

| | 1_python_html | 2_streamlit |
|---|---|---|
| 파일 개수 | weather_report.py + dashboard.html + weather_data.js (3개 이상 역할 분리) | app.py 1개 |
| 데이터 갱신 확인 | 파이썬 실행 → html 새로고침 (2단계) | 파일 저장 → 화면 자동 갱신 |
| 화면을 계속 보려면 | HTML 파일만 있으면 됨 (서버 불필요) | `streamlit run` 서버가 떠 있어야 함 |
| 디자인 자유도 | CSS로 자유롭게 (높음) | Streamlit 기본 위젯 범위 내 (낮음) |

## 같은 데이터를 씁니다

위경도(서울 37.5665, 126.978)와 작업가능/주의/중단 판정 기준값을
1_python_html/weather_report.py와 동일하게 맞췄습니다. 세 폴더의 결과 화면이
"같은 데이터로 다른 방식을 썼을 때 무엇이 달라지는지"에 집중해서 비교되도록
하기 위함입니다.

## 장단점 (PPT 121p 그대로)

- 장점: 파이썬 코드 하나로 데이터 처리부터 화면 구성까지 가능 → 진입장벽이 낮음
- 단점: 대시보드를 확인하려면 서버(`streamlit run`)를 계속 띄워 놓아야 하고,
  Streamlit 특성상 UI 커스터마이징이 어려움
