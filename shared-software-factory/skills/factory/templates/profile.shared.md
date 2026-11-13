# Repo profile
# Committed as .factory/profile.md and shared by every developer: no absolute paths.
# The orchestrator resolves the skills directory at run time and passes it to agents.
repo: <owner/name>
stack: <language/framework, or "undecided" if no app code yet>
install: <cmd or none>
test: <cmd, or "undecided">
lint: <cmd or none>
has_ui: <yes|no|undecided>
max_parallel: 3
conventions: <bullets: layout, naming, test style, standards docs found>
# UX testing (only when has_ui: yes; otherwise all "none"). Relative paths and commands only.
ui_globs: <git pathspec globs that are UI, comma-separated, e.g. src/**/*.tsx, **/*.css, public/**>
ui_global: <files whose change can affect every screen, e.g. package.json, vite.config.*, src/index.css>
dev_start: <cmd run in the worktree root to serve the app, e.g. npm run dev -- --port 5173 --strictPort>
dev_stop: <cmd or none>
dev_url: <base URL, e.g. http://localhost:5173>
dev_ready: <URL that answers when the app is up, default dev_url>
dev_port: <port>
dev_env: <VAR=value ... or none; non-secret only>
ux_login: <steps to sign in using env var NAMES for credentials, or none>
