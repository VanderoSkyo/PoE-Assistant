"""
pob_updater.py - keeps a local copy of Path of Building Community's source files up to date.

On every start of PoE Assistant:
  1. asks GitHub for the latest Path of Building Community release,
  2. compares it with the version stored in pob_core/.pob_version,
  3. if it differs (or nothing is installed yet) downloads the release archive,
     extracts only what the app needs and swaps it in atomically.
The previous copy is kept as pob_core.prev so the app can roll back if a new
version turns out to be incompatible.

Path of Building Community is MIT licensed (see THIRD_PARTY_NOTICES.md); its LICENSE.md is
copied next to the extracted files.
"""
import os
import shutil
import tempfile
import time
import zipfile

import requests

REPO = "PathOfBuildingCommunity/PathOfBuilding"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
TAG_ZIP_URL = f"https://api.github.com/repos/{REPO}/zipball/" + "{tag}"

# Version the app was developed and tested with. Used as a fallback when the newest
# release turns out to be incompatible (Path of Building sometimes adds new Lua syntax).
KNOWN_GOOD = "v2.68.1"

# files/folders that must exist for the app to work
REQUIRED = ["Launch.lua", "Modules/Main.lua", "Classes/ImportTab.lua", "Data", "TreeData", "lua/dkjson.lua"]
# folders of the source tree that the headless engine does not need (saves disk space)
SKIP_DIRS = ("Export/", "Assets/", "spec/", "tests/")
# what to copy when falling back to a locally installed Path of Building
LOCAL_COPY = ["Launch.lua", "GameVersions.lua", "LICENSE.md", "manifest.xml",
              "Classes", "Data", "Modules", "TreeData", "lua"]


class PoBUpdateError(Exception):
    pass


class PoBUpdater:
    def __init__(self, core_dir, user_agent, log=print, progress=None, skip_versions=None):
        self.core = os.path.abspath(core_dir)
        self.prev = self.core + ".prev"
        self.ua = user_agent
        self.log = log
        self.progress = progress or (lambda msg: None)
        self.skip = set(skip_versions or [])

    # ------------------------------------------------------------ state
    @property
    def marker(self):
        return os.path.join(self.core, ".pob_version")

    def local_version(self):
        try:
            with open(self.marker, "r", encoding="utf-8") as f:
                return f.read().strip() or None
        except OSError:
            return None

    def is_complete(self, base=None):
        base = base or self.core
        return all(os.path.exists(os.path.join(base, *item.split("/"))) for item in REQUIRED)

    # ------------------------------------------------------------ public API
    def ensure(self):
        """Makes sure a usable copy exists. Returns a dict: updated, version, [previous, offline, error]."""
        local, complete = self.local_version(), self.is_complete()
        try:
            tag, url = self.latest_release()
        except Exception as e:
            self.log(f"update check failed: {e}")
            if complete:
                return {"updated": False, "version": local or "unknown", "offline": True}
            if self.install_from_local_pob():
                return {"updated": False, "version": self.local_version(), "offline": True}
            raise PoBUpdateError(
                f"Could not download Path of Building data ({e}). "
                "Check your internet connection and start the app again.")

        if complete and local == tag:
            return {"updated": False, "version": tag}
        if tag in self.skip:
            # the newest release is known not to work with this app
            if complete:
                return {"updated": False, "version": local or "unknown", "skipped": tag}
            if self.install_known_good():
                return {"updated": False, "version": self.local_version(), "skipped": tag}

        self.progress(f"Downloading Path of Building {tag}...")
        try:
            self.download_and_install(tag, url)
        except Exception as e:
            self.log(f"install failed: {e}")
            if complete:
                return {"updated": False, "version": local or "unknown", "error": str(e)}
            if self.install_from_local_pob():
                return {"updated": False, "version": self.local_version(), "error": str(e)}
            raise PoBUpdateError(f"Could not install Path of Building data: {e}")
        return {"updated": True, "version": tag, "previous": local}

    def install_known_good(self):
        """Installs the tested fallback version (KNOWN_GOOD). Returns True on success."""
        self.progress(f"Downloading Path of Building {KNOWN_GOOD}...")
        try:
            self.download_and_install(KNOWN_GOOD, TAG_ZIP_URL.format(tag=KNOWN_GOOD))
            return True
        except Exception as e:
            self.log(f"fallback install of {KNOWN_GOOD} failed: {e}")
            return self.install_from_local_pob()

    def _leave_core(self):
        """Windows cannot rename or delete a folder that is the process's current directory
        (the engine sets it to the core folder), so step out of it first."""
        try:
            cwd = os.path.abspath(os.getcwd()).lower()
            if cwd == self.core.lower() or cwd.startswith(self.core.lower() + os.sep):
                os.chdir(os.path.dirname(self.core))
        except OSError:
            pass

    @staticmethod
    def _replace(src, dst, attempts=6):
        """os.replace with a few retries - antivirus or OneDrive may briefly lock freshly written files."""
        for i in range(attempts):
            try:
                os.replace(src, dst)
                return
            except PermissionError:
                if i == attempts - 1:
                    raise
                time.sleep(0.7)

    def rollback(self):
        """Restores the previous copy (used when a freshly downloaded version does not work)."""
        if not os.path.isdir(self.prev):
            return False
        self._leave_core()
        shutil.rmtree(self.core, ignore_errors=True)
        self._replace(self.prev, self.core)
        return True

    # ------------------------------------------------------------ GitHub
    def latest_release(self):
        r = requests.get(LATEST_URL, headers={"User-Agent": self.ua, "Accept": "application/vnd.github+json"},
                         timeout=15)
        if r.status_code != 200:
            raise PoBUpdateError(f"GitHub returned HTTP {r.status_code}")
        data = r.json()
        tag, url = data.get("tag_name"), data.get("zipball_url")
        if not tag or not url:
            raise PoBUpdateError("Unexpected answer from GitHub")
        return tag, url

    def _download(self, url, dest):
        with requests.get(url, headers={"User-Agent": self.ua}, stream=True, timeout=30) as r:
            if r.status_code != 200:
                raise PoBUpdateError(f"Download failed (HTTP {r.status_code})")
            total = int(r.headers.get("Content-Length") or 0)
            done, last = 0, 0.0
            with open(dest, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
                    done += len(chunk)
                    if time.time() - last > 0.5:
                        last = time.time()
                        msg = f"Downloading Path of Building data... {done / 1e6:.0f} MB"
                        if total:
                            msg += f" / {total / 1e6:.0f} MB"
                        self.progress(msg)

    # ------------------------------------------------------------ install
    def download_and_install(self, tag, url):
        parent = os.path.dirname(self.core)
        os.makedirs(parent, exist_ok=True)
        work = tempfile.mkdtemp(prefix="pob_update_", dir=parent)
        try:
            zip_path = os.path.join(work, "pob.zip")
            self._download(url, zip_path)
            self.progress("Unpacking Path of Building data...")
            new_core = os.path.join(work, "core")
            self.extract(zip_path, new_core)
            if not self.is_complete(new_core):
                raise PoBUpdateError("the downloaded archive does not contain the expected files")
            with open(os.path.join(new_core, ".pob_version"), "w", encoding="utf-8") as f:
                f.write(tag)
            self._swap(new_core)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    @staticmethod
    def _shallowest(names, suffix):
        found = [n for n in names if n.endswith(suffix)]
        return min(found, key=lambda n: n.count("/")) if found else None

    def extract(self, zip_path, dest):
        """Extracts the source tree (src/) and the Lua helper libraries (runtime/lua) into dest."""
        with zipfile.ZipFile(zip_path) as z:
            names = [n for n in z.namelist() if not n.endswith("/")]
            launch = self._shallowest(names, "/Launch.lua")
            dkjson = self._shallowest(names, "/lua/dkjson.lua")
            if not launch:
                raise PoBUpdateError("Launch.lua not found in the archive")
            src_prefix = launch[:-len("Launch.lua")]
            lua_prefix = dkjson[:-len("dkjson.lua")] if dkjson else None
            root = os.path.abspath(dest)
            for n in names:
                target = None
                if n.startswith(src_prefix):
                    rel = n[len(src_prefix):]
                    if rel.startswith(SKIP_DIRS):
                        continue
                    target = rel
                elif lua_prefix and n.startswith(lua_prefix):
                    target = "lua/" + n[len(lua_prefix):]
                elif n.count("/") == 1 and n.endswith(("/LICENSE.md", "/manifest.xml")):
                    target = n.split("/")[1]
                if not target:
                    continue
                out = os.path.abspath(os.path.join(dest, *target.split("/")))
                if not out.startswith(root + os.sep):      # never write outside the target folder
                    continue
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with z.open(n) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst)

    def _swap(self, new_core):
        self._leave_core()
        had_old = os.path.isdir(self.core)
        if os.path.isdir(self.prev):
            shutil.rmtree(self.prev, ignore_errors=True)
        if had_old:
            self._replace(self.core, self.prev)
        try:
            shutil.move(new_core, self.core)
        except Exception:
            if had_old and not os.path.isdir(self.core):
                self._replace(self.prev, self.core)
            raise

    # ------------------------------------------------------------ offline fallback
    def install_from_local_pob(self):
        """Fallback: copy the files from a locally installed Path of Building Community (Windows)."""
        appdata = os.environ.get("APPDATA", "")
        src = os.path.join(appdata, "Path of Building Community") if appdata else ""
        if not (src and os.path.isfile(os.path.join(src, "Launch.lua"))):
            return False
        parent = os.path.dirname(self.core)
        os.makedirs(parent, exist_ok=True)
        work = tempfile.mkdtemp(prefix="pob_local_", dir=parent)
        try:
            new_core = os.path.join(work, "core")
            os.makedirs(new_core)
            for name in LOCAL_COPY:
                s = os.path.join(src, name)
                d = os.path.join(new_core, name)
                if os.path.isdir(s):
                    shutil.copytree(s, d)
                elif os.path.isfile(s):
                    shutil.copy2(s, d)
            if not self.is_complete(new_core):
                return False
            with open(os.path.join(new_core, ".pob_version"), "w", encoding="utf-8") as f:
                f.write("local-install")
            self._swap(new_core)
            return True
        except Exception as e:
            self.log(f"local install failed: {e}")
            return False
        finally:
            shutil.rmtree(work, ignore_errors=True)
