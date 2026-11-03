# second-brain-template

Un kit di partenza per un "second brain" personale: un vault Obsidian di semplice Markdown, tenuto aggiornato da un agente di codice AI ([Claude Code](https://claude.com/claude-code)) con regole che decidi tu. Versione inglese: [README.md](README.md).

> **Stato: v0.1.** La struttura del vault, la procedura di setup, i controlli e la dashboard locale funzionano. I job pianificati sono generati per macOS, Linux e Windows. Usato ogni giorno su macOS. Su Linux e Windows i test automatici passano nella CI, ma nessuno ha ancora usato l'installer lì per davvero: vedi "Sistemi supportati".

## Cosa ottieni

- **Progetti**: uno `STATE.md` breve per progetto, riscritto (mai appeso), un `decisions.md` datato e una riga in `projects/INDEX.md`.
- **Regole che l'agente segue**: un `CLAUDE.md` breve, le decisioni in `docs/adr/` (note riservate, livello di autonomia), un glossario.
- **Permessi a sostegno delle regole**: `.claude/settings.json` blocca push, force-push, riscritture della storia e la cartella riservata.
- **Un controllo**: `scripts/verify` verifica le regole del vault. Nessun modello, solo file.
- **Comandi e subagenti** in `.claude/`: `/nuovo-progetto`, `/morning`, `/chiudi-giornata`, `/weekly-review`, `/post`, `/bozze-settimana`, `/commit-push-pr`, e i subagenti researcher, reviewer e writer. I testi dei comandi sono in italiano nella v0.1.
- **Una dashboard locale** (solo libreria standard di Python, solo `127.0.0.1`): progetti, piano, radar, servizi e limiti, post.
- **`setup.py` e `doctor.py`**: una procedura di primo avvio e un controllo dei prerequisiti.

## Requisiti

Python 3.9+, git, [Claude Code](https://code.claude.com/docs/en/setup) con un piano Claude a pagamento (il piano gratuito non lo include). Facoltativi: [Ollama](https://ollama.com) per il filtro locale del radar, Chrome, Chromium o Edge per le immagini dei post.

## Avvio rapido

```
git clone <questo repository> my-second-brain
cd my-second-brain
python3 setup.py        # Windows: py -3 setup.py
python3 doctor.py       # dice cosa manca e come installarlo
python3 scripts/verify  # stampa OK
```

Poi segui [INIZIA.md](INIZIA.md): circa 15 minuti, ogni passo dice cosa devi vedere.

## Job pianificati

`scripts/jobs.json` definisce i job una volta sola; `python3 install_jobs.py` li registra nello scheduler del tuo sistema: launchd su macOS, timer utente di systemd su Linux, Utilità di pianificazione su Windows. Comincia con `python3 install_jobs.py --dry-run` per leggere cosa farebbe. Ogni job si può lanciare due volte senza danni, quindi recuperare dopo che il computer era spento è innocuo. I job, per nome (quelli facoltativi richiedono `--all`):

| Job | Quando | Cosa fa |
|---|---|---|
| `second-brain.morning` | feriali 08:00 e al login (per ora solo macOS) | l'avvio del mattino: chiude il lavoro in sospeso, crea la nota del giorno |
| `second-brain.chiusura` | feriali 18:30 | `/chiudi-giornata`: riscrive gli STATE dai tuoi commit |
| `second-brain.pulizia` | venerdì 18:00 | controllo e report settimanale |
| `second-brain.dashboard` | al login, sempre acceso | la dashboard locale |
| `second-brain.radar` (facoltativo) | lunedì 07:30 | filtra le novità di `inbox/` per i tuoi progetti (serve Ollama) |
| `second-brain.bozze` (facoltativo) | lunedì 08:30 | `/bozze-settimana`: tre bozze di post |

## Sistemi supportati

| Parte | macOS | Linux | Windows |
|---|---|---|---|
| Vault, `scripts/verify`, `setup.py`, `doctor.py` | sì | test CI passano | test CI passano |
| Dashboard | sì | in parte (senza calendario né pulsanti dei job) | in parte |
| Calendario in "Oggi" | sì (app Calendario) | no | no |
| Job pianificati (`install_jobs.py`) | sì | file generati e testati, non ancora registrati per davvero | idem |

Su Windows, WSL 2 è la strada più sicura per Claude Code finché Windows nativo non è provato.

## Privacy

Claude Code manda al modello i file che legge. Metti le note riservate in `projects/_private/` (ignorata da git e bloccata da regole `deny`) e leggi l'[ADR-002](docs/adr/ADR-002-confidential-notes.md) per i limiti di quel blocco. Il tuo nome, le note e i file di memoria restano nella tua copia: `setup.py` li scrive dai file `*.example.md` e git li ignora.

## Licenza

MIT, vedi `LICENSE`. Per segnalare dati personali finiti qui per errore, vedi `SECURITY.md`.
