# Anchor Protocol Rules — read this before editing any file in this project

Anchor Protocol is installed and governs all AI-assisted edits here. Do not
write to any file directly. Every change goes through Anchor's mediated
workflow below.

## Before touching anything

```
anchor status .
anchor report .
```

If `anchor report .` shows a drift score above 0 or lists top risk nodes,
treat those files as higher risk and check blast radius before editing them.

## Before editing a specific symbol/function

```
anchor blast-radius . --symbol <name>
anchor simulate . --symbol <name>
```

If risk is HIGH or CRITICAL, propose the change but do not execute it —
flag it for human review instead.

## Making the change

You do not have direct file-write access. Submit changes as:

```
anchor propose . --file <path> --old-file <tmp_old> --new-file <tmp_new> \
  --reason "<why>" --actor gemini-2.0-flash --confidence <0.0-1.0>
```

This returns a ticket id. Confidence should reflect genuine uncertainty —
if you are guessing at behavior you can't verify, use a low number (< 0.6),
not 1.0 by default.

Only after the proposal is reviewed:

```
anchor execute . --ticket <ticket_id>
```

## Recording why

If the change reflects a non-obvious judgment call, record it:

```
anchor decision record . --actor gemini-2.0-flash --reason "<reasoning>" \
  --confidence <0.0-1.0> --symbol <name> --evidence "<file:line>" \
  --consequences "<what this affects>"
```

If the change relies on something that isn't guaranteed by the code itself
(e.g. "assumes only one payment provider exists"), declare it instead of
leaving it implicit:

```
anchor assumption add . --text "<the assumption>" --symbol <name>
```

## After the change

```
anchor report .
anchor invariant check . --file <path>
```

Explain any invariant violations before considering the task done. Do not
silently ignore them.

## Never

- Never write a file directly, bypassing `anchor propose`/`anchor execute`.
- Never claim confidence 1.0 for a change you have not actually verified
  (e.g. by running tests).
- Never remove or weaken a declared invariant to make a proposal pass —
  flag the conflict instead.
