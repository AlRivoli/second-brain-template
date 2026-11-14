#!/usr/bin/env python3
"""Marcatori di piano.md (id, dopo, ...) e stato derivato dei task. Modulo puro: niente I/O."""
import math
import re
import unicodedata
from datetime import date, timedelta

# `(.*\S)` instead of a lazy `(.+?)\s*$`: the lazy form re-scans a whitespace run at every step (quadratic)
VOCE_PIANO = re.compile(r"^- \[( |x|X|~)\] (.*\S)\s*$")
CHIAVI = ("id", "dopo", "obiettivo", "repo", "chi", "stima")

_ID = r"[a-z0-9][a-z0-9-]{0,39}"
_REPO = r"[A-Za-z0-9._-]{1,60}"
# key -> (pattern for one value item, is a comma-separated list)
_VALORI = {
    "id": (re.compile(_ID), False),
    "dopo": (re.compile(_ID), True),
    "obiettivo": (re.compile(_ID), False),
    "repo": (re.compile(_REPO), True),
    "chi": (re.compile(r"te"), False),
    # bounded: an unbounded number would be float('inf') hours and break the due-date walk; a longer value stays text
    "stima": (re.compile(r"\d{1,4}(?:[.,]\d{1,2})?[hg]"), False),
}
# One goal line of docs/obiettivi.md: `- slug: titolo`
_RIGA_OBIETTIVO = re.compile(r"^- (%s):(.*)$" % _ID)
_TITOLO_MAX = 120
_ULTIMO_TOKEN = re.compile(r"\s(\S+)$")
# A marker-like token left in the text after the trailing markers were split off
_QUASI_MARCATORE = re.compile(r"\b(?:%s):\S*" % "|".join(CHIAVI))
# Goal markers of docs/obiettivi.md, same trailing rule as the task markers
GIORNI = ("lun", "mar", "mer", "gio", "ven", "sab", "dom")  # position = date.weekday()
_GIORNI_DEFAULT = frozenset(range(5))
_ORE_GIORNO_DEFAULT = 6.0
_PIANO = re.compile(r"[A-Za-z0-9._/-]{1,200}")
# `(?=\S|$)`: a bare trailing `giorni:` is a leftover, `Nuovo piano: rilascio` is prose
_QUASI_MARCATORE_OBIETTIVO = re.compile(r"\b(scadenza|giorni|piano):(?=\S|$)(\S*)")
_AIUTO_OBIETTIVO = {
    "scadenza": "scadenza: non è una data valida: scrivi `scadenza:AAAA-MM-GG` in fondo alla riga",
    "giorni": "giorni: non è valido: scrivi `giorni:` con lun,mar,mer,gio,ven,sab,dom separati da virgole, "
              "oppure `giorni:tutti`; intanto vale il calendario del vault",
    "piano": "piano: non è valido: scrivi un percorso relativo alla radice del repo, senza spazi né `..` (es. `piano:docs/piano.md`)",
}
# Upper bound of the calendar walk, so a sparse calendar cannot walk back for ever
_FINESTRA_GIORNI = 366 * 7
_CASELLA = {" ": "da_fare", "~": "in_corso", "x": "fatto", "X": "fatto"}
# Same rule as the dashboard server: the first `#tag` of the text names the project
_TAG = re.compile(r"(?:^|\s)#([A-Za-z][\w-]*)")


def _valore(chiave, grezzo):
    """Parsed value of a task marker, or None when `chiave` is not a task key or `grezzo` is not valid for it."""
    if chiave not in _VALORI:
        return None
    modello, lista = _VALORI[chiave]
    parti = grezzo.split(",") if lista else [grezzo]
    if not all(modello.fullmatch(p) for p in parti):
        return None
    return parti if lista else grezzo


def separa_marcatori(testo, valore_di=_valore):
    """Splits trailing `key:value` markers off a task text: (text without them, {key: value}).

    Scans from the end and stops at the first token that is not a valid marker or whose key was
    already seen, so `https://x.it/a:b` or a marker in the middle of a sentence stay plain text.
    `valore_di(chiave, grezzo)` parses one marker, None when invalid: the task keys by default, the goal keys for obiettivi.md.
    """
    resto = testo.rstrip()
    trovati = {}
    while (m := _ULTIMO_TOKEN.search(resto)):
        chiave, due_punti, grezzo = m.group(1).partition(":")
        valore = valore_di(chiave, grezzo) if due_punti and chiave not in trovati else None
        if valore is None:
            break
        trovati[chiave] = valore
        resto = resto[:m.start()].rstrip()
    return resto, trovati


def _id_unici(voci):
    """(id -> index for ids used once, set of ids used more than once)."""
    visti, doppi = {}, set()
    for i, v in enumerate(voci):
        id_ = v["marcatori"].get("id")
        if id_ is None:
            continue
        if id_ in visti or id_ in doppi:
            doppi.add(id_)
            visti.pop(id_, None)
        else:
            visti[id_] = i
    return visti, doppi


def _nodi_in_ciclo(archi):
    """Indices that sit on a dependency cycle (self-loops included), given adjacency lists.

    Iterative Tarjan SCC: a node is on a cycle iff its component has more than one node or it
    points to itself. A plain three-colour back-edge scan would miss nodes reached through a
    cross edge, so the components are used instead. O(V+E) time, O(V) space, no recursion.
    """
    n = len(archi)
    ordine, basso, nello_stack = [-1] * n, [0] * n, [False] * n
    stack, in_ciclo, contatore = [], set(), 0
    for radice in range(n):
        if ordine[radice] != -1:
            continue
        ordine[radice] = basso[radice] = contatore
        contatore += 1
        stack.append(radice)
        nello_stack[radice] = True
        lavoro = [(radice, iter(archi[radice]))]
        while lavoro:
            v, vicini = lavoro[-1]
            for w in vicini:
                if ordine[w] == -1:
                    ordine[w] = basso[w] = contatore
                    contatore += 1
                    stack.append(w)
                    nello_stack[w] = True
                    lavoro.append((w, iter(archi[w])))
                    break
                if nello_stack[w]:
                    basso[v] = min(basso[v], ordine[w])
            else:
                lavoro.pop()
                if lavoro:
                    padre = lavoro[-1][0]
                    basso[padre] = min(basso[padre], basso[v])
                if basso[v] == ordine[v]:
                    componente = []
                    while True:
                        w = stack.pop()
                        nello_stack[w] = False
                        componente.append(w)
                        if w == v:
                            break
                    if len(componente) > 1 or v in archi[v]:
                        in_ciclo.update(componente)
    return in_ciclo


def stati_derivati(voci):
    """Derived state per task, same order as `voci`.

    Precedence: fatto > errore (own) > open dependencies (in_attesa / incoerente) > pronto / in_corso.
    A dependency is met only by a `[x]` task; a task depending on one in error is not in error
    itself, it just keeps waiting. `errore` is reported even when the task is `fatto`.
    """
    unici, doppi = _id_unici(voci)
    deps = [[unici[r] for r in dict.fromkeys(v["marcatori"].get("dopo", ())) if r in unici] for v in voci]
    # Only uniquely-identified tasks can be the target of an edge, so only they can close a cycle.
    in_ciclo = _nodi_in_ciclo([d if v["marcatori"].get("id") in unici else [] for v, d in zip(voci, deps)])
    risultato = []
    for i, v in enumerate(voci):
        m = v["marcatori"]
        mancanti = [r for r in dict.fromkeys(m.get("dopo", ())) if r not in unici]
        aspetta = [j for j in deps[i] if voci[j]["stato"] != "fatto"]
        if m.get("id") in doppi:
            errore = "id_doppio"
        elif mancanti:
            errore = "riferimento"
        elif i in in_ciclo:
            errore = "ciclo"
        else:
            errore = None
        if v["stato"] == "fatto":
            derivato = "fatto"
        elif errore:
            derivato = "errore"
        elif aspetta:
            derivato = "incoerente" if v["stato"] == "in_corso" else "in_attesa"
        else:
            derivato = "in_corso" if v["stato"] == "in_corso" else "pronto"
        risultato.append({"derivato": derivato, "aspetta": aspetta, "errore": errore, "mancanti": mancanti})
    return risultato


def leggi_voci(testo):
    """Checkbox lines of a plan file: {riga (1-based), stato, testo (markers removed), tag (lowercase or None), marcatori}."""
    voci = []
    for numero, riga in enumerate(testo.splitlines(), 1):
        if m := VOCE_PIANO.match(riga):
            senza, marcatori = separa_marcatori(m.group(2))
            tag = _TAG.search(senza)
            voci.append({"riga": numero, "stato": _CASELLA[m.group(1)], "testo": senza,
                         "tag": tag.group(1).lower() if tag else None, "marcatori": marcatori})
    return voci


def nomi_repo(percorsi):
    """Short names of a project's `Repo` lines: ({name: path} in order, [names used by more than one path]).

    The short name is the last folder of the path, with a slash or a backslash separator, on every OS. `nessuno`, blank lines,
    roots and paths ending in `.` or `..` are not repos, and the same path repeated counts once. A duplicate name is left out of the dict: it cannot be told apart, so it is
    never allowed. O(n) time and space.
    """
    per_nome, doppi = {}, []
    for p in dict.fromkeys(p.strip() for p in percorsi):
        if not p or p == "nessuno":
            continue
        nome = re.split(r"[\\/]", p.rstrip("\\/"))[-1]  # not Path().name: that keeps a whole Windows path on POSIX
        # A root (`/`, `C:\`, `C:`) or a path ending in `.` or `..` names no folder of its own: it is never a candidate
        if not nome or nome in (".", "..") or nome.endswith(":") or nome in doppi:
            continue
        if nome in per_nome:
            del per_nome[nome]
            doppi.append(nome)
        else:
            per_nome[nome] = p
    return per_nome, doppi


def percorso_piano_valido(valore):
    """A `piano:` path: relative to the repo root, no spaces, no `..`, not absolute (`C:` fails the charset)."""
    return bool(_PIANO.fullmatch(valore)) and not valore.startswith("/") and ".." not in valore


def _data(grezzo):
    # The ASCII regex first: from Python 3.11 fromisoformat also takes `20261204`
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", grezzo):
        return None
    try:
        return date.fromisoformat(grezzo)
    except ValueError:
        return None


def _giorni(grezzo):
    """`tutti` or a comma list of GIORNI -> frozenset of weekdays (0 = Monday), None when invalid."""
    if grezzo == "tutti":
        return frozenset(range(7))
    parti = grezzo.split(",")
    return frozenset(GIORNI.index(p) for p in parti) if all(p in GIORNI for p in parti) else None


_VALORI_OBIETTIVO = {"scadenza": _data, "giorni": _giorni, "piano": lambda g: g if percorso_piano_valido(g) else None}


def _valore_obiettivo(chiave, grezzo):
    leggi = _VALORI_OBIETTIVO.get(chiave)
    return leggi(grezzo) if leggi else None


def leggi_obiettivi(testo):
    """Goal lines of docs/obiettivi.md: ({slug: goal} in file order, [(riga, message saying what to fix)]).

    A line is `- slug: titolo [scadenza:AAAA-MM-GG] [giorni:<lista>|tutti] [piano:<percorso>]`; a goal is
    {"titolo", "scadenza": date|None, "giorni": frozenset of weekdays|None, "piano": str|None}, None meaning not given
    (for `giorni`, use the vault calendar). Only lines starting with `- ` count; headings and prose are ignored.
    A line with a title problem is reported and not defined, except a duplicate slug, which keeps its first definition.
    A goal marker left in the title (invalid value, repeated, or not at the end) stopped the scan, like the task
    leftovers: it is reported, but the goal stays defined, so the tasks pointing to it are not flagged as well.
    O(n) time and space.
    """
    obiettivi, trovati, righe = {}, [], {}
    # A BOM left by an editor would hide line 1 from the `- ` check below
    for numero, riga in enumerate(testo.removeprefix("\ufeff").splitlines(), 1):
        if not riga.startswith("- "):
            continue
        m = _RIGA_OBIETTIVO.match(riga.rstrip())
        if not m:
            trovati.append((numero, "riga non valida: scrivi `- slug: titolo`"))
            continue
        slug = m.group(1)
        titolo, marcatori = separa_marcatori(m.group(2), _valore_obiettivo)
        titolo = titolo.strip()
        if slug in righe:
            trovati.append((numero, f"obiettivo:{slug} è già definito alla riga {righe[slug]}: usa uno slug diverso"))
        elif not titolo:
            trovati.append((numero, f"obiettivo:{slug} senza titolo: scrivi `- {slug}: titolo`"))
        elif len(titolo) > _TITOLO_MAX:
            trovati.append((numero, f"il titolo di {slug} ha {len(titolo)} caratteri: al massimo {_TITOLO_MAX}"))
        elif any(unicodedata.category(c) in ("Cc", "Cf") for c in titolo):  # bidi overrides (U+202E, U+2066-2069) could spoof the title
            trovati.append((numero, "titolo con caratteri di controllo o di direzione: toglili"))
        else:
            obiettivi[slug] = {"titolo": titolo, **{k: marcatori.get(k) for k in _VALORI_OBIETTIVO}}
            righe[slug] = numero
            if avanzi := _QUASI_MARCATORE_OBIETTIVO.findall(titolo):
                chiave, grezzo = avanzi[-1]  # the last leftover is the token that stopped the scan
                # the raw value is not echoed: the message names the key and how to write it
                messaggio = (_AIUTO_OBIETTIVO[chiave] if _valore_obiettivo(chiave, grezzo) is None else
                             f"{chiave}: non è in fondo alla riga o è ripetuto: scrivi ogni marcatore una volta sola, in fondo alla riga")
                # fail-open, like the task leftovers: the markers before the stopper are lost too (a lost `scadenza:` means no deadline)
                if persi := list(dict.fromkeys(k for k, _ in avanzi[:-1])):
                    messaggio += "; finché non lo correggi non si leggono neanche " + ", ".join(f"`{k}:`" for k in persi)
                trovati.append((numero, messaggio))
    return obiettivi, trovati


def impostazioni_piano(config):
    """Vault work calendar from config.json `piano`: ({"ore_giorno": float, "giorni": frozenset}, [problems]).

    Defaults: 6 hours a day, Monday to Friday. A missing value takes its default silently, an invalid one takes
    its default and is reported. The written value is never echoed.
    """
    impostazioni = {"ore_giorno": _ORE_GIORNO_DEFAULT, "giorni": _GIORNI_DEFAULT}
    piano = config.get("piano") if isinstance(config, dict) else None
    if piano is None:
        return impostazioni, []
    if not isinstance(piano, dict):
        return impostazioni, ["piano deve essere un oggetto con ore_giorno e giorni_lavoro: uso 6 ore e lun-ven"]
    trovati = []
    ore = piano.get("ore_giorno")
    if ore is not None:
        # bool is an int subclass, so `true` would pass as 1 hour; NaN fails the range check by itself
        if isinstance(ore, (int, float)) and not isinstance(ore, bool) and 1 <= ore <= 24:
            impostazioni["ore_giorno"] = float(ore)
        else:
            trovati.append("piano.ore_giorno deve essere un numero tra 1 e 24: uso 6")
    giorni = piano.get("giorni_lavoro")
    if giorni is not None:
        if isinstance(giorni, list) and giorni and all(isinstance(g, str) and g in GIORNI for g in giorni):
            impostazioni["giorni"] = frozenset(GIORNI.index(g) for g in giorni)
        else:
            trovati.append("piano.giorni_lavoro deve essere una lista non vuota di lun, mar, mer, gio, ven, sab, dom: uso lun-ven")
    return impostazioni, trovati


def ore_stima(valore, ore_giorno):
    """Hours of a `stima:` value the marker scan already validated (`9h`, `1,5g`); None when the task has none."""
    if valore is None:
        return None
    n = float(valore[:-1].replace(",", "."))
    return n * ore_giorno if valore.endswith("g") else n


def date_obiettivo(voci, stati, slug, scadenza, giorni, ore_giorno, oggi):
    """Computed due dates of a goal: never written in the plan.

    `voci` and `stati` come from leggi_voci/stati_derivati, or are the server's tasks with `marcatori` and `aspetta`.
    Only the goal's open tasks not in error count (a cycle is an error), with the `dopo` edges between them. The tail
    (coda) of a task is the longest sum of estimates along its open successors in the goal, itself excluded;
    `entro` = deadline minus ceil(tail / ore_giorno) working days of `giorni` (empty = Monday to Friday), and a deadline
    on a non-working day moves to the working day before. A task without estimate counts 0 hours and is in senzaStima.
    Assumption: independent tasks proceed in parallel, so the days needed are those of the longest chain.

    Returns {"entro": {index: date}, "senzaStima": [indices], "giorniNecessari", "giorniDisponibili" (today to the
    deadline, both included), "aRischio", "scaduto"}. Backward topological pass (Kahn from the sinks):
    O(N + V + E) time and O(V) space for N plan tasks, V open goal tasks and E edges among them, plus a calendar walk of
    at most 366 weeks.
    """
    giorni = giorni or _GIORNI_DEFAULT
    aperti, scaduto = [], False
    for i, (v, s) in enumerate(zip(voci, stati)):
        if v["marcatori"].get("obiettivo") != slug or s["derivato"] == "fatto":
            continue
        scaduto = scadenza < oggi  # an open task in error is still open work past the deadline
        if s["derivato"] != "errore":
            aperti.append(i)
    dentro = set(aperti)
    # `aspetta` holds the not-done unique predecessors, already deduplicated: keep those inside the goal
    prima = {i: [j for j in stati[i]["aspetta"] if j in dentro] for i in aperti}
    successori = dict.fromkeys(aperti, 0)
    for i in aperti:
        for j in prima[i]:
            successori[j] += 1
    ore, senza_stima = {}, []
    for i in aperti:
        h = ore_stima(voci[i]["marcatori"].get("stima"), ore_giorno)
        if h is None:
            senza_stima.append(i)
        ore[i] = h or 0.0
    coda = dict.fromkeys(aperti, 0.0)
    pronti, ordinati = [i for i in aperti if not successori[i]], []
    while pronti:
        n = pronti.pop()
        ordinati.append(n)  # a task never popped would sit on a cycle: it gets no date
        for p in prima[n]:
            coda[p] = max(coda[p], ore[n] + coda[n])
            successori[p] -= 1
            if not successori[p]:
                pronti.append(p)

    def in_giorni(h):
        # rounded first: a sum of decimal hours like 6.000000000000001 is still one day
        return math.ceil(round(h / ore_giorno, 9))

    necessari = max((in_giorni(ore[i] + coda[i]) for i in ordinati), default=0)
    # lavorativi[k] = the k-th working day before the deadline (k = 0: the deadline or the working day before it)
    lavorativi, giorno = [], scadenza
    for _ in range(_FINESTRA_GIORNI):
        if giorno.weekday() in giorni:
            lavorativi.append(giorno)
            if len(lavorativi) > necessari:
                break
        if giorno == date.min:
            break
        giorno -= timedelta(days=1)
    lavorativi = lavorativi or [scadenza]  # only a deadline in the first days of year 1 finds no working day
    # ponytail: past the 366-week window entro is clamped to the earliest day found; such a chain is years long
    entro = {i: lavorativi[min(in_giorni(coda[i]), len(lavorativi) - 1)] for i in ordinati}
    if scadenza < oggi:
        disponibili = 0
    else:
        settimane, resto = divmod((scadenza - oggi).days + 1, 7)
        disponibili = settimane * len(giorni) + sum((oggi.weekday() + k) % 7 in giorni for k in range(resto))
    return {"entro": entro, "senzaStima": senza_stima, "giorniNecessari": necessari, "giorniDisponibili": disponibili,
            "aRischio": scaduto or necessari > disponibili, "scaduto": scaduto}


def problemi(voci, obiettivi=None, repo=None):
    """(riga, message saying what to fix) for duplicate ids, `dopo` pointing nowhere, cycles, and marker-like leftovers.

    With `obiettivi` (the slugs defined in docs/obiettivi.md, possibly empty) it also flags `obiettivo:` markers
    that name an undefined slug; `None` skips that check.

    With `repo` ({project tag: set of repo short names}, possibly empty) it flags `repo:` markers on a task whose
    tag is not a project, and names that are not a repo of the task's project; `None` skips that check.

    A malformed trailing token stops the marker scan, so the markers before it stay plain text: the task silently
    loses its `dopo:` or `chi:te` and reads as ready. That is fail-open, so it is reported.
    """
    stati = stati_derivati(voci)
    trovati = []
    for v, s in zip(voci, stati):
        m = v["marcatori"]
        if s["errore"] == "id_doppio":
            trovati.append((v["riga"], f"id:{m['id']} è usato da più task: dai a ciascuno un id diverso"))
        if s["mancanti"]:
            elenco = ", ".join(s["mancanti"])
            trovati.append((v["riga"], f"dopo:{elenco} non corrisponde a nessun task con id unico: correggi l'id o togli il riferimento"))
        if s["errore"] == "ciclo":
            trovati.append((v["riga"], "le dipendenze dopo: formano un ciclo: togli almeno un riferimento del giro"))
        if resto := _QUASI_MARCATORE.search(v["testo"]):
            trovati.append((v["riga"], f"`{resto.group()}` non è un marcatore valido: scrivi i marcatori in fondo alla riga, "
                                       "come `chiave:valore` separati da spazi e senza niente dopo (es. `chi:te`)"))
        slug = v["marcatori"].get("obiettivo")
        if obiettivi is not None and slug is not None and slug not in obiettivi:
            trovati.append((v["riga"], f"obiettivo:{slug} non è definito in docs/obiettivi.md: aggiungi `- {slug}: <titolo>`"))
        nomi = m.get("repo")
        if repo is None or not nomi:
            continue
        tag = v.get("tag")
        if tag not in repo:
            trovati.append((v["riga"], f"repo:{','.join(nomi)} su un task senza progetto: aggiungi il #tag del progetto o togli repo:"))
            continue
        for nome in dict.fromkeys(nomi):
            if nome not in repo[tag]:
                elenco = ", ".join(sorted(repo[tag])) or "nessuno, il progetto non ha repo"
                trovati.append((v["riga"], f"repo:{nome} non è un repo di {tag}: usa uno di {elenco} "
                                           "(nome della cartella nella riga Repo dello STATE)"))
    return trovati
