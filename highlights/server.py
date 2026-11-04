"""Local helper: API + clips for the site (public GitHub Pages page or the bundled copy).

Only the site's own origin (and localhost) may call it. It exits by itself when nobody
has had the site open for a while and nothing is being recorded.
"""
import json
import os
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from . import config, demo, plan, recorder, setup, stealth

JOB = {"running": False, "log": [], "done": 0, "total": 0, "result": None, "error": None}
ANALYZED = {}
MAPS = {}  # (path, mtime) -> map name, so the list doesn't re-read files on every refresh
LAST_SEEN = [time.time()]
IDLE_EXIT = 120  # seconds without an open site tab before the helper quits


def job_log(msg):
    JOB["log"].append(f"{time.strftime('%H:%M:%S')}  {msg}")
    print(msg)


def start_job(path, steamid):
    JOB.update(running=True, log=[], done=0, total=0, result=None, error=None)

    def work():
        try:
            meta = recorder.run(path, steamid, log=job_log,
                                progress=lambda d, t: JOB.update(done=d, total=t))
            JOB["result"] = meta["key"]
        except Exception as e:
            JOB["error"] = str(e)
            job_log("Ошибка: " + str(e))
            traceback.print_exc()
        finally:
            JOB["running"] = False

    threading.Thread(target=work, daemon=True).start()


def find_demos():
    cfg = config.load()
    found = []
    dirs = [os.path.join(os.path.expanduser("~"), "Downloads")]
    if cfg.get("cs2_dir"):
        dirs.insert(0, os.path.join(cfg["csgo_dir"], "replays"))
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            full = os.path.join(d, name)
            if not name.lower().endswith((".dem", ".dem.gz", ".dem.zst")) or name.startswith("fh_"):
                continue
            if os.path.isdir(full):  # unpacked archive: folder named *.dem with the demo inside
                inner = [f for f in os.listdir(full) if f.lower().endswith(".dem")]
                if not inner:
                    continue
                full = os.path.join(full, inner[0])
            if os.path.getsize(full) > 1024 * 1024:
                mtime = os.path.getmtime(full)
                if (full, mtime) not in MAPS:
                    MAPS[(full, mtime)] = demo.peek_map(full)
                found.append({"path": full, "name": name, "map": MAPS[(full, mtime)],
                              "size_mb": round(os.path.getsize(full) / 2**20),
                              "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))})
    found.sort(key=lambda x: x["modified"], reverse=True)
    return found


def allowed_origins(port):
    site = urllib.parse.urlsplit(config.SITE_URL)
    return {f"{site.scheme}://{site.netloc}", f"http://localhost:{port}", f"http://127.0.0.1:{port}"}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=config.SITE, **kw)

    def log_message(self, *a):
        pass

    def translate_path(self, path):
        path = urllib.parse.unquote(path.split("?")[0])
        if path.startswith("/library/"):
            rel = os.path.normpath(path[len("/library/"):]).lstrip("\\/")
            if rel.startswith(".."):
                return os.path.join(config.LIBRARY, "__nope__")
            return os.path.join(config.LIBRARY, rel)
        return super().translate_path(path)

    def _origin_ok(self):
        origin = self.headers.get("Origin")
        return origin is None or origin in allowed_origins(self.server.server_port)

    def end_headers(self):
        origin = self.headers.get("Origin")
        if origin and origin in allowed_origins(self.server.server_port):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_OPTIONS(self):
        # CORS + Chrome's private-network preflight for an https page calling localhost
        if not self._origin_ok():
            self.send_response(403)
            self.end_headers()
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path.startswith("/api/"):
            if not self._origin_ok():
                return self._json({"error": "forbidden"}, 403)
            LAST_SEEN[0] = time.time()
            if path == "/api/ping":
                return self._json({"app": "cs2-highlights", "version": config.VERSION})
            if path == "/api/setup":
                return self._json(setup.status())
            if path == "/api/job":
                return self._json({k: JOB[k] for k in ("running", "log", "done", "total", "result", "error")})
            if path == "/api/demos":
                return self._json(find_demos())
            return self._json({"error": "not found"}, 404)
        if path.endswith(".mp4") and "download=1" in self.path:
            return self._download()
        if "Range" in self.headers and path.endswith(".mp4"):
            return self._range()
        return super().do_GET()

    def _download(self):
        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            return self.send_error(404)
        # clip name for the saved file: <player>_<map>_<clip>.mp4
        parts = os.path.normpath(path).split(os.sep)
        name = f"cs2_{parts[-2]}_{parts[-1]}"
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(os.path.getsize(path)))
        self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.end_headers()
        with open(path, "rb") as f:
            try:
                while chunk := f.read(1 << 20):
                    self.wfile.write(chunk)
            except (ConnectionResetError, BrokenPipeError):
                pass

    def do_POST(self):
        if not self._origin_ok():
            return self._json({"error": "forbidden"}, 403)
        LAST_SEEN[0] = time.time()
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        try:
            if self.path == "/api/setup/accept":
                setup.accept()
                return self._json(setup.status())
            if self.path == "/api/analyze":
                path = demo.unpack_if_gz(data["path"].strip('"'), os.path.join(config.WORK, "demos"))
                if path not in ANALYZED:
                    ANALYZED[path] = demo.analyze(path)
                info = ANALYZED[path]
                players = []
                for p in info["players"]:
                    clips = plan.build(info, p["steamid"])
                    players.append(dict(p, video_seconds=round(plan.total_seconds(clips))))
                return self._json({"path": path, "map": info["map"], "rounds": len(info["rounds"]), "players": players})
            if self.path == "/api/record":
                if not setup.status()["ready"]:
                    return self._json({"error": "Сначала закончи установку"}, 409)
                if JOB["running"]:
                    return self._json({"error": "Уже идёт запись"}, 409)
                start_job(data["path"], data["steamid"])
                return self._json({"ok": True})
            if self.path == "/api/quit":
                self._json({"ok": True})
                threading.Thread(target=shutdown, daemon=True).start()
                return
            if self.path == "/api/open-folder":
                os.startfile(os.path.join(config.LIBRARY, data.get("key", "")) if data.get("key") else config.LIBRARY)
                return self._json({"ok": True})
        except Exception as e:
            traceback.print_exc()
            return self._json({"error": str(e)}, 400)
        self._json({"error": "not found"}, 404)

    def _range(self):
        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            return self.send_error(404)
        size = os.path.getsize(path)
        spec = self.headers["Range"].replace("bytes=", "").split(",")[0]
        a, _, b = spec.partition("-")
        start = int(a) if a else max(0, size - int(b))
        end = min(int(b), size - 1) if a and b else size - 1
        self.send_response(206)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            left = end - start + 1
            try:
                while left > 0:
                    chunk = f.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except (ConnectionResetError, BrokenPipeError):
                pass


def _watchdog():
    """Quit when the site has been closed for IDLE_EXIT seconds and nothing is running."""
    while True:
        time.sleep(10)
        busy = JOB["running"] or setup.STATE["running"]
        if busy:
            LAST_SEEN[0] = time.time()
        elif time.time() - LAST_SEEN[0] > IDLE_EXIT:
            print("Сайт закрыт — выключаюсь.")
            os._exit(0)


def site_url(port):
    if "REPLACE_OWNER" in config.SITE_URL:  # not published yet: use the bundled copy
        return f"http://localhost:{port}/"
    return config.SITE_URL


def _already_running(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=2) as r:
            return json.load(r).get("app") == "cs2-highlights"
    except Exception:
        return False


def serve(open_browser=True, with_window=True):
    os.makedirs(config.LIBRARY, exist_ok=True)
    if getattr(sys, "frozen", False):  # windowed exe: keep a log instead of a console
        sys.stdout = sys.stderr = open(config.LOG, "a", encoding="utf-8", buffering=1)
    cfg = config.load()
    port = cfg["web_port"]
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        if _already_running(port):  # second launch: just bring the site up again
            if open_browser:
                webbrowser.open(site_url(port))
            return
        raise
    if cfg.get("steam_dir"):
        stealth.restore_video(cfg["steam_dir"])  # in case the last recording was cut off mid-way
    threading.Thread(target=_watchdog, daemon=True).start()
    print(time.strftime("%Y-%m-%d %H:%M:%S"), "CS2 Highlights", config.VERSION, "на порту", port)
    if open_browser:
        webbrowser.open(site_url(port))
    if not with_window:
        srv.serve_forever()
        return
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    from . import ui
    ui.run(JOB, site_url(port), shutdown)


def shutdown():
    """Quit for real: stop a running recording (closing CS2), put the user's graphics back."""
    print("Выключаюсь по кнопке.")
    if JOB["running"]:
        subprocess.run(["taskkill", "/F", "/IM", "cs2.exe"], capture_output=True, creationflags=config.NO_WINDOW)
        stealth.wait_cs2_exit(10)
        _mark_stopped()
    cfg = config.load()
    if cfg.get("steam_dir"):
        stealth.restore_video(cfg["steam_dir"])
    os._exit(0)


def _mark_stopped():
    """Recordings cut off by quitting keep their finished clips, just not the 'recording' badge."""
    for path in (os.path.join(config.LIBRARY, "index.json"),
                 *[os.path.join(config.LIBRARY, d, "meta.json") for d in os.listdir(config.LIBRARY)
                   if os.path.isdir(os.path.join(config.LIBRARY, d))]):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            items = data if isinstance(data, list) else [data]
            for it in items:
                if it.get("status") == "recording":
                    it["status"] = "stopped"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
        except (OSError, ValueError):
            pass
