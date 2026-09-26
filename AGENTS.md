# IDMA — 입력문서관리기

## 목적
유입 파일을 파일명 기반으로 자동 분류(Rule 우선, AI 보조)해 Phase 폴더에 배치하고, 제출물 관리대장을 자동 갱신한다.

## 목표
- `source_root` 유입 파일을 Rule Engine(abbr/full_name 매칭)으로 1차 분류하고, 실패 시 AI 보조 분류로 Phase를 판정한다.
- 분류 성공 파일은 Phase 폴더로, 실패 파일은 `project_root`에 폴백 배치한다(원본 파일명 유지, 덮어쓰기 금지).
- 분류 결과(방식·근거·최종 경로·상태)를 관리대장(xlsx)에 기록하고, 로컬 Python UI로 운영 설정(threshold·경로 등)을 편집한다.

@.agents/CONVERSATION.md

## 항상 지킬 것
1. Deliverables (PRD, SRS, SDD, code) must pass traceability, consistency and accuracy checks against each other: PRD holds user requirements without contradiction, SRS refines PRD without omission, SDD traces SRS consistently.
2. Plan and investigate before implementing. Initial development runs PRD -> SRS -> SDD; start each only after its predecessor is complete.
3. Before changing software, analyze and update PRD/SRS/SDD first, and apply `karpathy-guidelines`.

## 상황별 참조
| Situation | Read |
|---|---|
| Feature add/change request; `docs`/`impl`/`vv` stage work | `by-stage-rules` skill ([SKILL.md](../.claude/skills/by-stage-rules/SKILL.md)). Tests are never skipped. |
| ADR need and format | `by-adr-writer` |
| PRD/SRS writing | `by-prd-writer`, `by-srs-writer` |
| Flowcharts and structure diagrams | `by-mermaid-flowchart` |
| Delegating authoring/implementation/review | agents `ieee-830-srs-author` (SRS), `ieee-1016-sdd-author` (SDD), `implementer`, `code-reviewer`, `design-reader`, `ieee-1012-sil4-vv-expert` |
