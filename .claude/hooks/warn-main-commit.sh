#!/usr/bin/env bash
# PreToolUse (Bash, only for `git commit`): a gentle, non-blocking reminder when committing on main.
# main is release-only; feature work belongs on development or a feature branch.
br=$(git branch --show-current 2>/dev/null)
if [ "$br" = "main" ]; then
  printf '%s' '{"systemMessage":"Heads up: you are on main (release-only). Feature work belongs on development or a feature branch."}'
fi
