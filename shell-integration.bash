# Source this file to route desktop CLI calls through the mobile panel.
TERMINAL_MOBILE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export TERMINAL_MOBILE_DIR
codex() { "$TERMINAL_MOBILE_DIR/venv/bin/python" "$TERMINAL_MOBILE_DIR/route_cli.py" codex "$@"; }
claude() { "$TERMINAL_MOBILE_DIR/venv/bin/python" "$TERMINAL_MOBILE_DIR/route_cli.py" claude "$@"; }
