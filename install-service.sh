#!/usr/bin/env bash
set -euo pipefail
base_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
service_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$service_dir"
cat > "$service_dir/terminal-mobile.service" <<EOF
[Unit]
Description=Terminal Mobile
After=network-online.target
[Service]
Type=simple
WorkingDirectory="$base_dir"
Environment="PATH=$PATH"
ExecStart="$base_dir/serve.sh"
Restart=on-failure
RestartSec=3
KillMode=process
[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now terminal-mobile.service
