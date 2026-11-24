#!/usr/bin/env bash
set -euo pipefail
window_id="${1:-}"
[[ "$window_id" =~ ^@[0-9]+$ ]] || exit 2
tmux -L "${TERMINAL_MOBILE_SOCKET:-terminal-mobile}" list-windows -t agentes -F '#{window_id}' | grep -Fxq -- "$window_id" || exit 2
view="view-$$-$(openssl rand -hex 4)"
unset TMUX
tmux -L "${TERMINAL_MOBILE_SOCKET:-terminal-mobile}" new-session -d -t agentes -s "$view"
trap 'tmux -L "${TERMINAL_MOBILE_SOCKET:-terminal-mobile}" kill-session -t "$view" 2>/dev/null || true' EXIT
trap 'exit 0' HUP TERM INT
tmux -L "${TERMINAL_MOBILE_SOCKET:-terminal-mobile}" select-window -t "$view:$window_id"
tmux -L "${TERMINAL_MOBILE_SOCKET:-terminal-mobile}" set-option -t "$view" status off
tmux -L "${TERMINAL_MOBILE_SOCKET:-terminal-mobile}" attach-session -t "$view"
