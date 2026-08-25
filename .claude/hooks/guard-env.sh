#!/usr/bin/env bash
# PreToolUse (Write|Edit): ask for confirmation before editing a real .env file (protect secrets).
# .env.example is allowed freely. Reads the tool input JSON on stdin.
# No jq dependency (not installed in this environment) — extract file_path with sed.
input=$(cat)
f=$(printf '%s' "$input" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | tr '\\' '/')
b=${f##*/}
case "$b" in
  .env.example) : ;;
  .env | .env.*)
    printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"Editing a .env file (secrets). Confirm this is intended; .env.example is the template."}}'
    ;;
esac
