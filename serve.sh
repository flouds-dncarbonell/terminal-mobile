#!/usr/bin/env bash
set -euo pipefail
base_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$base_dir/.env" ]]; then
  set -a
  source "$base_dir/.env"
  set +a
fi
exec env -u TMUX "$base_dir/venv/bin/python" "$base_dir/mobile_server.py" "$@"
