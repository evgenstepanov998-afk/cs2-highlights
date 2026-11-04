"""Killcam desktop window: the UI runs inside WebView2, Python does files, dialogs and CS2."""
import ctypes
import json
import os
import shutil
import sys
import webbrowser

import webview
from webview.dom import DOMEventHandler

from . import config, server

MUTEX_NAME = "Local\\KillcamSingleInstance"
DEMO_EXT = (".dem", ".dem.gz", ".dem.zst")


class Bridge:
    """Methods the page calls as window.pywebview.api.<name>(...)."""

    def __init__(self):
        self._window = None

    def pick_demo(self):
        res = self._window.create_file_dialog(
            webview.FileDialog.OPEN, allow_multiple=False,
            file_types=("CS2 demo (*.dem;*.gz;*.zst)", "All files (*.*)"))
        return res[0] if res else None

    def save_clip(self, key, file, suggested):
        src = os.path.join(config.LIBRARY, key, file)
        if not os.path.isfile(src) or os.path.basename(file) != file:
            return {"ok": False}
        res = self._window.create_file_dialog(webview.FileDialog.SAVE, save_filename=suggested,
                                             file_types=("MP4 video (*.mp4)",))
        if not res:
            return {"ok": False, "cancelled": True}
        dst = res if isinstance(res, str) else res[0]
        if not dst.lower().endswith(".mp4"):
            dst += ".mp4"
        shutil.copyfile(src, dst)
        return {"ok": True, "path": dst}

    def show_in_folder(self, path):
        if os.path.exists(path):
            os.startfile(os.path.dirname(path))

    def open_external(self, url):
        if url.startswith("https://"):
            webbrowser.open(url)

    def is_recording(self):
        return server.JOB["running"]


def _single_instance():
    """Second launch focuses the running window instead of starting a second copy."""
    ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        hwnd = ctypes.windll.user32.FindWindowW(None, config.APP_NAME)
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        return False
    return True


def main():
    if not _single_instance():
        return
    os.makedirs(os.path.dirname(config.LOG), exist_ok=True)
    if getattr(sys, "frozen", False):  # windowed app: keep a log instead of a console
        sys.stdout = sys.stderr = open(config.LOG, "a", encoding="utf-8", buffering=1)
    config.migrate_old_install()
    cfg = config.load()
    if cfg.get("steam_dir"):
        server.stealth.restore_video(cfg["steam_dir"])  # in case the last run was cut off mid-recording

    base = server.start()
    bridge = Bridge()
    window = webview.create_window(
        config.APP_NAME, f"{base}/index.html#token={server.TOKEN}", js_api=bridge,
        width=1360, height=860, min_size=(1040, 680), background_color="#09090c")
    bridge._window = window

    def on_drop(e):
        files = e.get("dataTransfer", {}).get("files", [])
        paths = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
        demos = [p for p in paths if p.lower().endswith(DEMO_EXT) or os.path.isdir(p)]
        if demos:
            window.evaluate_js(f"window.onDemoDropped && window.onDemoDropped({json.dumps(demos[0])})")

    def on_loaded():
        window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)

    def on_closing():
        if server.JOB["running"]:
            ru = cfg["lang"] == "ru"
            ok = window.create_confirmation_dialog(
                "Killcam",
                "Идёт запись. Остановить её и закрыть Killcam?\nГотовые клипы сохранятся."
                if ru else "Recording in progress. Stop it and close Killcam?\nFinished clips are kept.")
            if not ok:
                return False
        server.shutdown_cleanup()
        return True

    window.events.loaded += on_loaded
    window.events.closing += on_closing
    print(config.APP_NAME, config.VERSION, "started")
    webview.start(gui="edgechromium", debug=False, private_mode=True)
    os._exit(0)
