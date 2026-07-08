# Privacy Policy — Anchor Protocol Telemetry

Anchor Protocol's telemetry is local-first and opt-in. This document
describes exactly what is collected, what never is, how to see it, and how
to turn it off. It governs the telemetry feature specifically; the software
itself is licensed under MIT, unrelated to this policy.

## Off by default

Telemetry records nothing until you run `anchor telemetry enable` in a
given project, and it is a per-project setting — enabling it in one
project does not enable it anywhere else. Even once enabled, in the
default **manual** sync mode nothing is ever transmitted anywhere until you
explicitly run `anchor telemetry sync`.

If you choose an automatic sync mode (`auto_time` or `auto_count`) during
`anchor telemetry enable`, you are asked to separately confirm that specific
choice before it takes effect. You can always check what auto-sync would do
next, or turn it off, with `anchor telemetry status` / `anchor telemetry
disable`.

## What we collect

When telemetry is enabled, an event is recorded locally (in your project's
own `.anchor/anchor.db`, on your machine) for actions like proposing or
executing an edit. Each event is metadata about *what happened*, for
example:

- which agent/provider was used (e.g. `gemini-2.0-flash`)
- the operation type (e.g. `edit_executed`)
- a file's language/extension (e.g. `py`)
- contract/invariant check counts and pass/fail status
- whether structural drift was detected
- an anonymous, randomly-generated installation ID (not tied to your name,
  email, or account — there is no account)

## What we never collect

Regardless of configuration, the following are stripped before an event is
even written to the local database, let alone sent anywhere: source code or
file contents, secrets/passwords/API keys/tokens/credentials, and
environment variables. File paths are not stored in readable form either —
where a path would otherwise appear (e.g. to correlate "this file keeps
drifting"), it is one-way hashed first, so the actual filename or directory
structure of your project is never recorded.

We also never collect your IP address, username, or machine identifiers
beyond the random installation ID above.

## Why we collect it

Telemetry is anonymous and is intended to improve Anchor's detection
quality, compatibility, and reliability — for example, understanding which
drift types are common in practice, or which providers are actually used,
so effort goes where it matters instead of where we guess it matters.

## Inspecting or exporting what's stored

- `anchor telemetry status <path>` — enabled/disabled, event counts, sync mode.
- `anchor telemetry pending <path>` — what's queued for the next sync,
  and its approximate size.
- `anchor telemetry sync <path> --dry-run` — prints the exact JSON payload
  a real sync would send, without sending anything.
- `anchor telemetry export <path> --out file.json` — writes everything
  recorded (synced or not) to a plain JSON file you control.

## Where it goes

There is currently no cloud endpoint this data is sent to by default in
released versions prior to this telemetry build; as of this version, a
sync (manual or auto, always something you've explicitly enabled) sends to
Anchor's own collection endpoint at `auth.atrivix.com`, or to an
endpoint you explicitly override. The server scrubs incoming payloads
again, independently of the client-side scrub described above, and never
trusts the client to have done it correctly.

## Data retention

Data is kept for a limited period to analyze trends (aggregate reliability
and compatibility patterns), then deleted. We are not yet at the scale
where a fixed retention window and a formal deletion-request workflow are
load-bearing; both will be published here with specific numbers once real
usage exists to base them on.

## Opting out

`anchor telemetry disable <path>` at any time, per project. This is also
the default for every new project — you have to opt in, not out.

## Contact

For questions, or to request deletion of data associated with a specific
installation ID, open an issue in this repository. `setup.py` does not
currently list a contact email — add one here (and there) if you want
deletion requests to go somewhere other than GitHub.
