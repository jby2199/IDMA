# 공통 대화패턴 진입점
대화 규칙은 워크스페이스의 by-human-interaction 스킬과 공통 참조 문서에서 읽는다.

Before responding, read and apply the skill and its common conversation reference for the active runtime:

- Claude: [skill](../../.claude/skills/by-human-interaction/SKILL.md), [conversation reference](../../.claude/skills/by-human-interaction/references/CONVERSATION.md).
- Codex: [skill](../../.codex/skills/by-human-interaction/SKILL.md), [conversation reference](../../.codex/skills/by-human-interaction/references/CONVERSATION.md).
- Other runtimes: read the Claude source files as plain Markdown instructions.

This routing file replaces the former copied rule body. The Claude reference is canonical; keep its Codex mirror synchronized. Do not maintain separate conversation rules here. If the parent workspace is unavailable, report the missing reference; do not claim it was read. Follow explicit user and higher-priority instructions.
