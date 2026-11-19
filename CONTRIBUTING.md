# Contributing

Thanks for helping. Two rules before anything else:

1. **No personal data in issues or pull requests**: no real names, e-mail addresses, paths under your home folder, notes from your vault, or logs that contain them. Describe the problem with made-up data.
2. **Run the checks** before you open a pull request: `python3 scripts/check` (on Windows `py -3 scripts/check`) must end with `check: OK`. It needs ruff and gitleaks; `python3 doctor.py` shows how to install them.

Small changes are easiest to review: one subject per pull request, with the reason in the description.
