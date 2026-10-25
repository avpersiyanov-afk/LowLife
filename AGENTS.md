# AGENTS.md

Instructions for Codex (ChatGPT) and other agents that read `AGENTS.md`.

## Project rules

The full project guide is [CLAUDE.md](CLAUDE.md) — read it completely before any change and follow it
exactly as if it were written here (it is named for Claude Code, but every rule applies to any agent:
repo layout, Python 2/3 compatibility shims, i18n, settings plumbing, icons, tests, never committing real
parameter names). Tests: `python -m pytest tests` (see `tests/README.md`).

## Handoff between agents

The user switches between Claude Code and Codex when one of them runs out of limits, and continues the
same task in the other. The shared state lives in `HANDOFF.local.md` at the repo root (gitignored via
`*.local.md`, never commit it).

- **At the start of a session** — if `HANDOFF.local.md` exists, read it, run `git status` / `git diff`,
  and continue from «Следующий шаг». Don't redo what «Сделано» lists.
- **When the user says «передай», «handoff», «сохрани состояние»** (or the limit is near) — rewrite
  `HANDOFF.local.md` by the template below: concise, concrete file paths, what is verified and how,
  what is not. Uncommitted work stays in the working tree; don't commit just to hand off.

```markdown
# Handoff — <date time>, from <Claude|Codex>
## Задача
<what the user asked, in their words>
## Сделано
- <change> — <file> (проверено: <tests / Revit / only read>)
## Не сделано / следующий шаг
1. <next concrete step>
## Решения и договорённости
- <choices the user made, things not to do>
## Ветка и коммиты
<branch, committed or not, PR>
```

## Git workflow

Work on a branch, never commit to `main` directly. When the user asks to commit/push: commit, push the
branch, open a PR with `gh pr create` and merge it into `main` (`gh pr merge --merge`). Commit messages are
in Russian, like the existing history.

## Revit

Code can be run in the user's Revit 2024 through the Revit MCP servers when connected (see «Deploying/testing
a change» in CLAUDE.md). If Revit isn't reachable, say that the change was verified only by reading the code.
