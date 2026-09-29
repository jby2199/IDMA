# 노트 배치·읽는 순서
범위별 notes 안에서 LLM 작업·진행보고·사람 할 일·참고자료를 구분한다.

```text
notes/
├─ LLM작업/진행중/       실행 상세·조사·초안·인계
├─ LLM작업/종료/         종료 근거 있는 작업 기록
├─ 진행보고/현재/        사람에게 알릴 계획·진척·결과
├─ 진행보고/이력/        지난 회차 보고
├─ 사람할일/대기중/      질문·결정·승인·실사용 확인
├─ 사람할일/종료/        답변·조치가 끝난 기록
└─ 참고자료/             다시 쓰는 지식·설명·규약·양식
```

## 위치 선택
모든 프로젝트 노트는 단계와 무관하게 docs/notes 한 곳에 둔다.

- Use only `docs/notes/` for every project note, including single-stage work. Do not create notes folders inside stages 1-5.
- Keep the role/state structure under that single project notes root. Use workspace `4.docs/notes/` for non-project and shared-workspace notes.
- Keep formal PRD/SRS/SAD/SDD/ADR, gate files, issue records and V&V reports in their canonical locations. Notes do not replace them.
- Prepare the seven leaf folders shown above. Preserve empty leaves with `.gitkeep`; create additional subject folders only when used.

## 역할과 원본
사람은 진행보고에서 상황을 읽고, 사람할일에서 행동한다. 상세 실행은 LLM작업에 둔다.

- `LLM작업`: agent execution details, investigations, drafts and handover. This is an audience convention, not access control.
- `진행보고`: concise human-readable planned actions, progress, results and blockers. Link to task evidence and any required human action.
- `사람할일`: actual human questions, choices, approvals and checks. Use `DISC-<number>-<slug>.md` for discussions and `human-todo-<date>.md` for action lists in the appropriate scope's `사람할일/대기중/`.
- `참고자료`: reusable explanations, observations, conventions and examples for either audience. Record the source/date and known limitations. Put superseded material in `이전/` with a replacement link.
- Maintain one authoritative body for each task, decision or checklist. For mixed notes, keep the original by its main purpose; expose short actionable links from the other role folders. Split independently managed long questions/tasks when needed, without duplicating their full bodies.
- Keep a subject's raw evidence and attachments together under its task or reference folder. Preserve frozen evidence bytes. Link human reports to that bundle.

## 진행·종료
보류·미확인은 종료하지 않는다. 논의 종료와 후속 구현 종료를 별도로 관리한다.

- Mark deferred items as `보류` with a reason and resumption condition, and unverified legacy status as `현재 상태 재확인 필요`. Keep them in the open folder; distinguish them from immediate actions in its index.
- Move a discussion to `사람할일/종료/` when its question is answered; link any outstanding implementation or validation to the relevant open task. Do not claim those tasks are complete.
- Move a task to `LLM작업/종료/` only with closure evidence. Record date, outcome and follow-up links. Label cancelled/superseded work explicitly rather than calling it successful.
- Move past reports to `진행보고/이력/`; a finished report is not proof that its findings were fixed. Current cumulative reports must label historical sections and link live work separately.
- Update inbound/outbound links, AGENTS/skill entry points and producer/consumer paths together with file moves. Keep a source-to-destination record. Never infer completion from age or filename.
- This contract supersedes older generic `notes/discussions/`, `notes/discussion-done/`, flat `human-todo` and flat `Orch-Rpt` output-location defaults. Historical paths in immutable raw evidence remain historical data.
