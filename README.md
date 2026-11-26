# PoE Assistant

Unofficial item-comparison HUD for **Path of Exile 1**, powered by the calculation engine of
[Path of Building Community](https://github.com/PathOfBuildingCommunity/PathOfBuilding).

Copy an item in game (hover it and press **Ctrl+C**) and the overlay tells you - using *your* character, tree,
gems and gear - whether it is an upgrade, what you gain and what you give up, and what could be improved on it.

> Early test version (alpha). Windows only. Feedback and bug reports are very welcome.

## Features

- Loads your character from the public character API and calculates it with Path of Building's own engine.
- Overlay with DPS, EHP, life, ES and resistances (capped value plus the full value, e.g. `FIRE 75% (135%)`).
- **Item analysis window** (opens automatically): current vs. new values, bars, what the new item brings and
  what you give up, resistance caps, and a per-modifier breakdown of both items.
- **Upgrade ideas** for the copied item: enchants, amulet anoints, single modifiers, best pairs and
  "replace the weakest modifier" suggestions (copy with **Ctrl+Alt+C** for full craft suggestions on rares).
- **Stats** window with the same stat list as Path of Building's sidebar.
- Main skill is pinned per character; the **Detect** button scans all skills on demand.
- Path of Building data is checked and **updated automatically** on every start.

## Install (Windows)

1. Install [Python 3.10 or newer](https://www.python.org/downloads/windows/) - tick **"Add python.exe to PATH"**.
2. Download or clone this repository, then double-click **`install.bat`**.
   It creates a virtual environment, installs the dependencies and puts a shortcut on your desktop.
3. Start **PoE Assistant** from the shortcut (or `run.bat`).
4. On first start enter your account name (e.g. `Name#1234`) in the settings panel (`≡`) and press **Save**.
   The first start also downloads the Path of Building data - this needs an internet connection and takes a moment.

Your characters must be **public** (pathofexile.com -> Profile -> Privacy settings), otherwise the server answers
with an error (HTTP 403).

## Usage

- Pick your character in the drop-down; `↻` refreshes it (it also refreshes every 2 minutes).
  The game's character data only updates after you change zones/log out.
- Hover an item in game and press **Ctrl+C**. For craft suggestions on rare items use **Ctrl+Alt+C**.
- `Upgrade ideas` calculates suggestions (can take up to ~30 s), `Compare` re-opens the analysis window.
- If the main skill is wrong, choose the right one in the **Skill** drop-down (it is remembered per character).

Supported slots: helmet, body armour, gloves, boots, belt, amulet, rings, weapons, shields and quivers.
Flasks and jewels are not supported yet.

## Limitations

- Uses the unofficial `character-window` endpoints of pathofexile.com. GGG can change or restrict them at any time.
- Numbers are calculated with Path of Building's *default configuration* (no boss/charges/flask assumptions yet),
  so they may differ from your own PoB setup.
- Craft suggestions rate the effect on your build only - not the price or the chance to roll a modifier.
- Developed and tested against Path of Building Community 2.68. Newer versions are downloaded automatically;
  if one fails to start, the app rolls back to the previous version and remembers to skip the broken one.

## Privacy

No telemetry. The app stores your account name, settings, a log file and the downloaded Path of Building data in
`%LOCALAPPDATA%\PoE Assistant`. It contacts only `pathofexile.com` (character data) and `github.com` (Path of Building updates).
The app never asks for or stores your session cookie.

## Troubleshooting

- Something does not work: run `run_debug.bat` (shows a console) and look at `poe_assistant.log` in the data folder
  (the path is shown at the bottom of the settings panel). Please attach it to bug reports.
- `HTTP 403`: your account or characters are private.
- Nothing happens when copying an item: make sure the item text starts with `Item Class:` / `Rarity:`
  (the game's own copy function) and that the supported slot is a gear slot (see above).

## Build a Setup.exe (optional)

Install [Inno Setup 6](https://jrsoftware.org/isinfo.php), run `install.bat` once, then run `build_installer.bat`.
It packs the app with PyInstaller and compiles `installer.iss` into `Output\PoE-Assistant-Setup.exe`.

## License

MIT - see [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
