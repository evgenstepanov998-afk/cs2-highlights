"""Local API + clip files for the Killcam window.

Bound to 127.0.0.1 on a random port, and every request must carry the per-launch token,
so nothing else on the PC (or any web page) can drive recordings or read the library.
"""
import json
import os
import secrets
import shutil
import subprocess
import threading
import time
import traceback
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from . import config, demo, plan, recorder, setup, stealth, support

TOKEN = secrets.token_urlsafe(24)
JOB = {"running": False, "log": [], "done": 0, "total": 0, "result": None, "error": None,
       "phase": None, "player": None, "map": None}
ANALYZED = {}
MAPS = {}  # (path, mtime) -> map name, so the list doesn't re-read files on every refresh


def job_log(msg):
    JOB["log"].append(f"{time.strftime('%H:%M:%S')}  {msg}")
    JOB["log"] = JOB["log"][-200:]
    print(msg)


def start_job(path, steamid):
    info = ANALYZED.get(path)
    me = next((p for p in info["players"] if p["steamid"] == steamid), None) if info else None
    JOB.update(running=True, log=[], done=0, total=0, result=None, error=None, phase="launch",
               player=me and me["name"], map=info and info["map"])

    def work():
        try:
            meta = recorder.run(path, steamid, log=job_log,
                                progress=lambda d, t: JOB.update(done=d, total=t),
                                phase=lambda name: JOB.update(phase=name))
            JOB["result"] = meta["key"]
        except recorder.GameError as e:
            JOB["error"] = {"code": e.code, "detail": e.detail}
            job_log(f"Ошибка: {e}")
        except Exception as e:
            JOB["error"] = {"code": "unknown", "detail": str(e)}
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
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            if size > 1024 * 1024:
                mtime = os.path.getmtime(full)
                if (full, mtime) not in MAPS:
                    MAPS[(full, mtime)] = demo.peek_map(full)
                found.append({"path": full, "name": name, "map": MAPS[(full, mtime)],
                              "size_mb": round(size / 2**20),
                              "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))})
    found.sort(key=lambda x: x["modified"], reverse=True)
    return found


def demo_info(path):
    """Players with K/D and how long their highlights will take, for the player picker."""
    path = demo.unpack_if_gz(path.strip('"'), os.path.join(config.WORK, "demos"))
    if path not in ANALYZED:
        ANALYZED[path] = demo.analyze(path)
    info = ANALYZED[path]
    players = []
    for p in info["players"]:
        clips = plan.build(info, p["steamid"])
        players.append(dict(p, video_seconds=round(plan.total_seconds(clips)),
                            clips=sum(1 for c in clips if not c.get("inside_death"))))
    return {"path": path, "map": info["map"], "rounds": len(info["rounds"]), "players": players}


def read_index():
    path = os.path.join(config.LIBRARY, "index.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            items = json.load(f)
    except ValueError:
        return []
    # an entry whose folder vanished (deleted by hand) shouldn't show up
    return [i for i in items if os.path.isdir(os.path.join(config.LIBRARY, i["key"]))]


def delete_recording(key):
    if not key or os.sep in key or "/" in key or key.startswith("."):
        raise ValueError("bad key")
    if JOB["running"] and JOB.get("result") == key:
        raise ValueError("busy")
    shutil.rmtree(os.path.join(config.LIBRARY, key), ignore_errors=True)
    items = [i for i in read_index() if i["key"] != key]
    with open(os.path.join(config.LIBRARY, "index.json"), "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)


def settings_view():
    cfg = config.load()
    return {"lang": cfg["lang"], "fps": cfg["fps"], "encoder": cfg.get("encoder"),
            "cs2_dir": cfg.get("cs2_dir"), "data_dir": config.DATA, "version": config.VERSION,
            "repo": config.REPO, "auto_update": cfg.get("auto_update", True),
            "reports_to_discord": bool(config.REPORT_WEBHOOK)}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=config.UI, **kw)

    def log_message(self, *a):
        pass

    def _authorized(self):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        return secrets.compare_digest(self.headers.get("X-Killcam-Token") or (q.get("t") or [""])[0], TOKEN)

    def translate_path(self, path):
        path = urllib.parse.unquote(path.split("?")[0])
        if path.startswith("/library/"):
            rel = os.path.normpath(path[len("/library/"):]).lstrip("\\/")
            if rel.startswith(".."):
                return os.path.join(config.LIBRARY, "__nope__")
            return os.path.join(config.LIBRARY, rel)
        return super().translate_path(path)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        # the UI shell itself is public (it's just our own HTML); data needs the token
        if path.startswith("/api/") or path.startswith("/library/"):
            if not self._authorized():
                return self._json({"error": "forbidden"}, 403)
        if path.startswith("/api/"):
            if path == "/api/setup":
                return self._json(setup.status())
            if path == "/api/job":
                return self._json({k: JOB[k] for k in JOB})
            if path == "/api/demos":
                return self._json(find_demos())
            if path == "/api/library":
                return self._json(read_index())
            if path == "/api/settings":
                return self._json(settings_view())
            if path == "/api/update":
                return self._json(support.UPDATE)
            return self._json({"error": "not found"}, 404)
        if "Range" in self.headers and path.endswith(".mp4"):
            return self._range()
        return super().do_GET()

    def do_POST(self):
        if not self._authorized():
            return self._json({"error": "forbidden"}, 403)
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        try:
            if self.path == "/api/setup/accept":
                setup.accept()
                return self._json(setup.status())
            if self.path == "/api/analyze":
                return self._json(demo_info(data["path"]))
            if self.path == "/api/record":
                if not setup.status()["ready"]:
                    return self._json({"error": "not_ready"}, 409)
                if JOB["running"]:
                    return self._json({"error": "busy"}, 409)
                start_job(data["path"], data["steamid"])
                return self._json({"ok": True})
            if self.path == "/api/settings":
                allowed = {k: data[k] for k in ("lang", "fps", "auto_update") if k in data}
                if "fps" in allowed and allowed["fps"] not in (60, 144):
                    allowed.pop("fps")
                config.save(**allowed)
                return self._json(settings_view())
            if self.path == "/api/report":
                return self._json(support.send_report(str(data.get("comment", ""))[:4000], dict(JOB)))
            if self.path == "/api/update/check":
                return self._json(support.check_updates())
            if self.path == "/api/update/install":
                if JOB["running"]:
                    return self._json({"error": "busy"}, 409)
                support.install_update(lambda: (shutdown_cleanup(), os._exit(0)))
                return self._json({"ok": True})
            if self.path == "/api/delete":
                delete_recording(data.get("key"))
                return self._json({"ok": True})
            if self.path == "/api/open-folder":
                key = data.get("key")
                target = os.path.join(config.LIBRARY, key) if key and os.sep not in key else config.LIBRARY
                os.makedirs(target, exist_ok=True)
                os.startfile(target)
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
            except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
                pass


def _find_demo_file(name):
    """The original demo (archive first: its time is closest to the match), not our unpacked copy."""
    cfg = config.load()
    dirs = [os.path.join(os.path.expanduser("~"), "Downloads")]
    if cfg.get("cs2_dir"):
        dirs.append(os.path.join(cfg["csgo_dir"], "replays"))
    for d in dirs:
        for cand in (os.path.join(d, name + ".gz"), os.path.join(d, name + ".zst"),
                     os.path.join(d, name), os.path.join(d, name, name)):
            if os.path.isfile(cand):
                return cand
    cand = os.path.join(config.WORK, "demos", name)
    return cand if os.path.isfile(cand) else None


def backfill():
    """Recordings made by older versions get a picture, the score and the match date."""
    cfg = config.load()
    _mark_stopped()  # nothing records at startup: a "recording" badge is left over from a crash
    for item in read_index():
        meta_path = os.path.join(config.LIBRARY, item["key"], "meta.json")
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            changed = False
            if not meta.get("thumb"):
                first = next((c["file"] for c in meta["clips"] if c.get("file")), None)
                if first:
                    meta["thumb"] = recorder.make_thumb(cfg["ffmpeg"], os.path.join(config.LIBRARY, item["key"], first),
                                                        os.path.join(config.LIBRARY, item["key"]), meta["map"])
                    changed = True
            if "score" not in meta or meta.get("time_v") != 2:
                path = _find_demo_file(meta["demo"])
                if path:
                    meta["time_v"] = 2  # v1 of this backfill took the time from the unpacked copy
                    info = demo.analyze(demo.unpack_if_gz(path, os.path.join(config.WORK, "demos")))
                    me = next((p for p in info["players"] if p["steamid"] == meta["player"]["steamid"]), None)
                    if me:
                        meta["score"] = [me["won"], me["lost"]]
                        meta["match_time"] = demo.match_time(path)
                        changed = True
            if changed:
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, ensure_ascii=False, indent=1)
                recorder.update_index(dict(item, thumb=meta.get("thumb"), score=meta.get("score"),
                                           match_time=meta.get("match_time")))
        except Exception:
            traceback.print_exc()


def start():
    """Start the API on a free localhost port; returns the base URL."""
    os.makedirs(config.LIBRARY, exist_ok=True)
    threading.Thread(target=backfill, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_port}"


def shutdown_cleanup():
    """Stop a running recording (closing CS2) and put the user's graphics back."""
    if JOB["running"]:
        subprocess.run(["taskkill", "/F", "/IM", "cs2.exe"], capture_output=True, creationflags=config.NO_WINDOW)
        stealth.wait_cs2_exit(10)
        _mark_stopped()
    cfg = config.load()
    if cfg.get("steam_dir"):
        stealth.restore_video(cfg["steam_dir"])


def _mark_stopped():
    """Recordings cut off by quitting keep their finished clips, just not the 'recording' badge."""
    paths = [os.path.join(config.LIBRARY, "index.json")]
    paths += [os.path.join(config.LIBRARY, d, "meta.json") for d in os.listdir(config.LIBRARY)
              if os.path.isdir(os.path.join(config.LIBRARY, d))]
    for path in paths:
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
