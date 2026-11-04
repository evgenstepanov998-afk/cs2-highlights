"""Reading a CS2 demo: players, rounds and every kill/death."""
import gzip
import hashlib
import os
import re
import shutil
from bisect import bisect_left

from demoparser2 import DemoParser

TICKRATE = 64


def unpack_if_gz(path, work_dir):
    """FACEIT gives .dem.gz / .dem.zst (or a folder named *.dem after unpacking);
    CS2 and the parser want a plain .dem."""
    if os.path.isdir(path):
        inner = [f for f in os.listdir(path) if f.lower().endswith((".dem", ".dem.gz", ".dem.zst"))]
        if not inner:
            raise FileNotFoundError(f"В папке нет демки: {path}")
        path = os.path.join(path, inner[0])
    low = path.lower()
    if not low.endswith((".gz", ".zst")):
        return path
    os.makedirs(work_dir, exist_ok=True)
    out = os.path.join(work_dir, os.path.basename(path).rsplit(".", 1)[0])
    if not os.path.exists(out):
        tmp = out + ".part"
        with open(tmp, "wb") as dst:
            if low.endswith(".gz"):
                with gzip.open(path, "rb") as src:
                    shutil.copyfileobj(src, dst, 16 * 1024 * 1024)
            else:
                import zstandard
                with open(path, "rb") as src:
                    zstandard.ZstdDecompressor().copy_stream(src, dst)
        os.replace(tmp, out)
    return out


MAP_RE = re.compile(rb"\b((?:de|cs|ar|dz|gd)_[a-z0-9_]{2,30})\b")


def peek_map(path):
    """Map name from the demo header without parsing the whole file
    (works on .gz / .zst too: only the first 64 KB get decompressed)."""
    low = path.lower()
    try:
        if low.endswith(".gz"):
            with gzip.open(path, "rb") as f:
                head = f.read(65536)
        elif low.endswith(".zst"):
            import zstandard
            with open(path, "rb") as raw, zstandard.ZstdDecompressor().stream_reader(raw) as f:
                head = f.read(65536)
        else:
            with open(path, "rb") as f:
                head = f.read(65536)
    except Exception:
        return None
    for m in MAP_RE.finditer(head):
        # header strings are protobuf fields: the byte before the text is its length
        n = head[m.start() - 1] if m.start() else 0
        if 3 <= n <= len(m.group(1)):
            return m.group(1)[:n].decode()
    return None


def demo_id(path):
    """Stable id from file size + first MB, so re-adding the same demo reuses it."""
    h = hashlib.sha1(str(os.path.getsize(path)).encode())
    with open(path, "rb") as f:
        h.update(f.read(1024 * 1024))
    return h.hexdigest()[:12]


def _int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def analyze(path):
    p = DemoParser(path)
    header = p.parse_header()

    match_start = 0
    try:
        bnm = p.parse_event("begin_new_match")
        if len(bnm):
            match_start = int(bnm["tick"].max())
    except Exception:
        pass

    ends = p.parse_event("round_end")
    ends = ends[ends["tick"] > match_start].sort_values("tick")
    try:
        freezes = sorted(int(t) for t in p.parse_event("round_freeze_end")["tick"])
    except Exception:
        freezes = []

    deaths = p.parse_event("player_death").sort_values("tick")
    deaths = deaths[deaths["tick"] > match_start]
    last_tick = int(deaths["tick"].max()) if len(deaths) else match_start

    rounds = []
    prev = match_start
    for _, r in ends.iterrows():
        tick = int(r["tick"])
        rounds.append({"start": prev, "end": tick, "winner": r.get("winner") if isinstance(r.get("winner"), str) else None})
        prev = tick
    if last_tick > prev:
        rounds.append({"start": prev, "end": last_tick + 5 * TICKRATE, "winner": None})
    for i, r in enumerate(rounds):
        r["number"] = i + 1
        fz = [t for t in freezes if r["start"] <= t < r["end"]]
        r["live"] = fz[0] if fz else r["start"]
    round_ends = [r["end"] for r in rounds]

    def round_of(tick):
        i = bisect_left(round_ends, tick)
        return rounds[min(i, len(rounds) - 1)]["number"]

    events = []
    for _, d in deaths.iterrows():
        tick = int(d["tick"])
        events.append({
            "tick": tick,
            "round": round_of(tick),
            "attacker": str(d["attacker_steamid"]) if d["attacker_steamid"] else None,
            "attacker_name": d["attacker_name"],
            "victim": str(d["user_steamid"]),
            "victim_name": d["user_name"],
            "weapon": d["weapon"],
            "headshot": bool(d["headshot"]),
            "wallbang": _int(d.get("penetrated")) > 0,
            "noscope": bool(d.get("noscope")),
            "thrusmoke": bool(d.get("thrusmoke")),
        })

    snap = p.parse_ticks(["team_num", "name"], ticks=[last_tick])
    players = []
    for _, row in snap.iterrows():
        sid = str(row["steamid"])
        players.append({
            "steamid": sid,
            "name": row["name"],
            "team": _int(row["team_num"]),
            "kills": sum(1 for e in events if e["attacker"] == sid and e["victim"] != sid),
            "deaths": sum(1 for e in events if e["victim"] == sid),
        })
    players.sort(key=lambda x: (x["team"], -x["kills"]))

    return {
        "map": header.get("map_name"),
        "server": header.get("server_name"),
        "rounds": rounds,
        "events": events,
        "players": players,
    }
