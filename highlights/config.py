"""Where things live and how this PC is set up (Steam, CS2, video encoder).

UI files ship inside the app; tools go to %LOCALAPPDATA%\\Killcam; clips and settings
go to Documents\\Killcam so the user can find them.
"""
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys

APP_NAME = "Killcam"
VERSION = "2.0.0"
REPO = "evgenstepanov998-afk/killcam"
# Discord webhook of the private bug-report channel; lives in the git-ignored secrets_local.py
# (empty = the report is saved to the Desktop instead)
try:
    from .secrets_local import REPORT_WEBHOOK
except ImportError:
    REPORT_WEBHOOK = ""

NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW: no console flashes from helper processes

BUNDLE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UI = os.path.join(BUNDLE, "ui")


def _documents():
    buf = ctypes.create_unicode_buffer(260)
    if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0:  # CSIDL_PERSONAL
        return buf.value
    return os.path.join(os.path.expanduser("~"), "Documents")


LOCAL = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
DATA = os.path.join(_documents(), APP_NAME)
LIBRARY = os.path.join(DATA, "library")
WORK = os.path.join(DATA, "work")
TOOLS = os.path.join(LOCAL, APP_NAME, "tools")
CONFIG = os.path.join(DATA, "settings.json")
LOG = os.path.join(LOCAL, APP_NAME, "log.txt")

DEFAULTS = {
    "width": 1920,
    "height": 1080,
    "fps": 60,
    "lang": None,  # None = follow Windows
    "auto_update": True,
    "netcon_port": 2121,
}

ENCODERS = [
    # (name, ffmpeg args) — first one that works on this PC wins
    ("h264_nvenc", "-c:v h264_nvenc -preset p1 -rc vbr -cq 23 -b:v 0 -maxrate 40M -bufsize 80M -pix_fmt yuv420p"),
    ("h264_amf", "-c:v h264_amf -quality speed -rc cqp -qp_i 23 -qp_p 23 -pix_fmt yuv420p"),
    ("h264_qsv", "-c:v h264_qsv -preset veryfast -global_quality 23 -pix_fmt nv12"),
    ("libx264", "-c:v libx264 -preset ultrafast -crf 23 -pix_fmt yuv420p"),
]


def migrate_old_install():
    """Earlier builds were called "CS2 Highlights": keep their clips and tools."""
    old_data = os.path.join(_documents(), "CS2 Highlights")
    old_tools = os.path.join(LOCAL, "CS2Highlights", "tools")
    try:
        if os.path.isdir(os.path.join(old_data, "library")) and not os.path.exists(LIBRARY):
            os.makedirs(DATA, exist_ok=True)
            shutil.move(os.path.join(old_data, "library"), LIBRARY)
            old_cfg = os.path.join(old_data, "config.json")
            if os.path.exists(old_cfg) and not os.path.exists(CONFIG):
                shutil.copyfile(old_cfg, CONFIG)
            shutil.rmtree(old_data, ignore_errors=True)
        if os.path.isdir(old_tools) and not os.path.exists(TOOLS):
            os.makedirs(os.path.dirname(TOOLS), exist_ok=True)
            shutil.move(old_tools, TOOLS)
            shutil.rmtree(os.path.dirname(old_tools), ignore_errors=True)
    except OSError:
        pass


def windows_lang():
    lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
    return "ru" if lang_id in (0x19, 0x22, 0x23) else "en"  # ru, uk, be → Russian UI


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
        try:
            with open(CONFIG, encoding="utf-8") as f:
                return json.load(f)
        except ValueError:
            pass
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
    cfg["lang"] = cfg.get("lang") or windows_lang()
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
