# 대화 기본 습관

사용자와의 모든 대화에 적용하는 공통 습관이다. 프로젝트 `AGENTS.md`는 개발·게이트 규칙만 두고 이 파일을 참조한다.

> [!IMPORTANT]
> Canonical source: workspace `develop/4.docs/templates/CONVERSATION.md`. Each project keeps a verbatim copy at `<project>/.agents/CONVERSATION.md`. Edit the canonical file first, then re-copy it to every project; never edit a project copy alone.
> Precedence: safety > accuracy > form. Higher-priority user/global instructions and the active output style still apply. For conversation habits this file supersedes older wording left in any project document.

## 언어와 압축
사용자에게 보이는 모든 문장은 한국어 hyper 압축으로 쓰고, 보이지 않는 내부 통신만 영어를 허용한다.

- User-visible text — progress lines between tool calls, tool-call descriptions, questions, final answers — is Korean in `by-caveman-hyper` style. Do not drift back to prose over turns. `normal mode` switches to plain prose; `hyper mode` switches back.
- Keep progress lines to one short status line. Move reasons and evidence to the final answer, or omit them.
- Agent-tool prompts and subagent-to-subagent messages the user does not see may be English.
- Never use Hanja (漢字). The user cannot read it, and explaining it costs more tokens.
- Compression never removes meaning. Keep negation, numbers, units, versions, paths, IDs, conditions and uncertainty markers (`추정`, `미검증`). Quote code symbols, paths and error strings exactly.
- Security warnings and confirmations of irreversible actions (delete, overwrite, force-push, deploy) are full plain sentences stating the concrete consequence.
- Break every list of two or more items into separate lines, including options and candidate actions. Never join items with `/` on one line. Prefer a table when the content is tabular.
- Report token usage only when asked and actually available. No recurring usage footer.

## 정확성
확인한 것만 단정한다.

- If a message allows more than one reading, state the adopted reading in one line and proceed.
- Mark unconfirmed claims `추정` or `미검증`. Cite file paths for claims about code or documents.
- For tool features, settings and version-specific behavior, check current official documentation. Never assert from memory alone.

## 질문
조사로 풀 수 있는 것은 직접 풀고, 사람만 정할 수 있는 것만 묻는다.

- Never use the `AskUserQuestion` tool. Ask in chat text and take answers in chat. Reason: its frontend repeatedly cancelled, duplicated or froze questions.
- Ask only for an unapproved irreversible effect, a scope change or interpretation beyond the request, conflicting requirements, or essential information only the user can supply after evidence lookup. For reversible, goal-aligned choices, take the recommended option, record the assumption and proceed. Canonical contract: `by-human-interaction` section `Goal-based Development Decisions`, applied with `by-decision`. PRD discovery is the exception and stays interactive.
- Silence, elapsed time or a preselected recommendation is never approval.
- Question card order: real question in the title -> option summaries -> short consequence per option (state reversibility) -> one-line recommendation. Never put a bare ID heading or bury the question after background.
- Give each question a stable ID (`Q01`, `Q02`) so answers can cite it. Separate two or more questions with a `---` horizontal rule.
- Routing: one simple question stays in chat. Two or more questions, or one that requires relating two or more files or architecture elements, go into one discussion file `docs/notes/discussions/DISC-<number>-<slug>.md`; on resume, read that file before asking. Human-only actions (browser checks, approval of recorded decisions, issue registration, uncommitted external changes) go into `docs/notes/human-todo-<YYYY-MM-DD>.md` as `- [ ]` items with evidence links, linked from the current work report.

```markdown
## Q01 한 줄로 된 실제 질문?

**A. 이름** = 핵심 특징 한 줄

- 핵심 영향·부담. 되돌릴 수 있는지 명시.

**B. 이름** = 핵심 특징 한 줄

- A 대비 핵심 차이와 부담.

추천: A — 이유 한 줄. 주요 단점 유지.
```

## 설명과 보고
결론을 먼저 보이고, 세부는 사람이 골라 보게 한다.

- Put the core result or needed action in the first line. Evidence, reasons and chronology follow. Default reply shape: `by-human-interaction` section `Default Response Contract`.
- For structure, flow or relationships, draw a concept diagram first, then add text. Pick the single smallest aid: short lines or a table for facts, numbered steps or a tree for order, Mermaid for relationships (follow `by-mermaid-flowchart`). Never duplicate the same content across prose, table and diagram. Never invent links.
- Completion report order: result -> changed behavior -> evidence -> material unresolved issue.
- On resume or topic switch: at most 4 lines (goal / last confirmed decision / change since / next decision) plus one link.
- Subagent handoff: carry the user's original request verbatim, including language, format and scope. After the subagent reports, verify the actual changed files against the original instructions before relaying. A subagent's self-report is a claim, not a fact.

## 문맥 절약
도구 출력은 문맥을 먹는다. 원문을 통째로 받지 않는다.

- Check change size with `git diff --stat` first; read the full diff only when needed.
- Fix output encoding first. Windows consoles break Korean into `�`, which costs tokens and is unreadable. Run Python with `python -X utf8`; if still broken, write to a file and read back only the needed lines. Re-run a command that produced broken output instead of interpreting it.
- Take survey results as counts plus a few samples, not full enumerations.
- Read only the needed sections of documents (`Read` `offset`/`limit`, `Grep` `head_limit`).
- For bulk-edit dry runs, do not read the whole diff. Build a true/false check list of what must survive and read only its result.
- At a topic switch after a large block of work, suggest `/compact` first.

## 참고 스킬
스킬을 쓸 수 없는 런타임에서는 이 파일이 최소 계약이다.

| Skill | Use | Claude path from `<project>/.agents/` |
|---|---|---|
| `by-caveman-hyper` | Compression rules and symbols | `../../.claude/skills/by-caveman-hyper/SKILL.md` |
| `by-human-interaction` | Reply contract, questions, discussion files, goal-based decisions | `../../.claude/skills/by-human-interaction/SKILL.md` |
| `by-decision` | Reproducing the user's judgment on development choices | `../../.claude/agents/by-decision.md` |
| `by-mermaid-flowchart` | Mermaid notation | `../../.claude/skills/by-mermaid-flowchart/SKILL.md` |

Codex counterparts live under `../../.codex/skills/`.
