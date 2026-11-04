# Glossary

Domain terms, no implementation details. Add a term when you notice you and the agent use the same word for different things.

- **Vault**: the single Markdown folder (Obsidian + Git) that holds memory, projects, daily notes, radar and inbox.
- **Private area**: the `projects/_private/` folder. High-level notes only, never sent to a cloud model, ignored by git. The level of detail is set by ADR-002.
- **State (STATE.md)**: one short file per project (under about 20 lines) that says goal, where you are, next three steps, blockers. Rewritten, never appended.
- **Decisions (decisions.md)**: the dated log of what is no longer current in a STATE.
- **Index (projects/INDEX.md)**: one row per project, with the date of its last update.
- **Deterministic step**: a step that can be written as a fixed rule (fetch a feed, deduplicate, apply a threshold). It lives in a script.
- **Judgement step**: a step that needs reading and reasoning (summarise, link to a project, choose an action). It lives in a model, local or cloud.
- **Unattended session**: a run with nobody in front of it to confirm, like a scheduled morning brief. Actions that need confirmation are not executed there.
- **Autonomous action**: something the agent does alone, like writing in the vault or making a local commit.
- **Action with confirmation**: something that needs your explicit approval in an attended session, like a push or a publication.
- **Forbidden action**: something the agent never does, like a force-push.
- **Subagent**: a specialised agent started by the main session for one task, with limited read and write paths.
- **Verify (scripts/verify)**: the script that checks the vault rules (STATE length, INDEX consistency, valid links, README cites the commands). It reads files only and uses no model.
