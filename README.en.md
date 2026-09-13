# dash — Project Progress Dashboard (Claude Code Plugin)

English | [中文](README.md)

dash is a lightweight project DAG dashboard for Claude Code: session-native (hooks record PostToolUse/Stop/SubagentStop events into `.dash/state.jsonl`) plus a zero-config git snapshot — works out of the box in any git repository, no configuration file required. When a repo contains a `.superpowers/sdd/*/dag.json` ledger (the superpowers SDD convention), dash automatically picks it up as a deep-semantics adapter (waves / lanes / barriers / stall detection). No daemon: every invocation renders on demand and exits; state lives only in the repo's `.dash/` directory and the authoritative data sources themselves.

## Quick Start

From this repository's root:

```bash
claude --plugin-dir /path/to/claude-dash
```

The `/dash` skill and event hooks take effect immediately. Render on demand any time:

```bash
python3 scripts/dash render panel        # terminal panel
python3 scripts/dash render graph        # character-cell DAG (real nodes + edges)
python3 scripts/dash render html --open  # browser mermaid graph snapshot
python3 scripts/dash oneline             # one-line summary (statusline)
```

## Install

| Form | How | What you get |
|---|---|---|
| Marketplace install | `claude plugin marketplace add cty12356541/claude-dash`, then `claude plugin install dash@claude-dash` | Everything, persisted across all sessions |
| Plugin dir | `claude --plugin-dir /path/to/claude-dash` | Full components: skill + hooks + CLI (`${CLAUDE_PLUGIN_ROOT}` available) |
| Repo-level copy | Copy this whole repo into the target repo as `.claude/skills/dash/` (keep `.claude-plugin/plugin.json`, preserving the plugin root) | Skill + CLI travel with the repo; hooks do not register under `.claude/skills/` → no session event layer (git + SDD snapshots only); call by repo path, e.g. `python3 .claude/skills/dash/scripts/dash render panel` |

## Statusline (manual)

The main statusLine belongs to user/project settings and cannot ship with a plugin (only `subagentStatusLine` can). To use the one-line summary as your status bar, add to `~/.claude/settings.json` (or the project's `.claude/settings.json`):

```json
{"statusLine": {"type": "command", "command": "python3 /abs/path/to/claude-dash/scripts/dash oneline 2>/dev/null || true", "refreshInterval": 30}}
```

`oneline` is ANSI-free with zero side effects; `2>/dev/null || true` keeps any failure from polluting the status bar.

## The `.dash/` runtime directory

Session events (`state.jsonl`), focus (`focus.json`) and config (`config.json`) live under `.dash/` at the repo root — session-local runtime. Gitignore it with the two-line form (a bare `.dash/` ignore stops git from descending, so `!` exceptions never apply; `/*` ignores only the contents, letting exceptions back in):

```
.dash/*
!.dash/config.json
```

`config.json` is the only human-edited file and may be committed for team sharing with the form above; omit the second line if you don't share.

## Configuration

`.dash/config.json` (optional — defaults apply if absent):

```json
{"stalled_threshold_h": 2.0}
```

- `stalled_threshold_h`: hours of inactivity before a task is flagged ⚑ (default `2.0`). A missing/corrupt/invalid config degrades to defaults with a panel warning — never throws.
- ⚑ detection is approximate: for SDD-sourced tasks `since` is the mtime of that wave's `progress.md` ("ledger silent beyond the threshold → ⚑"); session-sourced tasks use first-seen event time.

## tmux integration: `DASH_TMUX_TARGET`

`dash watch`'s ⏎ (send-to-conversation) and `dash send` deliver a "focus brief" prompt into your main conversation pane via tmux `send-keys`. Target resolution: `DASH_TMUX_TARGET` env var → default `dash:0.0`; without tmux or if the pane is missing, it degrades to copyable text — never fails.

```bash
export DASH_TMUX_TARGET="mysession:0.0"   # point at your main conversation pane
python3 scripts/dash watch 5  # f focus · c unfocus · ⏎ send · g toggle graph/panel · q quit
# In graph view, left-click a node = focus that task and send the brief into the conversation (requires SGR mouse support)
```

## Commands

| Command | What it does |
|---|---|
| `dash render panel` | Terminal panel (ANSI, respects focus) |
| `dash render graph` | Character-cell DAG: topological layering + box-drawing edges; press `g` inside `watch` to toggle |
| `dash render html [--open]` | HTML snapshot (mermaid.js CDN graph embedded); `--open` writes `.dash/snapshot.html` and opens the browser — `DASH_NO_OPEN=1` writes only |
| `dash render mermaid [--inject]` | Mermaid source; `--inject` writes it back into the newest `.superpowers/sdd/*/progress.md` (the only explicit write side effect, gated behind `--inject`) |
| `dash oneline` | Statusline one-liner (ANSI-free, zero side effects) |
| `dash watch [interval] [--once]` | Live refresh (default 5s); keys f/c/⏎/g/q plus click-a-node-to-conversation in graph view; `--once` renders one frame and exits |
| `dash focus <task id>` / `dash focus clear` | Set / clear panel focus (takes effect on next refresh; unmatched ids degrade gracefully to a focus header) |
| `dash send [--pane <target>]` | Send the focus brief into the main conversation (tmux send-keys; `--pane` overrides `DASH_TMUX_TARGET`; exits 1 with no focus) |

Bare `dash` prints usage and exits 2.

## Platform support

| Platform | Status |
|---|---|
| macOS | Full (panel/graph/html/oneline/watch with all interactions incl. click-to-conversation) |
| Linux | Rendering and watch fully work; `--open` falls back to `xdg-open` |
| Windows | Render commands (panel/graph/html/oneline/statusline) work; tmux integration (⏎/click send) unavailable — degrades to copyable text |

The HTML snapshot's DAG graph loads mermaid.js from the jsdelivr CDN; offline/intranet environments show the mermaid source in that section (other sections unaffected).

## License

[MIT](LICENSE) © 2026 cty12356541
