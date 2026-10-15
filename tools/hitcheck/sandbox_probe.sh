#!/bin/bash
# Sandbox hardening probe for the hit-check runner (run ON the machine that will run plugins, from a terminal in the desktop session).
# It builds the EXACT bwrap argument list of run_hitcheck.sh (build_bwrap_args, extracted from that file, never re-typed) and runs a hostile "plugin" payload in it:
# read real $HOME (.ssh, a canary file), reach host sockets (dbus, systemd, docker, hyprland, pipewire, ssh-agent), see host env secrets, see host processes,
# open /dev/input|disks, use the network, write outside the job dir, and replace evidence files with symlinks / FIFOs to host files that the (unsandboxed) hc_signal.py would read.
# It never prints the content of any host secret: existence/readability checks only, and a unique canary string that it plants itself.
# Exit 0 = every probe BLOCKED. Exit 1 = at least one LEAK (do not run plugins). Result lines: PROBE <name> <BLOCKED|LEAK|INFO> <detail>.
# usage: sandbox_probe.sh [OUTFILE]      env: BASE (work dir, default ~/usuba-hitcheck-probe)
set -uo pipefail
PKG="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"; BASE="${BASE:-$HOME/usuba-hitcheck-probe}"; OUT="${1:-$BASE/probe-result.txt}"
mkdir -p "$BASE"; : > "$OUT"
[ -n "${WAYLAND_DISPLAY:-}" ] || echo "note: no WAYLAND_DISPLAY; the socket pass-through is not exercised" >&2
# load build_bwrap_args from the runner without running its main
eval "$(sed -n '/^build_bwrap_args() {/,/^}/p' "$PKG/run_hitcheck.sh")"
NET=${NET:-0}; SESSION_ACCESS=0
CAN="$HOME/.usuba-probe-canary"; mkdir -p "$CAN"; MARK="CANARY-$(head -c12 /dev/urandom | od -An -tx1 | tr -d ' \n')"; echo "$MARK" > "$CAN/secret.txt"
J="$BASE/work/probe"; rm -rf "$J"; mkdir -p "$J/tmp" "$J/out" "$J/home"; XRD="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
HOSTHOME="$HOME"; HOSTUID=$(id -u)
cat > "$J/payload.sh" <<'PAY'
#!/bin/bash
r() { echo "PROBE $1 $2 $3"; }
RH="$PROBE_REALHOME"
# 1 real home
[ -e "$RH/.ssh" ] && r home-ssh-visible LEAK "$RH/.ssh exists in sandbox" || r home-ssh-visible BLOCKED "no $RH/.ssh"
for f in "$RH/.ssh/id_ed25519" "$RH/.ssh/id_rsa" "$RH/.gnupg" "$RH/.config/gh" "$RH/.config/omarchy/shell.json" "$RH/.bash_history"; do
  [ -r "$f" ] && r "home-read:${f#$RH/}" LEAK readable || r "home-read:${f#$RH/}" BLOCKED unreadable
done
[ -r "$RH/.usuba-probe-canary/secret.txt" ] && r home-canary LEAK "canary file readable: $(cat "$RH/.usuba-probe-canary/secret.txt" | head -c 40)" || r home-canary BLOCKED "canary not visible"
n=$(ls -A "$RH" 2>/dev/null | wc -l); r home-listing INFO "$n entries in sandbox view of real home (fake HOME dir is tmpfs-masked)"
for d in /home /root /var; do n=$(ls -A "$d" 2>/dev/null | grep -v -x "$(basename "$PROBE_REALHOME")" | wc -l); [ "$n" = 0 ] && r "dir-empty:$d" BLOCKED empty || r "dir-empty:$d" LEAK "$(ls -A $d | head -5 | tr '\n' ' ')"; done
# 2 sockets
for s in /run/user/$PROBE_UID/bus /run/dbus/system_bus_socket /var/run/dbus/system_bus_socket /run/systemd/private /run/systemd/journal/socket /var/run/docker.sock /run/docker.sock \
         /run/user/$PROBE_UID/pipewire-0 /run/user/$PROBE_UID/pulse/native /run/user/$PROBE_UID/hypr /run/user/$PROBE_UID/gnupg /run/user/$PROBE_UID/keyring /run/user/$PROBE_UID/ssh-agent.socket /run/user/$PROBE_UID/systemd/private /tmp/.X11-unix/X0; do
  [ -e "$s" ] && r "sock:$s" LEAK exists || r "sock:$s" BLOCKED absent
done
socks=$(find /run /var/run /tmp -maxdepth 3 -type s 2>/dev/null | tr '\n' ' '); r sockets-present INFO "${socks:-none}"
[ -S "$PROBE_XRD/$PROBE_WAYLAND" ] && r wayland-socket INFO "present (required by quickshell: RESIDUAL RISK, see docs)" || r wayland-socket INFO absent
# 3 environment: names only
bad=$(env | cut -d= -f1 | grep -E -i '^(SSH_|DBUS_|GPG_|GH_|GITHUB_|OPENROUTER|ANTHROPIC|OPENAI|AWS_|GOOGLE_|HYPRLAND_|SUDO_|XAUTHORITY|DISPLAY$)|TOKEN|SECRET|PASSWORD|API_KEY|_KEY$' | tr '\n' ' ')
[ -z "$bad" ] && r env-secrets BLOCKED "none among $(env | wc -l) vars" || r env-secrets LEAK "$bad"
r env-names INFO "$(env | cut -d= -f1 | sort | tr '\n' ' ')"
# 4 processes
n=$(ls /proc | grep -c '^[0-9]*$'); [ "$n" -le 12 ] && r pid-namespace BLOCKED "$n pids visible" || r pid-namespace LEAK "$n pids visible"
ps -eo comm= 2>/dev/null | grep -E -i '^(Hyprland|hyprland|quickshell|sshd|ssh-agent|gnome-keyring|systemd)' >/dev/null && r host-procs LEAK "host process names visible" || r host-procs BLOCKED "no host desktop/ssh processes visible"
[ "$(ps -o sid= -p $$ | tr -d ' ')" = "$$" ] && r new-session BLOCKED "own session leader" || r new-session INFO "sid=$(ps -o sid= -p $$ | tr -d ' ') pid=$$"
# 5 devices
bad=$(ls /dev | grep -E '^(input|sd[a-z]|nvme|mapper|mem|kmem|kmsg|tty[0-9]|video|snd|fuse|uinput|loop|disk|vhost|kvm|hidraw|usb|ttyS)' | tr '\n' ' ')
[ -z "$bad" ] && r dev-minimal BLOCKED "$(ls /dev | tr '\n' ' ')" || r dev-minimal LEAK "$bad"
# 6 network
if timeout 4 bash -c 'exec 3<>/dev/tcp/1.1.1.1/53' 2>/dev/null; then r network LEAK "TCP connect to 1.1.1.1:53 succeeded"; else r network BLOCKED "no route"; fi
ifs=$(ls /sys/class/net 2>/dev/null | tr '\n' ' '); [ "$ifs" = "lo " ] && r net-ifaces BLOCKED "only lo" || r net-ifaces INFO "$ifs"
# 7 writes outside the job
for p in /usr/usuba-probe /opt/usuba-probe /boot/usuba-probe /usr/bin/usuba-probe; do touch "$p" 2>/dev/null && r "write:$p" LEAK writable || r "write:$p" BLOCKED denied; done
touch /etc/usuba-probe-etc 2>/dev/null; r write-etc INFO "/etc is a tmpfs skeleton inside the sandbox; host-side check follows"
touch "$RH/usuba-probe-write" 2>/dev/null; r write-realhome-path INFO "writes land on a private tmpfs; host-side check follows"
touch /tmp/usuba-probe-tmp 2>/dev/null; r write-tmp INFO "private tmpfs; host-side check follows"
# 8 caps / privileges
c=$(grep CapEff /proc/self/status | awk '{print $2}'); [ "$c" = 0000000000000000 ] && r capabilities BLOCKED "CapEff=0" || r capabilities INFO "CapEff=$c (user-namespace root only, not host root)"
sudo -n true 2>/dev/null && r sudo LEAK "sudo works" || r sudo BLOCKED "no sudo"
# 9 sysfs / proc secrets
for f in /sys/class/dmi/id/product_serial /sys/class/dmi/id/board_serial /proc/kcore /proc/kmsg /proc/1/root/home; do [ -r "$f" ] && [ -n "$(head -c1 "$f" 2>/dev/null)" ] && r "read:$f" LEAK readable || r "read:$f" BLOCKED unreadable; done
# 10 evidence-file replacement: symlinks, FIFO and /dev/zero in the evidence dir that hc_signal.py reads outside the sandbox
D="$PROBE_OUT"
ln -sf "$RH/.usuba-probe-canary/secret.txt" "$D/toggle.txt" && r evidence-symlink-created INFO "toggle.txt -> canary"
ln -sf "$RH/.usuba-probe-canary/secret.txt" "$D/ipc_list.txt"
ln -sf /dev/zero "$D/qs_stdout.txt"; mkfifo "$D/qslog.txt" 2>/dev/null; ln -sf "$RH/.usuba-probe-canary" "$D/raw_dirlink"
echo done
PAY
BW=(); ENVV=(HOME="$J/home" TMPDIR="$J/tmp" PROBE_REALHOME="$HOSTHOME" PROBE_UID="$HOSTUID" PROBE_XRD="$XRD" PROBE_WAYLAND="${WAYLAND_DISPLAY:-wayland-1}" PROBE_OUT="$J/out")
build_bwrap_args "$J" "$HOSTHOME" "$XRD"
export SSH_AUTH_SOCK=/nonexistent/probe-agent GITHUB_TOKEN=probe-token-not-real OPENROUTER_API_KEY=probe-key-not-real DBUS_SESSION_BUS_ADDRESS=unix:path=/nonexistent/bus   # fake host secrets: must NOT appear inside
timeout -k 3 60 env -i PATH="$PATH" HOME="$HOME" SSH_AUTH_SOCK="$SSH_AUTH_SOCK" GITHUB_TOKEN="$GITHUB_TOKEN" OPENROUTER_API_KEY="$OPENROUTER_API_KEY" DBUS_SESSION_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS" \
  WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-}" XDG_RUNTIME_DIR="$XRD" bwrap "${BW[@]}" /bin/bash "$J/payload.sh" </dev/null 2>&1 | tee "$BASE/payload.log" | grep -a -E '^(PROBE|done)' >> "$OUT"
# host-side checks after the run
[ -e "$HOSTHOME/usuba-probe-write" ] && echo "PROBE write-realhome-path-host LEAK file appeared on the host" >> "$OUT" || echo "PROBE write-realhome-path-host BLOCKED nothing appeared on the host home" >> "$OUT"
[ -e /etc/usuba-probe-etc ] && echo "PROBE write-etc-host LEAK file appeared in host /etc" >> "$OUT" || echo "PROBE write-etc-host BLOCKED nothing appeared in host /etc" >> "$OUT"
[ -e /tmp/usuba-probe-tmp ] && echo "PROBE write-tmp-host LEAK file appeared in host /tmp" >> "$OUT" || echo "PROBE write-tmp-host BLOCKED nothing appeared in host /tmp" >> "$OUT"
# hc_signal.py on the poisoned evidence dir: the canary must not be copied into the JSON, and it must not hang on the FIFO or /dev/zero
echo '{"jobs":[{"job":"probe","batch":"P","kinds":["panel"]}]}' > "$J/jobs.json"
grep -q "$MARK" "$J/out/toggle.txt" 2>/dev/null && echo "PROBE control-naive-read INFO a naive read of the poisoned toggle.txt DOES expose the canary (so the next probe is meaningful)" >> "$OUT" || echo "PROBE control-naive-read LEAK control failed: poisoned symlink did not resolve, evidence probe is not meaningful" >> "$OUT"
if timeout 20 python3 "$PKG/hc_signal.py" "$J/out" "$J/jobs.json" probe probe.plugin > "$J/signal.json" 2> "$J/signal.err"; then
  grep -q "$MARK" "$J/signal.json" && echo "PROBE evidence-symlink-exfil LEAK canary string present in hc_signal output" >> "$OUT" || echo "PROBE evidence-symlink-exfil BLOCKED canary not in hc_signal output ($(wc -c < "$J/signal.json") bytes, no hang)" >> "$OUT"
else echo "PROBE evidence-symlink-exfil LEAK hc_signal.py failed or hung: $(head -c 200 "$J/signal.err")" >> "$OUT"; fi
grep -q "$MARK" "$J"/out/* 2>/dev/null; true
rm -rf "$CAN" "$J"
grep -q '^done' "$OUT" && echo "PROBE payload-completed INFO yes" >> "$OUT" || echo "PROBE payload-completed LEAK payload did not finish (sandbox failed to start?)" >> "$OUT"
grep -v '^done' "$OUT" > "$OUT.tmp"; mv "$OUT.tmp" "$OUT"
cat "$OUT"; n=$(grep -c ' LEAK ' "$OUT"); echo "SUMMARY blocked=$(grep -c ' BLOCKED ' "$OUT") info=$(grep -c ' INFO ' "$OUT") leak=$n"; [ "$n" = 0 ]
