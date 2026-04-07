#!/bin/bash
# entrypoint.sh
# Container entrypoint: initializes firewall as root, drops to claude user,
# then starts Claude Code with bypass permissions.
#
# SETTINGS PATH MODEL:
# - Project settings: /workspace/.claude/settings.json (from bind mount)
#   Contains permissions, hooks, agents, commands, skills
# - User state: /home/claude/.claude/ (from named Docker volume)
#   Contains auth tokens, session history, auto-memory
# Claude Code merges both at runtime. Project settings take precedence
# over user settings for permissions and hooks.

set -e

# Step 1: Initialize firewall (running as root — no sudo needed)
/usr/local/bin/init-firewall.sh

# Step 2: Ensure the claude user owns its home directory volumes
# The named Docker volumes may have been created by root on first run.
# Exclude read-only mounts (like the GCP service account key).
chown -R claude:claude /home/claude/.claude 2>/dev/null || true
chown -R claude:claude /home/claude/.local 2>/dev/null || true

# Step 3: Print banner and drop to non-root user
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Claude Code Sandbox                                    ║"
echo "║                                                         ║"
echo "║  Running as: claude                                     ║"
echo "║  Workspace:  /workspace                                 ║"
echo "║  Mode:       --dangerously-skip-permissions             ║"
echo "║                                                         ║"
echo "║  Network:    Allowlisted domains only (see firewall)    ║"
echo "║  Git push:   Blocked by bash-guard hook                 ║"
echo "║  Dev server: Run on host (port not forwarded)           ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Step 4: Drop privileges and exec Claude Code as the claude user.
# exec replaces this shell — no root process remains.
# All arguments are forwarded to Claude Code after --dangerously-skip-permissions.
exec runuser -u claude -- claude --dangerously-skip-permissions "$@"
