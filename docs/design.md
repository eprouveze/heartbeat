# Heartbeat — design notes

The kit is small on purpose. Every rule below was earned by a failure mode an
unattended agent loop actually hits. This doc is the "why" behind the protocol in
`skills/heartbeat-kit/SKILL.md`.

## The shape: a self-pacing loop, not a cron job

A cron job runs on a fixed cadence whether or not there's anything to do, and has no
memory between runs. The heartbeat is a single long-lived session that decides *its own*
next wake-up: short when there's work in flight (stay warm), long when idle. Recurrence
comes from `/loop /heartbeat-kit`; the skill itself defines exactly one tick and never
schedules itself. That separation keeps "what one tick does" auditable.

## One item per tick

The failure mode of an eager agent is doing five half-considered things at once. The gate
is cheap and read-only; the act step picks the **single** highest-value actionable item.
This bounds blast radius, makes each tick reviewable, and makes "what did the loop do
overnight" answerable line by line in the tick log.

## Predictions before actions

The antidote to confabulated success ("looks done to me") is a falsifiable prediction
written *before* the action, with a verification command and a success regex. After the
action, you run the command and record CONFIRMED/REFUTED. Post-hoc predictions are
banned — a prediction written after you know the outcome verifies nothing. This is the
loop's learning signal: a hit rate you can actually trust.

## The hard envelope

An unattended agent must have a bright line between what it may do alone and what it may
only *prepare*. Free: branch, commit, PR, draft, read, research. Queued (never done):
prod-merge, deploy, spend, anything that sends to humans, anything irreversible. "Queued"
means a card in the board's "Waiting on owner" column with enough detail that the owner's
approval is a single yes.

The approval gate that lets a *later* tick execute a queued card is deliberately strict:
content-hash + explicit owner signal + freshness window. The point is that an approval is
for a specific, unchanged proposal — edit the card and the old approval is void.

## Adversarial review

The most dangerous output is the plausible-but-wrong one, because nothing flags it. So any
significant work product gets a fresh-context pass *prompted to refute it* before it's
queued. Defaulting the reviewer to "reject unless convinced" catches the leak a confirming
reviewer waves through. (In the author's deployment, a PR once carried 19 unrelated
internal files into a public repo; it was caught by luck. This step makes the catch
structural.)

## Durability and liveness — making silent death loud

Two distinct failures, two defenses:

- **Lost work.** A session dies after creating a durable file but before committing it.
  `orphan-audit.sh` finds untracked durable files so the next tick commits them.
- **Lost loop.** The machine sleeps or the loop dies, and the only thing that could tell
  you is the thing that's down. So the loop **pushes every tick**, and an **off-machine**
  GitHub Action reads the pushed tick log and alerts when it goes stale. Never monitor a
  service from the same machine that runs it.

## Empty ticks are good ticks

If there's nothing to do, the correct action is *nothing* — log "none" and sleep longer.
An agent that invents work to look busy is worse than one that's honest about an idle day.
Busy-ticking is an explicit anti-pattern.

## No self-modification

The loop never edits its own skill, envelope, or approval mechanics from inside a tick.
Those are changed only in an interactive session with the owner. An autonomous process
that can rewrite its own guardrails has no guardrails.

## Machine-local, model-agnostic state

State lives in `~/.heartbeat/`, outside `~/.claude/`, so dotfile syncs can't clobber it or
carry one machine's state to another — each deployment is isolated. And no model name
appears in the protocol or state: run the gate on the cheapest tier available, the act
step on the most capable, whatever those happen to be on the machine.
