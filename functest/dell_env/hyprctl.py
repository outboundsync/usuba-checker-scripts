#!/usr/bin/env python3
"""hyprctl emulator replaying Hyprland 0.56.2 reply shapes (fixtures/hyprland-0.56.2). Used inside the functest sandbox."""
import json, os, sys, re
FX = os.environ.get("FT_HYPR_FX") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "../fixtures/hyprland-0.56.2")
# default option overrides for the emulator (reference values: gaps, border, rounding, layout)
OVR = {"general:gaps_out": "16 16 16 16", "general:gaps_in": "8 8 8 8", "general:border_size": "4", "decoration:rounding": "24",
       "general:layout": "dwindle", "input:kb_layout": "us", "input:kb_options": "compose:caps"}
KEY = {"Int": "int", "Color": "int", "Bool": "bool", "Float": "float", "String": "str", "CssGap": "css", "Gradient": "gradient",
       "Vec2": "vec2", "FontWeight": "font_weight"}
TXT = {"Int": "int", "Color": "int", "Bool": "bool", "Float": "float", "String": "str", "CssGap": "css gap data",
       "Gradient": "gradient data", "Vec2": "vec2", "FontWeight": "font weight data"}
def opt_value(name, t, d):
    v = OVR.get(name, d)
    v = str(v).strip().strip('"')
    if t in ("Int", "Color"):
        m = re.search(r"0x[0-9a-fA-F]+|-?\d+", v); n = int(m.group(0), 0) if m else 0
        if n >= 2**31: n -= 2**32
        return n
    if t == "Bool": return v.lower() in ("true", "1", "yes", "on")
    if t == "Float":
        try: return float(re.sub(r"[fF]$", "", v))
        except Exception: return 0.0
    if t == "Vec2":
        n = re.findall(r"-?\d+(?:\.\d+)?", v) or ["0", "0"]; return [float(n[0]), float(n[-1])]
    if t == "CssGap":
        n = re.findall(r"-?\d+", v) or ["0"]
        n = (n * 4)[:4] if len(n) == 1 else (n + n)[:4]
        return " ".join(n)
    if t == "Gradient":
        m = re.search(r"0x([0-9a-fA-F]+)", v); return (m.group(1) if m else "ffffffff") + " 0deg"
    return v
def respond(argv):
    """argv like hyprctl's (flags + command + args) -> reply text."""
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf): main(argv)
    return buf.getvalue()

def serve(d):
    """Minimal Hyprland IPC: .socket.sock answers requests like 'j/workspaces' with the same replies as hyprctl;
    .socket2.sock accepts event listeners (no events are sent: the box has no real compositor events)."""
    import socket, threading
    os.makedirs(d, exist_ok=True)
    log = os.environ.get("FT_HYPRLOG")
    def req_loop(srv):
        while True:
            c, _ = srv.accept()
            try:
                data = c.recv(65536).decode(errors="replace")
                if log: open(log, "a").write(data.replace("\n", " ") + "\n")
                m = re.match(r"^([a-z]*)/(.*)$", data, re.S)
                flags, body = (m.group(1), m.group(2)) if m else ("", data)
                argv = (["-j"] if "j" in flags else []) + body.split()
                if body.startswith("[[BATCH]]"): out = "ok\n"
                elif body.split()[:1] == ["status"]: out = json.dumps({"configProvider": "lua", "backend": "drm"})
                else: out = respond(argv)
                c.sendall(out.rstrip("\n").encode())
            except Exception: pass
            finally: c.close()
    ev_clients = []
    def ev_loop(srv):
        while True:
            c, _ = srv.accept(); ev_clients.append(c)
    for name, fn in ((".socket.sock", req_loop), (".socket2.sock", ev_loop)):
        p = os.path.join(d, name)
        if os.path.exists(p): os.remove(p)
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); srv.bind(p); srv.listen(64)
        threading.Thread(target=fn, args=(srv,), daemon=True).start()
    threading.Event().wait()

def main(argv):
    fmt_json = False; args = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-j", "--json"): fmt_json = True
        elif a in ("-r", "--refresh", "-q", "--quiet"): pass
        elif a in ("-i", "--instance"): i += 1
        elif a.startswith("--batch") or a == "--batch": args.append("[[BATCH]]")
        else: args.append(a)
        i += 1
    if not args: print("usage: hyprctl [flags] <command> [args]"); return 1
    cmd, rest = args[0], args[1:]
    F = json.load(open(os.path.join(FX, "fixtures.json")))
    mon = os.environ.get("FT_HYPR_MONNAME")   # the box compositor's output name (HEADLESS-1) so Quickshell can map the Dell's eDP-1 data
    if mon:
        for m in F.get("monitors", []): m["name"] = mon
        for w in F.get("workspaces", []) + [F.get("activeworkspace") or {}]:
            if "monitor" in w: w["monitor"] = mon
    if cmd == "getoption":
        if not rest: print("no such option"); return 0
        name = rest[0]; o = json.load(open(os.path.join(FX, "options_raw.json"))).get(name)
        if not o: print("no such option"); return 0
        t, d = o; v = opt_value(name, t, d); s = "true" if name in OVR else "false"
        if fmt_json:
            k = KEY.get(t, "custom")
            print(json.dumps({"option": name, k: v, "set": name in OVR}))
        else:
            vv = ("true" if v else "false") if t == "Bool" else (f"[{v[0]}, {v[1]}]" if t == "Vec2" else v)
            print(f"{TXT.get(t, 'custom type')}: {vv}\nset: {s}")
        return 0
    if cmd in ("keyword", "dispatch", "reload", "notify", "dismissnotify", "setcursor", "switchxkblayout", "seterror", "kill", "[[BATCH]]", "output", "plugin", "eval", "reloadshaders"):
        if cmd in ("keyword", "dispatch") and len(rest) < 1: print("Invalid"); return 0
        print("ok"); return 0
    if cmd in F:
        v = F[cmd]
        if fmt_json: print(json.dumps(v, indent=4))
        else:
            if cmd == "submap": print(v)
            elif cmd == "monitors":
                for m in v: print(f"Monitor {m['name']} (ID {m['id']}):\n\t{m['width']}x{m['height']}@{m['refreshRate']:.5f} at {m['x']}x{m['y']}\n\tactive workspace: {m['activeWorkspace']['id']} ({m['activeWorkspace']['name']})\n\tscale: {m['scale']:.2f}\n\tfocused: yes\n")
            elif cmd in ("workspaces", "activeworkspace"):
                for w in (v if isinstance(v, list) else [v]): print(f"workspace ID {w['id']} ({w['name']}) on monitor {w['monitor']}:\n\tmonitorID: {w['monitorID']}\n\twindows: {w['windows']}\n\thasfullscreen: 0\n\tlastwindow: {w['lastwindow']}\n\tlastwindowtitle: {w['lastwindowtitle']}\n\tispersistent: 1\n\ttiledLayout: dwindle\n")
            elif cmd == "version": print(f"Hyprland {v['version']} built from branch  at commit {v['commit']}  ({v['commit_message']}).\nTag: {v['tag']}")
            elif cmd == "cursorpos": print(f"{v['x']}, {v['y']}")
            else: print(json.dumps(v))
        return 0
    print("unknown request"); return 0
if __name__ == "__main__":
    if sys.argv[1:2] == ["--serve"]: serve(sys.argv[2])
    sys.exit(main(sys.argv[1:]))
