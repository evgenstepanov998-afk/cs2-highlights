"""Turning kills/deaths of one player into a list of camera segments to record.

Every clip shown on the site is built from one or more segments:
  kill  -> player's POV, KILL_BEFORE s before .. KILL_AFTER s after (close kills merged)
  death -> player's POV DEATH_BEFORE s before the death,
           then the killer's POV KILLCAM_BEFORE s before .. KILLCAM_AFTER s after
"""
from .demo import TICKRATE

KILL_BEFORE = 3.0
KILL_AFTER = 1.0
MERGE_GAP = 2.0        # kills closer than this become one clip (multikill)
DEATH_BEFORE = 6.0
KILLCAM_BEFORE = 4.0
KILLCAM_AFTER = 0.5


def s(sec):
    return int(sec * TICKRATE)


def build(info, steamid):
    names = {p["steamid"]: p["name"] for p in info["players"]}
    me = names[steamid]
    lives = {r["number"]: r["live"] for r in info["rounds"]}
    rstart = {r["number"]: r["start"] for r in info["rounds"]}

    def clamp(tick, rnd):
        return max(tick, rstart[rnd] + s(1))

    clips = []

    kills = [e for e in info["events"] if e["attacker"] == steamid and e["victim"] != steamid]
    group = []
    for e in kills + [None]:
        if group and (e is None or e["round"] != group[-1]["round"]
                      or e["tick"] - group[-1]["tick"] > s(KILL_BEFORE + KILL_AFTER + MERGE_GAP)):
            rnd = group[0]["round"]
            clips.append({
                "kind": "kill",
                "round": rnd,
                "tick": group[0]["tick"],
                "events": group,
                "segments": [{
                    "pov": steamid, "pov_name": me,
                    "start": clamp(group[0]["tick"] - s(KILL_BEFORE), rnd),
                    "end": group[-1]["tick"] + s(KILL_AFTER),
                }],
            })
            group = []
        if e is not None:
            group.append(e)

    for e in info["events"]:
        if e["victim"] != steamid:
            continue
        rnd = e["round"]
        segs = [{
            "pov": steamid, "pov_name": me,
            "start": clamp(e["tick"] - s(DEATH_BEFORE), rnd),
            "end": e["tick"] + s(0.3),
        }]
        killer = e["attacker"]
        if killer and killer != steamid and killer in names:
            segs.append({
                "pov": killer, "pov_name": names[killer],
                "start": clamp(e["tick"] - s(KILLCAM_BEFORE), rnd),
                "end": e["tick"] + s(KILLCAM_AFTER),
            })
        clips.append({"kind": "death", "round": rnd, "tick": e["tick"], "events": [e], "segments": segs})

    # A kill shortly before dying is already inside the death clip's 10 s.
    deaths_by_round = {}
    for c in clips:
        if c["kind"] == "death":
            deaths_by_round.setdefault(c["round"], []).append(c)
    for c in clips:
        if c["kind"] != "kill":
            continue
        for d in deaths_by_round.get(c["round"], []):
            seg = d["segments"][0]
            if seg["start"] <= c["tick"] <= seg["end"]:
                c["inside_death"] = True

    clips.sort(key=lambda c: (c["tick"], c["kind"]))
    for i, c in enumerate(clips):
        c["id"] = f"c{i:03d}"
        c["live"] = lives[c["round"]]
    return clips


def recording_passes(clips):
    """Segments grouped so the demo only ever seeks forward inside a pass."""
    segs = []
    for c in clips:
        if c.get("inside_death"):
            continue
        for i, seg in enumerate(c["segments"]):
            segs.append(dict(seg, clip=c["id"], part=i))
    passes = []
    for seg in sorted(segs, key=lambda x: x["start"]):
        for p in passes:
            if p[-1]["end"] + s(0.5) <= seg["start"]:
                p.append(seg)
                break
        else:
            passes.append([seg])
    return passes


def total_seconds(clips):
    return sum((seg["end"] - seg["start"]) / TICKRATE
               for c in clips if not c.get("inside_death") for seg in c["segments"])
