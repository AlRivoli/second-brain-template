"""Lettura di un calendario iCal (.ics) con la sola libreria standard: eventi singoli e ricorrenti in una finestra di date.

Copre ciò che i calendari reali producono: DTSTART/DTEND/DURATION, giorno intero, UTC, fuso con nome (TZID), orario locale, RRULE
(DAILY, WEEKLY con BYDAY, MONTHLY con BYMONTHDAY o BYDAY con ordinale, YEARLY; INTERVAL, COUNT, UNTIL), EXDATE, RECURRENCE-ID
(occorrenza spostata o cancellata). Ciò che non copre non si ignora in silenzio: finisce nella lista degli avvisi, perché una
disponibilità calcolata su eventi mancanti sarebbe sbagliata senza che nessuno lo sappia.
"""
import re
from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9
    ZoneInfo = None

RIGA = re.compile(r'^([A-Za-z0-9-]+)((?:;[^:;"]+(?:=(?:"[^"]*"|[^:;]*))?)*):(.*)$')
GIORNI = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
MAX_PASSI = 20000


def _svolgi(testo):
    return re.sub(r"\r?\n[ \t]", "", testo).splitlines()


def _togli_escape(v):
    return re.sub(r"\\([nN,;\\])", lambda m: "\n" if m.group(1) in "nN" else m.group(1), v)


def _proprieta(riga):
    m = RIGA.match(riga)
    if not m:
        return None
    parametri = {}
    for p in re.findall(r';([^;=]+)=("[^"]*"|[^;]*)', m.group(2)):
        parametri[p[0].upper()] = p[1].strip('"')
    return m.group(1).upper(), parametri, m.group(3)


class Avvisi(list):
    def aggiungi(self, testo):
        if testo not in self:
            self.append(testo)


def _fuso(tzid, avvisi):
    if tzid and ZoneInfo is not None:
        try:
            return ZoneInfo(tzid)
        except Exception:  # fuso sconosciuto, oppure su Windows senza il pacchetto tzdata
            avvisi.aggiungi("fuso orario %s non riconosciuto: gli orari di quegli eventi sono letti come locali" % tzid)
    return None


def _valore_data(v, parametri, avvisi):
    """(datetime naive nell'ora locale del computer, tuttoIlGiorno, fuso dell'evento o None). Gli orari con fuso si portano all'ora locale."""
    v = v.strip()
    if parametri.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", v):
        d = datetime.strptime(v[:8], "%Y%m%d")
        return d, True, None
    base = datetime.strptime(v.rstrip("Z"), "%Y%m%dT%H%M%S")
    if v.endswith("Z"):
        return base.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None), False, timezone.utc
    zona = _fuso(parametri.get("TZID"), avvisi)
    if zona is not None:
        return base.replace(tzinfo=zona).astimezone().replace(tzinfo=None), False, zona
    return base, False, None


def _locale(naive_nel_fuso, zona):
    """Un orario 'a muro' nel fuso dell'evento -> ora locale del computer, senza fuso."""
    if zona is None:
        return naive_nel_fuso
    return naive_nel_fuso.replace(tzinfo=zona).astimezone().replace(tzinfo=None)


def _durata(testo):
    m = re.fullmatch(r"([+-]?)P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", testo.strip())
    if not m:
        return None
    s, w, d, h, mi, se = m.groups()
    t = timedelta(weeks=int(w or 0), days=int(d or 0), hours=int(h or 0), minutes=int(mi or 0), seconds=int(se or 0))
    return -t if s == "-" else t


def _regola(testo):
    return {k.upper(): v for k, _, v in (p.partition("=") for p in testo.split(";") if p)}


def _occorrenze(inizio, regola, fino, avvisi):
    """Date e ore 'a muro' (naive) delle occorrenze di una regola, da `inizio` fino a `fino` (esclusa)."""
    freq = regola.get("FREQ", "")
    if freq not in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY") or any(k in regola for k in ("BYSETPOS", "BYWEEKNO", "BYYEARDAY", "BYHOUR", "BYMINUTE")):
        avvisi.aggiungi("ripetizione non supportata (%s): si vede solo la prima occorrenza" % (testo_regola(regola)))
        yield inizio
        return
    passo = max(1, int(regola.get("INTERVAL", 1)))
    conta = int(regola["COUNT"]) if "COUNT" in regola else None
    limite = None
    if "UNTIL" in regola:  # UNTIL è una data (tutto quel giorno) o un istante
        u = regola["UNTIL"]
        limite = datetime.strptime(u[:8], "%Y%m%d") + timedelta(days=1) if len(u) == 8 else datetime.strptime(u.rstrip("Z"), "%Y%m%dT%H%M%S")
    ora = inizio.time()
    n = 0
    k = 0
    while k < MAX_PASSI:
        if freq == "DAILY":
            giorni = [inizio.date() + timedelta(days=k * passo)]
        elif freq == "WEEKLY":
            lunedi = inizio.date() - timedelta(days=inizio.weekday()) + timedelta(weeks=k * passo)
            by = [b[-2:] for b in regola.get("BYDAY", GIORNI[inizio.weekday()]).split(",")]
            giorni = sorted(lunedi + timedelta(days=GIORNI.index(b)) for b in by if b in GIORNI)
        elif freq == "MONTHLY":
            mese = inizio.month - 1 + k * passo
            anno, mese = inizio.year + mese // 12, mese % 12 + 1
            giorni = _giorni_del_mese(anno, mese, regola, inizio)
        else:
            anno = inizio.year + k * passo
            giorni = _giorni_del_mese(anno, inizio.month, regola, inizio) if "BYDAY" in regola else \
                [d for d in [_data_sicura(anno, inizio.month, inizio.day)] if d]
        for g in giorni:
            d = datetime.combine(g, ora)
            if d < inizio:
                continue
            if (limite is not None and d >= limite) or d >= fino:
                return
            n += 1
            yield d
            if conta is not None and n >= conta:
                return
        k += 1
        if giorni and datetime.combine(giorni[-1], ora) >= fino:
            return
        if not giorni and k > 400:
            return
    avvisi.aggiungi("ripetizione troppo lunga: le occorrenze oltre il limite non sono state lette")


def testo_regola(regola):
    return ";".join("%s=%s" % kv for kv in regola.items())


def _data_sicura(anno, mese, giorno):
    try:
        return date(anno, mese, giorno)
    except ValueError:
        return None


def _giorni_del_mese(anno, mese, regola, inizio):
    if "BYDAY" in regola:
        out = []
        for b in regola["BYDAY"].split(","):
            m = re.fullmatch(r"([+-]?\d)?(MO|TU|WE|TH|FR|SA|SU)", b)
            if not m:
                continue
            ordinale, nome = m.groups()
            tutti = [date(anno, mese, d) for d in range(1, 32) if _data_sicura(anno, mese, d) and date(anno, mese, d).weekday() == GIORNI.index(nome)]
            if ordinale is None:
                out += tutti
            elif tutti and -len(tutti) <= int(ordinale) <= len(tutti) and int(ordinale) != 0:
                out.append(tutti[int(ordinale) - 1 if int(ordinale) > 0 else int(ordinale)])
        return sorted(out)
    giorni = [int(x) for x in regola.get("BYMONTHDAY", str(inizio.day)).split(",")]
    return sorted(d for d in (_data_sicura(anno, mese, g) for g in giorni) if d)


def eventi(testo, da, a):
    """([evento], [avvisi]) per la finestra [da, a) in ora locale senza fuso. evento: {titolo, inizio, fine, tuttoIlGiorno}."""
    avvisi = Avvisi()
    blocchi, corrente = [], None
    for riga in _svolgi(testo):
        if riga.upper() == "BEGIN:VEVENT":
            corrente = []
        elif riga.upper() == "END:VEVENT" and corrente is not None:
            blocchi.append(corrente)
            corrente = None
        elif corrente is not None:
            p = _proprieta(riga)
            if p:
                corrente.append(p)
    base, spostate = [], {}
    for props in blocchi:
        d = {}
        for nome, par, valore in props:
            d.setdefault(nome, []).append((par, valore))
        if d.get("STATUS", [({}, "")])[0][1].upper() == "CANCELLED" and "RECURRENCE-ID" not in d:
            continue
        if "DTSTART" not in d:
            continue
        try:
            (inizio, intero, zona) = _valore_data(d["DTSTART"][0][1], d["DTSTART"][0][0], avvisi)
            if "DTEND" in d:
                fine = _valore_data(d["DTEND"][0][1], d["DTEND"][0][0], avvisi)[0]
            elif "DURATION" in d and _durata(d["DURATION"][0][1]):
                fine = inizio + _durata(d["DURATION"][0][1])
            else:
                fine = inizio + (timedelta(days=1) if intero else timedelta())
        except ValueError:
            avvisi.aggiungi("un evento con una data illeggibile è stato saltato")
            continue
        titolo = _togli_escape(d.get("SUMMARY", [({}, "")])[0][1]) or "(senza titolo)"
        voce = {"uid": d.get("UID", [({}, "")])[0][1], "titolo": titolo, "inizio": inizio, "fine": fine, "tuttoIlGiorno": intero, "zona": zona,
                "par": d["DTSTART"][0][0], "cancellato": d.get("STATUS", [({}, "")])[0][1].upper() == "CANCELLED"}
        if "RECURRENCE-ID" in d:
            try:
                spostate[(voce["uid"], _valore_data(d["RECURRENCE-ID"][0][1], d["RECURRENCE-ID"][0][0], avvisi)[0])] = voce
            except ValueError:
                pass
            continue
        voce["regola"] = _regola(d["RRULE"][0][1]) if "RRULE" in d else None
        voce["esclusi"] = set()
        for par, valore in d.get("EXDATE", []):
            for v in valore.split(","):
                try:
                    voce["esclusi"].add(_valore_data(v, par, avvisi)[0])
                except ValueError:
                    pass
        base.append(voce)

    fuori = []
    for e in base:
        durata = e["fine"] - e["inizio"]
        if e["regola"]:
            zona = e["zona"]
            # la regola si ripete sull'ora a muro del fuso dell'evento, così un orario resta alle 9 anche a cavallo del cambio dell'ora
            muro = e["inizio"].replace(tzinfo=None) if zona is None else e["inizio"].astimezone().astimezone(zona).replace(tzinfo=None)
            inizi = [_locale(m, zona) for m in _occorrenze(muro, e["regola"], a + timedelta(days=2), avvisi)]
        else:
            inizi = [e["inizio"]]
        for i in inizi:
            if i in e["esclusi"]:
                continue
            mossa = spostate.get((e["uid"], i))
            if mossa is not None:
                if mossa["cancellato"]:
                    continue
                i, durata_occ, titolo = mossa["inizio"], mossa["fine"] - mossa["inizio"], mossa["titolo"]
            else:
                durata_occ, titolo = durata, e["titolo"]
            if i < a and i + durata_occ > da or (durata_occ == timedelta() and da <= i < a):
                fuori.append({"titolo": titolo, "inizio": i, "fine": i + durata_occ, "tuttoIlGiorno": e["tuttoIlGiorno"]})
    fuori.sort(key=lambda x: (x["inizio"], x["titolo"]))
    return fuori, list(avvisi)
