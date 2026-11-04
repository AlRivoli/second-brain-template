# Getting started (about 15 minutes)

Italian version: [INIZIA.md](INIZIA.md). Each step says what you should see. If you see something else, stop and run `python3 doctor.py`.

On Windows write `py -3` where this guide says `python3`.

## 1. Install Claude Code

macOS, Linux or WSL: `curl -fsSL https://claude.ai/install.sh | bash`. Windows PowerShell: `irm https://claude.ai/install.ps1 | iex`. You need a paid Claude plan.
You should see: `claude --version` prints a version number.

## 2. Get the template

`git clone https://github.com/FabriGinseng/second-brain-template.git my-second-brain`, then `cd my-second-brain`. You can open the folder as a vault in Obsidian.
You should see: `CLAUDE.md`, `projects/`, `scripts/` in the folder.

## 3. Run the setup wizard

`python3 setup.py`. It asks your name, your role and the language, then offers the optional modules one at a time: a confidential folder (with a name you choose), the news radar, weekly post drafts, the services page, the assistant with a calendar, and repo tracking. The README describes each one. `python3 setup.py --list` shows the modules; `python3 setup.py --add <module>` adds one later. Before it writes anything it shows a summary and waits for your yes. After that it checks your computer (RAM, disk) and, step by step, offers to install what your choices need, download the local models that fit, and set up the secret scan and the Claude usage bar; it asks before each one and shows the command.
You should see: `config.json`, `memory/about-me.md`, `memory/preferences.md`, `memory/radar-topics.md` and `memory/feeds.md` (only if you chose the radar) written, and the confidential folder if you chose it. Nothing is overwritten if it already exists.

## 4. Check the prerequisites

`python3 doctor.py`.
You should see: `OK` next to Python, git, Claude Code and the vault rules. Ollama, a browser and gitleaks are optional; for each one that is missing you get the install command for your system.

## 5. Open the dashboard

`python3 scripts/dashboard/server.py`, then open http://127.0.0.1:8765.
You should see: a page with the example project. Press Ctrl+C in the terminal to stop it. On Linux and Windows the calendar and the job buttons stay empty.

## 6. Create your first project

In the folder, start `claude` and type `/nuovo-progetto my-first-project`, then fill its `projects/my-first-project/STATE.md` (goal, where you are, next three steps).
You should see: a new folder and a row in `projects/INDEX.md`. Then `python3 scripts/verify` prints `OK`.

## 7. Close the day

In `claude`, type `/chiudi-giornata`. The agent rewrites the STATE files from your commits, runs `scripts/verify` and commits locally. It never pushes.
You should see: one new local commit.

## 8. Remove the example

`python3 setup.py --clean-example` removes `projects/example-project` and its row in the index.

## Scheduled jobs

`python3 install_jobs.py --dry-run` shows what would be registered with your system's scheduler (launchd, systemd or Task Scheduler) and writes nothing. If it looks right, run it without `--dry-run`. You should see each job listed with the commands it ran. On Linux, run `loginctl enable-linger $USER` once so the timers also run when you are not logged in. `python3 install_jobs.py --uninstall` removes them. The radar (and its feed collector) and the weekly drafts are optional: the radar jobs are registered if you chose that module in `setup.py`, the others with `--all`.

## Uninstall

Delete the folder. Claude Code and Ollama have their own uninstall guides.
