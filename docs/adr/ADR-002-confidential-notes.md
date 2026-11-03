# ADR-002 – Confidential notes

- **Status:** Accepted (template default: edit it to match your own situation)
- **Date:** <YYYY-MM-DD>

## Context

Claude Code is a cloud service: every file the agent reads is sent to the model. Some notes (work, clients, health, finances) must not leave your computer. A line in `CLAUDE.md` is an instruction, not an access control, so the rule needs a technical layer.

## Decision

1. **Where.** Confidential notes live in `projects/_private/`. The folder is in `.gitignore`, so it never reaches a remote.
2. **Level of detail.** Even there, write only high-level state: goal, phase, next steps. No client names, data, code or credentials. Details stay in the systems they came from.
3. **Technical block.** `.claude/settings.json` has `deny` rules for reading and editing `projects/_private/`, one for the file tools and one for Bash, because the first alone does not stop `cat`. The rules use the path forms the Claude Code documentation requires (`//` for absolute, `~/` for home).
4. **Know the limit.** Deny rules are applied by Claude Code, not by the model, but they are best-effort: `grep -r`, scripts that open files themselves, and other tools can bypass them. For a real block, use the Claude Code sandbox or keep the folder outside the working directory of the agent.
5. **Transcripts.** Anything the agent has read once stays in the session transcript under `~/.claude/projects/` (30 days by default) and in the prompt already sent. Do not open confidential files in a session "just to look".
6. **Local models.** Notes that may be read by a local model (Ollama) never leave the machine; say so explicitly if you allow it.

## Consequences

- The agent cannot answer "where am I with project X?" for confidential projects. You write those states by hand.
- `scripts/verify` must not contain client details.
- If your employer's policy allows cloud AI on this material, write a new ADR that supersedes this one and then remove the `deny` rules.

## Action items

- [ ] Check what your employer or clients allow, and record the answer and date in a new ADR.
- [ ] Review the `deny` rules in `.claude/settings.json` after any Claude Code update.
