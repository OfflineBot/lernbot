#!/usr/bin/env python3
"""Focus Lern-Daemon.

Alle 5 Minuten:
  1. aktuell offene Firefox-Tabs aus der Session-Datei lesen,
  2. jeden Tab gegen die Whitelist (whitelist.txt) pruefen,
  3. wenn verbotene Tabs offen sind: Firefox sauber beenden, die Session
     bereinigen (nur erlaubte Tabs behalten) und Firefox neu starten,
     wobei genau diese eine Session wiederhergestellt wird.

Keine externen Abhaengigkeiten (mozLz4 + LZ4-Block in reinem Python).
"""

import configparser
import json
import os
import signal
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WHITELIST_FILE = HERE / "whitelist.txt"
INTERVAL = 300  # Sekunden zwischen den Pruefungen (5 Minuten)
MAGIC = b"mozLz40\0"


# --------------------------------------------------------------------------- #
# mozLz4 (Firefox' .jsonlz4) lesen/schreiben - reines Python, kein lz4-Paket   #
# --------------------------------------------------------------------------- #
def lz4_decompress(data: bytes, out_size: int) -> bytes:
    out = bytearray()
    i, n = 0, len(data)
    while i < n:
        token = data[i]; i += 1
        lit = token >> 4
        if lit == 15:
            while True:
                b = data[i]; i += 1; lit += b
                if b != 255:
                    break
        out += data[i:i + lit]; i += lit
        if i >= n:
            break
        offset = data[i] | (data[i + 1] << 8); i += 2
        m = token & 15
        if m == 15:
            while True:
                b = data[i]; i += 1; m += b
                if b != 255:
                    break
        m += 4
        start = len(out) - offset
        for j in range(m):
            out.append(out[start + j])
    return bytes(out)


def lz4_compress_literals(data: bytes) -> bytes:
    """Gueltiger LZ4-Block ganz ohne Matches (nur Literale). Groesser als ein
    echter Kompressor, aber Firefox liest ihn problemlos und re-komprimiert
    beim naechsten Speichern selbst."""
    out = bytearray()
    n = len(data)
    if n < 15:
        out.append(n << 4)
    else:
        out.append(0xF0)
        rem = n - 15
        while rem >= 255:
            out.append(255); rem -= 255
        out.append(rem)
    out += data
    return bytes(out)


def read_mozlz4(path: Path) -> bytes:
    raw = path.read_bytes()
    if raw[:8] != MAGIC:
        raise ValueError(f"kein mozLz4: {path}")
    size = int.from_bytes(raw[8:12], "little")
    return lz4_decompress(raw[12:], size)


def write_mozlz4(path: Path, data: bytes) -> None:
    blob = MAGIC + len(data).to_bytes(4, "little") + lz4_compress_literals(data)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(blob)
    tmp.replace(path)


# --------------------------------------------------------------------------- #
# Firefox-Profil / Session                                                     #
# --------------------------------------------------------------------------- #
def find_profile() -> Path | None:
    for base in (Path.home() / ".config/mozilla/firefox",
                 Path.home() / ".mozilla/firefox"):
        ini = base / "profiles.ini"
        if not ini.exists():
            continue
        cp = configparser.ConfigParser()
        cp.read(ini)
        # 1) Bevorzugt das in [InstallXXXX] als Default eingetragene Profil
        for sec in cp.sections():
            if sec.startswith("Install") and cp.has_option(sec, "Default"):
                cand = base / cp.get(sec, "Default")
                if cand.exists():
                    return cand
        # 2) Sonst ein Profil mit Default=1 oder Name *default-release*
        for sec in cp.sections():
            if not sec.startswith("Profile"):
                continue
            name = cp.get(sec, "Name", fallback="")
            if cp.get(sec, "Default", fallback="0") == "1" or "default-release" in name:
                p = cp.get(sec, "Path", fallback="")
                if not p:
                    continue
                cand = Path(p) if os.path.isabs(p) else base / p
                if cand.exists():
                    return cand
    return None


def session_path(profile: Path) -> Path | None:
    rec = profile / "sessionstore-backups" / "recovery.jsonlz4"
    if rec.exists():
        return rec
    ss = profile / "sessionstore.jsonlz4"
    return ss if ss.exists() else None


# --------------------------------------------------------------------------- #
# Whitelist                                                                    #
# --------------------------------------------------------------------------- #
def load_config() -> tuple[bool, list[str]]:
    """Liest whitelist.txt. Gibt (aktiv, muster) zurueck.

    Eine Zeile 'active=false' (irgendwo, Gross-/Kleinschreibung egal) schaltet
    den Daemon komplett ab - dann werden keine Tabs geschlossen. Fehlt die
    Zeile oder steht sie auf true/1/yes/on, ist der Daemon aktiv.
    """
    active = True
    pats = []
    try:
        for line in WHITELIST_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key = line.split("=", 1)[0].strip().lower()
            if key == "active":
                val = line.split("=", 1)[1].strip().lower() if "=" in line else ""
                active = val in ("1", "true", "yes", "on", "")
                continue
            pats.append(line.lower())
    except FileNotFoundError:
        pass
    return active, pats


def current_url(tab: dict) -> str:
    entries = tab.get("entries", [])
    idx = tab.get("index", len(entries))
    if entries and 1 <= idx <= len(entries):
        return entries[idx - 1].get("url", "")
    if entries:
        return entries[-1].get("url", "")
    return ""


def is_allowed(url: str, patterns: list[str]) -> bool:
    u = (url or "").lower()
    # Leere/interne Seiten (neuer Tab etc.) nie schliessen
    if u == "" or u.startswith("about:"):
        return True
    return any(p in u for p in patterns)


def forbidden_urls(data: dict, patterns: list[str]) -> list[str]:
    bad = []
    for w in data.get("windows", []):
        for t in w.get("tabs", []):
            u = current_url(t)
            if not is_allowed(u, patterns):
                bad.append(u)
    return bad


def filter_tabs(data: dict, patterns: list[str]) -> int:
    """Entfernt nicht-erlaubte Tabs in-place. Gibt Anzahl entfernter zurueck."""
    removed = 0
    new_windows = []
    for w in data.get("windows", []):
        kept = []
        for t in w.get("tabs", []):
            if is_allowed(current_url(t), patterns):
                kept.append(t)
            else:
                removed += 1
        if kept:
            w["tabs"] = kept
            sel = w.get("selected", 1)
            w["selected"] = max(1, min(sel, len(kept)))
            new_windows.append(w)
    data["windows"] = new_windows
    if "selectedWindow" in data:
        sw = data["selectedWindow"]
        if not new_windows:
            data["selectedWindow"] = 0
        elif sw > len(new_windows):
            data["selectedWindow"] = len(new_windows)
    return removed


# --------------------------------------------------------------------------- #
# Firefox-Prozesse                                                             #
# --------------------------------------------------------------------------- #
def firefox_pids() -> list[int]:
    r = subprocess.run(["pgrep", "-x", "firefox"], capture_output=True, text=True)
    return [int(x) for x in r.stdout.split()]


def read_proc_env(pid: int) -> dict:
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes()
    except OSError:
        return dict(os.environ)
    env = {}
    for part in raw.split(b"\0"):
        if b"=" in part:
            k, v = part.split(b"=", 1)
            try:
                env[k.decode()] = v.decode()
            except UnicodeDecodeError:
                pass
    return env or dict(os.environ)


def wait_gone(timeout: float = 30) -> bool:
    t = 0.0
    while firefox_pids() and t < timeout:
        time.sleep(0.5); t += 0.5
    return not firefox_pids()


def set_resume_once(profile: Path) -> None:
    """Firefox stellt beim naechsten Start genau einmal die Session wieder her."""
    pj = profile / "prefs.js"
    try:
        lines = pj.read_text().splitlines()
    except FileNotFoundError:
        lines = []
    lines = [l for l in lines if "browser.sessionstore.resume_session_once" not in l]
    lines.append('user_pref("browser.sessionstore.resume_session_once", true);')
    pj.write_text("\n".join(lines) + "\n")


def relaunch(env: dict) -> None:
    try:
        subprocess.Popen(
            ["firefox"], env=env, start_new_session=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            cwd=env.get("HOME", str(Path.home())),
        )
        log("Firefox neu gestartet")
    except Exception as e:  # noqa: BLE001
        log(f"Neustart fehlgeschlagen: {e}")


def clean_and_restart(profile: Path, patterns: list[str], pids: list[int]) -> None:
    env = read_proc_env(pids[0])

    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    if not wait_gone(30):
        log("Firefox beendet nicht sauber -> SIGKILL")
        for pid in firefox_pids():
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        wait_gone(10)
    time.sleep(1.5)  # Session-Schreiben abwarten

    total = 0
    targets = [
        profile / "sessionstore.jsonlz4",
        profile / "sessionstore-backups" / "recovery.jsonlz4",
    ]
    for tp in targets:
        if not tp.exists():
            continue
        try:
            data = json.loads(read_mozlz4(tp))
        except Exception as e:  # noqa: BLE001
            log(f"konnte {tp.name} nicht lesen: {e}")
            continue
        n = filter_tabs(data, patterns)
        if n:
            write_mozlz4(tp, json.dumps(data, separators=(",", ":")).encode())
            total += n
    # ungueltig gewordene Sicherungskopie entfernen
    try:
        (profile / "sessionstore-backups" / "recovery.baklz4").unlink()
    except FileNotFoundError:
        pass

    log(f"{total} Tab(s) entfernt")
    set_resume_once(profile)
    relaunch(env)


# --------------------------------------------------------------------------- #
def log(msg: str) -> None:
    print(msg, flush=True)


def run_once() -> None:
    profile = find_profile()
    if not profile:
        log("kein Firefox-Profil gefunden")
        return
    active, patterns = load_config()
    if not active:
        log("deaktiviert (active=false) - keine Aktion")
        return

    sp = session_path(profile)
    if not sp:
        log("keine Session-Datei (Firefox lief noch nie?)")
        return
    try:
        data = json.loads(read_mozlz4(sp))
    except Exception as e:  # noqa: BLE001
        log(f"Session nicht lesbar: {e}")
        return

    bad = forbidden_urls(data, patterns)
    if not bad:
        log("ok - keine verbotenen Tabs")
        return

    pids = firefox_pids()
    if not pids:
        log(f"{len(bad)} verbotene Tab(s) in Session, aber Firefox laeuft nicht -> uebersprungen")
        return

    log(f"verbotene Tabs: {bad}")
    clean_and_restart(profile, patterns, pids)


def main() -> None:
    log("Focus Lern-Daemon gestartet")
    while True:
        try:
            run_once()
        except Exception as e:  # noqa: BLE001
            log(f"Fehler: {e}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    import sys
    if "--once" in sys.argv:
        run_once()
    else:
        main()
