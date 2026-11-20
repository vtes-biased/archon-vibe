---
name: watch-check
description: Read WATCH.md and check every item's trigger — dated checks, recurring checks and externally-gated asks — then send each fired one through /intake as a board line and leave the rest. Use when asked to check the watch list, see whether anything waiting has become actionable, or run the watch check; also before /upkeep and after a production release.
---

# Watch check

`WATCH.md` holds the work that waits. This pass asks each item one question: **has
it fired?** It writes nothing to the board itself; a fired item goes through
`/intake` like any other ask.

```sh
cat WATCH.md
```

## 1. Check every item

Run each item's **Check**, and only that. Some are yours to run: a date, a re-run
of an audit script, a curl, a changelog, a `gh issue list`. Others are the owner's
alone — a production command, the owner's mail, an answer from the VEKN admins or
the Rules Director. Hand those over as one question each, grouped in one message.
Never guess an outside party's answer.

The verdict on each item is one of three:

- **fired** — the trigger is observably met;
- **not yet** — it is observably not met; do what the item's **Not yet** says,
  or nothing;
- **unknown** — the check could not be run. Say which, and why.

An item whose trigger fired long ago and whose ask turns out already done is a
deletion, not an intake.

## 2. Act on the fired ones

For each fired item, run `/intake` with its **Fired** text as the ask and its
evidence links as context. A dated or one-off item is deleted from `WATCH.md` in
the same change that adds its board line. A recurring item stays and its **When**
moves to the next date.

The owner accepts or declines each intake. A declined one is a drop: delete the
item, and if a feedback issue was waiting on it, it needs a reply.

## 3. Report

One line per item that is no longer **not yet**: fired and sent through `/intake`,
deleted as already done, or unknown pending the owner's answer. Keep it short.
"Nothing fired" is a complete report.
