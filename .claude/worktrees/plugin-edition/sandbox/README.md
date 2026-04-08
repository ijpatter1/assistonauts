# Claude Code Sandbox

Isolated Docker environment for running Claude Code with `--dangerously-skip-permissions` safely.

## Quick Start

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # add to ~/.zshrc for persistence
make sandbox                          # build + start
```

## Commands

| Command | Description |
|---------|-------------|
| `make build` | Build the sandbox Docker image |
| `make sandbox` | Start interactive Claude Code session |
| `make attach` | Reattach to a running sandbox (after crash/disconnect) |
| `make shell` | Start bash shell in sandbox (debugging) |
| `make prompt P="..."` | Run a headless prompt |
| `make resume S="name"` | Resume a named session |
| `make dev` | Run dev server on **host** (not in Docker) |
| `make stop` | Stop the running container |
| `make clean` | Remove container and image (preserves volumes) |
| `make clean-all` | Full reset — remove container, image, AND volumes |
| `make gcp-setup` | Print GCP service account setup instructions |
| `make test-fw` | Verify firewall blocks non-allowlisted traffic |

## How Settings Load

Claude Code loads configuration from two `.claude/` directories:

**Project settings** → `/workspace/.claude/` (bind-mounted from your project)
- `settings.json`, agents, commands, skills, hooks

**User state** → `/home/claude/.claude/` (Docker named volume)
- Auth tokens, session history, auto-memory

Claude Code merges both at runtime. Project settings take precedence. Use `make clean-all` for a full reset if stale user-level settings cause issues.

## Dev Server

The sandbox does not forward ports. Run the dev server on your host:

```bash
# Terminal 1: Claude Code in sandbox
make sandbox

# Terminal 2: Dev server on host
make dev
```

File changes from Claude Code appear instantly via bind mount. Hot reload works normally.

## Security Model

**Filesystem isolation:** Only `/workspace` (your project) is visible. No host home directory, SSH keys, or `.env` files.

**Network isolation:** iptables default-deny. Edit `init-firewall.sh` to add project-specific domains.

**Non-root execution.** Entrypoint runs as root for iptables only, then drops to `claude` user via `runuser`. No root process after startup.

**Git push blocked.** The bash-guard hook blocks all `git push`. Push from your host terminal after review.

## Adding Domains

Edit `sandbox/init-firewall.sh` → add domains to `PROJECT_DOMAINS` or uncomment `GCLOUD_DOMAINS`. Rebuild with `make build`.

## GCP Access

```bash
make gcp-setup    # prints full setup instructions
```

Places a service account key at `secrets/gcp-service-account.json` (gitignored). The Makefile auto-detects and mounts it read-only.

## Volumes

| Volume | Path | Contains |
|--------|------|----------|
| `claude-config` | `/home/claude/.claude` | Auth, session history |
| `claude-data` | `/home/claude/.local/share/claude` | Transcripts |

`make clean` keeps volumes. `make clean-all` removes them (re-authenticate after).
