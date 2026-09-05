"""
마크다운 문서 규칙 기반 청킹 스크립트

규칙:
1. ## 기준으로 먼저 분할
2. 분할한 텍스트 중 크기가 크면 ### 기준으로 재분할 (그래도 크면 #### 기준으로 재분할)
3. ### / #### 기준으로 분할한 경우, 청크 맨 앞에 상위 ## (혹은 ###) 제목 라인을
   붙여서 어떤 주제의 소제목인지 알 수 있도록 함
4. 표가 청크 경계에서 잘리는 경우, 뒤쪽 청크 앞부분에 표 헤더(헤더 행 + 구분선 행)를
   다시 추가하여 표의 맥락(컬럼 의미)을 잃지 않도록 함

사용법:
    python chunk_markdown.py --input-dir ../documents --output-dir . --max-chars 1000
"""

import argparse
import json
import re
from pathlib import Path

HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.*)$")
TABLE_ROW_RE = re.compile(r"^\|.*\|[ \t]*$")
TABLE_SEP_RE = re.compile(r"^\|[\s:\-|]+\|?$")


def split_by_level(text, level):
    """text를 지정한 heading level(정확히 그 레벨의 #) 기준으로 분할한다.

    반환값: (preamble, sections)
      - preamble: 해당 레벨의 첫 heading 이전의 텍스트
      - sections: [(title, section_text), ...]
        section_text 는 heading 라인부터 다음 동일 레벨 heading 직전까지
        (더 깊은 하위 heading 내용 포함, 원문 그대로)
    """
    lines = text.split("\n")
    heading_positions = []
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m and len(m.group(1)) == level:
            heading_positions.append((i, m.group(2).strip()))

    if not heading_positions:
        return text, []

    preamble = "\n".join(lines[: heading_positions[0][0]])
    sections = []
    for idx, (start, title) in enumerate(heading_positions):
        end = (
            heading_positions[idx + 1][0]
            if idx + 1 < len(heading_positions)
            else len(lines)
        )
        section_text = "\n".join(lines[start:end]).rstrip("\n")
        sections.append((title, section_text))
    return preamble, sections


def split_leaf(text, max_chars):
    """더 이상 나눌 heading이 없는 텍스트를 크기 기준으로 분할한다.

    - 빈 줄(문단 경계)을 우선적인 분할 지점으로 사용한다.
    - 표(| 로 시작하는 연속된 줄)는 절대 행 중간에서 자르지 않는다.
    - 표가 여러 청크로 나뉘게 되면, 이어지는 청크 앞에 표의 헤더 행 +
      구분선 행을 다시 삽입한다 (규칙 4).
    """
    lines = text.split("\n")
    n = len(lines)

    pieces = []
    current = []
    current_len = 0
    current_table_header = None  # (header_line, sep_line) : 현재 위치가 속한 표의 헤더

    def flush():
        nonlocal current, current_len
        if current:
            pieces.append("\n".join(current))
        current = []
        current_len = 0

    i = 0
    while i < n:
        line = lines[i]
        is_table_row = bool(TABLE_ROW_RE.match(line))
        prev_line = lines[i - 1] if i > 0 else ""
        prev_is_table_row = bool(TABLE_ROW_RE.match(prev_line))

        if is_table_row and not prev_is_table_row:
            # 새 표의 시작: 이 줄이 헤더, 다음 줄이 구분선인지 확인
            if i + 1 < n and TABLE_SEP_RE.match(lines[i + 1]):
                current_table_header = (line, lines[i + 1])
            else:
                current_table_header = None
        elif not is_table_row:
            current_table_header = None

        line_len = len(line) + 1  # 개행 포함 근사치

        if current and current_len + line_len > max_chars:
            flush()
            # 표 중간에서 잘렸다면 헤더를 이어지는 청크 앞에 재삽입 (규칙 4)
            if (
                is_table_row
                and current_table_header is not None
                and line not in current_table_header
            ):
                header_line, sep_line = current_table_header
                current.append(header_line)
                current.append(sep_line)
                current_len += len(header_line) + 1 + len(sep_line) + 1

        current.append(line)
        current_len += line_len
        i += 1

    flush()
    return [p for p in pieces if p.strip("\n")]


def with_context(text, ancestor_lines):
    """ancestor_lines(상위 heading 라인들)를 텍스트 앞에 붙인다."""
    if not ancestor_lines:
        return text
    return "\n".join(ancestor_lines) + "\n\n" + text


def chunk_section(section_text, level, ancestor_lines, max_chars):
    """레벨 `level`의 heading으로 시작하는 section_text를 청크 리스트로 변환한다.

    - 크기가 max_chars 이하이면 그대로 한 청크 (필요 시 상위 문맥만 덧붙임).
    - 크기가 크면 다음 레벨(level+1) heading 기준으로 재귀 분할한다 (규칙 2, 3).
    - level이 4(####)를 넘어서면 더 나눌 heading이 없으므로 leaf 분할(규칙 4)로 처리한다.
    """
    if len(section_text) <= max_chars:
        return [with_context(section_text, ancestor_lines)]

    if level >= 4:
        pieces = split_leaf(section_text, max_chars)
        return [with_context(p, ancestor_lines) for p in pieces]

    next_level = level + 1
    first_line, _, rest = section_text.partition("\n")
    own_preamble, sub_sections = split_by_level(rest, next_level)

    if not sub_sections:
        # 더 깊은 하위 heading이 없는데도 여전히 크다면 leaf 분할
        pieces = split_leaf(section_text, max_chars)
        return [with_context(p, ancestor_lines) for p in pieces]

    out = []
    new_ancestor_lines = ancestor_lines + [first_line]

    # 자기 heading 라인 + 첫 하위 heading 이전의 도입부
    preamble_full = first_line
    if own_preamble.strip("\n"):
        preamble_full += "\n" + own_preamble

    if len(preamble_full) <= max_chars:
        out.append(with_context(preamble_full, ancestor_lines))
    else:
        pieces = split_leaf(preamble_full, max_chars)
        out.extend(with_context(p, ancestor_lines) for p in pieces)

    for _, sub_text in sub_sections:
        out.extend(chunk_section(sub_text, next_level, new_ancestor_lines, max_chars))

    return out


def chunk_markdown(text, max_chars):
    chunks = []
    preamble, h2_sections = split_by_level(text, 2)

    if preamble.strip("\n"):
        if len(preamble) <= max_chars:
            chunks.append(preamble.strip("\n"))
        else:
            chunks.extend(p for p in split_leaf(preamble, max_chars))

    for _, h2_text in h2_sections:
        chunks.extend(chunk_section(h2_text, 2, [], max_chars))

    return [c.strip("\n") for c in chunks if c.strip("\n")]


def extract_heading_path(chunk_text):
    """청크 텍스트에서 heading 라인들을 뽑아 (레벨, 제목) 경로를 만든다 (manifest용)."""
    path = []
    for line in chunk_text.split("\n"):
        m = HEADING_RE.match(line)
        if m:
            path.append({"level": len(m.group(1)), "title": m.group(2).strip()})
    return path


def process_file(md_path: Path, output_root: Path, max_chars: int, manifest_rows: list):
    text = md_path.read_text(encoding="utf-8")
    chunks = chunk_markdown(text, max_chars)

    doc_dir = output_root / md_path.stem
    doc_dir.mkdir(parents=True, exist_ok=True)

    for idx, chunk_text in enumerate(chunks, start=1):
        out_path = doc_dir / f"chunk_{idx:04d}.md"
        out_path.write_text(chunk_text + "\n", encoding="utf-8")
        manifest_rows.append(
            {
                "source_file": md_path.name,
                "chunk_index": idx,
                "chunk_file": str(out_path.relative_to(output_root)).replace("\\", "/"),
                "char_count": len(chunk_text),
                "heading_path": extract_heading_path(chunk_text),
            }
        )

    print(f"[{md_path.name}] {len(chunks)}개 청크 생성 -> {doc_dir}")


def main():
    parser = argparse.ArgumentParser(description="마크다운 문서 규칙 기반 청킹")
    parser.add_argument("--input-dir", default="../documents", help="원본 .md 파일이 있는 폴더")
    parser.add_argument("--output-dir", default=".", help="청크 결과를 저장할 폴더 (기본: 이 스크립트 위치)")
    parser.add_argument("--max-chars", type=int, default=1000, help="청크 최대 문자 수")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    input_dir = (script_dir / args.input_dir).resolve() if not Path(args.input_dir).is_absolute() else Path(args.input_dir)
    output_dir = (script_dir / args.output_dir).resolve() if not Path(args.output_dir).is_absolute() else Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_rows = []
    md_files = sorted(input_dir.glob("*.md"))
    if not md_files:
        print(f"경고: {input_dir} 에 .md 파일이 없습니다.")
        return

    for md_path in md_files:
        process_file(md_path, output_dir, args.max_chars, manifest_rows)

    manifest_path = output_dir / "manifest.jsonl"
    with manifest_path.open("w", encoding="utf-8") as f:
        for row in manifest_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"manifest 저장: {manifest_path} (총 {len(manifest_rows)}개 청크)")


if __name__ == "__main__":
    main()
