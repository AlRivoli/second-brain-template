#!/usr/bin/env python3
"""Registra nel vault un piano approvato: una riga di docs/piano.md per task e la riga del suo obiettivo in docs/obiettivi.md.

Uso: scripts/registra-piano.py <piano.md> --tag <progetto> --obiettivo <slug> [--titolo T] [--scadenza AAAA-MM-GG]
     [--giorni lun,mar,...|tutti] [--piano-rel <percorso relativo>] [--senza-commit]

Il vault è sempre quello in cui sta lo script. Il piano viene da un altro repo: è un dato non fidato. Deve essere un file di
uno dei repo del progetto (righe `Repo:` del suo STATE), mai dentro projects/ del vault né nella cartella riservata, ovunque
sia e anche dove porta se è un link, né in projects/<lavoro o cartella riservata> di un altro vault (ADR-002);
`piano:` è il suo percorso relativo alla radice di quel repo (--piano-rel, se passato, deve essere uguale). Si apre solo in
lettura (.md, al massimo 1 MB) e se ne ricavano solo il titolo `# `, i titoli `### Task <N>: <titolo>` e tre campi per task:
`**Dipende da:** Task 1, Task 3` (oppure `nessuna`), `**Stima:** 3h|1g` e `**Repo:** <nome>`. I blocchi di codice si saltano.
Il testo scritto passa la validazione di aggiungi_voce della dashboard, senza wikilink, link né immagini; il tag deve essere un
progetto dell'INDEX, non del lavoro né della cartella riservata, e i repo quelli del suo STATE.

Ogni task diventa `- [ ] #<tag> <titolo del piano> · Task <N>: <titolo> id:<slug>-t<N> [dopo:...] obiettivo:<slug> [stima:...]
[repo:...]` in «Prossimi giorni», dopo l'ultima voce aperta del tag in quella sezione. Rilanciato sullo stesso piano aggiorna
le righe con lo stesso id dove sono (testo e marcatori; casella e data in testa restano) e non duplica niente, ma solo se
l'obiettivo ha già lo stesso `piano:`: il piano è il suo file. Con id già nel vault e un altro piano si ferma. La riga
dell'obiettivo prende titolo, scadenza, giorni e piano dagli argomenti; un valore non passato resta quello che c'era.

Uscite: 0 se ha scritto o non c'era niente da cambiare, 2 se il piano o gli argomenti non vanno (non scrive niente e dice su
stderr cosa correggere, con la riga del piano), 1 se config.json o un file del vault non si leggono, una scrittura o il commit
non riescono. Niente rete; git solo su docs/piano.md e docs/obiettivi.md, con una lista di argomenti e senza le variabili
GIT_* di chi lo lancia. Tempo e spazio O(righe del piano + righe dei due file + repo del progetto).
"""
import argparse
import importlib.util
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent


def _modulo(percorso):
    """Carica un modulo da file: con 'python3 -I' la cartella dello script non è nel path."""
    spec = importlib.util.spec_from_file_location(percorso.stem.replace("-", "_"), percorso)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


server = _modulo(HERE / "dashboard" / "server.py")
dipendenze = server.dipendenze

PIANO_MASSIMO = 1024 * 1024  # byte
TASK_MASSIMI = 100  # a real plan has a handful: more is a mistake or an attack on the size of piano.md
PREFISSO_MASSIMO = 60  # the plan title in front of every task line is cut here
FILE = ("docs/piano.md", "docs/obiettivi.md")
TITOLO = re.compile(r"^# (.+)$")
TASK = re.compile(r"^### Task ([0-9]+):(.*)$")
TASK_SBAGLIATO = re.compile(r"^#{2,4}\s*Task\b")  # a heading meant as a task that TASK does not read: silently lost otherwise
CAMPO = re.compile(r"^\s*(?:[-*] )?\*\*(Dipende da|Stima|Repo):\*\*(.*)$")
RIFERIMENTO = re.compile(r"Task ([1-9][0-9]*)", re.I)
RECINTO = re.compile(r"^ {0,3}(```|~~~)")
FINE_TASK = re.compile(r"^#{1,3} ")
GIT_TIMEOUT = 120  # seconds: the vault's pre-commit hook runs gitleaks
LINK = "link e immagini non sono ammessi nel piano: scrivili come testo"
CONFIG_ILLEGGIBILE = "config.json non leggibile: non posso escludere la cartella riservata"


def _link(testo):
    """A Markdown link or image, or a URL: an agent reading the vault could follow or fetch it (ADR-002)."""
    return any(s in testo for s in ("](", "![", "://"))


def _testo_vietato(testo):
    """The rule of aggiungi_voce of the dashboard (no `<`, `>` or characters of the forbidden Unicode categories), plus no
    `[[`, `]]`, `|` or link: an agent reading the vault would follow a wikilink or a link planted by a plan (ADR-002).
    Backticks stay allowed."""
    return (any(s in testo for s in ("<", ">", "[[", "]]", "|")) or _link(testo)
            or any(unicodedata.category(c) in server.CATEGORIE_VIETATE for c in testo))


def leggi_riservata(vault):
    """(reserved names under projects/, the setup's reserved folder or None) from one reading of config.json, failing closed:
    a config.json that exists but cannot be read, is ill-shaped or names a folder the setup wizard would refuse could hide the
    reserved folder, so it is RuntimeError(CONFIG_ILLEGGIBILE) (percorsi.scelta_riservata). A missing config.json is fine."""
    try:
        scelta = server.percorsi.scelta_riservata(vault)
    except RuntimeError as e:
        raise RuntimeError(getattr(e, "motivo", None) or CONFIG_ILLEGGIBILE) from None
    return server.percorsi.nomi_riservati(scelta), scelta


def _in_riservata_di_un_vault(percorso, scelta):
    """The path holds, as consecutive parts and in any case, projects/ then the work folder, _private or the setup's reserved folder
    (`scelta`, relative to a vault) right after a folder that has a projects/ subfolder: a note of any checkout of a vault, not
    only this one (ADR-002). The projects/<name> runs are text only; for a folder configured elsewhere the vault-like root is
    checked on disk (os.path.isdir never raises), on the local path already accepted. O(p * r) time, p = parts, r = runs."""
    parti = Path(percorso).parts
    piegate = [x.casefold() for x in parti]
    corse = [("projects", n) for n in server.percorsi.FISSE] + ([tuple(scelta.casefold().split("/"))] if scelta else [])
    for corsa in corse:
        for i in range(1, len(parti) - len(corsa) + 1):
            if (tuple(piegate[i:i + len(corsa)]) == corsa
                    and (corsa[0] == "projects" or os.path.isdir(os.path.join(*parti[:i], "projects")))):
                return True
    return False


def _testo_percorso(percorso):
    return os.path.normpath(str(percorso)).casefold()


def percorso_del_piano(percorso, tag, vault):
    """(resolved plan file, its path relative to the repo root in POSIX form) when the file lies inside a repo of the
    project `tag` (its STATE `Repo:` lines), else ValueError([problem]). Never inside the vault's projects/ (notes, lavoro,
    the reserved folder: ADR-002), even through a link. A path not on a local disk is refused before touching the disk, like
    every repo root. The deepest matching repo wins. RuntimeError(CONFIG_ILLEGGIBILE) as leggi_riservata, the one reading of
    config.json. O(r + k + p) time and space and k resolves, r = repos of the project, k = reserved folders, p = path parts.
    No path is ever echoed back."""
    vault = Path(vault)
    riservate, scelta = leggi_riservata(vault)
    p = Path(os.path.abspath(percorso))
    if not server._percorso_locale(p):
        raise ValueError(["il piano deve stare su un disco di questo computer, non in rete"])
    try:
        file = p.resolve(strict=True)
    except (OSError, RuntimeError):  # RuntimeError: a symlink loop
        raise ValueError(["il file del piano non esiste o non si raggiunge"]) from None
    testo = _testo_percorso(file)
    progetti = {_testo_percorso(radice / "projects") for radice in (vault, vault.resolve())}
    if (any(testo == b or testo.startswith(b + os.sep) for b in progetti)
            or server._in_cartella_riservata(file, server._basi_riservate(vault, scelta))):
        raise ValueError(["il piano non può stare in projects/ del vault né nella sua cartella riservata: le note non sono piani (ADR-002)"])
    if _in_riservata_di_un_vault(p, scelta) or _in_riservata_di_un_vault(file, scelta):
        raise ValueError(["il piano non può stare nelle note riservate di un vault (projects/ seguita da lavoro o da una "
                          "cartella riservata): le note non sono piani (ADR-002)"])
    info = None
    if isinstance(tag, str) and server.TAG_NUOVO.fullmatch(tag) and tag.casefold() not in riservate:
        info = server.progetti_indice(vault, riservate).get(tag.lower())
    radici = []
    # percorsi_repo, as the launcher: nomi_repo drops roots, paths ending in `.` or `..` and twins. A root would make
    # the guard «any .md on the drive»; one reached through a link is caught once resolved.
    for repo in [] if info is None or info.get("lavoro") else map(Path, info["percorsi_repo"].values()):
        if not server._percorso_locale(repo):  # text first: a network root would open a connection
            continue
        try:
            radice = repo.resolve()
        except (OSError, RuntimeError):
            continue
        if radice.parent != radice and file.is_relative_to(radice):
            radici.append(radice)
    if not radici:
        raise ValueError(["il piano deve stare in uno dei repo del progetto --tag (righe `Repo:` del suo STATE)"])
    rel = file.relative_to(max(radici, key=lambda r: len(r.parts))).as_posix()
    if not dipendenze.percorso_piano_valido(rel):
        raise ValueError(["il percorso del piano nel repo deve avere solo lettere, cifre, `.`, `_`, `-` e `/`, senza spazi: "
                          "rinomina il file o la cartella"])
    return file, rel


def _senza_cancelletti(titolo):
    """A title without `#`, like aggiungi_voce_libera: a plan cannot add a second hashtag. Only spaces are collapsed, so a
    line separator stays and is refused."""
    return re.sub(r" {2,}", " ", titolo.replace("#", "")).strip()


def leggi_piano(testo):
    """(title (riga, testo) or None, [task], [problems]) of a writing-plans file. Code fences are skipped.

    A task is {riga, n (the raw number), titolo, campi: {name: (riga, value)}}; its block ends at the next `#`, `##` or `###`.
    Lines are split on `\\n` only, so a line separator inside a title stays there and is refused, and line numbers match an editor's.
    """
    titolo, tasks, problemi = None, [], []
    task, recinto = None, None
    for numero, riga in enumerate(testo.removeprefix("﻿").split("\n"), 1):
        riga = riga.removesuffix("\r")
        if m := RECINTO.match(riga):
            recinto = m.group(1) if recinto is None else (None if m.group(1) == recinto else recinto)
            continue
        if recinto:
            continue
        if titolo is None and (m := TITOLO.match(riga)):
            # «X — Implementation Plan» -> «X»
            titolo = (numero, _senza_cancelletti(m.group(1)).removesuffix("Implementation Plan").rstrip(" —–-:"))
            continue
        if m := TASK.match(riga):
            task = {"riga": numero, "n": m.group(1), "titolo": _senza_cancelletti(m.group(2)), "campi": {}}
            tasks.append(task)
        elif TASK_SBAGLIATO.match(riga):
            problemi.append(f"riga {numero}: scrivi `### Task <N>: <titolo>`")
            task = None
        elif FINE_TASK.match(riga):
            task = None
        elif task and (m := CAMPO.match(riga)):
            nome = m.group(1)
            if nome in task["campi"]:
                problemi.append(f"riga {numero}: **{nome}:** ripetuto nel Task {task['n']}: lascialo una volta sola")
            else:
                task["campi"][nome] = (numero, m.group(2).strip())
    return titolo, tasks, problemi


def _dipendenze_task(task, numeri, problemi, avvisi):
    """Numbers the task depends on, in order and without repeats; problems and warnings go to the lists."""
    n = task["n"]
    if "Dipende da" not in task["campi"]:
        avvisi.append(f"riga {task['riga']}: Task {n}: dipendenza non dichiarata: chiedila all'utente")
        return []
    riga, valore = task["campi"]["Dipende da"]
    if valore.lower() == "nessuna":
        return []
    parti = [RIFERIMENTO.fullmatch(p.strip()) for p in valore.split(",")]
    if not all(parti):
        problemi.append(f"riga {riga}: **Dipende da:** del Task {n}: scrivi `Task 1, Task 3` oppure `nessuna`")
        return []
    dopo = []
    for m in dict.fromkeys(p.group(1) for p in parti):
        if m == n:
            problemi.append(f"riga {riga}: il Task {n} dipende da sé stesso: togli il riferimento")
        elif m not in numeri:
            problemi.append(f"riga {riga}: Task {m} non esiste nel piano: correggi il numero o togli il riferimento")
        else:
            dopo.append(m)
    return dopo


def _riga_obiettivo(righe, slug, problemi):
    """Index of the goal line of `slug` in docs/obiettivi.md, None when missing; a repeated slug is a problem."""
    trovate = [i for i, r in enumerate(righe) if (m := dipendenze._RIGA_OBIETTIVO.match(r.rstrip())) and m.group(1) == slug]
    if len(trovate) > 1:
        problemi.append(f"docs/obiettivi.md:{trovate[1] + 1}: obiettivo {slug} definito più volte: lascia una riga sola")
    return trovate[0] if trovate else None


def _fine_riga(riga):
    return riga[len(riga.rstrip("\r\n")):]


def _leggi(file, nome):
    """Text of a vault file with its line ends as they are; RuntimeError naming it (`nome`, relative) when it cannot be read."""
    try:
        with open(file, encoding="utf-8", newline="") as f:  # newline="": CRLF stays as it is
            return f.read()
    except UnicodeDecodeError:
        raise RuntimeError(f"{nome} non è UTF-8 valido: correggilo o riscrivi la riga rotta") from None
    except OSError as e:
        raise RuntimeError(f"non riesco a leggere {nome}: {e.strerror or type(e).__name__}") from None


def registra(testo_piano, tag, slug, vault, titolo=None, scadenza=None, giorni=None, piano_rel=None):
    """Writes the plan's tasks in docs/piano.md and its goal in docs/obiettivi.md, atomically, file by file.

    Returns {aggiunte, aggiornate (the lines written, without line end), legami ({id: [ids it depends on]}), avvisi, cambiato}.
    ValueError([problems]): nothing is written; each problem says the line (of the plan, or `docs/<file>:<line>`) and what to fix.
    RuntimeError(message naming the file): config.json unreadable (leggi_riservata), docs/piano.md or docs/obiettivi.md
    not UTF-8 or not readable, or a write that failed (the message says which file was already written).
    """
    vault = Path(vault)
    problemi, avvisi = [], []
    file_piano, file_obiettivi = vault / FILE[0], vault / FILE[1]
    if not (vault / "projects" / "INDEX.md").is_file() or not file_piano.is_file():
        raise ValueError(["il vault dello script non ha projects/INDEX.md o docs/piano.md"])
    riservate = leggi_riservata(vault)[0]

    # Arguments: the values are not echoed, the message says how to write them
    info = None
    if isinstance(tag, str) and server.TAG_NUOVO.fullmatch(tag):
        info = server.progetti_indice(vault, riservate).get(tag.lower())
    if info is None:
        problemi.append("--tag: non è un progetto di projects/INDEX.md: usa il nome della sua riga nell'INDEX")
    elif info.get("lavoro") or tag.casefold() in riservate:
        problemi.append("--tag: è un progetto del lavoro o della cartella riservata: i suoi piani non entrano nel vault")
        info = None
    slug_ok = isinstance(slug, str) and re.fullmatch(dipendenze._ID, slug)
    if not slug_ok:
        problemi.append("--obiettivo: scrivi uno slug di lettere minuscole, cifre e trattini, al massimo 40 caratteri (es. `rilascio`)")
    if scadenza is not None and dipendenze._data(scadenza) is None:
        problemi.append("--scadenza: scrivi una data vera come AAAA-MM-GG")
    if giorni is not None and dipendenze._giorni(giorni) is None:
        problemi.append("--giorni: scrivi lun,mar,mer,gio,ven,sab,dom separati da virgole, oppure `tutti`")
    if piano_rel is not None and not dipendenze.percorso_piano_valido(piano_rel):
        problemi.append("--piano-rel: scrivi un percorso relativo alla radice del repo, con lettere, cifre, `.`, `_`, `-` e `/`, "
                        "senza spazi né `..` e non assoluto (es. `docs/piano.md`)")
    if titolo is not None and _link(titolo):
        problemi.append("--titolo: " + LINK)
    elif titolo is not None and (not titolo.strip() or _testo_vietato(titolo)):
        problemi.append("--titolo: scrivi un titolo senza `<`, `>`, `[[`, `]]`, `|` e caratteri di controllo o di direzione")

    # The plan
    titolo_piano, tasks, trovati = leggi_piano(testo_piano)
    problemi += trovati
    prefisso = ""
    if titolo_piano is None or not titolo_piano[1]:
        problemi.append("riga 1: manca il titolo del piano: scrivi `# <titolo>` in cima")
    elif _link(titolo_piano[1]):
        problemi.append(f"riga {titolo_piano[0]}: {LINK}")
    elif _testo_vietato(titolo_piano[1]) or dipendenze._QUASI_MARCATORE.search(titolo_piano[1]):
        problemi.append(f"riga {titolo_piano[0]}: il titolo del piano contiene `<`, `>`, `[[`, `]]`, `|`, caratteri di controllo o di direzione, "
                        "o una parola come `chiave:` che si leggerebbe come marcatore: riscrivilo")
    else:
        prefisso = titolo_piano[1]
        if len(prefisso) > PREFISSO_MASSIMO:
            prefisso = prefisso[:PREFISSO_MASSIMO - 1].rstrip() + "…"
    if not tasks:
        problemi.append("nessun task: scrivi ogni task con un titolo `### Task <N>: <titolo>`")
    elif len(tasks) > TASK_MASSIMI:
        problemi.append(f"il piano ha {len(tasks)} task: al massimo {TASK_MASSIMI}, dividilo in più piani")
        tasks = []
    numeri = {}
    for t in tasks:
        n = t["n"]
        if n == "0" or n.startswith("0"):
            problemi.append(f"riga {t['riga']}: numera i task da 1, senza zeri davanti")
        elif n in numeri:
            problemi.append(f"riga {t['riga']}: Task {n} è già alla riga {numeri[n]['riga']}: dai a ogni task un numero diverso")
        else:
            numeri[n] = t
        if not t["titolo"]:
            problemi.append(f"riga {t['riga']}: Task {n} senza titolo: scrivi `### Task {n}: <titolo>`")
        elif _link(t["titolo"]):
            problemi.append(f"riga {t['riga']}: {LINK}")
        elif _testo_vietato(t["titolo"]):
            problemi.append(f"riga {t['riga']}: il titolo del Task {n} contiene `<`, `>`, `[[`, `]]`, `|` o caratteri di controllo o di direzione: toglili")
        elif m := dipendenze._QUASI_MARCATORE.search(t["titolo"]):
            chiave = m.group().partition(":")[0]
            problemi.append(f"riga {t['riga']}: nel titolo del Task {n} `{chiave}:` si leggerebbe come marcatore: riscrivilo")
        if slug_ok and not re.fullmatch(dipendenze._ID, f"{slug}-t{n}"):
            problemi.append(f"riga {t['riga']}: id:{slug}-t{n} supera 40 caratteri: usa un --obiettivo più corto")

    validi = list(numeri.values())
    dopo = {t["n"]: _dipendenze_task(t, numeri, problemi, avvisi) for t in validi}
    posizione = {t["n"]: i for i, t in enumerate(validi)}
    for i in sorted(dipendenze._nodi_in_ciclo([[posizione[m] for m in dopo[t["n"]]] for t in validi])):
        t = validi[i]
        problemi.append(f"riga {t['campi']['Dipende da'][0]}: il Task {t['n']} è in un ciclo di **Dipende da:**: "
                        "togli almeno un riferimento del giro")
    stime, repo = {}, {}
    for t in validi:
        n = t["n"]
        if "Stima" not in t["campi"]:
            avvisi.append(f"riga {t['riga']}: Task {n}: senza stima")
        else:
            riga, valore = t["campi"]["Stima"]
            if dipendenze._valore("stima", valore) is None:
                problemi.append(f"riga {riga}: **Stima:** del Task {n}: scrivi le ore o i giorni come `3h`, `1g` o `1,5g`")
            stime[n] = valore
        if "Repo" in t["campi"] and info is not None:
            riga, valore = t["campi"]["Repo"]
            nomi = dipendenze._valore("repo", ",".join(p.strip() for p in valore.split(",")))
            if nomi is None:
                problemi.append(f"riga {riga}: **Repo:** del Task {n}: scrivi i nomi delle cartelle dei repo separati da virgole")
                continue
            for nome in dict.fromkeys(nomi):
                if nome in info.get("repo_doppi", []):
                    problemi.append(f"riga {riga}: due repo di {tag} si chiamano {nome}: rinomina una delle due cartelle")
                elif nome not in info.get("nomi_repo", []):
                    elenco = ", ".join(info.get("nomi_repo", [])) or "nessuno, il progetto non ha repo"
                    problemi.append(f"riga {riga}: {nome} non è un repo di {tag}: usa uno di {elenco}")
            repo[n] = list(dict.fromkeys(nomi))
    if problemi:
        raise ValueError(problemi)

    # The two files
    vecchio_piano = _leggi(file_piano, FILE[0])
    righe = vecchio_piano.splitlines(keepends=True)
    eol = "\r\n" if righe and righe[0].endswith("\r\n") else "\n"
    esiste_obiettivi = file_obiettivi.is_file()
    if esiste_obiettivi:
        vecchi_obiettivi = _leggi(file_obiettivi, FILE[1])
    else:
        vecchi_obiettivi = "# Obiettivi" + eol + eol
    righe_obiettivi = vecchi_obiettivi.splitlines(keepends=True)
    eol_obiettivi = "\r\n" if righe_obiettivi and righe_obiettivi[0].endswith("\r\n") else "\n"
    i_obiettivo = _riga_obiettivo(righe_obiettivi, slug, problemi)
    vecchio_titolo, vecchi = None, {}
    if i_obiettivo is not None:
        resto = dipendenze._RIGA_OBIETTIVO.match(righe_obiettivi[i_obiettivo].rstrip()).group(2)
        # raw strings back, not parsed values: the markers are written again as they were
        vecchio_titolo, vecchi = dipendenze.separa_marcatori(
            resto, lambda k, g: g if dipendenze._valore_obiettivo(k, g) is not None else None)
    # A plan is its file: only a run with the `piano:` path already on the goal may touch the goal's ids in the vault.
    # Titles cannot tell two plans apart (they can be equal, or differ only past the cut). An existing `piano:` is never
    # changed: a first run of another plan with no colliding id would move the goal, and the next run take its ids over.
    if vecchi.get("piano") is not None and piano_rel != vecchi["piano"]:
        problemi.append(f"docs/obiettivi.md:{i_obiettivo + 1}: l'obiettivo {slug} appartiene al piano {vecchi['piano']}: "
                        "usa lo stesso --piano-rel o un altro --obiettivo")
        raise ValueError(problemi)
    stesso_piano = piano_rel is not None and vecchi.get("piano") == piano_rel

    # The task lines
    per_id = {}
    for v in dipendenze.leggi_voci(vecchio_piano):
        if "id" in v["marcatori"]:
            per_id.setdefault(v["marcatori"]["id"], []).append(v)
    nostri = {f"{slug}-t{t['n']}" for t in validi}
    for id_, voci in per_id.items():
        if stesso_piano and id_ not in nostri and re.fullmatch(re.escape(slug) + r"-t[1-9][0-9]*", id_):
            avvisi.append(f"docs/piano.md:{voci[0]['riga']}: id:{id_} non è più nel piano: togli la riga o chiudila a mano")

    aggiunte, aggiornate, legami, nuove, occupata = [], [], {}, [], None
    for t in validi:
        n, id_ = t["n"], f"{slug}-t{t['n']}"
        legami[id_] = [f"{slug}-t{m}" for m in dopo[n]]
        testo = f"{prefisso} · Task {n}: {t['titolo']}"
        marcatori = {"id": id_, **({"dopo": legami[id_]} if legami[id_] else {}), "obiettivo": slug,
                     **({"stima": stime[n]} if n in stime else {}), **({"repo": repo[n]} if n in repo else {})}
        corpo = f"#{tag} {testo} " + " ".join(f"{k}:{','.join(v) if isinstance(v, list) else v}" for k, v in marcatori.items())
        if len(corpo) - len(tag) - 2 > server.TESTO_MASSIMO:
            problemi.append(f"riga {t['riga']}: la riga del Task {n} avrebbe {len(corpo) - len(tag) - 2} caratteri, "
                            f"al massimo {server.TESTO_MASSIMO}: accorcia il titolo del task")
            continue
        # Read back as verify and the dashboard will: a title must not turn into a marker or move the tag
        letta = dipendenze.leggi_voci("- [ ] " + corpo)
        if not letta or letta[0]["marcatori"] != marcatori or letta[0]["tag"] != tag.lower() or letta[0]["testo"] != f"#{tag} {testo}":
            problemi.append(f"riga {t['riga']}: il titolo del Task {n} si leggerebbe come un marcatore: riscrivilo")
            continue
        esistenti = per_id.get(id_, [])
        if len(esistenti) > 1:
            problemi.append(f"docs/piano.md:{esistenti[1]['riga']}: id:{id_} compare più volte: lascia una riga sola")
            continue
        if not esistenti:
            nuove.append("- [ ] " + corpo)
            continue
        v = esistenti[0]
        # Same id from another plan or project: overwriting it would hand its checkbox to a different task
        if not stesso_piano:
            occupata = occupata or v
            continue
        if v["tag"] != tag.lower():
            problemi.append(f"docs/piano.md:{v['riga']}: id:{id_} è di un task di un altro progetto: correggi o togli quella riga")
            continue
        i = v["riga"] - 1
        # Markers added by hand survive: chi:te, and dopo: toward tasks of other plans (this plan's own links come from the plan)
        sul_file = v["marcatori"]
        a_mano = [r for r in sul_file.get("dopo", ()) if r not in legami[id_] and not re.fullmatch(re.escape(slug) + r"-t[1-9][0-9]*", r)]
        if a_mano or "chi" in sul_file:
            marcatori = {**marcatori, **({"dopo": legami[id_] + a_mano} if legami[id_] or a_mano else {}), **({"chi": sul_file["chi"]} if "chi" in sul_file else {})}
            corpo = f"#{tag} {testo} " + " ".join(f"{k}:{','.join(v) if isinstance(v, list) else v}" for k, v in marcatori.items())
        voce = dipendenze.VOCE_PIANO.match(righe[i].rstrip("\r\n"))
        data = server.DATA_PIANO.match(voce.group(2))
        nuova = f"- [{voce.group(1)}] " + (data.group(1) + " — " if data else "") + corpo
        if nuova != righe[i].rstrip("\r\n"):
            righe[i] = nuova + _fine_riga(righe[i])
            aggiornate.append(nuova)
    if occupata:
        id_ = occupata["marcatori"]["id"]
        problemi.append(
            f"docs/piano.md:{occupata['riga']}: id:{id_} è già nel vault: per aggiornare il piano registrato passa --piano-rel "
            f"con lo stesso percorso scritto in `piano:` dell'obiettivo {slug}" if piano_rel is None else
            f"docs/piano.md:{occupata['riga']}: id:{id_} è già nel vault e l'obiettivo {slug} è di un altro piano "
            "(senza `piano:` in docs/obiettivi.md): usa un altro --obiettivo")
    if problemi:
        raise ValueError(problemi)
    if nuove:
        pos = server.posto_nuova_voce(righe, tag, eol, in_prossimi=True)
        righe[pos:pos] = [r + eol for r in nuove]
        aggiunte = nuove
    nuovo_piano = "".join(righe)

    # The goal line
    i = i_obiettivo
    valori = {"scadenza": scadenza, "giorni": giorni, "piano": piano_rel}
    titolo_obiettivo, origine = titolo, "--titolo"
    if i is not None:
        valori = {k: v if v is not None else vecchi.get(k) for k, v in valori.items()}
        if titolo_obiettivo is None:
            titolo_obiettivo, origine = vecchio_titolo.strip(), f"docs/obiettivi.md:{i + 1}"
    elif titolo_obiettivo is None:
        titolo_obiettivo, origine = prefisso, f"riga {titolo_piano[0]}"
    titolo_obiettivo = titolo_obiettivo.strip()
    riga_obiettivo = f"- {slug}: {titolo_obiettivo}" + "".join(f" {k}:{v}" for k, v in valori.items() if v)
    if (not titolo_obiettivo or len(titolo_obiettivo) > dipendenze._TITOLO_MAX or _testo_vietato(titolo_obiettivo)
            or dipendenze._QUASI_MARCATORE_OBIETTIVO.search(titolo_obiettivo)):
        problemi.append(f"{origine}: il titolo dell'obiettivo deve avere da 1 a {dipendenze._TITOLO_MAX} caratteri, senza `<`, `>`, `[[`, `]]`, `|`, "
                        "caratteri di controllo o di direzione e senza marcatori come `scadenza:`, `giorni:` o `piano:`: passa un --titolo valido")
    else:
        letti, _ = dipendenze.leggi_obiettivi(riga_obiettivo)
        if letti.get(slug, {}).get("titolo") != titolo_obiettivo:
            problemi.append(f"{origine}: il titolo dell'obiettivo si leggerebbe come un marcatore: passa un --titolo diverso")
    if problemi:
        raise ValueError(problemi)
    if i is not None:
        righe_obiettivi[i] = riga_obiettivo + _fine_riga(righe_obiettivi[i])
    else:
        ultime = [j for j, r in enumerate(righe_obiettivi) if dipendenze._RIGA_OBIETTIVO.match(r.rstrip())]
        pos = ultime[-1] + 1 if ultime else len(righe_obiettivi)
        if pos and not righe_obiettivi[pos - 1].endswith("\n"):
            righe_obiettivi[pos - 1] += eol_obiettivi
        righe_obiettivi.insert(pos, riga_obiettivo + eol_obiettivi)
    nuovi_obiettivi = "".join(righe_obiettivi)

    # Goal first: if the second write fails, a goal without tasks is harmless, tasks pointing to no goal are not
    # ponytail: re-read just before writing, not a lock shared with the dashboard: the window left is a few milliseconds
    if _leggi(file_piano, FILE[0]) != vecchio_piano or (esiste_obiettivi and _leggi(file_obiettivi, FILE[1]) != vecchi_obiettivi):
        raise RuntimeError("docs/piano.md o docs/obiettivi.md è cambiato mentre registravo (la dashboard?): non scrivo nulla, rilancia")
    scritti, in_scrittura = [], FILE[1]
    try:
        if not esiste_obiettivi:
            with open(file_obiettivi, "x", encoding="utf-8", newline="") as f:
                f.write(nuovi_obiettivi)
            scritti.append(FILE[1])
        elif nuovi_obiettivi != vecchi_obiettivi:
            server._scrivi_atomico(file_obiettivi, righe_obiettivi)
            scritti.append(FILE[1])
        in_scrittura = FILE[0]
        if nuovo_piano != vecchio_piano:
            server._scrivi_atomico(file_piano, righe)
    except OSError as e:  # strerror only: the text of the exception holds the absolute path
        raise RuntimeError(f"non riesco a scrivere {in_scrittura}: {e.strerror or type(e).__name__}; "
                           f"file già scritti: {', '.join(scritti) or 'nessuno'}") from None
    return {"aggiunte": aggiunte, "aggiornate": aggiornate, "legami": legami, "avvisi": avvisi,
            "cambiato": not esiste_obiettivi or nuovi_obiettivi != vecchi_obiettivi or nuovo_piano != vecchio_piano}


def committa(vault, slug, risultato):
    """Commits only docs/piano.md and docs/obiettivi.md (the pathspec keeps out anything else already staged).
    RuntimeError(message) when git is missing, fails or does not answer within GIT_TIMEOUT seconds.

    The message names ids and links, never titles. git's output is not echoed: a hook (gitleaks) may print what it found.
    git runs without the caller's GIT_* variables: a GIT_DIR or GIT_WORK_TREE left by a hook of another repo would commit there.
    """
    corpo = "\n".join(f"- {id_}" + (f" dopo:{','.join(d)}" if d else "") for id_, d in risultato["legami"].items())
    messaggio = f"docs(piano): register plan {slug}\n\n{corpo}\n"
    base = ["git", "-C", str(vault)]
    ambiente = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}  # Windows names ignore case
    for comando, ingresso in ((base + ["add", "--", *FILE], None), (base + ["commit", "-F", "-", "--", *FILE], messaggio)):
        try:
            r = subprocess.run(comando, input=ingresso, capture_output=True, text=True, encoding="utf-8", timeout=GIT_TIMEOUT,
                               env=ambiente)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"file scritti, ma git non ha risposto entro {GIT_TIMEOUT} secondi: controlla il vault e committa a mano") from None
        except OSError:
            raise RuntimeError("file scritti, ma git non si avvia: committa a mano docs/piano.md e docs/obiettivi.md") from None
        if r.returncode:
            raise RuntimeError("file scritti, ma il commit non è riuscito: lancia `git commit` nel vault per vedere perché")


def leggi_file_piano(percorso):
    """Text of the plan file: only a regular `.md` file up to 1 MB, decoded with errors="replace". ValueError([problem])."""
    p = Path(percorso)
    if p.suffix.lower() != ".md":
        raise ValueError(["il piano deve essere un file .md"])
    try:
        if not p.is_file():
            raise ValueError(["il file del piano non esiste o non è un file"])
        if p.stat().st_size > PIANO_MASSIMO:
            raise ValueError([f"il piano supera {PIANO_MASSIMO // (1024 * 1024)} MB: non è un piano"])
        with open(p, "rb") as f:
            dati = f.read(PIANO_MASSIMO + 1)  # a file that grew after stat still cannot pass the cap
    except OSError:
        raise ValueError(["il file del piano non si legge"]) from None
    if len(dati) > PIANO_MASSIMO:
        raise ValueError([f"il piano supera {PIANO_MASSIMO // (1024 * 1024)} MB: non è un piano"])
    return dati.decode("utf-8", errors="replace")


def main(argv=None):
    for flusso in (sys.stdout, sys.stderr):
        if hasattr(flusso, "reconfigure"):
            flusso.reconfigure(encoding="utf-8", errors="replace")  # la console di Windows non è UTF-8 per conto suo
    ap = argparse.ArgumentParser(description="Registra nel vault un piano approvato: righe di docs/piano.md e obiettivo.")
    ap.add_argument("piano", help="il file .md del piano")
    ap.add_argument("--tag", required=True, help="il progetto, come nell'INDEX")
    ap.add_argument("--obiettivo", required=True, help="lo slug dell'obiettivo; gli id sono <slug>-t<N>")
    ap.add_argument("--titolo", help="titolo dell'obiettivo (di default resta quello che c'è, o il titolo del piano)")
    ap.add_argument("--scadenza", help="AAAA-MM-GG")
    ap.add_argument("--giorni", help="lun,mar,... oppure tutti")
    ap.add_argument("--piano-rel", help="percorso del piano relativo alla radice del suo repo: se lo passi, deve essere quello vero")
    ap.add_argument("--senza-commit", action="store_true")
    args = ap.parse_args(argv)
    vault = VAULT  # always the vault the script lives in: no argument can point it at another folder
    # Order matters: UnicodeDecodeError and JSONDecodeError are ValueErrors, and a ValueError here carries a list of problems
    try:
        file, piano_rel = percorso_del_piano(args.piano, args.tag, vault)
        if args.piano_rel is not None and args.piano_rel != piano_rel:
            raise ValueError([f"--piano-rel: questo piano è {piano_rel} nel suo repo: togli --piano-rel o passa quello"])
        risultato = registra(leggi_file_piano(file), args.tag, args.obiettivo, vault, titolo=args.titolo,
                             scadenza=args.scadenza, giorni=args.giorni, piano_rel=piano_rel)
    except RuntimeError as e:  # config.json, docs/piano.md or docs/obiettivi.md: the message names the file
        print(e, file=sys.stderr)
        return 1
    except UnicodeDecodeError:  # read by the dashboard's helpers, which do not name the file
        print("projects/INDEX.md o uno STATE.md dei progetti non è UTF-8 valido: correggilo", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"non riesco a leggere projects/INDEX.md o uno STATE.md: {e.strerror or type(e).__name__}", file=sys.stderr)
        return 1
    except ValueError as e:
        for problema in e.args[0]:
            print(problema, file=sys.stderr)
        return 2
    for avviso in risultato["avvisi"]:
        print("avviso: " + avviso, file=sys.stderr)
    if not risultato["cambiato"]:
        print("niente da cambiare: il piano è già registrato")
        return 0
    print(f"obiettivo:{args.obiettivo}: {len(risultato['aggiunte'])} righe nuove, {len(risultato['aggiornate'])} aggiornate "
          f"({', '.join(risultato['legami'])})")
    if args.senza_commit:
        return 0
    try:
        committa(vault, args.obiettivo, risultato)
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 1
    print("commit fatto")
    return 0


if __name__ == "__main__":
    sys.exit(main())
