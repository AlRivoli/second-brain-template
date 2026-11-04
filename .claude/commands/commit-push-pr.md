---
description: Commit, push del ramo e apertura della PR per un repo di codice, con conferma prima del push
---

Porta le modifiche del repo corrente in una PR. Scrivi in italiano.

1. **Controlli preliminari.**
   - Il ramo corrente non deve essere `main`. Se lo è, fermati e proponi un nome di ramo.
   - Deve esistere un remoto (`git remote -v`). Se manca, fermati e dillo.
   - Se ci sono modifiche non committate, leggile prima di committare. Non includere file sospetti come `.env` o chiavi.
2. **Commit locale.** Crea il commit con un messaggio convenzionale (`feat:`, `fix:`, `chore:`, `docs:`) e la riga `Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>`.
3. **Riepilogo.** Mostra ramo, commit, file coinvolti e remoto. Poi termina.
4. **Push e PR solo con un sì nel messaggio.** Fai `git push -u origin <ramo>` e `gh pr create` **solo se il messaggio dell'utente in questa sessione contiene un sì esplicito al push** (per esempio "sì, pusha"). Un sì dato prima, per un'altra richiesta, non vale. Senza questo sì non fare nessuna delle due cose, nemmeno in parte: fermati al riepilogo.
   Il corpo della PR termina con la riga `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

Non fare push su `main` in nessun caso.
