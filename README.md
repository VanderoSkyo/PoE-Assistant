# PoE Assistant

**Unofficial item-comparison overlay for Path of Exile 1, powered by Path of Building's own calculation engine.**

Hover an item in game, press **Ctrl+C**, and PoE Assistant tells you - using *your* character, passive tree, gems and
gear - whether the item is an upgrade, what you gain, what you give up, and what could still be improved on it.

> **Status: early alpha.** Windows only. It works on the author's machine; expect rough edges and please report them.
> Not affiliated with or endorsed by Grinding Gear Games.

## Why

Price-check tools tell you what an item is worth. PoE Assistant tells you what it is worth **to your build**.
It does not re-implement any game math: it runs the real Path of Building Community calculation code (in an
embedded LuaJIT) on your imported character, so the numbers follow the same rules as the Path of Building you know.

## Features

- **Your character, automatically.** Loads your public character (items, passive tree, jewels, gems) and calculates it.
- **Compact overlay:** DPS, EHP, life, ES and resistances - capped value plus full value, e.g. `FIRE 75% (135%)`.
- **Item analysis window** (opens when you copy an item):
  - current vs. new values with change bars,
  - what the new item brings, what you give up, resistance caps,
  - per-modifier value for both items, side by side.
- **Upgrade ideas** for the copied item - enchants, amulet anoints, single modifiers, best modifier pairs and
  "replace the weakest modifier" suggestions. Copy rares with **Ctrl+Alt+C** to unlock craft suggestions.
- **Stats window** with the same stat list as Path of Building's sidebar.
- **Main skill pinned per character** (with an on-demand *Detect* scan), so the numbers always refer to the skill you play.
- **Path of Building data updates itself** on every start, with an automatic fallback to a tested version.

## Install (Windows)

### Option A - installer (no Python needed)

Download **`PoE-Assistant-Setup-<version>.exe`** from the [Releases](../../releases) page, run it, start *PoE Assistant*.
(The installer carries its own Python, so nothing else has to be installed. Windows SmartScreen may warn about an
unsigned app - choose *More info -> Run anyway*.)

### Option B - from source

1. Install [Python 3.10 or newer](https://www.python.org/downloads/windows/) (3.12 or 3.13 are the safest choices; the new Python Install Manager for 3.14 works too).
2. Download this repository (Code -> Download ZIP) and unpack it. Double-click **`install.bat`**.
   It finds the installed Python wherever it lives, creates a private environment, installs the dependencies and puts a shortcut on your desktop.
3. Start **PoE Assistant** from the shortcut (or `run.bat`).

### First start

Enter your account name (e.g. `Name#1234`) in the settings panel (`≡`) and press **Save**.
The first start also downloads the Path of Building data, which needs an internet connection.

Your characters must be **public** (pathofexile.com -> Profile -> Privacy settings), otherwise the server answers with HTTP 403.

## Usage

| Action | How |
|---|---|
| Rate an item | Hover it in game, **Ctrl+C** |
| Craft suggestions on a rare | Hover it, **Ctrl+Alt+C** |
| Refresh the character | `↻` (also automatic every 2 minutes; the game updates character data after zoning/logout) |
| Change the skill the numbers refer to | **Skill** drop-down (remembered per character), *Detect* scans all skills |
| Full Path of Building stat list | **Stats** button |

Supported: helmet, body armour, gloves, boots, belt, amulet, rings, weapons, shields, quivers.
Not supported yet: flasks and jewels.

## Compatibility with Path of Building updates

Path of Building is written in an extended dialect of Lua. When its authors adopt new syntax, third-party tools that run its
code outside the official program can break. PoE Assistant handles this in layers:

- It downloads the latest Path of Building Community release on start and compares it with its local copy.
- Source files are passed through a small compatibility step (for example `a += 1` is rewritten for plain LuaJIT).
- If a release does not start, the app **remembers it as incompatible, rolls back to the previous copy or installs the
  tested version (currently 2.68.1)**, and keeps working. The skipped versions are listed in `config.json`.

Developed and tested against Path of Building Community **2.68.1**.

## Limitations

- Uses the unofficial `character-window` endpoints of pathofexile.com; GGG may change or restrict them at any time.
- Calculated with Path of Building's *default configuration* (no boss, charges or flask assumptions yet), so numbers can differ from your own PoB setup.
- Craft suggestions rate the effect on your build only - not price or the chance of rolling a modifier.
- English interface only.

## Privacy

No telemetry. The app stores your account name, settings, a log file and the Path of Building data in
`%LOCALAPPDATA%\PoE Assistant`. It contacts only `pathofexile.com` (character data) and `github.com` (Path of Building updates).
It never asks for or stores your session cookie.

## Troubleshooting

- Run `run_debug.bat` (shows a console) and read `poe_assistant.log` in the data folder (shown at the bottom of the settings panel).
  Please attach the log to bug reports.
- *HTTP 403*: your account or characters are private.
- You updated or uninstalled Python: just start the app again - it rebuilds its environment automatically (or run `install.bat`).
- *Path of Building ... is not supported yet*: normal after a new PoB release - the app falls back to a tested version. Please open an issue so support can be added.
- Nothing happens when you copy an item: the text must start with `Item Class:` / `Rarity:` (use the game's own copy shortcut).

## For developers

```
poe_assistant.py   UI, character loading, item parsing, result presentation
pob_engine.py      embeds Path of Building (via lupa/LuaJIT): import, skill selection, comparison, craft analysis
pob_updater.py     downloads/updates/rolls back the Path of Building source
```

Run from source: `pip install -r requirements.txt` then `python poe_assistant.py`.
Contributions are welcome - especially compatibility fixes for new Path of Building releases, flasks/jewels, and tests.

## Credits and license

Built on [Path of Building Community](https://github.com/PathOfBuildingCommunity/PathOfBuilding) (MIT) - thank you to its authors.
PoE Assistant is released under the MIT license; see [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
*Path of Exile* is a trademark of Grinding Gear Games.
