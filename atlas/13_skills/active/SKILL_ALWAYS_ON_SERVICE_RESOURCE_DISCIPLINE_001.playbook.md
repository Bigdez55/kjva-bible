# Always-On Service Resource Discipline

> Canonical skill playbook. Source of truth: `platform/sdlc/13_skills/active/SKILL_ALWAYS_ON_SERVICE_RESOURCE_DISCIPLINE_001.playbook.md`
> Human-authored (skill-text is never machine-mutated — see `definition-of-done-gate` risk note).

**Summary.** Any process registered to run *unattended* (launchd LaunchAgent/Daemon, systemd
unit, pm2, supervisord, Docker `restart: always`, a `while true` loop, a `KeepAlive` of any
kind) MUST be bounded so a failure degrades **gracefully** instead of cascading into a
machine-wide resource runaway. The default behavior of "keep it alive" is a crash→respawn loop
that — combined with child-process orphaning and no memory ceiling — silently consumes the whole
machine while no one is watching. This skill is the always-on-service analog of
`process-group-kill-discipline` (which governs gate harnesses).

## When to invoke

Triggers (any of):
- Creating/editing ANY launchd plist, systemd unit, pm2/supervisor config, Docker restart policy,
  or a script that respawns a child in a loop.
- "always on", "keep alive", "run as a service", "daemon", "background service", "auto-restart".
- "the machine ran out of memory overnight", "100 processes open", "duplicate processes",
  "Node/Python piling up", "it keeps reopening", "fans spun up / laptop hot overnight".
- launchd `Status -9` (SIGKILL/jetsam) on a KeepAlive agent.
- Before ending a session or leaving an agent in **auto/unattended mode** — account for every
  background process you started or touched (see "Mindfulness" below).

## Core directive

**"Keep it alive" without bounds is a resource bomb with a timer.** A supervised process that
crashes is respawned; if it crashes again it is respawned again. With no throttle, no memory cap,
and orphaned children, that loop converts one bug into thousands of processes and an exhausted
machine — and because it happens unattended, the first symptom is a frozen laptop in the morning.

Every always-on service MUST carry **five guardrails** AND ship an **operator OFF switch**.

### The five guardrails (mandatory)

1. **Throttle the respawn.** Enforce ≥ 30–60 s between respawns. A 10 s (or 0 s) interval lets a
   crash-looper spin 6–360×/min and pile up faster than anyone can react.
   - launchd: `<key>ThrottleInterval</key><integer>60</integer>`
   - systemd: `RestartSec=60` + `StartLimitIntervalSec` / `StartLimitBurst` (fail-stop after N).
   - The throttle is the **real backstop** — it converts a runaway into a slow, visible blink.

2. **Cap memory.** Give the runtime a heap ceiling so a leak self-bounds (clean exit / GC
   pressure) **before** the kernel OOM-kills it. The OOM-kill → respawn cascade IS the overnight
   pile-up engine.
   - Node: `NODE_OPTIONS=--max-old-space-size=<MB>` (web ~2048, small service ~512–1024). Set it
     too low and the process V8-OOMs *itself* into the same loop — size it generously; the throttle
     is the safety net, the cap just makes a leak fail soft + early.
   - Python / other: container memory limit, `resource.setrlimit(RLIMIT_AS, …)`, or a watchdog.
   - **macOS caveat:** launchd `HardResourceLimits`/`ResidentSetSize` are *no-ops* — do not rely on
     them. Use the runtime's own heap flag + the throttle.

3. **Reap orphans on (re)start.** `SIGKILL`/OOM-kill is **uncatchable** — a parent cannot reap its
   child at crash time, so the child orphans to PID 1 and squats the port/resource. The supervised
   entrypoint MUST, *before* binding, kill any process already holding its port:
   ```sh
   lsof -ti tcp:"$PORT" -sTCP:LISTEN | xargs -r kill -9
   ```
   This guarantees the *next* respawn cleans the leak instead of accumulating one orphan per cycle.

4. **Single-instance, and flaky/optional deps are OPT-IN.** Exactly one instance per port. A flaky
   or optional dependency (a research daemon, a broker, an experimental sidecar) must **not** run
   unattended on KeepAlive — make it opt-in (`ENABLE_X=1`) and let its consumer **degrade
   gracefully** when it is down. **Never leave a known-degraded daemon** (missing module, dead
   broker, repeating traceback) on KeepAlive: it will crash-loop forever, unattended.

5. **Idempotent boot.** The entrypoint must not do heavy work (large file copies, full re-scans,
   re-downloads) on *every* respawn — gate it on a build-id sentinel / mtime check. Under a
   crash-loop, per-boot heavy work is its own storm (e.g., `cpSync` of an asset tree over a
   cloud-synced folder like OneDrive/iCloud triggers a sync storm that itself drives load/IO).

### The operator owns the switch (authority)

Every always-on service MUST ship a **one-command OFF that STAYS off** — not a "stop" that the
supervisor instantly respawns, and never forcing the operator to hand-kill processes in a terminal.

- launchd: `launchctl disable gui/$UID/<label>` + `bootout` → persists across login/reboot.
  (A bare `stop`/`bootout` is respawned at next login via `RunAtLoad` — that is NOT "off".)
- systemd: `systemctl disable --now <unit>`.
- Provide `enable` / `disable` / `reap` (kill leaks + evict legacy + census) / `status` subcommands
  so turning it off, on, or cleaning up is always one command. The operator's intent wins —
  "if I turn it off, it stays off."

## Mindfulness when leaving tasks/agents running (the trigger discipline)

The overnight pile-up happened because an agent was left in auto mode with unbounded services
running. **Before ending a session, or before leaving any agent in unattended/auto mode:**

1. Account for every background process and supervised service you started or *touched*. For each:
   is it bounded (throttle + mem cap + reap)? Can it crash-loop? Will it orphan children?
2. If you cannot answer "yes, bounded" for all of them, run the reaper / `status` and verify a
   **FLAT process census + stable free RAM** before declaring done.
3. **Agent-green ≠ machine-healthy.** A passing build/test run with 100 leaked processes is a
   *failure*, not a success. The deliverable is "the work is done AND the machine is clean."

## Detection symptoms

- launchd `launchctl list` shows `Status -9` (SIGKILL/jetsam) on a KeepAlive agent.
- `ps -axo pid,ppid,etime,rss,command` shows accumulating same-named processes (Node/Python) with
  **PPID 1** (orphaned to launchd/init).
- Two+ servers where one squats the port (leaked orphan) while the managed one cannot bind →
  launchd crash-respawns → leaks another → self-sustaining loop.
- Free RAM trending down over hours; heavy `vm_stat` Pageouts (swap thrash).
- A daemon log repeating the *same* connect-failure / missing-dependency traceback forever.

## Recipe — bring an unbounded service into compliance

1. **Census first.** `ps -axo pid,ppid,rss,etime,command | grep -E '<your procs>'` and
   `launchctl list | grep <label>`. Identify orphans (PPID 1) and `Status -9`.
2. **Reap the residue.** Kill orphans by PID; `bootout` + `disable` + `rm` any broken/legacy agent.
3. **Add the five guardrails** to the plist/unit + the entrypoint (throttle, mem cap, port-reap,
   single-instance/opt-in, idempotent boot).
4. **Add the OFF switch** (`enable`/`disable`/`reap`/`status`).
5. **Verify by observation, not config.** Restart, then confirm: exactly one listener per port,
   health 200, `runs = 1` / no respawn churn, and a **flat** process census + stable RAM over
   several minutes. An edited plist is not a fixed machine — a flat census is.

## Anchor episode

**ATLAS, 2026-06-03 (macOS, 16 GB).** An unattended overnight agent session plus three KeepAlive
launchd agents — `com.atlas.web`, `com.atlas.mcp`, and a legacy Python `com.atlas.bookworm.local`
— piled up 100+ Node/Python processes and exhausted RAM; the operator had to manually kill
everything through the Terminal in the morning. Root causes, all five-guardrail violations:

1. **No single-instance / opt-in:** the legacy `com.atlas.bookworm.local` Python daemon crash-looped
   forever on a missing `Citadel` module + a dead broker on `:18600`, KeepAlive with **no
   ThrottleInterval** — a known-degraded daemon left running unattended.
2. **No orphan reap:** `start-standalone-atlas.mjs` reaped its `next-server` child only via a JS
   `exit` handler — uncatchable jetsam `SIGKILL` orphaned a `next-server` to PID 1 every crash cycle
   (one was found leaked, squatting a random port, 17.5 h old).
3. **No memory cap + tight throttle:** `ThrottleInterval=10`, no heap ceiling → kernel jetsam
   OOM-kill (`Status -9`) → 10 s respawn → cascade.
4. **Multiplier:** a per-editor-window MCP `.mcp.json` spawned a fresh `node` server per Claude
   Code / Codex window across ~25 workspaces.

**Fix:** `ThrottleInterval`→60 s, `NODE_OPTIONS` heap caps (web 2048 / mcp 1024), pre-flight
port-reap + build-id-gated asset copy in the runner, Bookworm made **opt-in** (`ATLAS_ENABLE_BOOKWORM=1`,
web route already falls back to the local index), and `atlas-service.sh enable|disable|reap|status`
for operator authority. Verified by observation: one listener per port, `runs=1`, flat census,
`disable web` → `:4317` to 0 and stays off across an 8 s KeepAlive window.
(Per-window MCP multiplier logged as a follow-up — a larger, riskier change.)

## Anti-patterns

- `KeepAlive=true` (or `restart: always`) with no throttle, no memory cap, and no orphan reap.
- A `stop` command the supervisor instantly respawns, presented to the operator as "off".
- Leaving a known-degraded daemon (missing dep / dead broker / repeating traceback) on KeepAlive.
- Heavy work (asset copy, full re-scan) on every boot of a crash-looping service.
- Declaring a task done on a green build without checking the **machine** is clean (flat census).
- `pkill -f node` / `pkill -f python` to clean up — blunt; kills editors, language servers,
  unrelated tools. Kill by specific PID and by service label.

## Cross-refs

- `process-group-kill-discipline` — the gate-harness sibling (kill the whole process group on
  timeout). This skill is its **always-on-service** analog.
- `electron-single-instance-discipline` — single-instance enforcement for desktop apps.
- `network-connectivity-discipline` — port/connect failure triage.
- `verify-validate` — pre-commit/done gate: now also requires "no runaway processes left behind".
- `definition-of-done-gate` — "done" must be probe/observation-verified, not self-reported.

## Changelog

- **1.0.0** (2026-06-03) — Initial authoring. Anchor: ATLAS overnight 100+ Node/Python pile-up.
  Five guardrails (throttle, memory cap, orphan reap, single-instance/opt-in, idempotent boot) +
  operator OFF-switch authority + leave-no-runaway mindfulness. Human-authored.
