# Per iniziare (circa 15 minuti)

Versione inglese: [GETTING_STARTED.md](GETTING_STARTED.md). Ogni passo dice cosa devi vedere. Se vedi altro, fermati e lancia `python3 doctor.py`.

Su Windows scrivi `py -3` dove questa guida dice `python3`.

## 1. Installa Claude Code

macOS, Linux o WSL: `curl -fsSL https://claude.ai/install.sh | bash`. PowerShell su Windows: `irm https://claude.ai/install.ps1 | iex`. Serve un piano Claude a pagamento.
Devi vedere: `claude --version` stampa un numero di versione.

## 2. Prendi il template

`git clone https://github.com/FabriGinseng/second-brain-template.git my-second-brain`, poi `cd my-second-brain`. Puoi aprire la cartella come vault in Obsidian.
Devi vedere: `CLAUDE.md`, `projects/`, `scripts/` nella cartella.

## 3. Lancia la procedura di setup

`python3 setup.py`. Chiede il tuo nome, il tuo ruolo e la lingua, poi propone i moduli facoltativi uno alla volta: una cartella riservata (con il nome che scegli tu), il radar delle novità, le bozze settimanali, la pagina servizi, l'assistente con un calendario e il tracciamento dei repo. Il README descrive ciascuno. `python3 setup.py --list` mostra i moduli; `python3 setup.py --add <modulo>` ne aggiunge uno dopo. Prima di scrivere qualcosa mostra un riepilogo e aspetta il tuo sì. Poi controlla il tuo computer (RAM, disco) e, un passo alla volta, propone di installare ciò che le tue scelte richiedono, scaricare i modelli locali adatti e attivare il controllo dei segreti e la barra dell'uso di Claude; chiede prima di ciascuno e mostra il comando.
Devi vedere: scritti `config.json`, `memory/about-me.md`, `memory/preferences.md`, `memory/radar-topics.md` e `memory/feeds.md` (solo se hai scelto il radar), e la cartella riservata se l'hai scelta. Se un file esiste già non viene toccato.

## 4. Controlla i prerequisiti

`python3 doctor.py`.
Devi vedere: `OK` accanto a Python, git, Claude Code e regole del vault. Ollama, un browser e gitleaks sono facoltativi; per ognuno che manca trovi il comando di installazione per il tuo sistema.

## 5. Apri la dashboard

`python3 scripts/dashboard/server.py`, poi apri http://127.0.0.1:8765.
Devi vedere: una pagina con il progetto d'esempio. Ctrl+C nel terminale la ferma. Su Linux e Windows il calendario e i pulsanti dei job restano vuoti.

## 6. Crea il tuo primo progetto

Nella cartella avvia `claude` e scrivi `/nuovo-progetto my-first-project`, poi compila `projects/my-first-project/STATE.md` (obiettivo, dove sei, prossimi tre passi).
Devi vedere: una nuova cartella e una riga in `projects/INDEX.md`. Poi `python3 scripts/verify` stampa `OK`.

## 7. Chiudi la giornata

In `claude` scrivi `/chiudi-giornata`. L'agente riscrive gli STATE dai tuoi commit, lancia `scripts/verify` e fa un commit locale. Non fa mai push.
Devi vedere: un nuovo commit locale.

## 8. Togli l'esempio

`python3 setup.py --clean-example` toglie `projects/example-project` e la sua riga nell'indice.

## Job pianificati

`python3 install_jobs.py --dry-run` mostra cosa verrebbe registrato nello scheduler del tuo sistema (launchd, systemd o Utilità di pianificazione) e non scrive niente. Se ti sembra giusto, lancialo senza `--dry-run`. Devi vedere ogni job elencato con i comandi che ha lanciato. Su Linux lancia una volta `loginctl enable-linger $USER`, così i timer girano anche quando non hai una sessione aperta. `python3 install_jobs.py --uninstall` li toglie. Il radar (e il suo raccoglitore di feed) e le bozze settimanali sono facoltativi: i job del radar si registrano se hai scelto quel modulo in `setup.py`, gli altri con `--all`.

## Disinstallare

Cancella la cartella. Claude Code e Ollama hanno le loro guide di disinstallazione.
