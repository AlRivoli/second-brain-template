# ADR-013 – Learning loop: a corrected mistake becomes a rule or a check

- **Status:** Accepted (template default: edit the thresholds to match your own practice)
- **Date:** <YYYY-MM-DD>
- **Builds on:** [ADR-004](ADR-004-autonomy-level.md) (what needs a yes), [ADR-012](ADR-012-deterministic-rules-hook.md) (rules enforced by a hook)

## Context

When the agent gets something wrong, somebody corrects it and the session ends. Nothing is left behind, so the same correction comes back a few days later. Rules pile up the other way too: a rule added after one bad day stays forever, and nobody knows whether it still stops real mistakes or only gets in the way.

`CLAUDE.md` already had a "Recurring errors" section, but no procedure filled it and nothing read it.

## Decision

1. **Every corrected mistake leaves one dated line** in "Recurring errors" of `CLAUDE.md`: `- YYYY-MM-DD · what happened · causa: why · layer: nessuno | regola <file> | check <name>`. It describes the fact, never who. No secrets, no names, no client details. `scripts/verify` fails on a line without a date.
2. **Three steps, by repetition.** The first time a cause shows up it gets the line only. The second time it becomes a rule: a file in `.claude/rules/` with `paths`, or a line in `CLAUDE.md` when it applies everywhere. A rule that can be verified becomes a check (in `scripts/verify`, in the hook's rule list, in a test), with a message that says what to do. A mistake that is serious the first time (lost data, exposed secret) goes straight to a check.
3. **Who rereads, and when.** `/chiudi-giornata` looks at the day: the rules the hook enforced, a failed `scripts/verify`, the corrections in the conversation, and proposes one line per cause. `/weekly-review` looks at the week: it proposes a rule or a check for a cause that appears twice, and asks which of the hook's blocks were false positives.
4. **Nothing is written without a yes.** `CLAUDE.md`, `.claude/` and `docs/adr/` already need confirmation (ADR-004). In an unattended run the proposal goes to "Da confermare" in the day's `daily/` file and `CLAUDE.md` is left alone.
5. **The hook keeps a count, not a history.** For each refusal or request for confirmation, `.claude/hooks/regole.py` appends one line to `second-brain-regole.log` in the system log folder: the date, the name of the rule (the `id` in `regole.json`) and the action. The name comes from the rule list, never from the command, so the log cannot hold a command, an argument or a path. If the log cannot be written the decision does not change. `scripts/blocchi-regole.py` counts the lines; `scripts/ruota-log.py` rotates the file with the other logs.

## Trade-off

- The log says which rule fired, not why: telling a false positive from a real stop is still a human judgement, asked once a week.
- A rule without an `id` is logged as `regola-N`, its position in the list, which changes when the list is reordered. Give every rule an `id`.
- The evening job counts the blocks only when it already has something to do, so a day with blocks and no other activity is reread at the next close or at the weekly review.
- Anyone who can write files on the machine can add lines to the log. The counting script accepts only rule names made of lowercase letters, digits and hyphens and the two known actions, so a forged line cannot carry text into a prompt, but it can inflate a count.
