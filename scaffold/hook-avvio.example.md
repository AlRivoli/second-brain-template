# Promemoria dei repo non tracciati (facoltativo)

Quando apri Claude Code dentro un repo git che il vault non conosce, un hook può ricordartelo e chiederti una volta: lo traccio, lo ignoro, ne riparliamo tra 7 giorni, è di lavoro. Lo script che decide è `scripts/repo-non-tracciato.py`: non scrive mai da solo e tace fuori da un repo, nel vault, nei worktree e nelle cartelle temporanee.

Il wizard **non tocca** la tua configurazione globale di Claude Code (`~/.claude`). Se lo vuoi, fai due cose a mano.

**1. In `~/.claude/settings.json`** aggiungi (sostituisci il percorso con quello di questo vault, assoluto):

```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [ { "type": "command", "command": "python3 /PERCORSO/DEL/VAULT/scripts/repo-non-tracciato.py" } ] }
    ]
  }
}
```

Se hai già una chiave `hooks`, aggiungi solo la voce `SessionStart`. Su Windows usa `py -3` al posto di `python3`.

**2. In `~/.claude/CLAUDE.md`** aggiungi una regola breve:

> Se l'hook di avvio segnala un repo non tracciato nel second brain, chiedi una volta all'utente se tracciarlo. Non tracciare mai senza una risposta. Per «lavoro» salva solo l'impronta (`python3 /PERCORSO/DEL/VAULT/scripts/repo-non-tracciato.py --registra lavoro`).

Per i repo che esistono già e il vault non conosce, usa `/adotta-repo` una volta.
