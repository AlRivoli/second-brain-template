"""Inventario di cosa Claude Code carica: skill, plugin, hook e MCP, globali e per progetto.

Sola lettura. Restituisce solo nomi, versioni e date: mai env, headers, url o args dei server MCP, perché possono
contenere token (vedi test_configurazione_senza_segreti).
"""
import json
import os
import re
import shutil
from pathlib import Path

FRONTMATTER_VERSIONE = re.compile(r"^version:\s*['\"]?([^'\"\n]+)", re.M)


def _json(percorso):
    try:
        dati = json.loads(Path(percorso).read_text(encoding="utf-8"))
        return dati if isinstance(dati, dict) else {}
    except (OSError, ValueError):
        return {}


def _nomi_mcp(percorso):
    """Nomi dei server di un .mcp.json o di un blocco mcpServers; i valori non si leggono."""
    dati = _json(percorso)
    server = dati.get("mcpServers", dati)
    return sorted(k for k, v in server.items() if isinstance(v, dict))


def _eventi_hook(dati):
    return sorted(dati.get("hooks", {}).keys()) if isinstance(dati.get("hooks"), dict) else []


def _cartelle(percorso):
    p = Path(percorso)
    return sorted(c.name for c in p.iterdir() if c.is_dir() and not c.name.startswith(".")) if p.is_dir() else []


def _file_md(percorso):
    p = Path(percorso)
    return sorted(f.stem for f in p.glob("*.md")) if p.is_dir() else []


def _versione_skill(cartella):
    try:
        testa = (Path(cartella) / "SKILL.md").read_text(encoding="utf-8", errors="replace")[:1500]
    except OSError:
        return None
    m = FRONTMATTER_VERSIONE.search(testa)
    return m.group(1).strip() if m else None


def _skill_locali(home, lock, override):
    out = []
    base = home / ".claude" / "skills"
    for nome in _cartelle(base):
        if nome == "synced":
            continue
        voce = base / nome
        if voce.is_symlink() and nome in lock:
            origine, tracciata = lock[nome].get("source", "github"), True
            aggiornata = (lock[nome].get("updatedAt") or "")[:10]
            hash_lock = (lock[nome].get("skillFolderHash") or "")[:7]
        else:
            origine, tracciata, aggiornata, hash_lock = "installata a mano", False, "", ""
        out.append({
            "nome": nome, "origine": origine, "tracciata": tracciata, "aggiornata": aggiornata,
            "hash": hash_lock, "versione": _versione_skill(voce), "attiva": override.get(nome) != "off",
            "lockObsoleto": not voce.is_symlink() and nome in lock,
        })
    return out


def _hook_e_mcp(percorso):
    """Eventi hook e nomi MCP di un plugin: dichiarati in plugin.json (percorso o blocco) o nei file predefiniti."""
    info = _json(percorso / ".claude-plugin" / "plugin.json")
    hook, mcp = info.get("hooks"), info.get("mcpServers")
    dati_hook = hook if isinstance(hook, dict) else _json(percorso / (hook if isinstance(hook, str) else "hooks/hooks.json"))
    if isinstance(mcp, dict):
        nomi = sorted(k for k, v in mcp.items() if isinstance(v, dict))
    else:
        nomi = _nomi_mcp(percorso / (mcp if isinstance(mcp, str) else ".mcp.json"))
    return _eventi_hook(dati_hook if "hooks" in dati_hook else {"hooks": dati_hook}), nomi


def _plugin_locali(home, abilitati):
    out = []
    for chiave, voci in _json(home / ".claude" / "plugins" / "installed_plugins.json").get("plugins", {}).items():
        nome, _, mercato = chiave.partition("@")
        for v in voci[:1]:
            percorso = Path(v.get("installPath", ""))
            hook, mcp = _hook_e_mcp(percorso)
            out.append({
                "nome": nome, "mercato": mercato, "ambito": v.get("scope"), "versione": v.get("version"),
                "aggiornato": (v.get("lastUpdated") or "")[:10], "attivo": abilitati.get(chiave, False),
                "progetto": v.get("projectPath"),
                "skill": _cartelle(percorso / "skills"),
                "hook": hook, "mcp": mcp,
            })
    return sorted(out, key=lambda p: (not p["attivo"], p["nome"]))


def _plugin_sincronizzati(home):
    """Plugin e skill di claude.ai sincronizzati in locale: non hanno una versione locale da aggiornare."""
    plugin = []
    for radice in sorted((home / ".claude" / "plugins" / "synced").glob("*_*")):
        if not radice.is_dir():
            continue
        for cartella in sorted(c for c in radice.iterdir() if c.is_dir() and (c / ".claude-plugin").is_dir()):
            info = _json(cartella / ".claude-plugin" / "plugin.json")
            plugin.append({"nome": info.get("name") or cartella.name, "versione": info.get("version"),
                           "mcp": _nomi_mcp(cartella / ".mcp.json")})
    skill = []
    for radice in sorted((home / ".claude" / "skills" / "synced").glob("*_*")):
        skill += _cartelle(radice)
    return {"plugin": plugin, "skill": sorted(set(skill))}


def globale(home=None):
    home = home or Path.home()
    impostazioni = _json(home / ".claude" / "settings.json")
    lock = _json(home / ".agents" / ".skill-lock.json").get("skills", {})
    return {
        "skill": _skill_locali(home, lock, impostazioni.get("skillOverrides", {})),
        "plugin": _plugin_locali(home, impostazioni.get("enabledPlugins", {})),
        "sincronizzati": _plugin_sincronizzati(home),
        "mcp": sorted(_json(home / ".claude.json").get("mcpServers", {}).keys()),
        "hook": _eventi_hook(impostazioni),
    }


def progetto(radice):
    radice = Path(radice)
    claude = radice / ".claude"
    impostazioni = [_json(claude / "settings.json"), _json(claude / "settings.local.json")]
    return {
        "esiste": radice.is_dir(),
        "skill": sorted(set(_cartelle(claude / "skills") + _cartelle(radice / ".agents" / "skills"))),
        "comandi": _file_md(claude / "commands"),
        "agenti": _file_md(claude / "agents"),
        "plugin": sorted({k: v for i in impostazioni for k, v in i.get("enabledPlugins", {}).items()}.items()),
        "hook": sorted({e for i in impostazioni for e in _eventi_hook(i)}),
        "mcp": sorted(set(_nomi_mcp(radice / ".mcp.json")) | {k for i in impostazioni for k in i.get("mcpServers", {})}),
    }


def raccogli(progetti, controllo, home=None):
    """progetti: [(nome, percorso)]. controllo: contenuto dell'ultimo controllo-skill.json o None."""
    out = {"globale": globale(home), "progetti": [{"nome": n, **progetto(p)} for n, p in progetti], "controllo": controllo}
    stati = {s["nome"]: s for s in (controllo or {}).get("skill", [])}
    for s in out["globale"]["skill"]:
        s["controllo"] = stati.get(s["nome"])
    return out


def imposta_interruttore(tipo, nome, attivo, home=None):
    """Attiva o disattiva una skill (skillOverrides) o un plugin (enabledPlugins) in ~/.claude/settings.json.
    Ne tiene una copia in settings.json.bak. LookupError: nome non installato. ValueError: tipo o file non validi."""
    home = home or Path.home()
    file = home / ".claude" / "settings.json"
    try:
        dati = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError("settings.json non leggibile") from e
    if not isinstance(dati, dict):
        raise ValueError("settings.json non valido")
    if tipo == "skill":
        if nome not in [s["nome"] for s in _skill_locali(home, {}, {})]:
            raise LookupError(nome)
        override = dati.setdefault("skillOverrides", {})
        if attivo:
            override.pop(nome, None)
        else:
            override[nome] = "off"
    elif tipo == "plugin":
        if nome not in ["%s@%s" % (p["nome"], p["mercato"]) for p in _plugin_locali(home, {})]:
            raise LookupError(nome)
        dati.setdefault("enabledPlugins", {})[nome] = bool(attivo)
    else:
        raise ValueError(tipo)
    shutil.copy2(file, file.with_name(file.name + ".bak"))
    provvisorio = file.with_name(file.name + ".tmp")
    provvisorio.write_text(json.dumps(dati, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(provvisorio, file)
