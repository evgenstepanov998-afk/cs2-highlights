import argparse

from . import demo, recorder, server

ap = argparse.ArgumentParser(prog="highlights")
sub = ap.add_subparsers(dest="cmd")
sub.add_parser("serve", help="открыть сайт (по умолчанию)")
r = sub.add_parser("record", help="записать хайлайты без сайта")
r.add_argument("demo")
r.add_argument("player", help="ник или steamid")
r.add_argument("--limit", type=int, help="записать только первые N клипов (для проверки)")
args = ap.parse_args()

if args.cmd == "record":
    info = demo.analyze(demo.unpack_if_gz(args.demo, "work/demos"))
    sid = next(p["steamid"] for p in info["players"] if args.player in (p["name"], p["steamid"]))
    recorder.run(args.demo, sid, limit=args.limit)
else:
    server.serve()
