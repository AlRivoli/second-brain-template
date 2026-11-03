# Changelog

All notable changes to this project are written here. The format follows [Keep a Changelog](https://keepachangelog.com/), versions follow [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-03

### Added
- Vault structure: projects with a rewritten `STATE.md`, decisions log, index, glossary, ADRs on confidential notes and autonomy.
- `.claude/settings.json` with deny rules for push, history rewrites and the confidential folder.
- `scripts/verify`: checks the vault rules without a model.
- `setup.py` (first-run wizard) and `doctor.py` (prerequisites per operating system).
- `install_jobs.py`: registers the scheduled jobs with launchd (macOS), systemd user timers (Linux) or Task Scheduler (Windows).
- Local dashboard (Python standard library, 127.0.0.1 only).
- Commands and subagents for Claude Code, in Italian.
- English and Italian documentation.

### Known limits
- Used daily on macOS only. On Linux and Windows the unit tests pass in CI (Python 3.9 and 3.13), but registering the jobs with systemd and Task Scheduler has not been done for real yet.
- The morning job opens the dashboard with a macOS command, so it is macOS only for now.
- The Calendar section of the dashboard needs the macOS Calendar app.
