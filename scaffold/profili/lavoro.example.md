# Profilo lavoro

Per i progetti del lavoro. Si sceglie sempre a mano. Nessun dato di lavoro va a un modello in cloud finché non hai verificato la regola della tua azienda (ADR-002).

- **Host e proprietario:** quello dell'azienda; scrivilo qui solo se la regola lo consente.
- **Visibilità di default:** non applicabile, nessun repo remoto creato da qui.
- **Creazione del repo:** solo cartella locale; il push lo fai tu. Mai sul tuo account personale.
- **Template ammessi:** solo `locale:` (nessun indirizzo o nome di azienda nel registro).
- **Tracciamento:** niente scritture nel vault; vengono stampate le righe da incollare a mano.

## Funzionalità AI

Nessuna finché la regola non è verificata. Le due voci qui sotto proteggono i segreti e non mandano dati a nessun modello. La tabella la modifichi solo tu.

| Voce | Tipo | Si applica a | Proposto | Origine |
|---|---|---|---|---|
| Regole `deny` sui file dei segreti | permessi | tutti | sì | file locale `.claude/settings.json` |
| Hook pre-commit gitleaks | hook | tutti | sì | copia di `scripts/hooks/pre-commit` |
