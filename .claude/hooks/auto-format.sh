#!/bin/bash
# .claude/hooks/auto-format.sh
# PostToolUse hook for Write/Edit/MultiEdit — runs Prettier on modified files.
# Receives JSON on stdin with tool_input containing file path.
# Exit 0 = success (non-blocking).
#
# npx prettier resolves both local (node_modules/.bin) and global installs.
# If Prettier isn't installed at all, npx will fail and we suppress the error.

INPUT=$(cat)

# Extract file path — different tools use different field names
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // empty')

if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
  exit 0
fi

# Only format file types Prettier handles
EXT="${FILE##*.}"
case "$EXT" in
  js|jsx|ts|tsx|json|css|scss|md|html|yml|yaml)
    # npx resolves Prettier from local node_modules or global install.
    # Suppress all output — this hook should be invisible when it works
    # and silent when it can't (e.g., Prettier not yet installed).
    npx prettier --write "$FILE" 2>/dev/null || true
    ;;
esac

exit 0
