"""
PoE Assistant - unofficial item-comparison HUD for Path of Exile 1.

Loads your character from the public PoE character API, calculates it with Path of Building's
own calculation engine (pob_engine.py, downloaded and kept up to date by pob_updater.py) and,
when you copy an item in game (Ctrl+C, or Ctrl+Alt+C for craft suggestions), tells you whether
it is an upgrade for your build.

Not affiliated with or endorsed by Grinding Gear Games.
Errors are written to poe_assistant.log (see the data folder shown in the settings panel).
"""
import os
import sys
import json
import shutil
import time
import queue
import threading
import traceback
import urllib.parse
import tkinter as tk

import requests
import pyperclip
import customtkinter as ctk

APP_VERSION = "0.1.0"
TESTED_POB = "2.68"            # Path of Building version the app was developed against
USER_AGENT = f"PoEAssistant/{APP_VERSION} (unofficial item comparison tool)"


def get_data_dir():
    """Writable per-user folder for settings, log and the Path of Building data."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "PoE Assistant")
    os.makedirs(path, exist_ok=True)
    return path


SCRIPT_DIR = os.path.dirname(os.path.abspath(sys.argv[0] if getattr(sys, "frozen", False) else __file__))
DATA_DIR = get_data_dir()
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
CACHE_FILE = os.path.join(DATA_DIR, "account_cache.json")
LOG_FILE = os.path.join(DATA_DIR, "poe_assistant.log")
CORE_DIR = os.path.join(DATA_DIR, "pob_core")

REFRESH_SECONDS = 120          # how often the character is refreshed from the server
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}
EPS = 0.05                     # changes below 0.05% count as no change

# kolory: jeden akcent, reszta neutralna; zielony/czerwony tylko dla zmian na plus/minus
BG, PANEL, LINE = "#0f1115", "#171a21", "#2a2f3a"
TEXT, MUTED, ACCENT = "#e6e8ec", "#8b93a1", "#e5a93b"
GOOD, BAD, WARN = "#4ade80", "#f87171", "#fbbf24"
FONT = "Segoe UI"


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    try:
        print(line)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ------------------------------------------------------------------ serwer PoE
def http_text(url):
    r = requests.get(url, headers=HEADERS, timeout=15)
    if r.status_code == 200:
        return r.text
    if r.status_code == 403:
        raise RuntimeError("Server rejected the request (403). Check that the account and characters are public.")
    if r.status_code == 429:
        raise RuntimeError("Too many requests (429). Wait a moment.")
    raise RuntimeError(f"Server returned code {r.status_code}.")


def fetch_characters(account):
    if not account:
        raise RuntimeError("Enter your PoE account name in the settings panel.")
    url = ("https://www.pathofexile.com/character-window/get-characters?accountName="
           + urllib.parse.quote(account))
    try:
        data = json.loads(http_text(url))
        if isinstance(data, list) and data:
            try:
                with open(CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump({"account_name": account, "characters": data}, f, indent=2)
            except Exception:
                pass
            return data
        raise RuntimeError("The account has no visible characters.")
    except Exception as e:
        log(f"fetch_characters: {e}")
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("account_name") == account and cached.get("characters"):
                return cached["characters"]
        except Exception:
            pass
        raise


# ------------------------------------------------------------------ drop ze schowka
WEAPON_WORDS = ["bow", "wand", "axe", "sword", "mace", "dagger", "claw", "staff", "staves", "sceptre"]


def classify_drop(raw):
    """Zwraca slownik z opisem przedmiotu albo None, jesli to nie jest przedmiot z PoE."""
    if not raw or "Rarity:" not in raw or ("--------" not in raw and "Item Class:" not in raw):
        return None
    lines = [l.strip() for l in raw.splitlines() if l.strip()]

    item_class = ""
    for l in lines:
        if l.startswith("Item Class:"):
            item_class = l.split(":", 1)[1].strip().lower()
            break

    slots = None
    exact = {
        "helmets": ["Helmet"], "body armours": ["Body Armour"], "gloves": ["Gloves"],
        "boots": ["Boots"], "belts": ["Belt"], "amulets": ["Amulet"],
        "rings": ["Ring 1", "Ring 2"], "shields": ["Weapon 2"], "quivers": ["Weapon 2"],
    }
    if item_class in exact:
        slots = exact[item_class]
    elif any(w in item_class for w in WEAPON_WORDS):
        slots = ["Weapon 1"]

    name = "Item"
    for i, l in enumerate(lines):
        if l.startswith("Rarity:"):
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            nxt2 = lines[i + 2] if i + 2 < len(lines) else ""
            if nxt2 and "---" not in nxt2:
                name = f"{nxt} ({nxt2})"
            elif nxt:
                name = nxt
            break

    return {"raw": raw.strip(), "slots": slots, "name": name, "item_class": item_class}


# ------------------------------------------------------------------ ocena
def pct(new, base):
    if base:
        return (new - base) / base * 100.0
    return 0.0 if not new else 100.0


def pick_best(results):
    """Wybiera najlepszy wariant (np. lepszy z dwoch pierscieni)."""
    best = None
    for r in results:
        b, n = r["base"], r["new"]
        d_dps = pct(n["dps"], b["dps"])
        d_ehp = pct(n["ehp"], b["ehp"])
        score = d_dps + d_ehp
        if best is None or score > best["score"]:
            best = {"r": r, "d_dps": d_dps, "d_ehp": d_ehp, "score": score}
    return best


STAT_LABELS = [
    ("Armour", "Armour", 0), ("Evasion", "Evasion", 0), ("es", "ES", 0), ("mana", "Mana", 0),
    ("BlockChance", "Block", 1), ("SpellBlockChance", "Spell Block", 1),
    ("SpellSuppressionChance", "Suppression", 1), ("CritChance", "Crit", 2),
    ("Str", "Str", 0), ("Dex", "Dex", 0), ("Int", "Int", 0),
]


def stat_changes(b, n):
    parts = []
    for key, label, dec in STAT_LABELS:
        d = n.get(key, 0) - b.get(key, 0)
        if round(abs(d), dec) > 0:
            parts.append(f"{label} {d:+.{dec}f}")
    return "   ".join(parts)


def evaluate(results):
    best = pick_best(results)
    r = best["r"]
    up = best["d_dps"] > EPS or best["d_ehp"] > EPS
    down = best["d_dps"] < -EPS or best["d_ehp"] < -EPS
    if up and not down:
        verdict, color, advice = "UPGRADE", GOOD, "Worth equipping."
    elif down and not up:
        verdict, color, advice = "DOWNGRADE", BAD, "Keep your current item."
    elif up and down:
        verdict, color, advice = "TRADE-OFF", WARN, "Depends: more damage or more defence."
    else:
        verdict, color, advice = "NO CHANGE", "#6b7280", "No difference for your build."
    where = r["slot"] + (f"  ·  replaces: {r['equipped'][:30]}" if r.get("equipped") else "  ·  empty slot")
    return {"verdict": verdict, "color": color, "advice": advice, "best": best, "where": where,
            "stats": stat_changes(r["base"], r["new"])}


def build_notes(best, analysis):
    """Short notes: resistance cap, most valuable and weakest modifier."""
    r = best["r"]
    b, n = r["base"], r["new"]
    notes = []
    for key, label in (("fire", "fire"), ("cold", "cold"), ("light", "lightning")):
        cap = n.get(key + "_max", 75)
        if b[key] < cap <= n[key]:
            notes.append(f"Closes the {label} resistance cap.")
        elif n[key] < cap:
            notes.append(f"{cap - n[key]:.0f}% short of the {label} resistance cap.")
    dead_lines = []
    if analysis:
        full = analysis["full"]
        scored = []
        for m in analysis.get("mods", []):
            d_dps = pct(full["dps"], m["without"]["dps"])
            d_ehp = pct(full["ehp"], m["without"]["ehp"])
            scored.append((d_dps + d_ehp, d_dps, d_ehp, m))
        top = sorted([x for x in scored if x[0] > 0.3], key=lambda x: -x[0])[:1]
        for _, dd, de, m in top:
            notes.append(f"Most valuable mod: {m['line'][:50]} ({dd:+.1f}% DPS, {de:+.1f}% EHP).")
        if analysis.get("rarity") == "UNIQUE":
            notes.append("Unique: modifiers cannot be changed.")
        else:
            dead = [x for x in scored if x[3]["kind"] == "explicit" and abs(x[1]) < 0.1 and abs(x[2]) < 0.1]
            dead_lines = [x[3]["line"] for x in dead[:2]]
            if dead_lines:
                notes.append("Barely useful for your build (replace candidate): " + "; ".join(l[:40] for l in dead_lines) + ".")
    return notes, dead_lines


def rank_entries(entries, base, limit=5, min_score=0.2):
    out = []
    for e in entries:
        n = e["new"]
        d_dps, d_ehp = pct(n["dps"], base["dps"]), pct(n["ehp"], base["ehp"])
        out.append((d_dps + d_ehp, d_dps, d_ehp, e))
    out.sort(key=lambda x: -x[0])
    return [x for x in out if x[0] > min_score][:limit]


def build_upgrade_report(data, dead_lines):
    """Zwraca liste (tekst, znacznik) do pola z pomyslami na ulepszenia."""
    base = data["base"]
    rows = []

    def head(t):
        rows.append((t + "\n", "h"))

    def entry(i, label, d_dps, d_ehp, extra=""):
        rows.append((f"{i}. {label}{extra}\n", "t"))
        col_d = "good" if (d_dps > EPS or d_ehp > EPS) else "mut"
        rows.append((f"     DPS {d_dps:+.1f}%   EHP {d_ehp:+.1f}%\n", col_d))

    rtype = data.get("base_type", "")
    if data.get("enchants"):
        head("ENCHANT")
        ranked = rank_entries(data["enchants"], base)
        if ranked:
            for i, (_, dd, de, e) in enumerate(ranked, 1):
                entry(i, e["label"][:90], dd, de)
        else:
            rows.append(("No available enchant improves this build (checked for the skills you use).\n", "mut"))
        rows.append(("\n", "t"))
    elif rtype in ("Helmet", "Gloves", "Boots") and not data.get("enchant_error"):
        head("ENCHANT")
        rows.append(("No enchants match the skills in your build.\n\n", "mut"))

    if data.get("anoints"):
        head("ANOINT")
        ranked = rank_entries(data["anoints"], base)
        if ranked:
            for i, (_, dd, de, e) in enumerate(ranked, 1):
                entry(i, e["label"], dd, de)
        else:
            rows.append(("No notable gives a clear improvement.\n", "mut"))
        rows.append(("\n", "t"))

    rarity = data.get("rarity")
    if data.get("craftable"):
        head(f"CRAFT  (open: {data.get('open_prefix', 0)} prefix, {data.get('open_suffix', 0)} suffix;"
             f" ilvl {data.get('item_level') or '?'})")
        any_craft = False
        for key, name in (("prefixes", "Prefix"), ("suffixes", "Suffix")):
            ranked = rank_entries(data.get(key, []), base, limit=4)
            for i, (_, dd, de, e) in enumerate(ranked, 1):
                any_craft = True
                entry(i, f"{name}: {e['label'][:80]}", dd, de, f"  (ilvl {e.get('tier_level', '?')})")
        if not any_craft:
            if data.get("open_prefix", 0) + data.get("open_suffix", 0) == 0:
                rows.append(("No open affix slots - see REPLACE below.\n", "mut"))
            else:
                rows.append(("No possible modifier gives a clear improvement.\n", "mut"))
        if data.get("combos"):
            rows.append(("\n", "t"))
            head("BEST PAIRS  (open prefix + suffix, or two of a kind)")
            ranked = rank_entries(data["combos"], base, limit=4)
            if ranked:
                for i, (_, dd, de, e) in enumerate(ranked, 1):
                    entry(i, e["label"][:110], dd, de)
            else:
                rows.append(("No pair gives a clear improvement.\n", "mut"))
        for rp in data.get("replace", []):
            rows.append(("\n", "t"))
            head(f"REPLACE A {rp['type'].upper()}  (weakest now: {rp['removed'][:55]})")
            ranked = rank_entries(rp.get("entries", []), base, limit=4)
            if ranked:
                for i, (_, dd, de, e) in enumerate(ranked, 1):
                    entry(i, e["label"][:90], dd, de, f"  (ilvl {e.get('tier_level', '?')})")
            else:
                rows.append(("No replacement gives a clear improvement.\n", "mut"))
    elif rarity == "RARE":
        head("CRAFT")
        rows.append(("To see craft suggestions, copy the item in game with Ctrl+Alt+C\n"
                     "(the version with full modifier details).\n", "mut"))
    elif rarity == "UNIQUE":
        head("CRAFT")
        rows.append(("Unique: modifiers cannot be added.\n", "mut"))

    if data.get("partial"):
        rows.append(("\nStopped after ~30 s - the list may be incomplete.\n", "mut"))
    if not rows:
        rows.append(("No meaningful upgrades found for this item.\n", "mut"))
    return rows


def mod_lines(analysis):
    """Linie do kolumny porownania: modyfikator + ile daje (DPS/EHP po jego usunieciu)."""
    if not analysis or not analysis.get("mods"):
        return [("(no modifier data)\n", "mut")]
    full = analysis["full"]
    items = []
    for m in analysis["mods"]:
        dd = pct(full["dps"], m["without"]["dps"])
        de = pct(full["ehp"], m["without"]["ehp"])
        items.append((m["kind"] != "implicit", -(dd + de), m["line"], dd, de))
    items.sort(key=lambda x: (x[0], x[1]))
    rows = []
    for _, neg, line, dd, de in items:
        score = -neg
        tag = "good" if score > 1.0 else "t" if score > 0.2 else "mut"
        rows.append((f"{line}\n", tag))
        tip = []
        if abs(dd) >= 0.05:
            tip.append(f"DPS {dd:+.1f}%")
        if abs(de) >= 0.05:
            tip.append(f"EHP {de:+.1f}%")
        rows.append(("    " + (", ".join(tip) if tip else "no effect on your build") + "\n", "mut"))
    return rows


def compare_rows(best):
    """Wiersze do wykresu slupkowego: (etykieta, wartosc, skala, tekst, kolor)."""
    r = best["r"]
    b, n = r["base"], r["new"]
    rows = []

    def pct_row(label, key):
        v = pct(n[key], b[key])
        rows.append((label, v, 25.0, f"{v:+.1f}%", delta_color(v)))

    pct_row("DPS", "dps")
    pct_row("EHP", "ehp")
    pct_row("LIFE", "life")
    if n["es"] or b["es"]:
        pct_row("ES", "es")
    for label, key in (("FIRE", "fire"), ("COLD", "cold"), ("LIGHTNING", "light"), ("CHAOS", "chaos")):
        d_cap = n[key] - b[key]
        d_tot = n.get(key + "_total", n[key]) - b.get(key + "_total", b[key])
        text = f"{d_cap:+.0f}%"
        if round(d_tot) != round(d_cap):
            text += f" ({d_tot:+.0f}%)"
        color = delta_color(d_cap, 0.5) if round(d_cap) != 0 else MUTED
        rows.append((label, d_cap, 30.0, text, color))
    return rows


def compare_table(best):
    """Wiersze tabeli: stat | aktualnie | po zmianie | zmiana (+ wartosc i skala do slupka)."""
    r = best["r"]
    b, n = r["base"], r["new"]
    rows = []

    def num(label, key, dec=0, unit="", always=False, by_pct=True):
        cur, new = b.get(key, 0), n.get(key, 0)
        d = new - cur
        if not always and round(abs(d), dec) == 0:
            return
        pc = pct(new, cur)
        change = f"{d:+,.{dec}f}{unit}"
        if by_pct and cur:
            change += f"  ({pc:+.1f}%)"
        v = pc if by_pct else d
        rows.append({"label": label, "cur": f"{cur:,.{dec}f}{unit}", "new": f"{new:,.{dec}f}{unit}",
                     "change": change, "v": v, "scale": 25.0 if by_pct else 30.0,
                     "color": delta_color(v, EPS if by_pct else 0.5)})

    num("DPS", "dps", always=True)
    num("EHP", "ehp", always=True)
    num("LIFE", "life", always=True)
    num("ES", "es")
    num("MANA", "mana")
    for label, key in (("FIRE", "fire"), ("COLD", "cold"), ("LIGHTNING", "light"), ("CHAOS", "chaos")):
        cur_c, new_c = b[key], n[key]
        cur_t, new_t = b.get(key + "_total", cur_c), n.get(key + "_total", new_c)
        d_cap, d_tot = new_c - cur_c, new_t - cur_t
        change = f"{d_cap:+.0f}"
        if round(d_tot) != round(d_cap):
            change += f" ({d_tot:+.0f})"
        rows.append({"label": label, "cur": fmt_res(cur_c, cur_t), "new": fmt_res(new_c, new_t),
                     "change": change + "%", "v": d_cap, "scale": 30.0,
                     "color": delta_color(d_cap, 0.5) if round(d_cap) != 0 else MUTED})
    num("ARMOUR", "Armour")
    num("EVASION", "Evasion")
    num("BLOCK", "BlockChance", 1, "%", by_pct=False)
    num("SPELL BLOCK", "SpellBlockChance", 1, "%", by_pct=False)
    num("SUPPRESSION", "SpellSuppressionChance", 1, "%", by_pct=False)
    num("CRIT CHANCE", "CritChance", 2, "%", by_pct=False)
    num("STR", "Str", by_pct=False)
    num("DEX", "Dex", by_pct=False)
    num("INT", "Int", by_pct=False)
    return rows


def explain(best, analysis_new, analysis_eq, new_name, eq_name):
    """Opis slowny porownania: podsumowanie, co dochodzi, co tracisz, odpornosci."""
    r = best["r"]
    b, n = r["base"], r["new"]
    rows = []

    def head(t):
        rows.append((t + "\n", "h"))

    def line(t, tag="t"):
        rows.append((t + "\n", tag))

    def tag_for(v):
        return "good" if v > EPS else "bad" if v < -EPS else "mut"

    head("SUMMARY")
    line(f"{r['slot']}:  {eq_name or 'empty slot'}  →  {new_name}", "mut")
    line(f"DPS   {b['dps']:,.0f}  →  {n['dps']:,.0f}   ({best['d_dps']:+.1f}%)", tag_for(best["d_dps"]))
    line(f"EHP   {b['ehp']:,.0f}  →  {n['ehp']:,.0f}   ({best['d_ehp']:+.1f}%)", tag_for(best["d_ehp"]))
    line(f"Life  {b['life']:,.0f}  →  {n['life']:,.0f}   ({n['life'] - b['life']:+,.0f})", tag_for(n["life"] - b["life"]))

    def contribs(analysis):
        out = []
        if analysis and analysis.get("mods"):
            full = analysis["full"]
            for m in analysis["mods"]:
                dd = pct(full["dps"], m["without"]["dps"])
                de = pct(full["ehp"], m["without"]["ehp"])
                out.append((dd + de, dd, de, m["line"], m["kind"]))
        return out

    new_c, eq_c = contribs(analysis_new), contribs(analysis_eq)
    gains = sorted([c for c in new_c if c[0] > 0.2], reverse=True)[:5]
    losses = sorted([c for c in eq_c if c[0] > 0.2], reverse=True)[:5]
    if gains:
        head("\nWHAT THE NEW ITEM BRINGS")
        for _, dd, de, text, _k in gains:
            line(f"+ {text[:62]}   (DPS {dd:+.1f}%, EHP {de:+.1f}%)", "good")
    if losses:
        head("\nWHAT YOU GIVE UP")
        for _, dd, de, text, _k in losses:
            line(f"- {text[:62]}   (DPS {dd:+.1f}%, EHP {de:+.1f}%)", "bad")
    dead_new = [c[3] for c in new_c if c[4] == "explicit" and abs(c[1]) < 0.1 and abs(c[2]) < 0.1]
    if dead_new:
        head("\nNO EFFECT ON YOUR BUILD (new item)")
        for text in dead_new[:4]:
            line(f"· {text[:70]}", "mut")

    head("\nRESISTANCES")
    for label, key in (("Fire", "fire"), ("Cold", "cold"), ("Lightning", "light"), ("Chaos", "chaos")):
        cur_c, new_c_ = b[key], n[key]
        cur_t, new_t = b.get(key + "_total", cur_c), n.get(key + "_total", new_c_)
        if key == "chaos":
            status, tag = "", tag_for(new_t - cur_t)
        else:
            cap = n.get(key + "_max", 75)
            if new_c_ >= cap:
                status, tag = f"cap kept, {new_t - cap:.0f}% over cap", "t"
            else:
                status, tag = f"{cap - new_c_:.0f}% BELOW cap", "bad"
        line(f"{label:<10} {fmt_res(cur_c, cur_t)}  →  {fmt_res(new_c_, new_t)}   {status}", tag)

    other = stat_changes(b, n)
    if other:
        head("\nOTHER CHANGES")
        line(other, "mut")
    return rows


# ------------------------------------------------------------------ praca w tle
class EngineWorker(threading.Thread):
    """Jedyny watek, ktory dotyka Path of Building (silnik Lua nie lubi wielu watkow)."""

    def __init__(self, results, skip_versions=None):
        super().__init__(daemon=True)
        self.tasks = queue.Queue()
        self.results = results
        self.skip_versions = list(skip_versions or [])
        self.engine = None

    def start_engine(self):
        os.chdir(CORE_DIR)
        from pob_engine import PoBEngine
        return PoBEngine(CORE_DIR, log=lambda s: log(f"[PoB] {s}"))

    def run(self):
        try:
            from pob_updater import PoBUpdater, KNOWN_GOOD
            updater = PoBUpdater(CORE_DIR, USER_AGENT, log=lambda s: log(f"[PoB update] {s}"),
                                 progress=lambda s: self.results.put(("status", s)),
                                 skip_versions=self.skip_versions)
            self.results.put(("status", "Checking Path of Building data..."))
            info = updater.ensure()
            try:
                self.engine = self.start_engine()
            except Exception:
                # The installed Path of Building version does not work with this app (it may have been
                # downloaded just now or on an earlier start). Go back to the previous copy if there is
                # one, otherwise install the version the app was tested with.
                bad = updater.local_version()
                if not bad or bad == KNOWN_GOOD:
                    raise
                log(f"Path of Building {bad} failed to start:\n" + traceback.format_exc())
                self.results.put(("bad_pob", bad))
                restored = updater.rollback() if info.get("updated") else False
                if not restored:
                    self.results.put(("status", f"Path of Building {bad} is not supported yet - installing a tested version..."))
                    restored = updater.install_known_good()
                if not restored:
                    raise
                info = {"updated": False, "version": updater.local_version() or "previous"}
                self.engine = self.start_engine()
            self.results.put(("engine_ready", info.get("version")))
        except Exception as e:
            log("Path of Building failed to start:\n" + traceback.format_exc())
            self.results.put(("fatal", f"PoB failed to start: {str(e)[:200]}"))
            return

        while True:
            kind, payload = self.tasks.get()
            try:
                if kind == "sync":
                    self.results.put(("synced", self.do_sync(*payload)))
                elif kind == "scan":
                    stats = self.engine.scan_skills()
                    info = self.engine.skills()
                    self.results.put(("scanned", {"stats": stats, "skills": info["skills"], "current": info["current"]}))
                elif kind == "select_skill":
                    self.results.put(("stats", self.engine.select_skill(*payload)))
                elif kind == "compare":
                    drop = payload
                    res = self.engine.compare_item(drop["raw"], drop["slots"])
                    self.results.put(("compared", {"drop": drop, "results": res}))
                    best = pick_best(res)
                    try:
                        analysis = self.engine.analyze_mods(drop["raw"], best["r"]["slot"])
                    except Exception:
                        log("analiza modyfikatorow nieudana:\n" + traceback.format_exc())
                        analysis = None
                    self.results.put(("tips", {"drop": drop, "best": best, "analysis": analysis}))
                elif kind == "equipped":
                    self.results.put(("equipped", {"slot": payload, "data": self.engine.analyze_equipped(payload)}))
                elif kind == "sidebar":
                    self.results.put(("sidebar", self.engine.sidebar()))
                elif kind == "upgrades":
                    drop, slot = payload
                    data = self.engine.suggest_upgrades(drop["raw"], slot)
                    self.results.put(("upgrades", {"drop": drop, "data": data}))
            except Exception as e:
                log(f"blad zadania '{kind}':\n" + traceback.format_exc())
                self.results.put(("error", (kind, str(e).splitlines()[0][:200] if str(e) else "error")))

    def do_sync(self, account, char, pinned=""):
        acc = urllib.parse.quote(account)
        name = urllib.parse.quote(char["name"])

        def url(kind):
            return (f"https://www.pathofexile.com/character-window/{kind}"
                    f"?accountName={acc}&character={name}&realm=pc")

        items_json = http_text(url("get-items"))
        passives_json = http_text(url("get-passive-skills"))
        stats = self.engine.import_character(char, items_json, passives_json, pinned)
        info = self.engine.skills()
        return {"char": char["name"], "stats": stats, "skills": info["skills"], "current": info["current"]}


# ------------------------------------------------------------------ HUD
def fmt_res(capped, total):
    """'75%' albo '75% (135%)' - w nawiasie pelna wartosc przed capem, gdy sie roznia."""
    text = f"{capped:.0f}%"
    if round(total) != round(capped):
        text += f" ({total:.0f}%)"
    return text


def delta_color(v, eps=EPS):
    return GOOD if v > eps else BAD if v < -eps else MUTED


class CompareWindow:
    """Szczegolowa analiza przedmiotu: zakladka Overview (tabela + opis) i Modifiers (obok siebie)."""
    W, H = 800, 740

    def __init__(self, app):
        self.app = app
        self.visible = False
        self.win = ctk.CTkToplevel(app.root, fg_color=BG)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.96)
        frame = ctk.CTkFrame(self.win, corner_radius=10, border_width=1, border_color=LINE, fg_color=BG)
        frame.pack(fill="both", expand=True, padx=1, pady=1)

        bar = ctk.CTkFrame(frame, height=30, fg_color=PANEL, corner_radius=8)
        bar.pack(fill="x", padx=6, pady=(6, 4))
        self.title = ctk.CTkLabel(bar, text="Item analysis", font=(FONT, 11, "bold"), text_color=ACCENT)
        self.title.pack(side="left", padx=10, pady=4)
        ctk.CTkButton(bar, text="✕", width=26, height=22, fg_color=BG, hover_color="#7f1d1d", text_color=MUTED,
                      font=(FONT, 12), command=self.hide).pack(side="right", padx=4, pady=3)
        for w in (bar, self.title):
            w.bind("<Button-1>", self._start_drag)
            w.bind("<B1-Motion>", self._do_drag)

        vrow = ctk.CTkFrame(frame, fg_color="transparent")
        vrow.pack(fill="x", padx=12, pady=(2, 4))
        self.badge = ctk.CTkLabel(vrow, text="", font=(FONT, 12, "bold"), text_color="#0b0d10",
                                  fg_color=MUTED, corner_radius=6)
        self.badge.pack(side="left")
        self.advice = ctk.CTkLabel(vrow, text="", font=(FONT, 11), text_color=MUTED)
        self.advice.pack(side="left", padx=10)

        self.tabs = ctk.CTkTabview(frame, fg_color=PANEL, height=600)
        self.tabs.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        t1 = self.tabs.add("Overview")
        t2 = self.tabs.add("Modifiers")

        # --- Overview: tabela ze slupkami + opis slowny
        self.canvas = tk.Canvas(t1, width=740, height=300, bg=PANEL, highlightthickness=0)
        self.canvas.pack(padx=4, pady=(2, 4))
        self.text = ctk.CTkTextbox(t1, font=(FONT, 11), fg_color=BG, text_color=TEXT, wrap="word",
                                   border_width=0, height=230)
        self.text.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        for tag, color in (("h", ACCENT), ("t", TEXT), ("good", GOOD), ("bad", BAD), ("mut", MUTED)):
            self.text.tag_config(tag, foreground=color)

        # --- Modifiers: dwie kolumny
        self.boxes, self.names = [], []
        cols = ctk.CTkFrame(t2, fg_color="transparent")
        cols.pack(fill="both", expand=True)
        for header in ("EQUIPPED", "NEW"):
            col = ctk.CTkFrame(cols, fg_color=BG, corner_radius=8)
            col.pack(side="left", fill="both", expand=True, padx=4, pady=4)
            ctk.CTkLabel(col, text=header, font=(FONT, 9), text_color=MUTED).pack(anchor="w", padx=10, pady=(6, 0))
            name = ctk.CTkLabel(col, text="", font=(FONT, 12, "bold"), text_color=ACCENT, anchor="w",
                                wraplength=330, justify="left")
            name.pack(fill="x", padx=10)
            box = ctk.CTkTextbox(col, font=(FONT, 11), fg_color=BG, text_color=TEXT, wrap="word", border_width=0)
            box.pack(fill="both", expand=True, padx=6, pady=(2, 6))
            for tag, color in (("good", GOOD), ("t", TEXT), ("mut", MUTED)):
                box.tag_config(tag, foreground=color)
            self.boxes.append(box)
            self.names.append(name)

    def _start_drag(self, e):
        self._dx, self._dy = e.x, e.y

    def _do_drag(self, e):
        self.win.geometry(f"+{self.win.winfo_x() + e.x - self._dx}+{self.win.winfo_y() + e.y - self._dy}")

    def hide(self):
        self.win.withdraw()
        self.visible = False

    def _fill(self, box, rows):
        box.configure(state="normal")
        box.delete("1.0", "end")
        for text, tag in rows:
            box.insert("end", text, tag)
        box.configure(state="disabled")

    def draw_table(self, rows):
        c = self.canvas
        c.delete("all")
        row_h = 24
        height = 30 + row_h * len(rows)
        c.configure(height=height)
        xl, xc, xn, xch = 10, 175, 300, 315          # etykieta, "aktualnie" (prawa kraw.), "po zmianie" (prawa), zmiana
        bar_mid, half = 600, 125
        for x, text, anchor in ((xl, "STAT", "w"), (xc, "CURRENT", "e"), (xn, "NEW", "e"), (xch, "CHANGE", "w")):
            c.create_text(x, 12, text=text, anchor=anchor, fill=MUTED, font=(FONT, 8, "bold"))
        c.create_line(8, 22, 735, 22, fill=LINE)
        c.create_line(bar_mid, 24, bar_mid, height - 2, fill=LINE)
        for i, row in enumerate(rows):
            y = 36 + row_h * i
            c.create_text(xl, y, text=row["label"], anchor="w", fill=MUTED, font=(FONT, 9, "bold"))
            c.create_text(xc, y, text=row["cur"], anchor="e", fill=TEXT, font=(FONT, 10))
            c.create_text(xn, y, text=row["new"], anchor="e", fill=TEXT, font=(FONT, 10, "bold"))
            c.create_text(xch, y, text=row["change"], anchor="w", fill=row["color"], font=(FONT, 10, "bold"))
            length = int(min(abs(row["v"]) / row["scale"], 1.0) * half)
            if length > 0:
                xa, xb = (bar_mid, bar_mid + length) if row["v"] > 0 else (bar_mid - length, bar_mid)
                c.create_rectangle(xa, y - 6, xb, y + 6, fill=row["color"], outline="")

    def show_data(self, drop, ev, analysis_new, equipped, slot):
        equipped = equipped or {}
        eq_name = "(loading...)" if not equipped else (None if equipped.get("empty") else equipped.get("name"))
        self.title.configure(text=f"Item analysis  ·  {slot}")
        self.badge.configure(text=f"  {ev['verdict']}  ", fg_color=ev["color"])
        self.advice.configure(text=ev["advice"])

        self.draw_table(compare_table(ev["best"]))
        self._fill(self.text, explain(ev["best"], analysis_new, (equipped or {}).get("analysis"),
                                      drop["name"][:60], eq_name))

        if equipped.get("empty"):
            self.names[0].configure(text="(empty slot)")
            self._fill(self.boxes[0], [("Nothing equipped in this slot.\n", "mut")])
        else:
            self.names[0].configure(text=equipped.get("name", "(loading...)"))
            self._fill(self.boxes[0], mod_lines(equipped.get("analysis")) if equipped
                       else [("Loading...\n", "mut")])
        self.names[1].configure(text=drop["name"][:60])
        self._fill(self.boxes[1], mod_lines(analysis_new) if analysis_new else [("Analysing modifiers...\n", "mut")])

        root = self.app.root
        x = root.winfo_x() - self.W - 6
        if x < 0:
            x = max(10, root.winfo_x() + root.winfo_width() + 6)
        self.win.geometry(f"{self.W}x{self.H}+{x}+{root.winfo_y()}")
        if not self.visible:
            self.win.deiconify()
            self.win.lift()
            self.visible = True


class StatsWindow:
    """Osobne, przeciagalne okienko z pelna lista statystyk z Path of Building."""
    W, H = 390, 560

    def __init__(self, app):
        self.app = app
        self.visible = False
        self.win = ctk.CTkToplevel(app.root, fg_color=BG)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.94)
        frame = ctk.CTkFrame(self.win, corner_radius=10, border_width=1, border_color=LINE, fg_color=BG)
        frame.pack(fill="both", expand=True, padx=1, pady=1)
        bar = ctk.CTkFrame(frame, height=30, fg_color=PANEL, corner_radius=8)
        bar.pack(fill="x", padx=6, pady=(6, 4))
        self.title = ctk.CTkLabel(bar, text="PoB stats", font=(FONT, 11, "bold"), text_color=ACCENT)
        self.title.pack(side="left", padx=10, pady=4)
        ctk.CTkButton(bar, text="✕", width=26, height=22, fg_color=BG, hover_color="#7f1d1d", text_color=MUTED,
                      font=(FONT, 12), command=self.hide).pack(side="right", padx=4, pady=3)
        for w in (bar, self.title):
            w.bind("<Button-1>", self._start_drag)
            w.bind("<B1-Motion>", self._do_drag)
        self.box = ctk.CTkTextbox(frame, font=("Consolas", 11), fg_color=BG, text_color=TEXT, wrap="none",
                                  border_width=0)
        self.box.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.box.tag_config("lab", foreground=MUTED)
        self.box.tag_config("val", foreground=TEXT)
        self.box.configure(state="disabled")

    def _start_drag(self, e):
        self._dx, self._dy = e.x, e.y

    def _do_drag(self, e):
        self.win.geometry(f"+{self.win.winfo_x() + e.x - self._dx}+{self.win.winfo_y() + e.y - self._dy}")

    def show(self):
        root = self.app.root
        x = root.winfo_x() - self.W - 6
        if x < 0:
            x = root.winfo_x() + root.winfo_width() + 6
        self.win.geometry(f"{self.W}x{self.H}+{x}+{root.winfo_y()}")
        self.win.deiconify()
        self.win.lift()
        self.visible = True

    def hide(self):
        self.win.withdraw()
        self.visible = False

    def set_lines(self, lines, subtitle=""):
        self.title.configure(text=f"PoB stats  ·  {subtitle}" if subtitle else "PoB stats")
        self.box.configure(state="normal")
        self.box.delete("1.0", "end")
        for ln in lines:
            if ln.get("sep"):
                self.box.insert("end", "\n")
            else:
                self.box.insert("end", f"{str(ln.get('label', ''))[:30]:<30}", "lab")
                self.box.insert("end", f"{str(ln.get('value', '')):>14}\n", "val")
        self.box.configure(state="disabled")


class App:
    def __init__(self):
        ctk.set_appearance_mode("dark")
        self.root = ctk.CTk(fg_color=BG)
        self.root.title("PoE Assistant")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)

        self.cfg = self.load_config()
        self.root.attributes("-alpha", self.cfg.get("opacity", 0.94))
        self.account = self.cfg.get("account_name", "")

        self.chars = []
        self.current_char = None
        self.skill_map = {}
        self.skill_names = {}
        self.syncing = False
        self.engine_ready = False
        self.settings_open = False
        self.eval_open = False
        self.upg_open = False
        self.eval_mode = "detail"
        self.last_clip = ""
        self.current_drop = None
        self.best_slot = None
        self.dead_lines = []
        self.last_results = None
        self.last_analysis = None
        self.equipped_cache = {}
        self.compare_pending = False
        self.results = queue.Queue()
        self.worker = EngineWorker(self.results, self.cfg.get("skip_pob_versions", []))

        x = self.cfg.get("pos_x", self.root.winfo_screenwidth() - 490)
        y = self.cfg.get("pos_y", 40)
        self.root.geometry(f"+{x}+{y}")

        self.build_ui()
        self.stats_win = StatsWindow(self)
        self.compare_win = CompareWindow(self)
        self.resize()
        self.worker.start()
        self.set_status("Loading Path of Building and character list...", MUTED)
        if self.account:
            threading.Thread(target=self.load_characters, daemon=True).start()
        else:
            self.root.after(400, self.prompt_account)

        self.root.after(100, self.process_results)
        self.root.after(300, self.poll_clipboard)
        self.root.after(REFRESH_SECONDS * 1000, self.auto_refresh)

    # --- konfiguracja
    def load_config(self):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_config(self):
        try:
            self.cfg["pos_x"] = self.root.winfo_x()
            self.cfg["pos_y"] = self.root.winfo_y()
            self.cfg["active_character"] = self.current_char
            self.cfg["account_name"] = self.account
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, indent=4)
        except Exception:
            pass

    # --- male pomocnicze do budowy interfejsu
    def label(self, parent, text="", size=11, bold=False, color=TEXT, **kw):
        return ctk.CTkLabel(parent, text=text, font=(FONT, size, "bold" if bold else "normal"),
                            text_color=color, **kw)

    def separator(self, parent):
        ctk.CTkFrame(parent, height=1, fg_color=LINE).pack(fill="x", padx=10, pady=6)

    def cell(self, parent, col, title, value_size=15, sub=False):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid(row=0, column=col, sticky="w", padx=(0, 6))
        parent.grid_columnconfigure(col, weight=1, uniform="c")
        self.label(f, title, 9, color=MUTED).pack(anchor="w")
        v = self.label(f, "—", value_size, True)
        v.pack(anchor="w")
        if sub:
            s = self.label(f, "", 9, color=MUTED)
            s.pack(anchor="w")
            return v, s
        return v

    # --- interfejs
    def build_ui(self):
        self.main_frame = ctk.CTkFrame(self.root, corner_radius=10, border_width=1, border_color=LINE, fg_color=BG)
        self.main_frame.pack(fill="both", expand=True, padx=1, pady=1)

        # pasek gorny
        top = ctk.CTkFrame(self.main_frame, height=34, fg_color=PANEL, corner_radius=8)
        top.pack(fill="x", padx=6, pady=(6, 4))
        grip = self.label(top, "⠿", 15, color=MUTED, width=20)
        grip.pack(side="left", padx=(6, 2))
        for w in (grip, top):
            w.bind("<Button-1>", self.start_drag)
            w.bind("<B1-Motion>", self.do_drag)
            w.bind("<ButtonRelease-1>", lambda e: self.save_config())
        self.char_menu = ctk.CTkOptionMenu(
            top, values=["(loading)"], command=self.on_switch_character, width=190, height=24,
            font=(FONT, 11, "bold"), fg_color=BG, button_color=LINE, button_hover_color="#3a4150",
            dropdown_fg_color=PANEL)
        self.char_menu.pack(side="left", padx=4, pady=4)
        for text, cmd, hover in (("✕", self.close, "#7f1d1d"), ("≡", self.toggle_settings, LINE),
                                 ("↻", self.start_sync, LINE), ("Stats", self.toggle_stats, LINE)):
            ctk.CTkButton(top, text=text, width=46 if len(text) > 1 else 28, height=24, fg_color=BG, hover_color=hover,
                          text_color=MUTED, font=(FONT, 12), command=cmd).pack(side="right", padx=2)

        # statystyki
        stats = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        stats.pack(fill="x", padx=12, pady=(2, 0))
        row1 = ctk.CTkFrame(stats, fg_color="transparent")
        row1.pack(fill="x")
        self.v_dps = self.cell(row1, 0, "DPS")
        self.v_ehp = self.cell(row1, 1, "EHP")
        self.v_life = self.cell(row1, 2, "LIFE")
        self.v_es = self.cell(row1, 3, "ES")
        row2 = ctk.CTkFrame(stats, fg_color="transparent")
        row2.pack(fill="x", pady=(4, 0))
        self.v_fire = self.cell(row2, 0, "FIRE", 13)
        self.v_cold = self.cell(row2, 1, "COLD", 13)
        self.v_light = self.cell(row2, 2, "LIGHTNING", 13)
        self.v_chaos = self.cell(row2, 3, "CHAOS", 13)

        skill_row = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        skill_row.pack(fill="x", padx=12, pady=(8, 0))
        self.label(skill_row, "Skill", 9, color=MUTED).pack(side="left", padx=(0, 8))
        self.skill_menu = ctk.CTkOptionMenu(
            skill_row, values=["(none)"], command=self.on_skill_change, height=22, font=(FONT, 10),
            fg_color=PANEL, button_color=LINE, button_hover_color="#3a4150", dropdown_fg_color=PANEL)
        self.skill_menu.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(skill_row, text="Detect", width=52, height=22, font=(FONT, 10), fg_color=PANEL,
                      hover_color=LINE, text_color=MUTED, command=self.detect_skills).pack(side="left", padx=(6, 0))

        self.lbl_status = self.label(self.main_frame, "", 9, color=MUTED, anchor="w")
        self.lbl_status.pack(fill="x", padx=14, pady=(4, 4))

        # panel oceny przedmiotu
        self.eval_frame = ctk.CTkFrame(self.main_frame, fg_color=PANEL, corner_radius=8)
        self.lbl_e_title = self.label(self.eval_frame, "", 13, True, ACCENT, anchor="w")
        self.lbl_e_title.pack(fill="x", padx=12, pady=(8, 0))
        self.lbl_e_where = self.label(self.eval_frame, "", 9, color=MUTED, anchor="w")
        self.lbl_e_where.pack(fill="x", padx=12)

        self.body = ctk.CTkFrame(self.eval_frame, fg_color="transparent")
        self.body.pack(fill="x")
        self.lbl_e_msg = self.label(self.body, "", 11, color=TEXT, anchor="w", justify="left", wraplength=420)
        self.detail = ctk.CTkFrame(self.body, fg_color="transparent")
        vrow = ctk.CTkFrame(self.detail, fg_color="transparent")
        vrow.pack(fill="x", padx=12, pady=(6, 4))
        self.badge = ctk.CTkLabel(vrow, text="", font=(FONT, 11, "bold"), text_color="#0b0d10",
                                  fg_color=MUTED, corner_radius=6)
        self.badge.pack(side="left")
        self.lbl_e_advice = self.label(vrow, "", 10, color=MUTED)
        self.lbl_e_advice.pack(side="left", padx=10)

        g1 = ctk.CTkFrame(self.detail, fg_color="transparent")
        g1.pack(fill="x", padx=12)
        self.d_dps, self.s_dps = self.cell(g1, 0, "ΔDPS", 13, sub=True)
        self.d_ehp, self.s_ehp = self.cell(g1, 1, "ΔEHP", 13, sub=True)
        self.d_life, self.s_life = self.cell(g1, 2, "ΔLIFE", 13, sub=True)
        g2 = ctk.CTkFrame(self.detail, fg_color="transparent")
        g2.pack(fill="x", padx=12, pady=(4, 0))
        self.d_fire = self.cell(g2, 0, "FIRE", 12)
        self.d_cold = self.cell(g2, 1, "COLD", 12)
        self.d_light = self.cell(g2, 2, "LIGHTNING", 12)
        self.d_chaos = self.cell(g2, 3, "CHAOS", 12)

        self.lbl_e_stats = self.label(self.detail, "", 9, color=MUTED, anchor="w", justify="left", wraplength=420)
        self.lbl_e_stats.pack(fill="x", padx=12, pady=(4, 0))
        self.separator(self.detail)
        self.lbl_e_notes = self.label(self.detail, "", 10, color=TEXT, anchor="w", justify="left", wraplength=420)
        self.lbl_e_notes.pack(fill="x", padx=12, pady=(0, 4))

        btns = ctk.CTkFrame(self.eval_frame, fg_color="transparent")
        btns.pack(fill="x", padx=12, pady=(2, 8))
        self.btn_upg = ctk.CTkButton(btns, text="Upgrade ideas", height=26, font=(FONT, 10, "bold"),
                                     fg_color=ACCENT, hover_color="#c98f26", text_color="#0b0d10",
                                     command=self.request_upgrades)
        self.btn_upg.pack(side="left")
        ctk.CTkButton(btns, text="Compare", height=26, width=76, font=(FONT, 10, "bold"), fg_color=PANEL,
                      hover_color=LINE, text_color=TEXT, command=self.open_compare).pack(side="left", padx=(6, 0))
        ctk.CTkButton(btns, text="Collapse", height=26, width=60, font=(FONT, 10), fg_color=BG,
                      hover_color=LINE, text_color=MUTED, command=self.collapse_eval).pack(side="right")

        self.upg_box = ctk.CTkTextbox(self.eval_frame, height=210, font=(FONT, 11), fg_color=BG,
                                      text_color=TEXT, wrap="word", border_width=0)
        for tag, color in (("h", ACCENT), ("t", TEXT), ("good", GOOD), ("mut", MUTED)):
            self.upg_box.tag_config(tag, foreground=color)

        # ustawienia
        self.settings_frame = ctk.CTkFrame(self.main_frame, fg_color=PANEL, corner_radius=8)
        self.label(self.settings_frame, "PoE account (e.g. Name#1234)", 10, color=MUTED).pack(pady=(6, 0))
        self.entry_account = ctk.CTkEntry(self.settings_frame, width=220, height=24, font=(FONT, 11))
        self.entry_account.insert(0, self.account)
        self.entry_account.pack(pady=(2, 4))
        ctk.CTkButton(self.settings_frame, text="Save and load characters", font=(FONT, 10, "bold"), height=24,
                      fg_color="#16a34a", hover_color="#15803d", command=self.change_account).pack(pady=(0, 6))
        self.label(self.settings_frame, f"v{APP_VERSION}  ·  data folder: {DATA_DIR}", 8, color=MUTED,
                   wraplength=440, justify="left").pack(pady=(0, 6), padx=8)
        self.auto_var = tk.BooleanVar(value=self.cfg.get("auto_compare", True))
        ctk.CTkSwitch(self.settings_frame, text="Open item analysis automatically", font=(FONT, 10),
                      variable=self.auto_var, command=self.on_auto_toggle).pack(pady=(0, 8))

    def resize(self):
        # wysokosc dopasowana do zawartosci (zamiast recznych liczb, przez ktore ucinalo przyciski)
        self.root.update_idletasks()
        h = self.main_frame.winfo_reqheight() + 6
        self.root.geometry(f"480x{h}")

    def set_status(self, text, color=MUTED):
        self.lbl_status.configure(text=text, text_color=color)

    def start_drag(self, e):
        self._dx, self._dy = e.x, e.y

    def do_drag(self, e):
        x = self.root.winfo_x() + e.x - self._dx
        y = self.root.winfo_y() + e.y - self._dy
        self.root.geometry(f"+{x}+{y}")

    def close(self):
        self.save_config()
        for w in (self.stats_win, self.compare_win):
            try:
                w.win.destroy()
            except Exception:
                pass
        self.root.destroy()

    def toggle_stats(self):
        if self.stats_win.visible:
            self.stats_win.hide()
        else:
            self.stats_win.show()
            self.request_sidebar()

    def request_sidebar(self):
        if self.engine_ready and self.current_char:
            self.worker.tasks.put(("sidebar", None))

    def prompt_account(self):
        if not self.settings_open:
            self.toggle_settings()
        self.set_status("Enter your PoE account name (Name#1234) and press Save.", WARN)

    def on_auto_toggle(self):
        self.cfg["auto_compare"] = bool(self.auto_var.get())
        self.save_config()

    def toggle_settings(self):
        if self.settings_open:
            self.settings_frame.pack_forget()
        else:
            self.settings_frame.pack(fill="x", padx=6, pady=4)
        self.settings_open = not self.settings_open
        self.resize()

    def collapse_eval(self):
        self.eval_frame.pack_forget()
        self.eval_open = False
        self.hide_upgrades()
        self.resize()

    def hide_upgrades(self):
        if self.upg_open:
            self.upg_box.pack_forget()
            self.upg_open = False

    # --- postacie
    def load_characters(self):
        try:
            self.results.put(("chars", fetch_characters(self.account)))
        except Exception as e:
            self.results.put(("error", ("chars", str(e)[:200])))

    def change_account(self):
        new = self.entry_account.get().strip()
        if new:
            self.account = new
            self.save_config()
            self.set_status("Loading characters...", MUTED)
            threading.Thread(target=self.load_characters, daemon=True).start()
            self.toggle_settings()

    def on_switch_character(self, name):
        self.current_char = name
        self.save_config()
        self.start_sync()

    def start_sync(self):
        if not self.current_char or not self.engine_ready or self.syncing:
            return
        char = next((c for c in self.chars if c.get("name") == self.current_char), None)
        if not char:
            return
        self.syncing = True
        self.set_status("Fetching character and calculating in PoB...", MUTED)
        pinned = self.cfg.get("pinned_skills", {}).get(self.current_char, "")
        self.worker.tasks.put(("sync", (self.account, char, pinned)))

    def auto_refresh(self):
        self.start_sync()
        self.root.after(REFRESH_SECONDS * 1000, self.auto_refresh)

    def on_skill_change(self, label):
        gi = self.skill_map.get(label)
        if gi:
            self.pin_skill(self.skill_names.get(label, ""))
            self.set_status("Recalculating...", MUTED)
            self.worker.tasks.put(("select_skill", gi))

    def pin_skill(self, name):
        """Zapamietuje wybrana umiejetnosc dla biezacej postaci (nie zmieni sie sama przy odswiezaniu)."""
        if name and self.current_char:
            self.cfg.setdefault("pinned_skills", {})[self.current_char] = name
            self.save_config()

    def detect_skills(self):
        if not self.engine_ready or not self.current_char:
            return
        self.set_status("Scanning all skills...", MUTED)
        self.worker.tasks.put(("scan", None))

    # --- wyswietlanie statystyk
    def show_stats(self, st):
        self.v_dps.configure(text=f"{st['DPS']:,.0f}")
        self.v_ehp.configure(text=f"{st['EHP']:,.0f}")
        self.v_life.configure(text=f"{st['LIFE']:,.0f}")
        self.v_es.configure(text=f"{st['ES']:,.0f}")
        for lbl, key in ((self.v_fire, "FIRE"), (self.v_cold, "COLD"), (self.v_light, "LIGHT")):
            lbl.configure(text=fmt_res(st[key], st.get(key + "_T", st[key])),
                          text_color=TEXT if st[key] >= 75 else WARN)
        self.v_chaos.configure(text=fmt_res(st["CHAOS"], st.get("CHAOS_T", st["CHAOS"])),
                               text_color=TEXT if st["CHAOS"] >= 0 else BAD)

    def show_skills(self, skills, current):
        # ukrywamy tylko te, ktorych DPS jest znany i rowny 0; reszta (jeszcze nie liczona) zostaje na liscie
        usable = [s for s in skills if s.get("dps") is None or s.get("dps", 0) > 0]
        usable.sort(key=lambda s: (-(s.get("dps") or -1), s["g"], s["i"]))
        self.skill_map, self.skill_names = {}, {}
        labels = []
        current_label = None
        for s in usable[:20]:
            dps = f"  ·  {s['dps']:,.0f}" if s.get("dps") else ""
            label = f"{s['name']} (gr. {s['g']}){dps}"
            self.skill_map[label] = (s["g"], s["i"])
            self.skill_names[label] = s["name"]
            labels.append(label)
            if current and s["g"] == current.get("g") and s["i"] == current.get("i"):
                current_label = label
        if not labels:
            labels = ["(no skills found)"]
        self.skill_menu.configure(values=labels)
        self.skill_menu.set(current_label or labels[0])

    # --- ocena przedmiotu
    def set_delta(self, lbl, value, suffix="", dec=1, eps=EPS):
        lbl.configure(text=f"{value:+.{dec}f}{suffix}", text_color=delta_color(value, eps))

    def set_delta_res(self, lbl, d_cap, d_total):
        text = f"{d_cap:+.0f}%"
        if round(d_total) != round(d_cap):
            text += f" ({d_total:+.0f}%)"
        color = delta_color(d_cap, 0.5) if round(d_cap) != 0 else MUTED
        lbl.configure(text=text, text_color=color)

    def show_eval_frame(self):
        if not self.eval_open:
            self.eval_frame.pack(fill="x", padx=6, pady=(0, 6))
            self.eval_open = True

    def show_evaluation(self, data):
        drop, results = data["drop"], data["results"]
        ev = evaluate(results)
        best = ev["best"]
        b, n = best["r"]["base"], best["r"]["new"]
        self.current_drop = drop
        self.best_slot = best["r"]["slot"]
        self.last_results = results
        self.last_analysis = None
        self.dead_lines = []
        self.hide_upgrades()
        self.btn_upg.configure(state="normal", text="Upgrade ideas")

        self.lbl_e_msg.pack_forget()
        self.eval_mode = "detail"
        self.lbl_e_title.configure(text=drop["name"][:52])
        self.lbl_e_where.configure(text=ev["where"])
        self.badge.configure(text=f"  {ev['verdict']}  ", fg_color=ev["color"])
        self.lbl_e_advice.configure(text=ev["advice"])
        self.set_delta(self.d_dps, best["d_dps"], "%")
        self.set_delta(self.d_ehp, best["d_ehp"], "%")
        self.set_delta(self.d_life, n["life"] - b["life"], "", 0, 0.5)
        self.s_dps.configure(text=f"{b['dps']:,.0f} → {n['dps']:,.0f}")
        self.s_ehp.configure(text=f"{b['ehp']:,.0f} → {n['ehp']:,.0f}")
        self.s_life.configure(text=f"{b['life']:,.0f} → {n['life']:,.0f}")
        for lbl, key in ((self.d_fire, "fire"), (self.d_cold, "cold"), (self.d_light, "light"), (self.d_chaos, "chaos")):
            d_cap = n[key] - b[key]
            d_tot = n.get(key + "_total", n[key]) - b.get(key + "_total", b[key])
            self.set_delta_res(lbl, d_cap, d_tot)
        self.lbl_e_stats.configure(text=ev["stats"])
        self.lbl_e_notes.configure(text="Analysing modifiers...")
        self.detail.pack(fill="x")
        self.show_eval_frame()
        self.resize()

    def show_tips(self, data):
        if not self.current_drop or data["drop"]["raw"] != self.current_drop["raw"]:
            return  # w miedzyczasie skopiowano inny przedmiot
        self.last_analysis = data["analysis"]
        notes, self.dead_lines = build_notes(data["best"], data["analysis"])
        if self.compare_win.visible:
            self.show_compare()
        self.lbl_e_notes.configure(text="\n".join(notes) if notes else "No additional notes.")

    def show_message(self, title, text):
        self.current_drop = None
        self.hide_upgrades()
        self.detail.pack_forget()
        self.eval_mode = "msg"
        self.lbl_e_title.configure(text=title)
        self.lbl_e_where.configure(text="")
        self.lbl_e_msg.configure(text=text)
        self.lbl_e_msg.pack(fill="x", padx=12, pady=(4, 6))
        self.show_eval_frame()
        self.resize()

    # --- porownanie obok siebie
    def open_compare(self):
        if not self.current_drop or not self.best_slot:
            return
        if self.best_slot in self.equipped_cache:
            self.show_compare()
            return
        self.compare_pending = True
        self.show_compare()                       # okno od razu, dane uzupelnia sie po chwili
        self.worker.tasks.put(("equipped", self.best_slot))

    def show_compare(self):
        if not self.current_drop or not self.last_results:
            return
        ev = evaluate(self.last_results)
        self.compare_win.show_data(self.current_drop, ev, self.last_analysis,
                                   self.equipped_cache.get(self.best_slot), self.best_slot)

    # --- pomysly na ulepszenia
    def request_upgrades(self):
        if not self.current_drop or not self.best_slot:
            return
        self.btn_upg.configure(state="disabled", text="Calculating... (up to ~30 s)")
        self.set_status("Calculating upgrade ideas...", MUTED)
        self.worker.tasks.put(("upgrades", (self.current_drop, self.best_slot)))

    def show_upgrades(self, data):
        if not self.current_drop or data["drop"]["raw"] != self.current_drop["raw"]:
            return
        self.btn_upg.configure(state="normal", text="Upgrade ideas")
        rows = build_upgrade_report(data["data"], self.dead_lines)
        self.upg_box.configure(state="normal")
        self.upg_box.delete("1.0", "end")
        for text, tag in rows:
            self.upg_box.insert("end", text, tag)
        self.upg_box.configure(state="disabled")
        if not self.upg_open:
            self.upg_box.pack(fill="x", padx=10, pady=(0, 8))
            self.upg_open = True
        self.set_status(f"{self.current_char} · {time.strftime('%H:%M:%S')}", MUTED)
        self.resize()

    # --- odbior wynikow z watku PoB
    def process_results(self):
        try:
            while True:
                kind, data = self.results.get_nowait()
                self.handle_result(kind, data)
        except queue.Empty:
            pass
        self.root.after(100, self.process_results)

    def handle_result(self, kind, data):
        if kind == "status":
            self.set_status(data, MUTED)
        elif kind == "engine_ready":
            self.engine_ready = True
            ver = (data or "").lstrip("v")
            if ver and ver[:1].isdigit() and not ver.startswith(TESTED_POB):
                self.set_status(f"PoB {ver} ready (app tested with {TESTED_POB}) - report issues if numbers look off.", WARN)
            else:
                self.set_status(f"PoB ready ({ver or 'unknown version'}).", MUTED)
            self.start_sync()
        elif kind == "bad_pob":
            skipped = self.cfg.setdefault("skip_pob_versions", [])
            if data not in skipped:
                skipped.append(data)
            self.save_config()
            self.set_status(f"PoB {data} is not compatible yet - using the previous version.", WARN)
        elif kind == "fatal":
            self.set_status(data, BAD)
        elif kind == "chars":
            self.chars = sorted(data, key=lambda c: c.get("lastLoginTime", 0), reverse=True)
            names = [c["name"] for c in self.chars]
            self.char_menu.configure(values=names)
            saved = self.cfg.get("active_character")
            self.current_char = saved if saved in names else names[0]
            self.char_menu.set(self.current_char)
            self.start_sync()
        elif kind == "synced":
            self.syncing = False
            self.equipped_cache = {}
            self.show_stats(data["stats"])
            self.show_skills(data["skills"], data["current"])
            ch = next((c for c in self.chars if c.get("name") == data["char"]), {})
            self.set_status(f"{data['char']} · lvl {ch.get('level', '?')} · {time.strftime('%H:%M:%S')}", MUTED)
            if self.stats_win.visible:
                self.request_sidebar()
        elif kind == "scanned":
            self.show_stats(data["stats"])
            self.show_skills(data["skills"], data["current"])
            cur = data["current"]
            name = next((s["name"] for s in data["skills"] if s["g"] == cur.get("g") and s["i"] == cur.get("i")), "")
            self.pin_skill(name)
            self.set_status(f"{self.current_char} · main skill: {name} · {time.strftime('%H:%M:%S')}", MUTED)
            if self.stats_win.visible:
                self.request_sidebar()
        elif kind == "stats":
            self.show_stats(data)
            self.set_status(f"{self.current_char} · {time.strftime('%H:%M:%S')}", MUTED)
            if self.stats_win.visible:
                self.request_sidebar()
        elif kind == "sidebar":
            self.stats_win.set_lines(data, self.current_char or "")
        elif kind == "compared":
            self.show_evaluation(data)
            self.set_status(f"{self.current_char} · {time.strftime('%H:%M:%S')}", MUTED)
            if self.cfg.get("auto_compare", True):
                self.open_compare()
        elif kind == "tips":
            self.show_tips(data)
        elif kind == "upgrades":
            self.show_upgrades(data)
        elif kind == "equipped":
            self.equipped_cache[data["slot"]] = data["data"]
            self.compare_pending = False
            if self.compare_win.visible:
                self.show_compare()
        elif kind == "error":
            where, msg = data
            self.syncing = False
            self.set_status(f"Error ({where}): {msg}", BAD)
            if where == "equipped":
                self.compare_pending = False
            if where in ("compare", "upgrades"):
                self.btn_upg.configure(state="normal", text="Upgrade ideas")
                if where == "compare":
                    self.show_message("Could not evaluate the item", msg)

    # --- schowek
    def poll_clipboard(self):
        try:
            clip = pyperclip.paste()
            if clip and clip != self.last_clip:
                self.last_clip = clip
                drop = classify_drop(clip)
                if drop:
                    if not drop["slots"]:
                        self.show_message(drop["name"][:52], "This item type is not supported yet.")
                    elif not self.engine_ready or not self.current_char:
                        self.show_message("Please wait", "PoB is still loading.")
                    else:
                        self.set_status("Evaluating item...", MUTED)
                        self.worker.tasks.put(("compare", drop))
        except Exception:
            pass
        self.root.after(300, self.poll_clipboard)

    def run(self):
        self.root.mainloop()


def migrate_old_files():
    """Older development versions kept config next to the script; carry the settings over once."""
    for name in ("config.json", "account_cache.json"):
        old, new = os.path.join(SCRIPT_DIR, name), os.path.join(DATA_DIR, name)
        try:
            if os.path.isfile(old) and not os.path.exists(new):
                shutil.copy2(old, new)
        except Exception:
            pass


def run_selftest():
    """For the build scripts/CI: checks that every dependency is present in the (frozen) application."""
    problems = []
    try:
        import customtkinter, requests, pyperclip  # noqa: F401
        import pob_updater  # noqa: F401
        from pob_engine import LuaRuntime
        assert LuaRuntime().eval("1 + 1") == 2
    except Exception:
        problems.append(traceback.format_exc())
    try:
        with open(os.path.join(DATA_DIR, "selftest.txt"), "w", encoding="utf-8") as f:
            f.write("OK\n" if not problems else "FAILED\n" + "\n".join(problems))
    except Exception:
        pass
    return 1 if problems else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(run_selftest())
    try:
        migrate_old_files()
        App().run()
    except Exception:
        log("CRITICAL ERROR:\n" + traceback.format_exc())
        try:
            from tkinter import messagebox
            messagebox.showerror("PoE Assistant", f"The application crashed.\nDetails were saved to:\n{LOG_FILE}")
        except Exception:
            pass
