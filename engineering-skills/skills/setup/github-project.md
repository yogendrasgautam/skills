# GitHub Project (v2) mapping — reference

How to add issues to a GitHub **Project** and set their fields. A Project (v2) is a board/table owned
by a **user or org**, separate from the repo's Issues. This is the detail behind the
`## GitHub Project mapping` section of `issue-tracker-github.md`.

## Prerequisite: token scope

`gh project ...` requires the `project` scope (or `read:project` for read-only). The default `gh`
login usually does **not** include it. Check:

```bash
gh auth status
```

If `project`/`read:project` is missing, the user runs this in their own terminal — it's an
interactive login the skill cannot perform:

```bash
gh auth refresh -s project        # read + write
# or: gh auth refresh -s read:project   # read only
```

## OWNER and NUMBER

- **NUMBER** is the number in the project URL:
  `https://github.com/orgs/<org>/projects/NUMBER` (org project) or
  `https://github.com/users/<user>/projects/NUMBER` (personal project).
- **OWNER** is the **org login** for an org project, or the **user login** for a personal project.
  Using the wrong owner kind returns "project not found" — a personal project can't be queried with an
  org owner and vice-versa.

## Discovery (run once; record the ids)

`item-edit` addresses fields and options by **node id**, not by name — so capture the ids once and
store them in `docs/agents/issue-tracker.md`.

```bash
# Project node id (PVT_...), title, number
gh project view NUMBER --owner OWNER --format json --jq '{id,title,number}'

# Every field with its id and type; single-selects (like Status) also list their option ids
gh project field-list NUMBER --owner OWNER --format json \
  --jq '.fields[] | {name, id, type, options: (.options // [] | map({name,id}))}'
```

Field ids look like `PVTF_...` (plain fields) or `PVTSSF_...` (single-select). Option ids are short
opaque strings under each single-select field.

## Add an issue and set its fields

```bash
# Add the issue (by URL or number) to the project; returns the item id.
ITEM_ID=$(gh project item-add NUMBER --owner OWNER --url <ISSUE_URL> --format json --jq '.id')

# Set a single-select field (e.g. Status = Todo)
gh project item-edit --id "$ITEM_ID" --project-id <PROJECT_NODE_ID> \
  --field-id <STATUS_FIELD_ID> --single-select-option-id <TODO_OPTION_ID>
```

`item-edit` needs **three** ids — `--id` (the item), `--project-id` (the `PVT_...` node id), and
`--field-id` — plus the value flag for the field's type:

| Field type          | Value flag                         |
| ------------------- | ---------------------------------- |
| Single-select       | `--single-select-option-id <id>`   |
| Text                | `--text "..."`                     |
| Number              | `--number 3`                       |
| Date                | `--date 2026-09-07`                |
| Iteration           | `--iteration-id <id>`              |
| Clear any field     | `--clear`                          |

## Useful reads

```bash
# List items already on the board (with their field values)
gh project item-list NUMBER --owner OWNER --format json
```

## Gotchas

- **Names won't work** with `item-edit` — that's the whole reason discovery exists. If option names
  change but ids don't, no update needed; if the Project is recreated, re-run discovery (ids change).
- **User vs org owner** — see above; the most common cause of "project not found".
- **Scope** — a missing `project` scope fails every command with a clear scope error; refresh and
  retry.
