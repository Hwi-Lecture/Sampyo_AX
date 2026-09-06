"""
문서를 문장 단위로 나눈 뒤 로컬 Ollama의 embeddinggemma 모델로 임베딩하고,
인접 문장 간 코사인 거리를 계산해 chunking_visualizer.html에 구워 넣을
SEMANTIC_DATA JSON을 만든다.

사용법:
    python compute_semantic_chunks.py

전제:
    - Ollama가 로컬(http://localhost:11434)에서 실행 중이어야 함.
    - embeddinggemma 모델이 pull되어 있어야 함: `ollama pull embeddinggemma`

출력:
    semantic_data.json  (documents/ 폴더의 각 문서 id별 sentences/distances)
    -> 이 값을 chunk_viz_template.html의 SEMANTIC_DATA 상수에 그대로 삽입한다.
"""
import json
import math
import re
import urllib.request
from pathlib import Path

OLLAMA_URL = "http://localhost:11434/api/embed"
MODEL = "embeddinggemma"

DOCS = [
    {"id": "unit-water", "path": "documents/단위수량시험_제규격(콘크리트학회).md"},
    {"id": "safety-law", "path": "documents/산업안전보건법 주요 개정내용(제조업).md"},
]

SENTENCE_END_RE = re.compile(r"[^.!?]*[.!?]+(?=\s|$)|[^.!?]+$")


def split_sentences(text):
    units = []
    offset = 0
    for line in text.split("\n"):
        if line.strip():
            for m in SENTENCE_END_RE.finditer(line):
                piece = m.group(0)
                if piece.strip():
                    start = offset + m.start()
                    end = start + len(piece)
                    units.append({"start": start, "end": end, "text": piece.strip()})
        offset += len(line) + 1
    return units


def embed_batch(texts):
    body = json.dumps({"model": MODEL, "input": texts}).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["embeddings"]


def cosine_distance(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 1.0
    sim = dot / (na * nb)
    sim = max(-1.0, min(1.0, sim))
    return round(1.0 - sim, 6)


def main():
    result = {}
    for doc in DOCS:
        text = Path(doc["path"]).read_text(encoding="utf-8")
        sentences = split_sentences(text)
        print(f"[{doc['id']}] {len(sentences)}개 문장, 임베딩 요청 중...")
        embeddings = embed_batch([s["text"] for s in sentences])
        distances = [
            cosine_distance(embeddings[i], embeddings[i + 1])
            for i in range(len(embeddings) - 1)
        ]
        if distances:
            print(
                f"  거리 범위: min={min(distances):.4f} max={max(distances):.4f} "
                f"평균={sum(distances)/len(distances):.4f}"
            )
        result[doc["id"]] = {
            "sentences": [[s["start"], s["end"]] for s in sentences],
            "distances": distances,
        }

    out_path = Path("semantic_data.json")
    out_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    print(f"\n작성 완료: {out_path.resolve()} ({out_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
