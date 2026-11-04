"""Exporting clips out of the library: several clips glued into one video, horizontal 16:9 or
vertical 9:16 (TikTok / Shorts / Reels), with the Killcam watermark; optionally posted to a
Discord channel through the user's own webhook.

Clips in the library stay clean; the watermark is added only to what leaves the app."""
import json
import os
import re
import subprocess
import threading
import time
import urllib.request
import uuid

from . import config

EXPORTS = {}  # id -> {"state": "working"|"done"|"error", "path", "seconds", "error", "sent"}
DISCORD_LIMIT = 10 * 1024 * 1024  # what a server without boosts accepts per file
WEBHOOK_RE = re.compile(r"^https://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]+$")


def valid_webhook(url):
    return bool(WEBHOOK_RE.match(url.strip()))


def _pieces(key, clip_ids):
    """(file, start, duration) for each chosen clip, in the order given. A kill that happened
    inside a death clip plays from that clip's file, 4 s from its offset (as in the viewer)."""
    with open(os.path.join(config.LIBRARY, key, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    by_id = {c["id"]: c for c in meta["clips"]}
    out = []
    for cid in clip_ids:
        c = by_id.get(cid)
        if not c or not c.get("file") or os.path.basename(c["file"]) != c["file"]:
            continue
        path = os.path.join(config.LIBRARY, key, c["file"])
        if c.get("inside_death"):
            out.append((path, float(c.get("offset") or 0), 4.0))
        else:
            out.append((path, 0.0, None))
    return meta, out


def _duration(cfg, path):
    r = subprocess.run([cfg["ffmpeg"], "-hide_banner", "-i", path], capture_output=True, text=True,
                       errors="replace", creationflags=config.NO_WINDOW)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def render(key, clip_ids, vertical=False, out_path=None):
    """One mp4 from the chosen clips. Returns (path, seconds)."""
    cfg = config.load()
    meta, pieces = _pieces(key, clip_ids)
    if not pieces:
        raise ValueError("no clips")
    os.makedirs(os.path.join(config.WORK, "exports"), exist_ok=True)
    out_path = out_path or os.path.join(config.WORK, "exports", f"{uuid.uuid4().hex[:10]}.mp4")
    W, H = (1080, 1920) if vertical else (1920, 1080)

    args, chains, labels = [], [], ""
    for i, (path, start, dur) in enumerate(pieces):
        if start:
            args += ["-ss", f"{start:.2f}"]
        if dur:
            args += ["-t", f"{dur:.2f}"]
        args += ["-i", path]
        frame = ("crop=trunc(ih*9/16/2)*2:ih," if vertical else "") + f"scale={W}:{H}:flags=lanczos,setsar=1,fps=60"
        chains.append(f"[{i}:v]{frame},setpts=PTS-STARTPTS[v{i}]")
        chains.append(f"[{i}:a]aresample=48000,asetpts=PTS-STARTPTS[a{i}]")
        labels += f"[v{i}][a{i}]"
    n = len(pieces)
    args += ["-i", os.path.join(config.UI, "watermark.png")]
    # vertical: centred just under the scoreboard (TikTok's own buttons and captions sit low/right)
    wm_w = 380 if vertical else 300
    pos = "x=(W-w)/2:y=H*0.205" if vertical else "x=W-w-30:y=H-h-26"
    chains.append(f"{labels}concat=n={n}:v=1:a=1[cv][ca]")
    chains.append(f"[{n}:v]scale={wm_w}:-1,format=rgba,colorchannelmixer=aa=0.88[wm]")
    chains.append(f"[cv][wm]overlay={pos}:format=auto[ov]")
    video_args = [a for a in cfg["ffmpeg_video"].split()]
    subprocess.run([cfg["ffmpeg"], "-hide_banner", "-loglevel", "error", "-y", *args,
                    "-filter_complex", ";".join(chains), "-map", "[ov]", "-map", "[ca]",
                    *video_args, "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out_path],
                   check=True, capture_output=True, creationflags=config.NO_WINDOW)
    return out_path, _duration(cfg, out_path)


def fit_for_discord(path, seconds):
    """Discord refuses files over 10 MB on ordinary servers: re-encode to fit, keeping 60 fps."""
    if os.path.getsize(path) <= DISCORD_LIMIT * 0.95:
        return path
    cfg = config.load()
    budget_kbit = DISCORD_LIMIT * 0.88 * 8 / 1000 / max(seconds, 1)
    v_kbit = max(300, int(budget_kbit - 96))
    small = path[:-4] + "_discord.mp4"
    portrait = _is_portrait(cfg, path)
    scale = "scale=720:1280" if portrait else "scale=1280:720"
    subprocess.run([cfg["ffmpeg"], "-hide_banner", "-loglevel", "error", "-y", "-i", path, "-vf", scale,
                    "-c:v", "libx264", "-preset", "veryfast", "-b:v", f"{v_kbit}k", "-maxrate", f"{v_kbit}k",
                    "-bufsize", f"{v_kbit * 2}k", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k",
                    "-movflags", "+faststart", small],
                   check=True, capture_output=True, creationflags=config.NO_WINDOW)
    return small


def _is_portrait(cfg, path):
    r = subprocess.run([cfg["ffmpeg"], "-hide_banner", "-i", path], capture_output=True, text=True,
                       errors="replace", creationflags=config.NO_WINDOW)
    m = re.search(r"Video:.*?(\d{3,5})x(\d{3,5})", r.stderr)
    return bool(m) and int(m.group(2)) > int(m.group(1))


def send_to_discord(webhook, path, text, filename):
    boundary = uuid.uuid4().hex
    payload = json.dumps({"content": text[:1900], "username": "Killcam", "allowed_mentions": {"parse": []}})
    with open(path, "rb") as f:
        data = f.read()
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"payload_json\"\r\n"
            f"Content-Type: application/json\r\n\r\n{payload}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"files[0]\"; filename=\"{filename}\"\r\n"
            f"Content-Type: video/mp4\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(webhook.strip(), data=body, method="POST", headers={
        "User-Agent": f"Killcam/{config.VERSION}", "Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.status < 300


def start(key, clip_ids, vertical, discord_text=None):
    """Runs in the background; the UI polls EXPORTS[id]. With discord_text the result is also
    posted to the webhook from the settings."""
    eid = uuid.uuid4().hex[:10]
    EXPORTS[eid] = {"state": "working", "path": None, "seconds": 0, "error": None, "sent": False}

    def work():
        st = EXPORTS[eid]
        try:
            path, secs = render(key, clip_ids, vertical)
            st.update(path=path, seconds=round(secs, 1))
            if discord_text is not None:
                hook = config.load().get("discord_webhook")
                if not hook:
                    raise RuntimeError("no_webhook")
                small = fit_for_discord(path, secs)
                if os.path.getsize(small) > DISCORD_LIMIT:
                    raise RuntimeError("too_big")
                st["sent"] = send_to_discord(hook, small, discord_text, os.path.basename(_nice_name(key, vertical)))
            st["state"] = "done"
        except Exception as e:
            st.update(state="error", error=str(e) if str(e) in ("no_webhook", "too_big") else "export_failed")
            print("export failed:", repr(e))

    threading.Thread(target=work, daemon=True).start()
    return eid


def _nice_name(key, vertical):
    try:
        with open(os.path.join(config.LIBRARY, key, "meta.json"), encoding="utf-8") as f:
            m = json.load(f)
        base = f"Killcam_{m['player']['name']}_{(m['map'] or '').replace('de_', '')}"
    except (OSError, ValueError, KeyError):
        base = "Killcam"
    base = re.sub(r"[^\w.\-]+", "_", base) + ("_9x16" if vertical else "") + time.strftime("_%H%M%S")
    return base + ".mp4"


def cleanup():
    """Exports are temporary: they live until the app closes."""
    d = os.path.join(config.WORK, "exports")
    if os.path.isdir(d):
        for name in os.listdir(d):
            try:
                os.remove(os.path.join(d, name))
            except OSError:
                pass
