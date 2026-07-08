# Telemetry

**Off by default, per project.** Nothing is recorded until you run `anchor
telemetry enable`. See [`PRIVACY.md`](../PRIVACY.md) for the full data
policy — what's collected, what never is, retention, and how to opt out.

## Enabling

```bash
anchor telemetry enable .
```

Interactively asks for a sync mode:

- **Manual** (default) — nothing is ever sent until you run `anchor
  telemetry sync` yourself.
- **Auto, every N hours** / **Auto, every N events** — background sync
  after ordinary commands, but only after you separately confirm this
  specific choice at setup time. Manual mode never asks for this
  confirmation because it never sends anything unattended.

Non-interactive (e.g. for scripts/CI):

```bash
anchor telemetry enable . --mode auto_count --yes
```

## Checking what's queued

```bash
anchor telemetry pending .
#   Telemetry enabled: Yes
#   Queued events: 47
#   Last sync: 2.3 day(s) ago
#   Estimated upload: 18421 bytes

anchor telemetry status .
#   Telemetry: ENABLED
#     Events recorded locally: 52
#     Events pending sync:     47
#     Sync mode:               manual
#     Config:                  .anchor/telemetry_config.json
```

## Seeing the exact payload before anything sends

```bash
anchor telemetry sync . --dry-run
```

Prints the full JSON body a real sync would POST — nothing leaves the
machine. This is the "trust me" verification step: what you see here is
exactly what gets sent, because `sync` (without `--dry-run`) builds the
identical payload and just adds the network call.

## Sending

```bash
anchor telemetry sync .              # asks to confirm first
anchor telemetry sync . --yes        # skips the confirmation
anchor telemetry sync . --endpoint https://your-own-collector/upload
```

A sync only ever includes events this project hasn't already sent — every
event is marked as synced on success, so re-running `sync` doesn't resend
history. In an auto-sync mode, this same `sync` path (with the same
confirmation-free send, since you already confirmed once at setup) runs
automatically after ordinary commands once the configured threshold is
met; it prints a one-line notice when it actually sends something and is
silent otherwise.

## Exporting everything, synced or not

```bash
anchor telemetry export . --out my_usage.json
```

## Data shape

Collected, when enabled — metadata only:

```json
{
  "agent": "gemini-2.0-flash",
  "path": "2497954a",
  "language": "py",
  "invariant_violations": [],
  "structural_drift": [],
  "io_contracts_checked": 3,
  "io_contracts_failed": 1
}
```

Note `path` is a one-way hash, not the real filename — see PRIVACY.md for
exactly which keys are hashed vs. dropped entirely.

## Disabling

```bash
anchor telemetry disable .
```
