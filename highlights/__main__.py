import argparse

from . import app, demo, recorder

ap = argparse.ArgumentParser(prog="killcam")
sub = ap.add_subparsers(dest="cmd")
r = sub.add_parser("record", help="записать хайлайты без окна")
r.add_argument("demo")
r.add_argument("player", help="ник или steamid")
r.add_argument("--limit", type=int, help="записать только первые N клипов (для проверки)")
args = ap.parse_args()

if args.cmd == "record":
    info = demo.analyze(demo.unpack_if_gz(args.demo, "work/demos"))
    sid = next(p["steamid"] for p in info["players"] if args.player in (p["name"], p["steamid"]))
    recorder.run(args.demo, sid, limit=args.limit)
else:
    app.main()
