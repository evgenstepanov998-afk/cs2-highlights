"""Driving CS2 (injected with HLAE) over the netcon port to record every segment.

HLAE records at a fixed FPS, so the game runs as fast as the GPU can render
instead of in real time. Each segment is armed with mirv_cmd tick triggers:
start recording at the first tick, stop + pause + echo a marker at the last.
"""
import glob
import json
import os
import queue
import shutil
import socket
import subprocess
import threading
import time

from . import config, demo, plan, stealth

TICK = demo.TICKRATE
PREROLL = 40  # ticks played before recording so the seek and camera settle
REC_VOLUME = 0.03  # in-game volume while recording: barely audible in the user's speakers
AUDIO_GAIN = 20    # back to the level of volume 0.6 in the clips


class GameError(RuntimeError):
    """`code` is a stable id the app translates; `detail` is extra context for the log."""

    def __init__(self, code, detail=""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


class NetCon:
    def __init__(self, port, log):
        self.port = port
        self.log = log
        self.sock = None
        self.buf = b""
        self.full = []  # whole console output, saved to work/netcon.log for debugging

    def connect(self, timeout):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                self.sock = socket.create_connection(("127.0.0.1", self.port), timeout=2)
                self.sock.settimeout(0.5)
                return
            except OSError:
                time.sleep(1)
        raise GameError("cs2_no_console")

    def send(self, *cmds):
        for c in cmds:
            self.sock.sendall((c + "\n").encode("utf-8"))

    def wait_for(self, marker, timeout):
        deadline = time.time() + timeout
        while time.time() < deadline:
            idx = self.buf.find(marker.encode())
            if idx >= 0:
                self.buf = self.buf[idx + len(marker):]
                return True
            if b"failed to deserialize entity data" in self.buf:
                raise GameError("broken_demo")
            try:
                chunk = self.sock.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                chunk = b""
            if not chunk:
                raise GameError("broken_demo" if b"Demo playback finished" in self.buf else "cs2_closed")
            self.buf = (self.buf + chunk)[-200000:]
            self.full.append(chunk)
        return False

    def close(self):
        if self.sock:
            self.sock.close()


def cs2_running():
    return bool(stealth.cs2_pids())


def stage_demo(cfg, dem_path, did):
    """playdemo wants a path inside game/csgo, so the demo is linked into replays/."""
    rel = f"replays/fh_{did}"
    target = os.path.join(cfg["csgo_dir"], "replays", f"fh_{did}.dem")
    if os.path.abspath(dem_path).lower() == os.path.abspath(target).lower():
        return rel
    inside = os.path.relpath(os.path.abspath(dem_path), cfg["csgo_dir"])
    if not inside.startswith("..") and ":" not in inside:
        return inside.replace("\\", "/")[:-4]
    if not os.path.exists(target):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        try:
            os.link(dem_path, target)
        except OSError:
            shutil.copyfile(dem_path, target)
    return rel


def launch(cfg, log):
    if cs2_running():
        raise GameError("cs2_running")
    for key in ("hlae_exe", "hook_dll", "cs2_exe", "ffmpeg"):
        if not os.path.exists(cfg[key]):
            raise GameError("missing_file", cfg[key])
    cmdline = (f"-steam -insecure +sv_lan 1 -console -novid -sw -noborder -w {cfg['width']} -h {cfg['height']} "
               f"-afxDisableSteamStorage -afxFixNetCon -netconport {cfg['netcon_port']} "
               "+fps_max 0 +fps_max_ui 0 +fps_max_tools 0 +mat_vsync 0 +demo_ui_mode 0 "
               f"+volume {REC_VOLUME} +snd_menumusic_volume 0")
    log("Запускаю CS2 через HLAE…")
    p = subprocess.Popen([cfg["hlae_exe"], "-customLoader", "-noGui", "-autoStart", "-noConfig",
                          "-hookDllPath", cfg["hook_dll"], "-programPath", cfg["cs2_exe"], "-cmdLine", cmdline],
                         creationflags=config.NO_WINDOW)
    stealth.LAUNCHER["pid"] = p.pid  # its cs2.exe child is ours; any other CS2 is the user's


def fix_sound(cfg, log):
    """Killcam 2.0.0–2.0.1 left CS2 muted in the Windows mixer. Windows only takes the unmute
    while the game is running, so start it out of sight, switch its sound on, and close it."""
    if stealth.cs2_pids():  # the user is playing right now: switch sound on in their game
        stealth.unmute(stealth.cs2_pids())
        return
    try:
        # low_graphics also backs up the convars file, so the launch volume is not saved
        with stealth.low_graphics(cfg["steam_dir"]), stealth.WindowHider():
            launch(cfg, log)
            deadline = time.time() + 150
            while time.time() < deadline and not stealth.has_audio(stealth.own_pids()):
                time.sleep(1)
            if not stealth.has_audio(stealth.own_pids()):
                raise GameError("cs2_no_console")
            time.sleep(2)
            stealth.unmute(stealth.own_pids())
    finally:
        stealth.kill_own()
        stealth.wait_cs2_exit(20)
        stealth.LAUNCHER["pid"] = None


def setup_streams(con, cfg, raw_dir):
    preset = cfg["ffmpeg_video"] + " {QUOTE}{AFX_STREAM_PATH}\\\\video.mp4{QUOTE}"
    con.send(
        "mirv_streams record screen enabled 1",
        f"mirv_streams record fps {cfg['fps']}",
        "mirv_streams record startMovieWav 1",
        f'mirv_streams settings add ffmpeg fhvideo "{preset}"',
        "mirv_streams settings edit afxDefault settings fhvideo",
        f'mirv_streams record name "{raw_dir}"',
        "mirv_endofmatch enabled 0",
        "cl_draw_only_deathnotices 0",
        "spec_show_xray 0",
        # The in-game volume is in the WAV too, so the game plays almost silently and the clip
        # audio is raised back by AUDIO_GAIN. The Windows mixer is never touched, and the
        # user's own volume returns with cs2_machine_convars.vcfg (stealth.low_graphics).
        f"volume {REC_VOLUME}", "snd_mute_losefocus 0",
        # no demo controls or perf overlays in the footage
        "demo_ui_mode 0",
        "cl_showfps 0", "cl_hud_telemetry_frametime_show 0", "cl_hud_telemetry_ping_show 0",
        "cl_hud_telemetry_net_misdelivery_show 0", "cl_hud_telemetry_serverrecvmargin_graph_show 0",
        "cl_hud_telemetry_net_quality_graph_show 0", "cl_hud_telemetry_net_detailed 0",
    )


def record_segment(con, seg, n, raw_dir, fps):
    """Returns the take folder HLAE wrote for this segment."""
    before = set(glob.glob(os.path.join(raw_dir, "take*")))
    name = seg["pov_name"].replace('"', "")
    spec = f'spec_player "{name}"; spec_mode 2'
    con.send(
        "mirv_cmd clear",
        f'mirv_cmd addAtTick {seg["start"] - PREROLL // 2} "{spec}; demo_timescale 1"',
        # host_framerate locks game time per frame, so the game renders as fast as it can
        f'mirv_cmd addAtTick {seg["start"]} "{spec}; host_framerate {fps}; mirv_streams record start; echo FH_REC_{n}"',
        f'mirv_cmd addAtTick {seg["end"]} "mirv_streams record end; host_framerate 0; demo_pause; echo FH_DONE_{n}"',
        f"demo_gototick {seg['start'] - PREROLL}",
        spec,
        "demo_timescale 4",
        "demo_resume",
    )
    t = time.time()
    con.wait_for(f"FH_REC_{n}", timeout=60)
    seg["seek_s"] = round(time.time() - t, 1)
    t = time.time()
    if not con.wait_for(f"FH_DONE_{n}", timeout=90):
        con.send("mirv_streams record end", "demo_pause")
        raise GameError("segment_failed", str(n))
    seg["rec_s"] = round(time.time() - t, 1)
    new = sorted(set(glob.glob(os.path.join(raw_dir, "take*"))) - before)
    if not new:
        raise GameError("segment_nofile", str(n))
    return new[-1]


def ffmpeg(cfg, *args):
    subprocess.run([cfg["ffmpeg"], "-hide_banner", "-loglevel", "error", "-y", *args],
                   check=True, capture_output=True, creationflags=config.NO_WINDOW)


def finish_clip(cfg, clip, takes, out_dir, tmp_dir):
    parts = []
    for i, seg in enumerate(clip["segments"]):
        take = takes.get((clip["id"], i))
        if not take:
            continue
        part = os.path.join(tmp_dir, f"{clip['id']}_{i}.mp4")
        video = os.path.join(take, "video.mp4")
        wav = os.path.join(take, "audio.wav")
        audio = ["-i", wav] if os.path.exists(wav) else ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        # HLAE may still be flushing the file right after "record end" — retry briefly
        for attempt in range(10):
            try:
                ffmpeg(cfg, "-i", video, *audio, "-c:v", "copy",
                       "-af", f"volume={AUDIO_GAIN},alimiter=limit=0.97",
                       "-c:a", "aac", "-b:a", "160k", "-shortest", part)
                break
            except subprocess.CalledProcessError:
                if attempt == 9:
                    raise
                time.sleep(0.5)
        parts.append(part)
    if not parts:
        return None
    out = os.path.join(out_dir, f"{clip['id']}.mp4")
    lst = os.path.join(tmp_dir, f"{clip['id']}.txt")
    with open(lst, "w", encoding="utf-8") as f:
        f.writelines(f"file '{p}'\n" for p in parts)
    ffmpeg(cfg, "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-movflags", "+faststart", out)
    return os.path.basename(out)


def update_index(entry):
    path = os.path.join(config.LIBRARY, "index.json")
    items = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            items = json.load(f)
    items = [i for i in items if i["key"] != entry["key"]] + [entry]
    items.sort(key=lambda i: i["recorded"], reverse=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)


class Library:
    """meta.json + index.json for one recording, rewritten each time a clip is ready,
    so the site can show clips while the rest are still recording."""

    def __init__(self, key, dem_path, info, me, clips, out_dir, t0, ffmpeg_exe):
        self.lock = threading.Lock()
        self.out_dir = out_dir
        self.t0 = t0
        self.ffmpeg = ffmpeg_exe
        self.meta = {
            "key": key,
            "demo": os.path.basename(dem_path),
            "demo_path": dem_path,
            "map": info["map"],
            "player": me,
            "score": [me.get("won", 0), me.get("lost", 0)],
            "match_time": demo.match_time(dem_path),
            "players": info["players"],
            "rounds": [{"number": r["number"], "winner": r["winner"]} for r in info["rounds"]],
            "clips": clips,
            "status": "recording",
            "recorded": time.strftime("%Y-%m-%d %H:%M"),
            "took_seconds": 0,
            "thumb": None,
        }
        self.save()

    def clip_ready(self, clip, file):
        clips = self.meta["clips"]
        if file and not self.meta["thumb"]:
            self.meta["thumb"] = make_thumb(self.ffmpeg, os.path.join(self.out_dir, file), self.out_dir, self.meta["map"])
        with self.lock:
            clip["file"] = file
            offs, acc = [], 0.0
            for seg in clip["segments"]:
                offs.append(round(acc, 2))
                acc += (seg["end"] - seg["start"]) / TICK
            clip["part_offsets"] = offs
            # kills that happened inside this death clip play from the same file
            for c in clips:
                if c.get("inside_death") and c["round"] == clip["round"] and clip["kind"] == "death" \
                        and clip["segments"][0]["start"] <= c["tick"] <= clip["segments"][0]["end"]:
                    c["file"], c["host"] = file, clip["id"]
                    c["offset"] = round(max(0, c["tick"] - plan.s(plan.KILL_BEFORE)
                                            - clip["segments"][0]["start"]) / TICK, 2)
        self.save()

    def save(self, status=None):
        with self.lock:
            if status:
                self.meta["status"] = status
            self.meta["took_seconds"] = round(time.time() - self.t0)
            with open(os.path.join(self.out_dir, "meta.json"), "w", encoding="utf-8") as f:
                json.dump(self.meta, f, ensure_ascii=False, indent=1)
            m = self.meta
            update_index({k: m.get(k) for k in ("key", "demo", "map", "player", "recorded", "took_seconds",
                                                "status", "score", "match_time", "thumb")}
                         | {"clips": sum(1 for c in m["clips"] if c.get("file"))})


MAPS_DIR = "_maps"  # inside the library: one picture per map, reused for demos not recorded yet


def make_thumb(ffmpeg_exe, clip_path, out_dir, map_name):
    """A frame from the player's own footage as the card picture (and the map's picture)."""
    try:
        thumb = os.path.join(out_dir, "thumb.jpg")
        subprocess.run([ffmpeg_exe, "-hide_banner", "-loglevel", "error", "-y", "-ss", "1.5", "-i", clip_path,
                        "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "4", thumb],
                       capture_output=True, creationflags=config.NO_WINDOW, timeout=30)
        if not os.path.exists(thumb):
            return None
        maps = os.path.join(config.LIBRARY, MAPS_DIR)
        os.makedirs(maps, exist_ok=True)
        map_pic = os.path.join(maps, f"{map_name}.jpg")
        if map_name and not os.path.exists(map_pic):
            shutil.copyfile(thumb, map_pic)
        return "thumb.jpg"
    except (OSError, subprocess.SubprocessError):
        return None


TOASTS = {
    "ru": ("Killcam записывает хайлайты", "CS2 работает в фоне. Не запускай CS2 и не закрывай Steam.",
           "Хайлайты готовы", "{n} клипов — открой Killcam"),
    "en": ("Killcam is recording", "CS2 runs in the background. Don't start CS2 or close Steam.",
           "Highlights ready", "{n} clips — open Killcam"),
}


MAX_PLAYERS = 3


def run(dem_path, steamids, log=print, progress=lambda done, total: None, limit=None,
        phase=lambda name: None):
    """Records one or several players (up to MAX_PLAYERS) of a demo in a single CS2 session.
    Each player gets their own library entry. Returns the first player's meta (with "keys")."""
    if isinstance(steamids, str):
        steamids = [steamids]
    steamids = list(dict.fromkeys(steamids))[:MAX_PLAYERS]
    cfg = config.load()
    t0 = time.time()
    dem_path = demo.unpack_if_gz(dem_path, os.path.join(config.WORK, "demos"))
    did = demo.demo_id(dem_path)

    # CS2 takes ~30 s to start; parse the demo meanwhile
    rel_demo = stage_demo(cfg, dem_path, did)
    if cs2_running():
        raise GameError("cs2_running")
    toast = TOASTS.get(cfg["lang"], TOASTS["en"])
    stealth.toast(toast[0], toast[1])
    phase("launch")
    with stealth.low_graphics(cfg["steam_dir"]), stealth.WindowHider():
        launch(cfg, log)
        metas = _run_in_game(cfg, log, progress, limit, t0, dem_path, did, steamids, rel_demo, phase)
    n = sum(1 for m in metas for c in m["clips"] if c.get("file"))
    stealth.toast(toast[2], toast[3].format(n=n))
    phase("done")
    return dict(metas[0], keys=[m["key"] for m in metas])


def _run_in_game(cfg, log, progress, limit, t0, dem_path, did, steamids, rel_demo, phase):
    try:
        log("Читаю демку…")
        info = demo.analyze(dem_path)
        game_patch = config.cs2_patch(cfg)
        players, segs = [], []
        for idx, sid in enumerate(steamids):
            me = next(p for p in info["players"] if p["steamid"] == sid)
            clips = plan.build(info, sid)
            if limit:  # quick test: only the first few clips
                clips = clips[:limit]
            key = f"{did}_{sid}"
            p = {"me": me, "clips": clips, "key": key, "takes": {},
                 "out_dir": os.path.join(config.LIBRARY, key),
                 "tmp_dir": os.path.join(config.WORK, "tmp", key),
                 "by_id": {c["id"]: c for c in clips}}
            # each clip recorded completely before the next one, so it can be shown right away
            p_segs = [dict(seg, p=idx, clip=c["id"], part=i)
                      for c in clips if not c.get("inside_death") for i, seg in enumerate(c["segments"])]
            segs += p_segs
            players.append(p)
            log(f"{info['map']}, {me['name']}: {me['kills']} убийств, {me['deaths']} смертей → "
                f"{len(clips)} клипов, {len(p_segs)} отрезков, {plan.total_seconds(clips):.0f} с видео")
        log(f"Версия демки {info.get('patch') or '?'}, версия CS2 {game_patch or '?'}")

        raw_dir = os.path.join(config.WORK, "raw", did)
        shutil.rmtree(raw_dir, ignore_errors=True)
        os.makedirs(raw_dir)
        for p in players:
            shutil.rmtree(p["tmp_dir"], ignore_errors=True)
            os.makedirs(p["tmp_dir"])
            shutil.rmtree(p["out_dir"], ignore_errors=True)
            os.makedirs(p["out_dir"])
            p["lib"] = Library(p["key"], dem_path, info, p["me"], p["clips"], p["out_dir"], t0, cfg["ffmpeg"])

        ready = queue.Queue()

        def glue():
            while (item := ready.get()) is not None:
                p, c = item
                try:
                    p["lib"].clip_ready(c, finish_clip(cfg, c, p["takes"], p["out_dir"], p["tmp_dir"]))
                except Exception as e:
                    log(f"Не склеился клип {c['id']}: {e}")

        gluer = threading.Thread(target=glue, daemon=True)
        gluer.start()
        try:
            rec_time = _record_all(cfg, log, progress, rel_demo, raw_dir, segs, players, ready, phase)
        except GameError as e:
            # a demo from another CS2 version can crash the game outright instead of printing an error
            if e.code in ("cs2_closed", "demo_load_failed") and info.get("patch") and game_patch \
                    and info["patch"] != game_patch:
                raise GameError("demo_version", f"демка {info['patch']}, CS2 {game_patch}") from e
            raise
    except Exception:
        stealth.kill_own()
        raise
    total_video = sum(plan.total_seconds(p["clips"]) for p in players)
    log(f"Запись: {rec_time:.0f} с на {total_video:.0f} с видео")
    phase("finishing")
    ready.put(None)
    gluer.join()
    for p in players:
        p["lib"].save("done")
        shutil.rmtree(p["tmp_dir"], ignore_errors=True)
    shutil.rmtree(raw_dir, ignore_errors=True)
    log(f"Готово за {time.time() - t0:.0f} с.")
    return [p["lib"].meta for p in players]


def _record_all(cfg, log, progress, rel_demo, raw_dir, segs, players, ready, phase):
    con = NetCon(cfg["netcon_port"], log)
    try:
        return _record_all_inner(con, cfg, log, progress, rel_demo, raw_dir, segs, players, ready, phase)
    finally:
        # keep the console even when CS2 dies: it is what a bug report needs most
        try:
            os.makedirs(config.WORK, exist_ok=True)
            with open(os.path.join(config.WORK, "netcon.log"), "wb") as f:
                f.write(b"".join(con.full))
        except OSError:
            pass
        con.close()


def _record_all_inner(con, cfg, log, progress, rel_demo, raw_dir, segs, players, ready, phase):
    con.connect(timeout=180)
    log("CS2 запущена, гружу демку…")
    phase("loading")
    con.send("mirv_cmd clear", 'mirv_cmd addAtTick 70 "demo_pause; echo FH_LOADED"', f"playdemo {rel_demo}")
    if not con.wait_for("FH_LOADED", timeout=180):
        raise GameError("demo_load_failed")
    setup_streams(con, cfg, raw_dir)
    phase("recording")
    t_rec = time.time()
    total = len(segs)
    progress(0, total)
    for n, seg in enumerate(segs, 1):
        ts = time.time()
        p = players[seg["p"]]
        try:
            p["takes"][(seg["clip"], seg["part"])] = record_segment(con, seg, n, raw_dir, cfg["fps"])
        except GameError as e:
            log(f"Пропускаю: {e}")
        log(f"  отрезок {n}/{total}: {(seg['end'] - seg['start']) / TICK:.1f} с видео за {time.time() - ts:.1f} с "
            f"(перемотка {seg.get('seek_s', '?')} с, захват {seg.get('rec_s', '?')} с)")
        progress(n, total)
        clip = p["by_id"][seg["clip"]]
        if seg["part"] == len(clip["segments"]) - 1:
            ready.put((p, clip))
    rec_time = time.time() - t_rec
    con.send("quit")
    return rec_time
