# ADR-004 – Autonomy level

- **Status:** Accepted (template default: edit it to match how much you trust the agent)
- **Date:** <YYYY-MM-DD>

## Context

The agent works in two ways. Attended: an interactive session where you can answer. Unattended: `claude -p` started by a scheduled job, with nobody in front of it. We need to decide what it does alone, what needs your confirmation, and what it never does.

## Decision

1. **Three levels of action.**
   - **Autonomous:** write inside the vault, create new files in `inbox/`, `radar/`, `daily/`, `projects/`, make local commits.
   - **With confirmation:** push, email, publishing anything, deleting files, changing `docs/adr/`, `CLAUDE.md`, `memory/`, adding an MCP server.
   - **Never:** force-push, `git reset --hard`, rewriting history.
2. **Unattended runs.** The autonomous set is the same. An action that needs confirmation is not executed: it goes in a "To confirm" section of `daily/YYYY-MM-DD.md`, with what would be done, why, and the command to confirm it. Unattended runs start with `--permission-mode dontAsk`, so anything that would prompt is denied explicitly.
3. **Enforcement.** `deny` rules in `.claude/settings.json` for push, force-push, `reset --hard` and deletions, plus one line in `CLAUDE.md`. These are a **guardrail, not a boundary**: a deny rule on Bash can be bypassed (`git -C . push`, `sh -c '...'`). If the repo gets a shared remote, add a `PreToolUse` hook that inspects the full command.
4. **Commits.** The agent commits locally only after `scripts/verify` passes, one commit per routine. It never pushes.
5. **Retry loop.** At most three attempts. If `scripts/verify` still fails, the changes stay uncommitted and the problem goes in the next brief.
6. **Recurring errors.** The agent may add dated lines to the "Recurring errors" section of `CLAUDE.md` on its own. Any other change to `CLAUDE.md`, `memory/` and `docs/adr/` needs confirmation.
7. **Subagents.** Subagents do not start other subagents. This is only a convention unless you enforce it: omit `Agent` from the `tools` list of each agent file.

## Consequences

- The morning brief never blocks waiting for an answer.
- A mistake by the agent leaves at most local commits.
- Every routine produces at most one traceable commit.
