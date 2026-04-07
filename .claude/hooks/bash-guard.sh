#!/bin/bash
# .claude/hooks/bash-guard.sh
# PreToolUse hook for Bash commands — blocks dangerous patterns.
# Receives JSON on stdin with tool_input.command.
# Exit 0 = allow, JSON stdout with deny = block.
#
# SECURITY MODEL:
# This hook is one layer of a defense-in-depth strategy:
#   1. settings.json permissions — first gate, auto-allow safe commands
#   2. This hook — deterministic enforcement, blocks dangerous patterns
#   3. Docker sandbox firewall — network-level isolation (when using sandbox)
#
# This hook should be safe to use WITH OR WITHOUT the Docker sandbox.
# When running outside Docker (e.g., native Claude Code with built-in sandbox),
# this hook provides the primary enforcement for patterns like git push and
# destructive gcloud commands that the Docker firewall would otherwise catch.

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

if [ -z "$COMMAND" ]; then
  exit 0
fi

# Dangerous patterns to block
BLOCKED_PATTERNS=(
  # Destructive filesystem operations
  'rm\s+-rf\s+/'                    # rm -rf from root
  'rm\s+-rf\s+~'                    # rm -rf home directory
  'rm\s+-rf\s+\.'                   # rm -rf current/parent directory
  'mkfs\.'                          # format filesystem
  'dd\s+if='                        # raw disk write
  'chmod\s+-R\s+777\s+/'            # open permissions from root
  '>\s*/dev/sd[a-z]'                # write to raw disk

  # Git push — all forms blocked. Push from host terminal after review.
  'git\s+push'                      # any git push (including safe ones)
  'git\s+reset\s+--hard\s+origin'   # hard reset to remote

  # Package publishing
  'npm\s+publish'                   # publish to npm
  'npx\s+npm\s+publish'             # publish via npx

  # Pipe-to-shell (remote code execution)
  'curl.*\|\s*(ba)?sh'              # pipe curl to shell
  'wget.*\|\s*(ba)?sh'              # pipe wget to shell

  # GCP destructive operations
  'gcloud\s+.*\s+delete'            # any gcloud delete
  'gcloud\s+projects\s+delete'      # delete GCP project
  'gcloud\s+run\s+services\s+delete' # delete Cloud Run service
  'gcloud\s+pubsub\s+topics\s+delete' # delete Pub/Sub topic
  'gcloud\s+pubsub\s+subscriptions\s+delete' # delete Pub/Sub subscription
  'gcloud\s+sql\s+instances\s+delete' # delete Cloud SQL instance
  'gcloud\s+compute\s+instances\s+delete' # delete Compute Engine instance
  'bq\s+rm'                         # delete BigQuery resource
  'bq\s+.*--delete'                 # BigQuery delete flag
)

for pattern in "${BLOCKED_PATTERNS[@]}"; do
  if echo "$COMMAND" | grep -qEi "$pattern"; then
    jq -n \
      --arg reason "Blocked by bash-guard: pattern '$pattern' matched in command: $COMMAND" \
      '{
        hookSpecificOutput: {
          hookEventName: "PreToolUse",
          permissionDecision: "deny",
          permissionDecisionReason: $reason
        }
      }'
    exit 0
  fi
done

# Command is safe — allow
exit 0
