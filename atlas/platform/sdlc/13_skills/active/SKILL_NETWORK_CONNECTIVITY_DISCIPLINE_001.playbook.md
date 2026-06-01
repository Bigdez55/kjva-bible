# Network Connectivity Triage Discipline

> Promoted from the 2026-05-30 fleet-push ordeal. A routine "commit and push"
> became hours of failed pushes because two LOCAL faults were misdiagnosed as a
> network/auth outage. This skill encodes the triage order so the real cause is
> found in seconds.

## The Core Rule

**A connectivity-looking error is a hypothesis, not a diagnosis.** Before you
wait, retry-loop, or blame GitHub/the ISP, run the 30-second local triage below.
Most "the network is down" moments are a local socket or SSH-config fault.

## Triage Order (run top to bottom, stop at first hit)

### 1. Does ICMP work but TCP fails? → port exhaustion

```bash
ping -c1 1.1.1.1                 # ICMP — needs no ephemeral port
nc -z -w3 1.1.1.1 443           # TCP  — needs an ephemeral port
```

| ping | TCP | Verdict |
|---|---|---|
| OK | OK | Network is fine — look elsewhere (auth, host key, DNS) |
| OK | FAIL | **Local TCP ephemeral-port exhaustion** — go to §A |
| FAIL | FAIL | Genuine link/DNS outage — check Wi-Fi/router |

The signature of exhaustion: TCP connect fails **instantly** (<5ms) with
`Can't assign requested address`, while ping is happy.

### 2. Connects but `Host key verification failed`? → §B

### 3. Connects, key OK, but `Permission denied (publickey)`? → real auth
(check `ssh-add -l`, the deploy key, the remote URL). Out of scope here.

---

## §A — TCP Ephemeral-Port Exhaustion

**Cause:** tens of thousands of sockets stuck in `TIME_WAIT` consume the macOS
ephemeral range (`net.inet.ip.portrange.first`..`last`, default 49152–65535 =
16,384 ports). New outbound connections have no source port to bind.

**Confirm:**
```bash
netstat -an | grep -c TIME_WAIT                 # tens of thousands = exhausted
netstat -an | awk '$6=="TIME_WAIT"{n=$5;sub(/\.[0-9]+$/,"",n);print n}' | sort | uniq -c | sort -rn | head
sysctl net.inet.ip.portrange.first net.inet.ip.portrange.last
```

**Fix — pick one (fastest first):**
```bash
# 1. Expand the range downward — ~33k fresh ports, works INSTANTLY, no drain wait
sudo sysctl -w net.inet.ip.portrange.first=16384

# 2. Cycle the link — drops all TCP state at once
networksetup -setairportpower en0 off && sleep 2 && networksetup -setairportpower en0 on

# 3. Reboot — guaranteed clean slate
```

**Do NOT:** lower `net.inet.tcp.msl` and wait for the backlog to drain. Darwin
pins each socket's MSL timer at creation; lowering it only affects NEW sockets,
so the stuck count does not drop. This wastes the most time of any wrong move.

**Restore after (optional — both reset on reboot):**
```bash
sudo sysctl -w net.inet.ip.portrange.first=49152
```

**What creates 50k TIME_WAITs?** Tight loops of short-lived TCP connections:
aggressive curl/health-check loops, Playwright/screenshot sweeps, a dev server
restarted dozens of times, retry loops with no backoff. If you ran any of those
this session, that's the source — kill them first.

---

## §B — SSH Host-Key Verification (port-22 fallback)

**Cause:** `~/.ssh/config` routes `github.com` over the port-443 fallback
(`HostName ssh.github.com`, `Port 443`) — added when outbound port 22 is blocked
— but `known_hosts` only holds the plain port-22 `github.com` entry. SSH looks up
`[github.com]:443` / `[ssh.github.com]:443`, finds no port-qualified key, and
fails `Host key verification failed` even though the key is "known".

**Confirm:**
```bash
grep -A4 github ~/.ssh/config                 # is there a Port 443 block?
ssh-keygen -F "[github.com]:443"              # empty = port-qualified entry missing
ssh -vvT git@github.com 2>&1 | grep -iE "Server host key|known_hosts|verification"
```

**Fix (persistent):**
```bash
printf '[github.com]:443 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl\n[ssh.github.com]:443 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl\n' >> ~/.ssh/known_hosts
```
Verify against GitHub's published fingerprint
`SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU` first.

**NEVER** `StrictHostKeyChecking no` — it trusts any key the server presents (MITM).

If outbound port 22 later works, the `~/.ssh/config` fallback block can be removed
and the port-443 known_hosts entries become unused (harmless to leave).

---

## Anti-Patterns

| Anti-pattern | Consequence | Correct move |
|---|---|---|
| "Push fails → network's down → wait" | Hours lost on a local fault | Run the §1 ping-vs-TCP test first |
| Lowering `tcp.msl` to drain TIME_WAIT | Count doesn't drop; more time lost | Expand port range / cycle link |
| `StrictHostKeyChecking no` | MITM-vulnerable | Add verified port-qualified known_hosts entry |
| Reading `Could not read from remote repository` literally | Chases an auth/repo red herring | It's usually host-key (§B) or exhaustion (§A) |
| Retry-loop with no diagnosis | Burns time + creates MORE TIME_WAITs, worsening §A | Diagnose once, fix root cause |

## Validation Gates

| Gate | Pass |
|---|---|
| TCP works | `nc -z -w3 1.1.1.1 443` succeeds |
| Port-qualified host key present (if :443 fallback) | `ssh-keygen -F "[github.com]:443"` returns a line |
| TIME_WAIT in steady state | `netstat -an \| grep -c TIME_WAIT` < ~10000 |
| Push works | `git ls-remote origin` returns refs |

## Incident Record

| Date | Project | Symptom | Root cause | Fix |
|---|---|---|---|---|
| 2026-05-30 | DS + 9-repo fleet push | Every push failed; `Can't assign requested address` then `Host key verification failed`; looked like an outage | (1) ~53k stuck TIME_WAIT exhausted ephemeral ports; (2) `~/.ssh/config` :443 fallback lacked port-qualified known_hosts | Expanded port range to 16384; appended verified `[github.com]:443` + `[ssh.github.com]:443` keys |

## Related Skills

- `SKILL_GIT_REMOTE_DISCIPLINE_001` STEP 7 — the git-push-specific view of the same two faults
- `SKILL_UI_LIVE_VERIFICATION_BEFORE_DONE_001` — sibling "diagnose, don't assume" discipline
