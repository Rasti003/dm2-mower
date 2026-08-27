#!/bin/sh
set -eu

PORTAL_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VENV_DIR=${MOWBI_PORTAL_VENV:-"$HOME/.venvs/mowbi-portal"}
CONFIG_DIR=${MOWBI_CONFIG_DIR:-"$HOME/.config/mowbi"}
DATA_DIR=${MOWBI_DATA_DIR:-"$HOME/.local/share/mowbi"}
CACHE_DIR="$HOME/.cache/pyocd"
SERVICE_DIR="$HOME/.config/systemd/user"
ENV_FILE="$CONFIG_DIR/portal.env"

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r "$PORTAL_DIR/requirements.txt"

mkdir -p "$CONFIG_DIR" "$DATA_DIR" "$CACHE_DIR" "$SERVICE_DIR"
chmod 700 "$CONFIG_DIR" "$DATA_DIR"

if [ ! -f "$ENV_FILE" ]; then
  TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')
  umask 077
  {
    printf 'MOWBI_ACCESS_TOKEN=%s\n' "$TOKEN"
    printf 'MOWBI_DATA_DIR=%s\n' "$DATA_DIR"
    printf 'MOWBI_CONFIG_PATH=%s\n' "$CONFIG_DIR/portal.json"
    printf 'MOWBI_PYOCD=%s\n' "$HOME/.venvs/mowbi-tools/bin/pyocd"
  } > "$ENV_FILE"
  printf 'MOWBI_PORTAL_TOKEN=%s\n' "$TOKEN"
fi

cp "$PORTAL_DIR/systemd/mowbi-portal.service" "$SERVICE_DIR/mowbi-portal.service"
systemctl --user daemon-reload
systemctl --user enable --now mowbi-portal.service
printf 'MOWBI_PORTAL_URL=http://%s:8080/\n' "$(hostname -I | awk '{print $1}')"
