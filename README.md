# second-brain-template

A starter kit for a personal "second brain": an Obsidian vault of plain Markdown, kept up to date by an AI coding agent ([Claude Code](https://claude.com/claude-code)) under rules you control. Italian version: [README.it.md](README.it.md).

> **Status: v0.1.** The vault structure, the setup wizard, the checks and the local dashboard work. Scheduled jobs are generated for macOS, Linux and Windows. Used daily on macOS. On Linux and Windows the automated tests pass in CI, but nobody has used the installer there for real yet: see "Platform support".

## What you get

- **Projects**: one short `STATE.md` per project, rewritten (never appended), a dated `decisions.md`, and a row in `projects/INDEX.md`.
- **Rules the agent follows**: a short `CLAUDE.md`, decisions in `docs/adr/` (confidential notes, autonomy level), a glossary.
- **Permissions that back the rules**: `.claude/settings.json` blocks push, force-push, history rewrites and the confidential folder.
- **A check**: `scripts/verify` verifies the vault rules. No model, files only.
- **Commands and subagents** in `.claude/`: `/nuovo-progetto`, `/morning`, `/chiudi-giornata`, `/weekly-review`, `/post`, `/bozze-settimana`, `/commit-push-pr`, and the subagents researcher, reviewer and writer. The command texts are in Italian in v0.1.
- **A local dashboard** (Python standard library, `127.0.0.1` only): projects, plan, radar, services and limits, posts.
- **`setup.py` and `doctor.py`**: a first-run wizard and a prerequisites check.

## Requirements

Python 3.9+, git, [Claude Code](https://code.claude.com/docs/en/setup) with a paid Claude plan (the free plan does not include it). Optional: [Ollama](https://ollama.com) for the local radar filter, Chrome, Chromium or Edge for the post images.

## Quick start

```
git clone <this repository> my-second-brain
cd my-second-brain
python3 setup.py        # Windows: py -3 setup.py
python3 doctor.py       # tells you what is missing and how to install it
python3 scripts/verify  # prints OK
```

Then follow [GETTING_STARTED.md](GETTING_STARTED.md): about 15 minutes, each step says what you should see.

## Scheduled jobs

`scripts/jobs.json` defines the jobs once; `python3 install_jobs.py` registers them with the scheduler of your system: launchd on macOS, systemd user timers on Linux, Task Scheduler on Windows. Start with `python3 install_jobs.py --dry-run` to read what it would do. Each job is safe to start twice, so catching up after the computer was off is harmless. The jobs, by name (the ones marked optional need `--all`):

| Job | When | What it does |
|---|---|---|
| `second-brain.morning` | weekdays 08:00 and at login (macOS only for now) | the morning start: closes pending work, creates the daily note |
| `second-brain.chiusura` | weekdays 18:30 | `/chiudi-giornata`: rewrites the STATE files from your commits |
| `second-brain.pulizia` | Friday 18:00 | weekly check and report |
| `second-brain.dashboard` | at login, kept running | the local dashboard |
| `second-brain.radar` (optional) | Monday 07:30 | filters the news in `inbox/` for your projects (needs Ollama) |
| `second-brain.bozze` (optional) | Monday 08:30 | `/bozze-settimana`: three post drafts |

## Platform support

| Part | macOS | Linux | Windows |
|---|---|---|---|
| Vault, `scripts/verify`, `setup.py`, `doctor.py` | yes | CI tests pass | CI tests pass |
| Dashboard | yes | partly (no calendar, no job buttons) | partly |
| Calendar in "Today" | yes (Calendar app) | no | no |
| Scheduled jobs (`install_jobs.py`) | yes | files generated and tested, not registered for real yet | same |

On Windows, WSL 2 is the safer path for Claude Code until native Windows is tested.

## Privacy

Claude Code sends the files it reads to the model. Put confidential notes in `projects/_private/` (ignored by git and blocked by `deny` rules) and read [ADR-002](docs/adr/ADR-002-confidential-notes.md) for the limits of that block. Your name, notes and memory files stay in your copy: `setup.py` writes them from the `*.example.md` files and git ignores them.

## Licence

MIT, see `LICENSE`. To report personal data that ended up here by mistake, see `SECURITY.md`.
