# Heartbeat kit

An autonomous work loop for a Claude Code session: it wakes itself, checks a small
set of ground-truth sources, advances **one item per tick** inside a hard envelope,
logs every tick, and queues anything irreversible to the human owner.

It is deliberately small. The interesting part isn't the code — it's the **discipline**:
predictions before actions, a hard envelope around what an unattended agent may do,
empty ticks treated as good ticks, and durability/liveness so a silent death is loud.

> These are working tools with rough edges, not a polished product. The author runs a
> heavily-extended version of this loop daily; this kit is the genericized core.

## What's in the kit

| Piece | Path | Role |
|---|---|---|
| Tick-protocol skill | `skills/heartbeat-kit/SKILL.md` | Defines one tick: kill switch → cheap gate → act (one item) → verify → log → pace |
| Board template | `templates/heartbeat-board.html` | Minimal kanban (single JSON block); the shared surface between owner and agent |
| Launcher | `bin/heartbeat-launch.sh` | First-ignite state setup + starts `claude "/loop /heartbeat-kit"` |
| Durability net | `bin/orphan-audit.sh` | Read-only check for untracked durable files a dead session left behind |
| Liveness watchdog | `.github/workflows/heartbeat-liveness.yml` | Off-machine alert when no tick has been pushed within a threshold |
| Gate sources example | `examples/sources.md` | Starter template for the one part you configure — what ground truth the gate reads |
| Board engine | `lib/board.py` + `lib/config.py` | Lock-guarded, file-per-card board read/write with a provenance ratchet (paths/columns in `config.py`) |
| Injection sanitizer | `lib/injection_sanitize.py` | Layer-1 producer-boundary defang of untrusted text + provenance stamp |
| Seeded prompt | `lib/seeded_prompt.py` | Layer-2 data-fenced prompt builder for opening a card into a session |
| Example producer | `lib/example_producer.py` | The sanitize → stamp → upsert-through-the-ratchet pattern, end to end |
| Tests | `tests/` | Sanitizer bypass vectors, the provenance ratchet, and the seeded-prompt fence |
| Design notes | `docs/design.md` | The "why" behind each rule — including the three-layer prompt-injection defense |

The skill is named `heartbeat-kit` so it never collides with a project-specific
`/heartbeat` skill you may already have.

## Install

```bash
git clone https://github.com/<you>/heartbeat.git ~/heartbeat
mkdir -p ~/.claude/skills/heartbeat-kit
cp ~/heartbeat/skills/heartbeat-kit/SKILL.md ~/.claude/skills/heartbeat-kit/
```

(The launcher pre-flight-checks that the skill is deployed and refuses to start otherwise.)

## Ignite

```bash
~/heartbeat/bin/heartbeat-launch.sh [working-directory]
```

`working-directory` defaults to `$HOME`. Set it to a **git repo the loop can push from** if
you want durable ticks and the off-machine liveness watchdog (the loop commits + pushes
tick state from there each tick).

Stop at any time:

```bash
touch ~/.heartbeat-stop
```

## Before you ignite — read this

1. **Permission mode.** The launcher defaults to `--permission-mode auto` (safe actions
   auto-approve; the permission classifier still hard-blocks risky ones). On a strict
   machine (e.g. an employer's), launch with `HEARTBEAT_MANUAL=1` so every action needs
   manual approval.
2. **Configure the gate.** The loop reads *ground truth*, and yours is specific to you.
   List your sources (CI status, a job queue, an inbox, a deploy-health check, an upstream
   agent's receipts) in your project's `CLAUDE.md` or `~/.heartbeat/sources.md` — start
   from [`examples/sources.md`](examples/sources.md). The kit ships the mechanics (board,
   ledger, durability, liveness); the source list is yours.
3. **State isolation.** All heartbeat state lives in `~/.heartbeat/` — deliberately
   OUTSIDE `~/.claude/`, so syncing your dotfiles can never clobber or carry heartbeat
   state across machines. Do not move it back inside `~/.claude`.
4. **Liveness.** If you want the off-machine watchdog, commit your tick log to a tracked
   path, make the loop `git push` every tick, and set `TICKS_PATH` in the workflow.

## Design properties

- **One item per tick.** The gate is cheap and read-only; the act step does exactly one
  thing — the most valuable actionable item.
- **Predictions before actions.** Significant actions append a falsifiable prediction to
  `~/.heartbeat/ledger.jsonl` (statement, verification command, success regex, baseline,
  deadline) BEFORE acting. Post-hoc entries are rejected.
- **Hard envelope.** Branch/commit/PR/draft/read are free. Prod-merge, deploy, spend,
  send-to-humans are queued to the board's "Waiting on owner" column, never done — and a
  queued card is only ever executed later behind a content-hashed, freshness-checked owner
  approval.
- **Adversarial review.** Significant work products get a fresh-context refute pass before
  they're queued for the owner.
- **Prompt-injection defense in depth.** Untrusted text scraped into a card is defanged at
  the producer boundary (`lib/injection_sanitize.py`), framed as data in the seeded prompt
  (`lib/seeded_prompt.py`), and stamped so the auto-land gate refuses it
  (`board.can_auto_land` — AI cannot approve its own work). Three independent layers, each
  assuming the others may fail. See [`docs/design.md`](docs/design.md) §Prompt-injection defense.
- **Durability.** A durability net catches uncommitted work; the loop pushes every tick so
  an unpushed tick can't die silently with the machine.
- **Liveness from the outside.** A GitHub Action reads the pushed tick log and alerts when
  the loop goes quiet — the machine can't be trusted to report its own death.
- **Empty ticks are good ticks.** No busy-work; the loop logs "none" and sleeps longer.
- **Machine-local state.** Board, ledger, and tick log live under `~/.heartbeat/` and are
  never synced across machines — each deployment is isolated.
- **Model-agnostic.** No model names in state or protocol; gate cheap, act capable.
- **No self-modification.** The loop never edits its own skill, envelope, or approval
  mechanics; those changes come from an interactive session with the owner.

## License

MIT — see [LICENSE](LICENSE).
