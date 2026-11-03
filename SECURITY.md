# Security and privacy

## If personal data ended up in this repository

Open a private security advisory on GitHub (Security tab, "Report a vulnerability"), or an issue that does **not** repeat the data: name the file and the line, not the content. Anything already pushed must be considered public: rotate secrets first, then remove the data.

## What this template does and does not protect

- It never contains the author's notes, memory files or confidential folder: the public repository is generated from an allow-list and checked against a deny-list.
- The checks find literal matches only. A paraphrase, a nickname or a client name written in another way can slip through. Read the diff before you publish your own fork.
- Claude Code sends the files it reads to the model. `.claude/settings.json` blocks `projects/_private/`, but the block is best-effort: read [ADR-002](docs/adr/ADR-002-confidential-notes.md).
