---
description: Crea un nuovo progetto nel vault: cartella, STATE dal template e riga in INDEX
argument-hint: <nome-in-minuscolo-con-trattini>
---

Crea il progetto `$ARGUMENTS` nel vault. Scrivi in italiano.

1. **Nome.** Il nome deve contenere solo lettere minuscole, cifre e trattini, e non deve iniziare con un trattino. Se non rispetta questa regola, fermati, dillo e proponi una versione corretta. Non creare nulla.
2. **Esistenza.** Se `projects/<nome>/` esiste già, fermati e dillo. Non toccare né lo `STATE.md` né la riga in `projects/INDEX.md`.
3. **STATE.** Crea `projects/<nome>/STATE.md` (la cartella nasce con il file) a partire da `templates/STATE.md`: sostituisci `{{title}}` con il nome del progetto e `{{date:YYYY-MM-DD}}` con la data di oggi. Lascia vuoti i campi da compilare. Non creare altre sottocartelle: `decisions.md` nasce quando c'è la prima decisione.
4. **Indice.** Aggiungi in fondo alla tabella di `projects/INDEX.md` una riga costruita da `templates/project-index-row.md`, con la data di oggi.
5. **Verifica.** Esegui `./scripts/verify`. Expected: `OK`. Se non passa, correggi solo ciò che hai creato tu.

Non fare commit: lo fa `/chiudi-giornata`.
