# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the actual
label strings used in this repo's issue tracker.

| Canonical role    | Label in our tracker | Meaning                                  |
| ----------------- | -------------------- | ---------------------------------------- |
| `needs-triage`    | `needs-triage`       | Maintainer needs to evaluate this issue  |
| `needs-info`      | `needs-info`         | Waiting on reporter for more information |
| `ready-for-agent` | `ready-for-agent`    | Fully specified, ready for an AFK agent  |
| `ready-for-human` | `ready-for-human`    | Requires human implementation            |
| `wontfix`         | `wontfix`            | Will not be actioned                     |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding label
string from this table.

Edit the right-hand column to match whatever vocabulary you actually use.

## Triage state → GitHub Project Status (optional)

If issues are mapped onto a GitHub Project (see `issue-tracker.md`), triage can also move the Project's
Status field when a state changes. Fill this in only if you want that behavior:

| Canonical role    | Project Status option |
| ----------------- | --------------------- |
| `needs-triage`    | _(e.g. Todo)_         |
| `ready-for-agent` | _(e.g. In Progress)_  |
| `ready-for-human` | _(e.g. In Progress)_  |
| `wontfix`         | _(e.g. Done)_         |

Leave this table out entirely if you don't use a Project.
