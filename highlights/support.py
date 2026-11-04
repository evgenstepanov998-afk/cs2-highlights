"""Bug reports (to the team's Discord) and self-update from GitHub releases."""
import io
import json
import os
import platform
import re
import subprocess
import tempfile
import threading
import time
import urllib.request
import uuid
import zipfile

from . import config

UA = {"User-Agent": f"Killcam/{config.VERSION}"}


# --- bug reports ---------------------------------------------------------------------------

def _tail(path, lines):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-lines:])
    except OSError:
        return "(нет файла)\n"


def _scrub(text):
    """No personal paths or Windows user name in reports."""
    home = os.path.expanduser("~")
    text = text.replace(home, "%USERPROFILE%").replace(home.replace("\\", "/"), "%USERPROFILE%")
    user = os.environ.get("USERNAME")
    if user and len(user) > 2:
        text = re.sub(re.escape(user), "<user>", text, flags=re.I)
    return text


def _run(*cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20, errors="replace",
                              creationflags=config.NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _gpu():
    out = _run("powershell", "-NoProfile", "-Command",
               "(Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name + ' / ' + $_.DriverVersion }) -join '; '")
    return out.strip() or None


def _file_version(path):
    out = _run("powershell", "-NoProfile", "-Command", f"(Get-Item -LiteralPath '{path}').VersionInfo.FileVersion")
    return out.strip() or None


def _crash_events():
    """Windows 'Application Error' entries for cs2.exe from the last day: they name the module that crashed."""
    out = _run("wevtutil", "qe", "Application", "/c:40", "/rd:true", "/f:text",
               "/q:*[System[(EventID=1000 or EventID=1001 or EventID=1002) and TimeCreated[timediff(@SystemTime) <= 86400000]]]")
    events = [e for e in out.split("Event[") if re.search(r"cs2\.exe|AfxHook|HLAE", e, re.I)]
    return "\n".join("Event[" + e.strip() for e in events[:6]) or "(нет падений cs2.exe за сутки)"


def build_report(comment, job):
    cfg = config.load()
    info = {
        "app": f"{config.APP_NAME} {config.VERSION}",
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "windows": platform.platform(),
        "cs2_version": config.cs2_patch(cfg),
        "hlae_version": _file_version(cfg["hlae_exe"]) if os.path.exists(cfg["hlae_exe"]) else None,
        "gpu": _gpu(),
        "encoder": cfg.get("encoder"),
        "fps": cfg.get("fps"),
        "lang": cfg.get("lang"),
        "cs2_found": bool(cfg.get("cs2_dir")),
        "tools_ok": all(os.path.exists(cfg[k]) for k in ("hlae_exe", "hook_dll", "ffmpeg")),
        "last_job": {k: job.get(k) for k in ("phase", "done", "total", "error", "map", "player")},
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("report.txt", _scrub(f"Комментарий:\n{comment or '-'}\n\n" + json.dumps(info, ensure_ascii=False, indent=1)))
        z.writestr("app_log.txt", _scrub(_tail(config.LOG, 600)))
        z.writestr("last_recording_log.txt", _scrub("\n".join(job.get("log") or [])))
        z.writestr("cs2_console_tail.txt", _scrub(_tail(os.path.join(config.WORK, "netcon.log"), 300)))
        z.writestr("windows_crashes.txt", _scrub(_crash_events()))
    return buf.getvalue(), info


def send_report(comment, job):
    """Posts the zip to the private #ошибки channel. Falls back to a file on the Desktop."""
    data, info = build_report(comment, job)
    name = f"killcam-report-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    if config.REPORT_WEBHOOK:
        try:
            boundary = uuid.uuid4().hex
            text = f"🐞 **Отчёт** · {info['app']} · {info['windows'][:40]}\n> {(comment or '—')[:1500]}"
            payload = json.dumps({"content": text, "username": "Killcam", "allowed_mentions": {"parse": []}})
            body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"payload_json\"\r\n"
                    f"Content-Type: application/json\r\n\r\n{payload}\r\n"
                    f"--{boundary}\r\nContent-Disposition: form-data; name=\"files[0]\"; filename=\"{name}\"\r\n"
                    f"Content-Type: application/zip\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
            req = urllib.request.Request(config.REPORT_WEBHOOK, data=body, method="POST",
                                         headers={**UA, "Content-Type": f"multipart/form-data; boundary={boundary}"})
            with urllib.request.urlopen(req, timeout=30) as r:
                if r.status < 300:
                    return {"ok": True, "sent": True}
        except Exception as e:
            print("report upload failed:", e)
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    path = os.path.join(desktop if os.path.isdir(desktop) else config.DATA, name)
    with open(path, "wb") as f:
        f.write(data)
    return {"ok": True, "sent": False, "path": path}


# --- updates -------------------------------------------------------------------------------

UPDATE = {"checked": None, "latest": None, "available": False, "notes": "", "url": None,
          "error": None, "downloading": False, "progress": 0.0}


def _ver(s):
    return tuple(int(x) for x in re.findall(r"\d+", s or "")[:3]) or (0,)


def check_updates():
    UPDATE["error"] = None
    if config.DEMO:  # the demo build is handed over by hand, never updated from the public releases
        UPDATE.update(available=False, checked=time.time())
        return UPDATE
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{config.REPO}/releases/latest", headers=UA)
        with urllib.request.urlopen(req, timeout=15) as r:
            rel = json.load(r)
        asset = next((a for a in rel.get("assets", []) if a["name"].lower().endswith("setup.exe")), None)
        UPDATE.update(latest=rel.get("tag_name", "").lstrip("v"), notes=(rel.get("body") or "")[:2000],
                      url=asset and asset["browser_download_url"])
        UPDATE["available"] = bool(asset) and _ver(UPDATE["latest"]) > _ver(config.VERSION)
    except urllib.error.HTTPError as e:
        # 404 = nothing published yet: that's "up to date", not an error
        if e.code != 404:
            UPDATE["error"] = f"HTTP {e.code}"
        UPDATE["available"] = False
    except Exception as e:
        UPDATE["error"] = type(e).__name__
    UPDATE["checked"] = int(time.time())
    return dict(UPDATE)


def install_update(on_exit):
    """Downloads the new installer, starts it silently and quits so it can replace the files.
    The installer starts Killcam again when it's done."""
    if not UPDATE.get("available") or UPDATE["downloading"]:
        return

    def work():
        UPDATE.update(downloading=True, progress=0.0, error=None)
        try:
            dst = os.path.join(tempfile.gettempdir(), f"KillcamSetup-{UPDATE['latest']}.exe")
            req = urllib.request.Request(UPDATE["url"], headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r, open(dst, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                done = 0
                while chunk := r.read(1 << 20):
                    f.write(chunk)
                    done += len(chunk)
                    UPDATE["progress"] = done / total if total else 0.5
            subprocess.Popen([dst, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
                             creationflags=0x00000008)  # DETACHED_PROCESS: outlives us
            on_exit()
        except Exception as e:
            UPDATE.update(downloading=False, error=type(e).__name__)

    threading.Thread(target=work, daemon=True).start()
