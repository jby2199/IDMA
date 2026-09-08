# claude/agent

## 도구의 목적/목표
### 목적
- <<프로젝트/프로그램의 목적을 기재한다>>

### 목표
- <<프로젝트/프로그램의 목표를 기재한다>>


---
## 범용 목표
- 이 프로젝트로 만들어지는 결과물간의 추적성, 일관성, 정확성 확인이 통과되어야 한다.
- PRD: 사용자 요구사항이 PRD 에 모순없이 담겨야 한다.
- SRS: PRD에 기반하여 소프트웨어 요구사항이 SRS에 누락없이 정제되어야 한다.
- SDD: 설계/구현 요구사항이 SDD 에 추적되고 일관성있게 작성되어야 한다.

## 범용 지시사항
1. 구현 정확성을 높이기 위해, 계획과 파악을 먼저 한다.
2. 최초 개발 프로세스는 PRD 완성 --> SRS 완성 --> SDD 완성 흐름으로 각 선행 산출물이 완성되면 후속 산출물을 시작한다.
3. 계획 과정에는
    - 모순되는 사항은 사용자에게 확인받는다.
    - 모호한 사항은 사용자에게 물어본다.
4. 소프트웨어 수정이 필요한 경우
    - 먼저 PRD/SRS/SDD 를 분석/수정한다.
    - karpathy-guidelines 을 사용한다. 다른 유용한 skill도 같이 활용한다.

## 언어 정책
도구 호출 사이 서술은 영문 caveman, 최종 답변은 한글.

- **Tool-call narration** (progress lines like "checking…", "done…") and **Agent-tool prompts / inter-subagent communication** use caveman **ultra English**. Prefix each such line with a short `[bracketed]` Korean gloss of the action, so a Korean-speaking user can tell what's happening at a glance.
- **Final user-facing replies** (summaries, conclusions, questions) are written in Korean.

## 대화 중 지켜야 할 것 — 언제나 적용
1. `AskUserQuestion` is disabled. Resolve ambiguity by asking directly in chat — never invoke that tool.
2. Check change size with `git diff --stat` first; read the full diff only when needed.

## Skill/Agent 참고
- ADR 작성 여부 판단·형식 → `by-adr-writer` 스킬
- 문서 작성 지원 → `by-prd-writer`, `by-srs-writer` 스킬
- 순서도/구조도 작성 → `by-mermaid-flowchart` 스킬
- 서브에이전트 델리게이션 판단 → `cavecrew` 스킬
- 설계/구현 리뷰 → `.claude/agents/code-reviewer`, `.claude/agents/implementer`
- 기존 설계/코드 조사 → `.claude/agents/design-reader`
- SRS/SDD 저작 → `.claude/agents/ieee-830-srs-author`, `.claude/agents/ieee-1016-sdd-author`
- 단계별 V&V → `.claude/agents/ieee-1012-sil4-vv-expert`

## 소규모 변경 — 문서 단계 생략 판단
문서에 남길 내용이 없으면 `docs` 를 건너뛰고 바로 구현한다. 어느 경로로 갈지 묻지 않는다.

기능 추가·수정 요청을 받으면 먼저 하나만 판단한다 — **나중에 이 코드가 왜 이렇게 됐는지
SDD 를 봐서 알아야 하는가.**

- 아니다 (버튼 문구, 로그 포맷, 오타, 국소 리팩터, 상수값 조정) -> `docs` 를 건너뛰고
  구현 + 테스트만 한다. 사용자에게 경로를 묻지 않는다.
- 그렇다 (새 입력 경로, 상태·모드 추가, 외부 인터페이스 변경, 데이터 스키마 변경) ->
  `docs` 단계부터 정상 진행한다 (PRD -> SRS -> SDD -> V&V -> `gate.ps1 docs`).
- 판단이 애매할 때만 사용자에게 묻는다.

게이트는 이 생략을 이미 허용한다. `docs/` 를 건드리지 않으면 `impl` 게이트의 요건
무단변경 검사(`Test-UpstreamDrift`)가 발동하지 않고, SDD-코드 매핑 검사도
`SDD -> 코드` 단방향이라 SDD 에 없는 새 코드는 잡지 않는다. 따로 예외 규칙을 두지 않는다.

**테스트는 생략 대상이 아니다.** `impl` 게이트는 실작업 테스트가 0 건이면 FAIL 이고,
있으면 전부 통과해야 한다. 문서를 건너뛴 변경에도 테스트는 붙인다.

