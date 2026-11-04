"""First run: after the user accepts the terms, download HLAE + ffmpeg and check the PC."""
import json
import os
import shutil
import threading
import urllib.request
import zipfile

from . import config

HLAE_API = "https://api.github.com/repos/advancedfx/advancedfx/releases/latest"
FFMPEG_API = "https://api.github.com/repos/GyanD/codexffmpeg/releases/latest"

STATE = {"running": False, "step": "", "progress": 0.0, "error": None}


def status():
    cfg = config.load()
    tools_ok = all(os.path.exists(cfg[k]) for k in ("hlae_exe", "hook_dll", "ffmpeg"))
    return {
        "accepted": bool(cfg.get("accepted")),
        "ready": bool(cfg.get("accepted") and tools_ok and cfg.get("ffmpeg_video")),
        "cs2_found": bool(cfg.get("cs2_dir")),
        "cs2_dir": cfg.get("cs2_dir"),
        "encoder": cfg.get("encoder"),
        "data_dir": config.DATA,
        "version": config.VERSION,
        **STATE,
    }


def _asset(api, pattern):
    req = urllib.request.Request(api, headers={"User-Agent": "cs2-highlights"})
    with urllib.request.urlopen(req, timeout=30) as r:
        rel = json.load(r)
    for a in rel["assets"]:
        if pattern(a["name"]):
            return a["browser_download_url"], a["size"]
    raise RuntimeError(f"не нашёл файл для скачивания в {api}")


def _download(url, size, dst, share_from, share_to):
    req = urllib.request.Request(url, headers={"User-Agent": "cs2-highlights"})
    done = 0
    with urllib.request.urlopen(req, timeout=60) as r, open(dst, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
            done += len(chunk)
            STATE["progress"] = share_from + (share_to - share_from) * min(1, done / max(size, 1))


def _work():
    tmp = os.path.join(config.TOOLS, "download")
    try:
        os.makedirs(tmp, exist_ok=True)
        hlae_dir = os.path.join(config.TOOLS, "hlae")

        STATE["step"] = "Скачиваю HLAE…"
        url, size = _asset(HLAE_API, lambda n: n.startswith("hlae_") and n.endswith(".zip"))
        _download(url, size, os.path.join(tmp, "hlae.zip"), 0.0, 0.1)
        shutil.rmtree(hlae_dir, ignore_errors=True)
        with zipfile.ZipFile(os.path.join(tmp, "hlae.zip")) as z:
            z.extractall(hlae_dir)

        STATE["step"] = "Скачиваю ffmpeg…"
        url, size = _asset(FFMPEG_API, lambda n: n.endswith("essentials_build.zip"))
        _download(url, size, os.path.join(tmp, "ffmpeg.zip"), 0.1, 0.9)
        STATE["step"] = "Распаковываю…"
        bin_dir = os.path.join(hlae_dir, "ffmpeg", "bin")
        os.makedirs(bin_dir, exist_ok=True)
        with zipfile.ZipFile(os.path.join(tmp, "ffmpeg.zip")) as z:
            for n in z.namelist():
                if n.endswith("/bin/ffmpeg.exe"):
                    with z.open(n) as src, open(os.path.join(bin_dir, "ffmpeg.exe"), "wb") as dst:
                        shutil.copyfileobj(src, dst)

        STATE["step"] = "Проверяю видеокарту…"
        STATE["progress"] = 0.95
        name, args = config.pick_encoder(os.path.join(bin_dir, "ffmpeg.exe"))
        config.save(encoder=name, ffmpeg_video=args)
        STATE["step"] = "Готово"
        STATE["progress"] = 1.0
    except Exception as e:
        STATE["error"] = f"Не получилось установить: {e}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        STATE["running"] = False


def accept():
    config.save(accepted=True)
    if STATE["running"] or status()["ready"]:
        return
    STATE.update(running=True, step="Начинаю…", progress=0.0, error=None)
    threading.Thread(target=_work, daemon=True).start()
