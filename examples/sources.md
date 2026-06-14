# Heartbeat gate sources — example

Copy this to `~/.heartbeat/sources.md` (or fold it into your project's `CLAUDE.md`) and
edit it to match your world. Each tick, the loop reads these — cheaply, read-only — to
decide whether there is anything actionable. The list is the ONLY part of the loop that is
specific to you; everything else (board, ledger, durability, liveness) is generic.

A good source is: **cheap to read, ground truth (not memory), and tells you about work to
do.** If reading it is expensive or it's just your own opinion, it doesn't belong here.

## Format

For each source, write: how to read it, and what counts as "actionable".

```
- <name>
  read:       <a shell command or file path — read-only>
  actionable: <the condition that makes this a tick action>
  priority:   <where it ranks vs other sources>
```

## Examples (delete the ones that don't apply)

- CI status
  read:       `gh run list --branch main --limit 5 --json conclusion`
  actionable: latest run conclusion == "failure" (broken automation outranks everything)
  priority:   1 — broken automation

- Outcome ledger
  read:       `~/.heartbeat/ledger.jsonl`
  actionable: any prediction past its `horizon` and still unverified → verify it now
  priority:   2 — due/unverified predictions

- Job / task queue
  read:       `ls ./queue/pending/`
  actionable: any file present → process the oldest one
  priority:   3 — queued work

- Board
  read:       JSON block in `~/.heartbeat/board.html`
  actionable: a "Now" or "Next" card with owner "A" (agent)
  priority:   4 — planned cards

- Deploy health
  read:       `curl -fsS -o /dev/null -w '%{http_code}' https://your-site.example/healthz`
  actionable: non-200 for N consecutive checks → queue a "deploy unhealthy" card (don't
              self-deploy — that's outside the envelope)
  priority:   1 — production outage

- Upstream agent receipts (if another agent feeds you work)
  read:       `tail -n 20 ./upstream/receipts.log`
  actionable: a new receipt with a failure/escalation flag → surface as a proposed card
  priority:   2

## Anti-sources (do NOT put these here)

- "Check if there's anything I could improve" — that's busy-ticking; the gate reads facts.
- Anything that costs real money or time to read every tick.
- Your own notes from last tick — that's memory, not ground truth.
