---
description: Brief del mattino: stato dei progetti, novità, priorità del giorno
---

Prepara il brief del mattino in `daily/` per oggi. Scrivi in italiano, breve: cinque o sette righe per progetto, come da `memory/preferences.md`.

1. **Stato dei progetti.** Leggi `projects/INDEX.md`, poi lo `STATE.md` di ogni progetto che l'indice elenca. Non leggere `decisions.md`.
2. **Novità.** Leggi `git log` dall'ultimo file in `daily/` (escluso quello di oggi). Leggi i file di `inbox/` e l'ultimo file di `radar/`. Non fare ricerche sul web: quello è compito del subagente `researcher`.
3. **Il file di oggi.** Se `daily/<oggi>.md` esiste già, aggiorna solo *Dove sei*, *Suggerimento di priorità* e *Dalla inbox*, e riscrivi *Da confermare*. Nella sezione *Oggi* mantieni le voci già presenti, anche se spuntate, e aggiungi solo quelle nuove. Non ricreare il file da zero. Se non esiste, crealo dal template `templates/daily.md`.
4. **Contenuto.**
   - *Dove sei*: una riga per progetto attivo, con il link `[[projects/<nome>/STATE|<nome>]]`. Se lo `STATE.md` di un progetto è fermo da più di due giorni, scrivilo: significa che l'aggiornamento automatico non ha funzionato.
   - *Oggi*: una checklist con le prossime azioni prese dagli STATE.
   - *Suggerimento di priorità*: una frase sola, con il motivo.
   - *Dalla inbox*: le novità non ancora lette, con link.
   - *Da confermare*: le azioni che richiedono un tuo ok e che non hai eseguito. Lasciala vuota se non ce ne sono.

Non modificare `STATE.md`, `INDEX.md`, né altri file del vault: quello è compito di `/chiudi-giornata`. Non fare commit.
