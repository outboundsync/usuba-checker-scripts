# Hit-check sandbox: proof that the hardening holds on the real machine

Date: 2026-10-15 (MT). Machine: Dell Latitude 7430, Omarchy 4.0.4, Hyprland, Quickshell 0.3.1, bubblewrap from Arch. Runner: `tools/hitcheck/run_hitcheck.sh` (final version, sha256 recorded in the S2 package `SHA256SUMS`).
This replaces the earlier package `dell-hitcheck-pkg.tgz` (built 10:32 MT, no `--clearenv`, `--ro-bind / /`, `--dev-bind /dev`, per-job real HOME hidden only by a tmpfs): the 344-job hit-check of 10:33-11:26 MT ran on that older sandbox. Nothing hostile was in it (plugins were reviewed samples), but it is **not** the hardened runner; all new runs use the version below.

## What was tested
Two probes, both using the exact bwrap argument list of the runner (`build_bwrap_args`, extracted from the file, never re-typed). The runner's bwrap arguments and `sandbox_ok` were diffed byte for byte between the version probed first and the final shipped version (host-side observer code changed in between; sandbox arguments identical), and **both probes were then re-run on the final file**.

1. **Static probe** `tools/hitcheck/sandbox_probe.sh` (a hostile shell payload run inside the sandbox; host side checks afterwards). Result: **46 BLOCKED, 12 INFO, 0 LEAK**. Full output below.
2. **Hostile plugin end to end**: a real Quickshell plugin (`probe.hostile`, kind panel, runs `probe.sh` via `Process`) pushed through the full runner (`OBSERVE=1`, i.e. including the host-side observer). The payload tried to read a planted canary file under the real `~`, `~/.ssh`, the session bus, the Hyprland socket, the system bus, host secrets in the environment, the network (1.1.1.1:53), to write into the real home, and then to **poison the evidence directory** that the unsandboxed collector reads: `toggle.txt` and `ipc_list.txt` replaced by symlinks to the canary, `qslog.txt` by a symlink to `/dev/zero`, and `obs` by a symlink to the canary directory (to make the orchestrator's later `mv` write through it). Results:
   - canary readable from inside: **no** (`PROBE_canary_BLOCKED`); `~/.ssh` visible: **no**; session bus, Hyprland socket, system bus: **absent**; secrets in env: **none**; network: **blocked**.
   - canary string in the result JSONL: **0** occurrences; in any regular file under `results/raw`: **0**; canary directory afterwards: only the original `secret.txt` (nothing written through the `obs` symlink); `PROBE_HOSTILE_HOME_WRITE` in the real home: **0**; collector did not hang on `/dev/zero`.
   - the forged evidence made the plugin read as `unsure` (harness), i.e. forged evidence fails safe.
   Summary file: `results/s1s2/probe-hostile-plugin-summary.json`.

A positive control is built in: a naive read of the poisoned `toggle.txt` *does* return the canary (`control-naive-read INFO`), so the symlink escape attempt was real and `hc_safe.py` is what stops it.

## Static probe output (final run on the Dell; home path shortened to ~)
```
PROBE home-ssh-visible BLOCKED no ~/.ssh
PROBE home-read:.ssh/id_ed25519 BLOCKED unreadable
PROBE home-read:.ssh/id_rsa BLOCKED unreadable
PROBE home-read:.gnupg BLOCKED unreadable
PROBE home-read:.config/gh BLOCKED unreadable
PROBE home-read:.config/omarchy/shell.json BLOCKED unreadable
PROBE home-read:.bash_history BLOCKED unreadable
PROBE home-canary BLOCKED canary not visible
PROBE home-listing INFO 1 entries in sandbox view of real home (fake HOME dir is tmpfs-masked)
PROBE dir-empty:/home BLOCKED empty
PROBE dir-empty:/root BLOCKED empty
PROBE dir-empty:/var BLOCKED empty
PROBE sock:/run/user/1000/bus BLOCKED absent
PROBE sock:/run/dbus/system_bus_socket BLOCKED absent
PROBE sock:/var/run/dbus/system_bus_socket BLOCKED absent
PROBE sock:/run/systemd/private BLOCKED absent
PROBE sock:/run/systemd/journal/socket BLOCKED absent
PROBE sock:/var/run/docker.sock BLOCKED absent
PROBE sock:/run/docker.sock BLOCKED absent
PROBE sock:/run/user/1000/pipewire-0 BLOCKED absent
PROBE sock:/run/user/1000/pulse/native BLOCKED absent
PROBE sock:/run/user/1000/hypr BLOCKED absent
PROBE sock:/run/user/1000/gnupg BLOCKED absent
PROBE sock:/run/user/1000/keyring BLOCKED absent
PROBE sock:/run/user/1000/ssh-agent.socket BLOCKED absent
PROBE sock:/run/user/1000/systemd/private BLOCKED absent
PROBE sock:/tmp/.X11-unix/X0 BLOCKED absent
PROBE sockets-present INFO none
PROBE wayland-socket INFO present (required by quickshell: RESIDUAL RISK, see docs)
PROBE env-secrets BLOCKED none among 18 vars
PROBE env-names INFO _ HOME LANG PROBE_OUT PROBE_REALHOME PROBE_UID PROBE_WAYLAND PROBE_XRD PWD QT_QPA_PLATFORM QT_QPA_PLATFORMTHEME SHLVL TERM TMPDIR WAYLAND_DISPLAY XDG_CURRENT_DESKTOP XDG_RUNTIME_DIR XDG_SESSION_TYPE 
PROBE pid-namespace BLOCKED 5 pids visible
PROBE host-procs BLOCKED no host desktop/ssh processes visible
PROBE new-session INFO sid=1 pid=2
PROBE dev-minimal BLOCKED core dri fd full null ptmx pts random shm stderr stdin stdout tty urandom zero 
PROBE network BLOCKED no route
PROBE net-ifaces INFO lo virbr0 wlp0s20f3 
PROBE write:/usr/usuba-probe BLOCKED denied
PROBE write:/opt/usuba-probe BLOCKED denied
PROBE write:/boot/usuba-probe BLOCKED denied
PROBE write:/usr/bin/usuba-probe BLOCKED denied
PROBE write-etc INFO /etc is a tmpfs skeleton inside the sandbox; host-side check follows
PROBE write-realhome-path INFO writes land on a private tmpfs; host-side check follows
PROBE write-tmp INFO private tmpfs; host-side check follows
PROBE capabilities BLOCKED CapEff=0
PROBE sudo BLOCKED no sudo
PROBE read:/sys/class/dmi/id/product_serial BLOCKED unreadable
PROBE read:/sys/class/dmi/id/board_serial BLOCKED unreadable
PROBE read:/proc/kcore BLOCKED unreadable
PROBE read:/proc/kmsg BLOCKED unreadable
PROBE read:/proc/1/root/home BLOCKED unreadable
PROBE evidence-symlink-created INFO toggle.txt -> canary
PROBE write-realhome-path-host BLOCKED nothing appeared on the host home
PROBE write-etc-host BLOCKED nothing appeared in host /etc
PROBE write-tmp-host BLOCKED nothing appeared in host /tmp
PROBE control-naive-read INFO a naive read of the poisoned toggle.txt DOES expose the canary (so the next probe is meaningful)
PROBE evidence-symlink-exfil BLOCKED canary not in hc_signal output (773 bytes, no hang)
PROBE payload-completed INFO yes
SUMMARY blocked=46 info=12 leak=0
```

## Residual risk (not removed by this sandbox)
- **The Wayland socket is passed in** (Quickshell cannot run without it). A hostile client can speak any Wayland protocol the compositor exposes to ordinary clients (screen capture, virtual keyboard/pointer protocols if Hyprland enables them for all clients). The probe does not and cannot show this blocked. Mitigation: run only plugins that already passed the static Checker and hand-review, short runs (24 s), and do not run on a session with sensitive windows open. This is why the S2 candidates are Checker-passing, previously-run-clean plugins.
- `/dev/dri` is bound (Mesa needs it) and `/sys` is read-only visible (hardware info, not secrets: the DMI serial files are unreadable).
- Kernel and bubblewrap bugs are out of scope (shared kernel; user namespaces).
- The observer (OBSERVE=1) runs on the host: it calls `hyprctl layers/clients/monitors` and `grim` on rectangles of surfaces owned by the job's own Quickshell pid. Screenshots can include whatever is visible under a transparent plugin surface; they stay on the Dell and the build box and are not committed.
