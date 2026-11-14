# Task reservations

This folder is how a contributor **claims a roadmap task so nobody else takes it**.
Each reservation is one file: `reservations/<TASK-ID>.json`. The task ids are the ones
on the dashboard **Contribute → Roadmap & TODOs** tab (and in [`CONTRIBUTING.md`](../CONTRIBUTING.md)),
e.g. `PENT-02`, `OS-11`, `FW-16`, Cleanup Lab `CLN-04`, or Source Lab bonus `SRC-B01`.

The dashboard reads every file here at build time and shows each task as
**Available**, **Reserved**, **PR open** or **Done**. One file per task means two people
reserving at once never conflict in git.

## Reserve a task (by PR)

The easy way: on the Contribute page, open the task card and click **Reserve via PR**.
That opens GitHub's new-file editor with the file pre-filled; fill in your name and GitHub
username, and "Propose new file" — GitHub forks the repo and opens the PR for you.

By hand:

1. Fork os-lab and create `reservations/<TASK-ID>.json` from the template below.
2. Open a PR titled `reserve: <TASK-ID>`.
3. When it is merged, the task shows as reserved to everyone.

```json
{
  "id": "PENT-02",
  "name": "Your Name · (student no if any)",
  "github": "your-username",
  "status": "reserved",
  "pr": "",
  "date": "2026-11-09"
}
```

Full field list: [`_schema.json`](_schema.json). Files whose name starts with `_` are ignored.

## Keep it current

- Started working? Set `"status": "in-progress"`.
- Opened your implementation PR? Set `"status": "pr-open"` and put the URL in `"pr"`.
- Merged? Set `"status": "done"`.
- Changed your mind? Set `"status": "released"` (or delete the file) so someone else can take it.

A reservation is a courtesy lock, not ownership: a reservation with no progress for a long time
may be released by a maintainer.

## Students (midterm)

If this is your **MYO062 / BGT207 / MYO203 midterm** reservation (or a **MYO063** Cleanup Lab bonus task), add `"course"` and, when several
exam options map to the same task id, put your option number in `"note"`
(e.g. `"note": "MYO062 vize seçenek 17"`). See the course's `vize/vize-projesi.md` for the options
and the PR acceptance gate (verification + proof video required).
