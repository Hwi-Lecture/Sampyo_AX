"""
df_all.csv(국가별 석탄 수출입 통계)에 대한 질문에 답하기 위한 ollama tool-calling 로직.

pandas 코드를 직접 실행하는 filter_and_aggregate 도구를 정의하고, 이를 이용해
ollama 모델이 사용자의 질문에 맞는 pandas 쿼리를 스스로 구성/실행하도록 한다.
"""

from pathlib import Path

import pandas as pd
import requests

BASE_DIR = Path(__file__).parent
CSV_PATH = BASE_DIR / "df_all.csv"

OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3-vl:4b-instruct"

_df = pd.read_csv(CSV_PATH)

COUNTRIES = sorted(_df["statCdCntnKor1"].unique().tolist())
COAL_TYPES = sorted(_df["statKor"].unique().tolist())
METRIC_LABELS = {
    "impDlr": "수입 금액(달러)",
    "impWgt": "수입 중량(kg)",
    "expDlr": "수출 금액(달러)",
    "expWgt": "수출 중량(kg)",
    "balPayments": "무역수지(달러)",
}

SYSTEM_PROMPT = (
    "당신은 df_all.csv(국가별 석탄 수출입 통계) 데이터를 분석해주는 어시스턴트입니다. "
    "이 데이터는 2025년 1~12월 동안 호주/인도네시아/미국의 석탄(무연탄/유연탄/그 밖의 석탄 등) "
    "수출입 실적을 담고 있으며, 컬럼은 다음과 같습니다: "
    "statCdCntnKor1(국가명), statKor(석탄 종류), year(YYYY.MM), "
    "impDlr(수입금액), impWgt(수입중량), expDlr(수출금액), expWgt(수출중량), balPayments(무역수지). "
    "수치를 묻는 질문에는 반드시 filter_and_aggregate 도구를 호출해 데이터를 조회한 뒤, "
    "그 결과를 근거로 답변하세요. 도구 결과에 없는 내용은 추측하지 말고 모른다고 답하세요."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "filter_and_aggregate",
            "description": (
                "df_all.csv를 국가/석탄 종류/기간으로 필터링한 뒤 지정한 지표를 집계한다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "country": {
                        "type": "string",
                        "description": f"국가명. 예: {', '.join(COUNTRIES)}. 생략 시 전체 국가.",
                        "enum": COUNTRIES,
                    },
                    "coal_type": {
                        "type": "string",
                        "description": f"석탄 종류. 예: {', '.join(COAL_TYPES)}. 생략 시 전체.",
                        "enum": COAL_TYPES,
                    },
                    "month_from": {
                        "type": "integer",
                        "description": "조회 시작 월(1~12). 생략 시 1월부터.",
                    },
                    "month_to": {
                        "type": "integer",
                        "description": "조회 종료 월(1~12). 생략 시 12월까지.",
                    },
                    "metric": {
                        "type": "string",
                        "description": "집계할 지표.",
                        "enum": list(METRIC_LABELS.keys()),
                    },
                    "agg": {
                        "type": "string",
                        "description": "집계 방식. 기본값은 sum.",
                        "enum": ["sum", "mean", "max", "min", "count"],
                    },
                },
                "required": ["metric"],
            },
        },
    }
]


def build_pandas_query(country=None, coal_type=None, month_from=None, month_to=None,
                        metric="impWgt", agg="sum"):
    """실제 실행되는 필터/집계 로직을 그대로 나타내는 pandas 코드 문자열을 반환한다."""
    conditions = []
    if country:
        conditions.append(f"(df['statCdCntnKor1'] == {country!r})")
    if coal_type:
        conditions.append(f"(df['statKor'] == {coal_type!r})")
    if month_from is not None:
        conditions.append(f"(df['year'] >= 2025 + {int(month_from)}/100)")
    if month_to is not None:
        conditions.append(f"(df['year'] <= 2025 + {int(month_to)}/100)")

    if conditions:
        mask = " & ".join(conditions)
        return f"df[{mask}]['{metric}'].{agg}()"
    return f"df['{metric}'].{agg}()"


def filter_and_aggregate(country=None, coal_type=None, month_from=None, month_to=None,
                          metric="impWgt", agg="sum"):
    """df_all.csv를 필터링하고 집계한 결과를 사람이 읽을 수 있는 문자열로 반환한다."""
    if metric not in METRIC_LABELS:
        return f"오류: 알 수 없는 지표 '{metric}'. 사용 가능한 지표: {', '.join(METRIC_LABELS)}"
    if agg not in ("sum", "mean", "max", "min", "count"):
        return f"오류: 알 수 없는 집계 방식 '{agg}'"

    filtered = _df
    if country:
        filtered = filtered[filtered["statCdCntnKor1"] == country]
    if coal_type:
        filtered = filtered[filtered["statKor"] == coal_type]
    if month_from is not None:
        filtered = filtered[filtered["year"] >= round(2025 + int(month_from) / 100, 2)]
    if month_to is not None:
        filtered = filtered[filtered["year"] <= round(2025 + int(month_to) / 100, 2)]

    if filtered.empty:
        return "조건에 맞는 데이터가 없습니다."

    value = getattr(filtered[metric], agg)()
    label = METRIC_LABELS[metric]
    return f"{label} {agg}: {value:,.0f} (조회된 행 수: {len(filtered)})"


def chat(model: str, messages: list, tools: list | None = None) -> dict:
    """ollama /api/chat 엔드포인트를 호출해 (스트리밍 없이) 응답 전체를 반환한다."""
    payload = {"model": model, "messages": messages, "stream": False}
    if tools:
        payload["tools"] = tools
    resp = requests.post(OLLAMA_CHAT_URL, json=payload, timeout=300)
    resp.raise_for_status()
    return resp.json()


TOOL_IMPL = {
    "filter_and_aggregate": filter_and_aggregate,
}
