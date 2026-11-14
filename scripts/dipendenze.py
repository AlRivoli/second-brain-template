#!/usr/bin/env python3
"""Marcatori di piano.md (id, dopo, ...) e stato derivato dei task. Modulo puro: niente I/O."""
import re

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
    "stima": (re.compile(r"\d+(?:[.,]\d+)?[hg]"), False),
}
_ULTIMO_TOKEN = re.compile(r"\s(\S+)$")
# A marker-like token left in the text after the trailing markers were split off
_QUASI_MARCATORE = re.compile(r"\b(?:%s):\S*" % "|".join(CHIAVI))
_CASELLA = {" ": "da_fare", "~": "in_corso", "x": "fatto", "X": "fatto"}


def _valore(chiave, grezzo):
    """Parsed value, or None when `grezzo` is not valid for `chiave`."""
    modello, lista = _VALORI[chiave]
    parti = grezzo.split(",") if lista else [grezzo]
    if not all(modello.fullmatch(p) for p in parti):
        return None
    return parti if lista else grezzo


def separa_marcatori(testo):
    """Splits trailing `key:value` markers off a task text: (text without them, {key: value}).

    Scans from the end and stops at the first token that is not a valid marker or whose key was
    already seen, so `https://x.it/a:b` or a marker in the middle of a sentence stay plain text.
    """
    resto = testo.rstrip()
    trovati = {}
    while (m := _ULTIMO_TOKEN.search(resto)):
        chiave, due_punti, grezzo = m.group(1).partition(":")
        valore = _valore(chiave, grezzo) if due_punti and chiave in _VALORI and chiave not in trovati else None
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
    """Checkbox lines of a plan file: {riga (1-based), stato, testo (markers removed), marcatori}."""
    voci = []
    for numero, riga in enumerate(testo.splitlines(), 1):
        if m := VOCE_PIANO.match(riga):
            senza, marcatori = separa_marcatori(m.group(2))
            voci.append({"riga": numero, "stato": _CASELLA[m.group(1)], "testo": senza, "marcatori": marcatori})
    return voci


def problemi(voci):
    """(riga, message saying what to fix) for duplicate ids, `dopo` pointing nowhere, cycles, and marker-like leftovers.

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
    return trovati
