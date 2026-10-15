#!/bin/bash
# Usuba Dell hit-check runner. USER SPACE ONLY: no sudo, no system changes, writes only under ~/usuba-hitcheck.
# Each plugin gets its own fake HOME, its own copy of the shell tree and its own quickshell instance on the live Wayland session (no keyboard/mouse input,
# no screenshots), inside a bubblewrap sandbox when available (/ is NOT bound: only /usr and a minimal /etc, read-only; /home /root /run /var are tmpfs, so the
# real $HOME, D-Bus, systemd and agent sockets are absent; minimal /dev; env cleared; new session; /tmp private; network off).
# usage:  run_hitcheck.sh --preflight
#         run_hitcheck.sh [A|B|all]            env: P=3 (parallel) TIMEOUT=70 (s per plugin) NET=0|1  SESSION_ACCESS=0|1  ALLOW_NO_SANDBOX=0|1  SHELL_SRC=/usr/share/omarchy/shell  ONLY=job1,job2  LIMIT=n
# results: ~/usuba-hitcheck/results/hitcheck-results.jsonl  (one line per plugin; resumable: finished jobs are skipped; `touch ~/usuba-hitcheck/STOP` ends the run after the running jobs)
set -euo pipefail
BASE="${BASE:-$HOME/usuba-hitcheck}"; PKG="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
SHELL_SRC=${SHELL_SRC:-/usr/share/omarchy/shell}; P=${P:-3}; TIMEOUT=${TIMEOUT:-70}; RUNSEC=${RUNSEC:-24}; NET=${NET:-0}; SESSION_ACCESS=${SESSION_ACCESS:-0}; ALLOW_NO_SANDBOX=${ALLOW_NO_SANDBOX:-0}
OBSERVE=${OBSERVE:-0}; QS=${QS:-$(command -v quickshell)}; RES="$BASE/results"; JSONL="$RES/hitcheck-results.jsonl"
export BASE PKG OBSERVE SHELL_SRC P TIMEOUT RUNSEC NET SESSION_ACCESS ALLOW_NO_SANDBOX QS RES JSONL

# Job names / plugin ids end up in `rm -rf` paths: letters, digits, . _ - only, and never "." / ".." / leading "-".
valid_name() { [[ "${1:-}" =~ ^[A-Za-z0-9._-]+$ ]] && [[ "$1" != "." && "$1" != ".." && "$1" != -* ]]; }

# Fills the global array BW with the bubblewrap arguments. Usage: build_bwrap_args JOBDIR REALHOME XDG_RUNTIME_DIR   (env: NET SESSION_ACCESS WAYLAND_DISPLAY)
# Never binds /; minimal /etc; tmpfs over /home /root /run /var; --dev (null, zero, random, tty... only) plus /dev/dri if present for Mesa.
build_bwrap_args() {
  local J=$1 RH=$2 XRD=$3 d e W=${WAYLAND_DISPLAY:-wayland-1}
  BW=(--unshare-ipc --unshare-uts --new-session --die-with-parent --clearenv --ro-bind /usr /usr)
  for d in bin sbin lib lib64; do
    if [ -L "/$d" ]; then BW+=(--symlink "$(readlink "/$d")" "/$d"); elif [ -d "/$d" ]; then BW+=(--ro-bind "/$d" "/$d"); fi
  done
  BW+=(--dir /etc)
  for e in ld.so.cache ld.so.conf ld.so.conf.d fonts localtime os-release passwd group nsswitch.conf alternatives xdg vulkan drirc ssl; do
    [ -e "/etc/$e" ] && BW+=(--ro-bind "/etc/$e" "/etc/$e")
  done
  BW+=(--proc /proc --dev /dev --dev-bind-try /dev/dri /dev/dri --ro-bind-try /sys /sys
       --tmpfs /tmp --tmpfs /home --tmpfs /root --tmpfs /run --tmpfs /var --tmpfs "$RH"
       --bind "$J" "$J" --bind "$J/tmp" /tmp)
  [ "${NET:-0}" = 1 ] || BW+=(--unshare-net)
  if [ "${SESSION_ACCESS:-0}" != 1 ]; then
    # private runtime dir: only the Wayland socket is passed in (no dbus, pipewire, pulse, hyprland, systemd, ssh/gpg agent sockets). Own pid namespace.
    BW+=(--unshare-pid --perms 0700 --tmpfs "$XRD")
    [ -S "$XRD/$W" ] && BW+=(--bind "$XRD/$W" "$XRD/$W")
  else BW+=(--bind "$XRD" "$XRD"); fi   # SESSION_ACCESS=1: shared runtime dir (hyprctl read-only shim still applies); no pid namespace, because quickshell derives its instance id from pid+time
  # allow-listed environment only (NOT DBUS_SESSION_BUS_ADDRESS, tokens, SSH_AUTH_SOCK, ...): job variables first, then a few display/locale ones
  local v
  for v in "${ENVV[@]:-}"; do [ -n "$v" ] && BW+=(--setenv "${v%%=*}" "${v#*=}"); done
  for v in LANG LC_ALL TERM WAYLAND_DISPLAY XDG_SESSION_TYPE XDG_CURRENT_DESKTOP QT_QPA_PLATFORM QT_QPA_PLATFORMTHEME XDG_RUNTIME_DIR; do
    [ -n "${!v:-}" ] && BW+=(--setenv "$v" "${!v}")
  done
  return 0
}

sandbox_ok() {
  command -v bwrap >/dev/null 2>&1 || return 1
  local t; t=$(mktemp -d) || return 1; mkdir -p "$t/tmp"
  local ENVV=() rc=0
  build_bwrap_args "$t" "$HOME" "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
  bwrap "${BW[@]}" true >/dev/null 2>&1 || rc=$?
  rm -rf "$t"; return $rc
}

# ------------------------------------------------------------------ preflight
preflight() {
  local bad=0; ok() { echo "ok    $*"; }; no() { echo "FAIL  $*"; bad=1; }; warn() { echo "warn  $*"; }
  [ "$(id -u)" != 0 ] && ok "not root" || no "do not run as root"
  [ -n "$QS" ] && ok "quickshell: $QS ($($QS --version 2>&1 | head -1))" || no "quickshell not found"
  case "$QS $SHELL_SRC" in *"$HOME"*) warn "quickshell or the shell tree lives under \$HOME, which the sandbox hides: use ALLOW_NO_SANDBOX=1 or move them";; esac
  [ -d "$SHELL_SRC" ] && ok "shell tree $SHELL_SRC" || no "shell tree $SHELL_SRC missing"
  command -v python3 >/dev/null && ok "python3" || no "python3"
  [ -n "${WAYLAND_DISPLAY:-}" ] && [ -S "${XDG_RUNTIME_DIR:-/nonexistent}/$WAYLAND_DISPLAY" ] && ok "wayland session: $WAYLAND_DISPLAY" || no "no live Wayland session in this shell (run from a terminal inside the desktop, not over ssh)"
  if sandbox_ok; then ok "bwrap sandbox works (no host /, real HOME/run/var hidden, env cleared, network off, /tmp private)"
  else warn "bwrap sandbox NOT available. Without it plugins can write outside ~/usuba-hitcheck (e.g. /tmp). Install is a system change, so it is not done here. To run anyway: ALLOW_NO_SANDBOX=1"; fi
  command -v systemd-run >/dev/null && systemd-run --user --scope -q true 2>/dev/null && ok "systemd user scope (10 GB memory cap)" || warn "no systemd user scope: memory cap skipped (jobs are still limited to $TIMEOUT s each)"
  local avail; avail=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo); [ "$avail" -gt 4000 ] && ok "MemAvailable ${avail} MB" || warn "MemAvailable only ${avail} MB; use P=2"
  local fb; fb=$(df -Pm "$HOME" | awk 'NR==2{print $4}'); [ "$fb" -gt 2000 ] && ok "free disk ${fb} MB" || warn "free disk ${fb} MB"
  [ -f "$PKG/jobs.tsv" ] && [ -f "$PKG/plugins-A.tar.gz" ] && [ -f "$PKG/plugins-B.tar.gz" ] && ok "package files present ($(wc -l < "$PKG/jobs.tsv") jobs)" || no "package files missing in $PKG"
  [ -f "$HOME/.config/omarchy/shell.json" ] && ok "shell.json found (read only, copied into each fake HOME)" || warn "no ~/.config/omarchy/shell.json (a default is generated)"
  return $bad
}

# ------------------------------------------------------------------ host-side surface observer (OBSERVE=1; runs OUTSIDE the sandbox, writes only to $BASE/obs/<job>, never into the plugin-writable dir)
# Takes hyprctl layer/window snapshots of the surfaces owned by this job's quickshell pid (compositor-reported pid) at: loaded (after listPlugins), open (2 s after the 1st toggle),
# closed (2 s after the 2nd toggle), and a grim crop of each surface rectangle (the plugin's own surfaces only, never the whole screen). Skipped when the display is asleep.
observe_job() {
  local J=$1 D=$2 OBS=$3 BWPID=${4:-} QPID="" i n
  set +e   # an observer failure must never affect the job
  mkdir -p "$OBS"
  for i in $(seq 1 60); do QPID=$(pgrep -f "quickshell -n -p $J/shell" | head -1 || true); [ -n "$QPID" ] && break; sleep 0.5; done
  [ -n "$QPID" ] || { echo "no quickshell pid" > "$OBS/error.txt"; return 0; }
  echo "$QPID" > "$OBS/qpid.txt"
  nexit() { local f="$D/$1"; if [ -f "$f" ] && [ ! -L "$f" ]; then timeout 2 grep -c '^exit=' "$f" 2>/dev/null || true; else echo 0; fi; }
  snap() {
    local tag=$1 f="$OBS/surfaces_$1.txt" k=0 ns g dp
    { timeout 5 hyprctl layers -j 2>/dev/null | python3 -c '
import json,sys
try: d=json.load(sys.stdin)
except Exception: sys.exit(0)
p=int(sys.argv[1])
for mon,v in d.items():
  for lv,L in v.get("levels",{}).items():
    for x in L:
      if x.get("pid")==p: print("layer\t"+x["namespace"].replace("/","_").replace(" ","_")+"\t%d,%d %dx%d\t%s"%(x["x"],x["y"],x["w"],x["h"],mon))
' "$QPID"
      timeout 5 hyprctl clients -j 2>/dev/null | python3 -c '
import json,sys
try: d=json.load(sys.stdin)
except Exception: sys.exit(0)
p=int(sys.argv[1])
for x in d:
  if x.get("pid")==p: print("window\t"+str(x.get("class","")).replace(" ","_")+"\t%d,%d %dx%d\t%s"%(x["at"][0],x["at"][1],x["size"][0],x["size"][1],x.get("monitor")))
' "$QPID"; } > "$f" 2>/dev/null || true
    dp=$(timeout 5 hyprctl monitors -j 2>/dev/null | python3 -c 'import json,sys
try: print(all(m.get("dpmsStatus",True) for m in json.load(sys.stdin)))
except Exception: print(False)')
    [ "$dp" = True ] || return 0
    while IFS=$'\t' read -r _ ns g _; do
      [ -z "$g" ] && continue; k=$((k+1)); [ $k -gt 3 ] && break
      case "$g" in *" 0x"*|*" 1x"*|*" 2x"*|*" 3x"*|*" 4x"*) continue;; esac
      timeout 5 grim -g "$g" "$OBS/shot_${tag}_${k}_${ns}.png" 2>/dev/null || true
    done < "$f"
  }
  alive() { [ -z "$BWPID" ] || kill -0 "$BWPID" 2>/dev/null; }
  for i in $(seq 1 80); do [ "$(nexit ipc_list.txt)" -ge 1 ] && break; alive || return 0; sleep 0.5; done; sleep 0.5; alive || return 0; snap loaded
  for i in $(seq 1 60); do [ "$(nexit toggle.txt)" -ge 1 ] && break; alive || return 0; sleep 0.5; done; sleep 2; alive || return 0; snap open
  for i in $(seq 1 80); do [ "$(nexit toggle.txt)" -ge 2 ] && break; alive || return 0; sleep 0.5; done; sleep 2; alive || return 0; snap closed
  return 0
}

# ------------------------------------------------------------------ one job, orchestrator side (prepares the fake HOME, runs the driver in the sandbox, extracts signals)
job_main() {
  local JOB=${1:-} DIR="" ID="" KINDS=""
  valid_name "$JOB" || { echo "refusing job name '$JOB' (allowed: ^[A-Za-z0-9._-]+\$)" >&2; return 2; }
  IFS=$'\t' read -r _ DIR ID KINDS < <(awk -F'\t' -v j="$JOB" '$1==j' "$PKG/jobs.tsv") || true
  [ -z "$ID" ] && { echo "unknown job $JOB" >&2; return 2; }
  valid_name "$ID" || { echo "refusing plugin id '$ID'" >&2; return 2; }
  case "$DIR" in ""|/*|*..*) echo "refusing plugin dir '$DIR'" >&2; return 2;; esac
  [ -e "$BASE/STOP" ] && { echo "stop requested, skipping $JOB"; return 0; }
  while [ "$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)" -lt 1500 ]; do sleep 5; done      # never push the desktop into memory pressure
  [ -n "$BASE" ] && [ "$BASE" != / ] || { echo "bad BASE" >&2; return 2; }
  local J="$BASE/work/$JOB" H="$BASE/work/$JOB/home" D="$BASE/work/$JOB/out"
  rm -rf -- "$J"; mkdir -p "$H/.config/omarchy/plugins" "$H/.cache" "$H/.local/state" "$H/.local/share" "$J/tmp" "$J/shims" "$D"
  cp -r "$SHELL_SRC" "$J/shell" && cp -r "$BASE/src/$DIR" "$H/.config/omarchy/plugins/$ID" || { echo "copy failed $JOB" >&2; return 2; }
  for x in current shell.toml bar extensions; do [ -e "$HOME/.config/omarchy/$x" ] && cp -rL "$HOME/.config/omarchy/$x" "$H/.config/omarchy/$x" 2>/dev/null || true; done
  python3 - "$H/.config/omarchy/shell.json" "$ID" "$KINDS" "$HOME/.config/omarchy/shell.json" <<'PY'
import json,sys,os
p,i,k,src=sys.argv[1:]; k=k.split(",")
try: c=json.load(open(src))
except Exception: c={"version":1,"bar":{"layout":{"left":[{"id":"omarchy.menu"},{"id":"omarchy.workspaces"}],"center":[{"id":"omarchy.clock"}],"right":[]}},"plugins":[]}
c["idle"]={"screensaver":999999,"lock":999999}
c["disabledPlugins"]=sorted(set(c.get("disabledPlugins",[]))|{"omarchy.idle","omarchy.lock","omarchy.polkit","omarchy.notifications","omarchy.background","omarchy.agents","omarchy.clipboard","omarchy.reminders","omarchy.nightlight"})
c["plugins"]=[x for x in c.get("plugins",[]) if isinstance(x,dict) and x.get("id","").startswith("omarchy.")]
b=c.setdefault("bar",{}); L=b.setdefault("layout",{}).setdefault("left",[])
if "bar" in k: b["id"]=i
elif "bar-widget" in k: L.append({"id":i})
if not ("bar" in k or "bar-widget" in k): c.setdefault("plugins",[]).append({"id":i})
json.dump(c,open(p,"w"),indent=1)
PY
  # PATH shims: log the call; refuse anything that installs, downloads, escalates or touches the live session
  local t
  for t in curl wget sudo pkexec doas su pip pip3 pipx npm npx pnpm yarn bun uv uvx cargo go yay paru pacman flatpak nc ncat ssh scp rsync xdg-open hyprctl git systemctl loginctl busctl gsettings dconf wl-copy notify-send; do
    cat > "$J/shims/$t" <<'SHIM'
#!/bin/bash
n=${0##*/}
rec="$EPOCHSECONDS"$'\t'"$n"; for a in "$@"; do a=${a//$'\t'/ }; rec+=$'\t'"${a//$'\n'/\\n}"; done; printf '%s\n' "$rec" >> "$HC_SHIMLOG" 2>/dev/null
IFS=: read -ra _d <<< "$HC_REALPATH"
real() { local d; for d in "${_d[@]}"; do [ -x "$d/$n" ] && { echo "$d/$n"; return; }; done; }
case "$n" in
  curl) exit 6;; wget) exit 4;; nc|ncat|ssh|scp|rsync) exit 1;;
  git) case "${1:-}" in clone|fetch|pull|push|submodule|ls-remote|remote) exit 128;; *) r=$(real); [ -n "$r" ] && exec "$r" "$@"; exit 127;; esac;;
  hyprctl) case "${1:-}" in monitors|clients|workspaces|activewindow|activeworkspace|version|devices|layers|binds|-j) if [ "${HC_SESSION_ACCESS:-0}" = 1 ]; then r=$(real); [ -n "$r" ] && exec "$r" "$@"; fi; exit 1;; *) exit 0;; esac;;
  systemctl|loginctl|busctl|gsettings|dconf) exit 1;;
  *) exit 1;;
esac
SHIM
    chmod +x "$J/shims/$t"
  done
  cp "$PKG/run_hitcheck.sh" "$J/driver.sh"
  local ENVV=(HOME="$H" XDG_CONFIG_HOME="$H/.config" XDG_CACHE_HOME="$H/.cache" XDG_STATE_HOME="$H/.local/state" XDG_DATA_HOME="$H/.local/share" TMPDIR="$J/tmp"
              HC_JOB="$JOB" HC_ID="$ID" HC_J="$J" HC_H="$H" HC_D="$D" HC_SHIMLOG="$D/shim.log" HC_REALPATH="$PATH" HC_SESSION_ACCESS="$SESSION_ACCESS" HC_RUNSEC="$RUNSEC" HC_QS="$QS" HC_NOTOGGLE="${NO_TOGGLE:-}")
  local RC=0 T0 MODE=sandbox; T0=$(date +%s); sandbox_ok || MODE=nosandbox
  ENVV+=(HC_MODE="$MODE")
  if [ "$MODE" = sandbox ]; then
    local XRD=${XDG_RUNTIME_DIR:-/run/user/$(id -u)} RH="$HOME"
    [ "$SESSION_ACCESS" = 1 ] || ENVV+=(HC_PIDNS=1)
    build_bwrap_args "$J" "$RH" "$XRD"
    # stdin from /dev/null; env is rebuilt inside bwrap (--clearenv), so nothing from the user's shell leaks in
    local BWPID OBPID=""
    timeout -k 5 "$TIMEOUT" env -i PATH="$PATH" bwrap "${BW[@]}" /bin/bash "$J/driver.sh" --driver >"$D/driver_stdout.txt" 2>&1 </dev/null &
    BWPID=$!
    if [ "${OBSERVE:-0}" = 1 ]; then observe_job "$J" "$D" "$BASE/obs/$JOB" "$BWPID" & OBPID=$!; fi
    wait "$BWPID" || RC=$?
    [ -n "$OBPID" ] && { wait "$OBPID" || true; }
    echo sandbox > "$D/mode.txt"
  elif [ "$ALLOW_NO_SANDBOX" = 1 ]; then
    echo "WARNING: running $JOB WITHOUT a sandbox (ALLOW_NO_SANDBOX=1): the plugin has your user's full access" >&2
    timeout -k 5 "$TIMEOUT" env "${ENVV[@]}" /bin/bash "$J/driver.sh" --driver >"$D/driver_stdout.txt" 2>&1 </dev/null || RC=$?
    echo nosandbox > "$D/mode.txt"
    pkill -9 -f "$H" 2>/dev/null || true
  else echo "no bwrap sandbox; set ALLOW_NO_SANDBOX=1 to run without" >&2; rm -rf -- "$J"; return 3; fi
  echo "$RC $(( $(date +%s) - T0 ))" > "$D/rc.txt"
  rm -rf "$RES/raw/$JOB"; mkdir -p "$RES/raw"; mv "$D" "$RES/raw/$JOB"
  if [ -d "$BASE/obs/$JOB" ]; then rm -rf -- "$RES/raw/$JOB/obs"; mv "$BASE/obs/$JOB" "$RES/raw/$JOB/obs"; fi   # rm first: the plugin could have left "obs" as a symlink, and mv would then write through it
  python3 "$PKG/hc_signal.py" "$RES/raw/$JOB" "$PKG/jobs.json" "$JOB" "$ID" | flock "$RES/.lock" tee -a "$JSONL" >/dev/null || echo "hc_signal failed for $JOB" >&2
  rm -rf -- "$J"; echo "done $JOB"
}

# ------------------------------------------------------------------ driver: runs INSIDE the sandbox
driver_main() {
  set +e   # inside the sandbox every probe may fail (timeouts, missing IPC); keep -u and pipefail from the top of the file
  cd "$HC_J" || exit 1; D=$HC_D; H=$HC_H; J=$HC_J; ID=$HC_ID
  export PATH="$J/shims:$HC_REALPATH"; : > "$HC_SHIMLOG"
  date +%s > "$D/t0.txt"; touch "$D/t0.stamp"
  ipc() { timeout 10 "$HC_QS" ipc -p "$J/shell" call "$@" 2>&1; }
  "$HC_QS" -n -p "$J/shell" >"$D/qs_stdout.txt" 2>&1 &
  QPID=$!; sleep 2
  : > "$D/samples.tsv"; : > "$D/procs.tsv"
  for s in $(seq 1 "$HC_RUNSEC"); do
    if kill -0 "$QPID" 2>/dev/null; then
      ps -eo pid=,ppid=,pcpu=,rss=,nlwp=,comm=,args= 2>/dev/null | awk -v s=$s '$6!="ps" && $6!="sleep" && $6!="awk" && $6!="timeout" && $0 !~ /driver\.sh --driver/{print s"\t"$0}' >> "$D/procs.tsv"
      ps -o pid=,pcpu=,rss=,nlwp=,comm= -p "$QPID" 2>/dev/null | awk -v s=$s '{print s"\t"$0}' >> "$D/samples.tsv"
    else echo "$s	DEAD" >> "$D/samples.tsv"; fi
    [ $s = 9 ] && { ipc shell listPlugins > "$D/ipc_list.txt"; echo "exit=$?" >> "$D/ipc_list.txt"; timeout 10 "$HC_QS" ipc -p "$J/shell" show > "$D/ipc_show.txt" 2>&1; }
    if [ $s = 10 ]; then if [[ " $HC_NOTOGGLE " == *" $ID "* ]]; then echo SKIPPED > "$D/toggle.txt"; else ipc shell toggle "$ID" '{}' > "$D/toggle.txt"; echo "exit=$?" >> "$D/toggle.txt"; fi; fi
    if [ $s = 12 ]; then
      python3 - "$D/ipc_show.txt" "$ID" > "$D/ipc_calls.txt" <<'PY'
import re,sys
t,pid=sys.argv[1:]; tail=pid.split(".")[-1].lower(); cur=None; out=[]
SAFE=r"^(refresh|reload|update|open|show|next|prev|previous|nextPage|prevPage|ping|state|status|isOpen|count|list|get[A-Z]\w*|showHistory|openPanel|togglePanel|expand|collapse)$"
BAD="set|delete|remove|clear|kill|send|post|submit|install|connect|lock|suspend|power|reboot|shutdown|exec|run|start|stop|enable|disable|write|save|copy|paste|push|pull|play|pause|dismiss|invoke|launch|activate"
FIRST={"image-selector","notifications","lock","shell","bar","menu","osd","emojis","clipboard","polkit","reminders","agents","background","idle","media","battery","nightlight","wifiqr","speedtest","disk-speedtest","dev-gallery","image-picker"}
try: lines=open(t,errors="replace").read().splitlines()
except Exception: lines=[]
for l in lines:
    m=re.match(r"target (\S+)",l)
    if m: cur=m.group(1); continue
    m=re.match(r"\s+function (\w+)\((.*?)\)",l)
    if not m or not cur: continue
    mine=(tail in cur.lower() or pid.lower() in cur.lower()) or (not cur.startswith("omarchy.") and cur not in FIRST)
    if mine and not m.group(2).strip() and re.match(SAFE,m.group(1)) and not re.search(BAD,m.group(1),re.I) and m.group(1)!="toggle": out.append(f"{cur}\t{m.group(1)}")
print("\n".join(out[:12]))
PY
      : > "$D/ipc_out.txt"
      while IFS=$'\t' read -r TG FN; do [ -z "$TG" ] && continue; r=$(ipc "$TG" "$FN" | head -c 400 | tr '\n\t' '  '); printf '%s.%s\t%s\n' "$TG" "$FN" "$r" >> "$D/ipc_out.txt"; done < "$D/ipc_calls.txt"
    fi
    [ $s = 18 ] && [[ " $HC_NOTOGGLE " != *" $ID "* ]] && { ipc shell toggle "$ID" '{}' >> "$D/toggle.txt"; echo "exit=$?" >> "$D/toggle.txt"; }
    [ $s = 22 ] && { ipc shell listPlugins > "$D/ipc_list_end.txt"; echo "exit=$?" >> "$D/ipc_list_end.txt"; }
    sleep 1
  done
  L=$(grep -o 'Saving logs to "[^"]*' "$D/qs_stdout.txt" | sed 's/.*"//')
  if [ -n "$L" ] && [ -f "$L" ]; then { strings "$L" 2>/dev/null || tr -cd '\11\12\15\40-\176' < "$L"; } | tail -800 > "$D/qslog.txt"; fi
  kill "$QPID" 2>/dev/null; sleep 1
  if [ "${HC_PIDNS:-}" = 1 ]; then   # inside the private pid namespace everything still alive after quickshell was killed is a leak
    ps -eo pid=,ppid=,args= 2>/dev/null | grep -v -E "driver\.sh|bwrap|ps -eo|grep|awk|sleep" > "$D/leaked_procs.txt"
  else pgrep -af "$H" 2>/dev/null | grep -v pgrep > "$D/leaked_procs.txt"; fi
  pkill -9 -f "$H" 2>/dev/null
  find "$H" -newer "$D/t0.stamp" \( -type f -o -type d -o -type l \) -printf '%P\t%m\t%y\t%s\t%l\n' 2>/dev/null | grep -v -E "^(\.config/omarchy/(plugins|current)|\.cache/(mesa|quickshell|qt|fontconfig)|\.local/state/quickshell|\.config/omarchy/shell\.json)" | head -200 > "$D/files_written.tsv"
  find "$J/tmp" -mindepth 1 \( -type f -o -type d -o -type l \) -printf '%P\t%m\t%y\t%s\t%l\n' 2>/dev/null | head -200 > "$D/tmp_entries.tsv"
  exit 0
}

# ------------------------------------------------------------------ main
[ -n "${HC_SOURCE_ONLY:-}" ] && return 0 2>/dev/null   # tests source the functions above without running anything
case "${1:-}" in
  --driver) driver_main; exit 0;;
  --job) job_main "$2"; exit $?;;
  --preflight) preflight; exit $?;;
esac
BATCH=${1:-all}
preflight || { echo "preflight failed"; exit 1; }
if ! sandbox_ok && [ "$ALLOW_NO_SANDBOX" != 1 ]; then echo "Refusing to run without the sandbox (see preflight). Re-run with ALLOW_NO_SANDBOX=1 to accept that plugins may write outside ~/usuba-hitcheck."; exit 1; fi
mkdir -p "$BASE/src" "$BASE/work" "$RES"
for b in A B; do [ -f "$BASE/src/.$b" ] || { tar xzf "$PKG/plugins-$b.tar.gz" -C "$BASE/src" && touch "$BASE/src/.$b"; }; done
rm -f "$BASE/STOP"; touch "$JSONL"
python3 - "$PKG/jobs.json" "$BATCH" "$JSONL" "${ONLY:-}" "${LIMIT:-0}" > "$BASE/todo.txt" <<'PY'
import json,sys
j=json.load(open(sys.argv[1]))["jobs"]; b=sys.argv[2]; done=set()
for l in open(sys.argv[3]):
    try: done.add(json.loads(l)["job"])
    except Exception: pass
only=set(x for x in sys.argv[4].split(",") if x); lim=int(sys.argv[5])
out=[x["job"] for x in j if (b=="all" or x["batch"]==b) and x["job"] not in done and (not only or x["job"] in only)]
print("\n".join(out[:lim] if lim else out))
PY
N=$(wc -l < "$BASE/todo.txt"); echo "$(date +%T) running $N jobs (batch $BATCH), P=$P, timeout ${TIMEOUT}s each; results -> $JSONL"
RUNNER=(xargs -a "$BASE/todo.txt" -P "$P" -I{} "$PKG/run_hitcheck.sh" --job {})
if command -v systemd-run >/dev/null && systemd-run --user --scope -q true 2>/dev/null; then
  systemd-run --user --scope -q -p MemoryMax=10G -p MemorySwapMax=0 "${RUNNER[@]}" 2>&1 | tee -a "$RES/run.log"
else "${RUNNER[@]}" 2>&1 | tee -a "$RES/run.log"; fi || echo "some jobs failed (see $RES/run.log)" >&2
echo "$(date +%T) finished: $(wc -l < "$JSONL") result lines in $JSONL"
rmdir "$BASE/work" 2>/dev/null; true
