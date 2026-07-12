#!/usr/bin/env python3
"""SRS 산출물 자가검증. 통과(0)/실패(1) 반환."""
import re, sys, pathlib
from collections import Counter

REQUIRED_SECTIONS = [
    "개요", "범위", "정의 및 약어", "참조 문서", "전체 설명",
    "기능 요구사항", "비기능 요구사항", "인터페이스 요구사항", "제약사항", "부록",
]

def strip_comments(text: str) -> str:
    """HTML 주석(<!-- -->)을 제거. 템플릿 안내 예시가 검증을 거짓 통과/실패시키지 않도록."""
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

def check(path: str):
    raw = pathlib.Path(path).read_text(encoding="utf-8")
    text = strip_comments(raw)
    problems = []

    # 1) 필수 H2 섹션 존재
    for sec in REQUIRED_SECTIONS:
        if not re.search(rf"^##\s.*{re.escape(sec)}", text, re.MULTILINE):
            problems.append(f"누락 섹션: {sec}")

    # 2) 기능/비기능 요구사항 정의(대괄호 형식) 존재
    #    정의는 [FR-001] / [NFR-001] 처럼 대괄호. 대괄호 없는 FR-001 은 참조로 간주.
    if not re.search(r"\[FR-\d{3}\]", text):
        problems.append("[FR-###] 형식의 기능 요구사항 정의가 없음")
    if not re.search(r"\[NFR-\d{3}\]", text):
        problems.append("[NFR-###] 형식의 비기능 요구사항 정의가 없음")

    # 3) ID 정의 중복 (대괄호 정의만 집계; 대괄호 없는 참조는 몇 번이든 허용)
    defs = re.findall(r"\[((?:N?FR)-\d{3})\]", text)
    for rid, cnt in Counter(defs).items():
        if cnt > 1:
            problems.append(f"중복 정의 ID: [{rid}] ({cnt}회 정의)")

    # 4) 정의는 한 줄을 단독으로 차지하고, 요구사항 내용은 그 아랫줄부터
    lines = text.split("\n")
    for idx, line in enumerate(lines):
        if not re.search(r"\[(?:N?FR)-\d{3}\]", line):
            continue
        stripped = line.strip()
        if not re.fullmatch(r"\[(?:N?FR)-\d{3}\]", stripped):
            problems.append(f"ID 정의는 한 줄에 단독 표기해야 함: '{stripped}'")
            continue
        nxt = lines[idx + 1].strip() if idx + 1 < len(lines) else ""
        if not nxt or re.fullmatch(r"\[(?:N?FR)-\d{3}\]", nxt):
            problems.append(f"{stripped} 아래에 요구사항 내용이 없음")

    # 5) 빈 섹션 (H2 헤더 뒤에 실질 내용 없이 다음 H2/문서끝)
    sections = re.split(r"^(##\s.+)$", text, flags=re.MULTILINE)
    # split 결과: [앞부분, 헤더1, 본문1, 헤더2, 본문2, ...]
    for i in range(1, len(sections), 2):
        header = sections[i].strip()
        body = sections[i + 1].strip() if i + 1 < len(sections) else ""
        if not body:
            problems.append(f"빈 섹션: {header}")

    # 6) 남은 자리표시자
    for ph in ["[시스템명]", "TODO", "작성 예정"]:
        if ph in text:
            problems.append(f"미완성 자리표시자 남음: {ph}")

    # 7) 모호어 경고(차단 아님, 검토 유도)
    for vague in ["빠르게", "신속히", "충분히", "적절히"]:
        if vague in text:
            problems.append(f"⚠ 측정 불가 표현 점검 필요: '{vague}'")

    return problems

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: validate.py <파일경로>"); sys.exit(2)
    issues = check(sys.argv[1])
    if issues:
        print("❌ 검증 실패:")
        for i in issues: print("  -", i)
        sys.exit(1)
    print("✅ 모든 검증 통과"); sys.exit(0)
