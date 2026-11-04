"""Where things live and how this PC is set up (Steam, CS2, video encoder).

Program files (site) ship inside the exe; tools go to %LOCALAPPDATA%\\CS2Highlights;
clips and settings go to Documents\\CS2 Highlights so the user can find them.
"""
import ctypes
import json
import os
import re
import subprocess
import sys

# Set at build time: the public site this app belongs to.
SITE_URL = "https://evgenstepanov998-afk.github.io/cs2-highlights/"
RELEASES_URL = "https://github.com/evgenstepanov998-afk/cs2-highlights/releases/latest"
VERSION = "1.0.0"

NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW: no console flashes from helper processes

BUNDLE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SITE = os.path.join(BUNDLE, "site")


def _documents():
    buf = ctypes.create_unicode_buffer(260)
    if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0:  # CSIDL_PERSONAL
        return buf.value
    return os.path.join(os.path.expanduser("~"), "Documents")


DATA = os.path.join(_documents(), "CS2 Highlights")
LIBRARY = os.path.join(DATA, "library")
WORK = os.path.join(DATA, "work")
TOOLS = os.path.join(os.environ.get("LOCALAPPDATA", DATA), "CS2Highlights", "tools")
CONFIG = os.path.join(DATA, "config.json")
LOG = os.path.join(DATA, "log.txt")

DEFAULTS = {
    "width": 1920,
    "height": 1080,
    "fps": 60,
    "netcon_port": 2121,
    "web_port": 8765,
}

ENCODERS = [
    # (name, ffmpeg args) — first one that works on this PC wins
    ("h264_nvenc", "-c:v h264_nvenc -preset p1 -rc vbr -cq 23 -b:v 0 -maxrate 40M -bufsize 80M -pix_fmt yuv420p"),
    ("h264_amf", "-c:v h264_amf -quality speed -rc cqp -qp_i 23 -qp_p 23 -pix_fmt yuv420p"),
    ("h264_qsv", "-c:v h264_qsv -preset veryfast -global_quality 23 -pix_fmt nv12"),
    ("libx264", "-c:v libx264 -preset ultrafast -crf 23 -pix_fmt yuv420p"),
]


def find_steam():
    import winreg
    for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                      (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
        for value in ("SteamPath", "InstallPath"):
            try:
                with winreg.OpenKey(hive, key) as k:
                    path = os.path.normpath(winreg.QueryValueEx(k, value)[0])
                    if os.path.isdir(path):
                        return path
            except OSError:
                pass
    default = r"C:\Program Files (x86)\Steam"
    return default if os.path.isdir(default) else None


def find_cs2(steam):
    """CS2 can sit in any Steam library folder; libraryfolders.vdf lists them."""
    libs = [steam]
    vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
    if os.path.exists(vdf):
        with open(vdf, encoding="utf-8", errors="ignore") as f:
            libs += [p.replace("\\\\", "\\") for p in re.findall(r'"path"\s+"([^"]+)"', f.read())]
    for lib in libs:
        d = os.path.join(lib, "steamapps", "common", "Counter-Strike Global Offensive")
        if os.path.exists(os.path.join(d, "game", "bin", "win64", "cs2.exe")):
            return d
    return None


def pick_encoder(ffmpeg):
    for name, args in ENCODERS:
        r = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                            "color=s=640x360:r=60", "-frames:v", "5", *args.split(), "-f", "null", "-"],
                           capture_output=True, creationflags=NO_WINDOW)
        if r.returncode == 0:
            return name, args
    return ENCODERS[-1]


def _read():
    if os.path.exists(CONFIG):
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save(**values):
    os.makedirs(DATA, exist_ok=True)
    cur = _read()
    cur.update(values)
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cur, f, ensure_ascii=False, indent=1)


def load():
    cfg = dict(DEFAULTS)
    cfg.update(_read())
    cfg.setdefault("hlae_dir", os.path.join(TOOLS, "hlae"))
    if not cfg.get("cs2_dir"):
        steam = find_steam()
        cfg["cs2_dir"] = find_cs2(steam) if steam else None
    cs2 = cfg["cs2_dir"] or ""
    cfg["steam_dir"] = os.path.dirname(os.path.dirname(os.path.dirname(cs2))) if cs2 else (find_steam() or "")
    cfg["cs2_exe"] = os.path.join(cs2, "game", "bin", "win64", "cs2.exe")
    cfg["csgo_dir"] = os.path.join(cs2, "game", "csgo")
    cfg["hlae_exe"] = os.path.join(cfg["hlae_dir"], "HLAE.exe")
    cfg["hook_dll"] = os.path.join(cfg["hlae_dir"], "x64", "AfxHookSource2.dll")
    cfg["ffmpeg"] = os.path.join(cfg["hlae_dir"], "ffmpeg", "bin", "ffmpeg.exe")
    return cfg
