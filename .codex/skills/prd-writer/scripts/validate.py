#!/usr/bin/env python3
"""PRD 산출물 자가검증. 통과(0)/실패(1) 반환."""
import re, sys, pathlib

REQUIRED_SECTIONS = [
    "개요", "사용자 및 환경", "사용자 스토리",
    "기능 요구사항", "비기능 요구사항", "범위 외",
]

ID_PATTERNS = {
    "US-## 형식의 사용자 스토리 ID": r"\bUS-\d{2,}\b",
    "F-## 형식의 기능 요구사항 ID": r"\bF-\d{2,}\b",
    "NF-## 형식의 비기능 요구사항 ID": r"\bNF-\d{2,}\b",
}

def check(path: str):
    text = pathlib.Path(path).read_text(encoding="utf-8")
    problems = []

    # 1) 필수 H2 섹션 존재
    for sec in REQUIRED_SECTIONS:
        if not re.search(rf"^##\s.*{re.escape(sec)}", text, re.MULTILINE):
            problems.append(f"누락 섹션: {sec}")

    # 2) 요구사항 ID 형식
    for label, pat in ID_PATTERNS.items():
        if not re.search(pat, text):
            problems.append(f"{label}가 없음")

    # 3) 남은 자리표시자
    for ph in ["[제품/기능명]", "[시스템명]", "TODO", "작성 예정"]:
        if ph in text:
            problems.append(f"미완성 자리표시자 남음: {ph}")

    # 4) 모호어 경고(차단 아님, 검토 유도)
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
