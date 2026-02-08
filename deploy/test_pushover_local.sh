#!/usr/bin/env bash
# Send a test Pushover notification from your local machine
# Reads PUSHOVER_USER_KEY and PUSHOVER_API_TOKEN from the project .env

set -euo pipefail

# Resolve project root (assumes script is in deploy/)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PROJECT_DIR}/.env"

if [ -f "${ENV_FILE}" ]; then
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
else
    echo "Error: .env not found at ${ENV_FILE}. Create it with PUSHOVER_USER_KEY and PUSHOVER_API_TOKEN."
    exit 1
fi

if [ -z "${PUSHOVER_USER_KEY:-}" ] || [ -z "${PUSHOVER_API_TOKEN:-}" ]; then
    echo "Error: PUSHOVER_USER_KEY and PUSHOVER_API_TOKEN must be set in ${ENV_FILE}"
    exit 1
fi

echo "Sending test notification to user ${PUSHOVER_USER_KEY}..."

if command -v curl >/dev/null 2>&1; then
    resp=$(curl -s -F "token=${PUSHOVER_API_TOKEN}" \
                -F "user=${PUSHOVER_USER_KEY}" \
                -F "title=TrendForce Test (local)" \
                -F "message=Local test message from mm-termux-node" \
                https://api.pushover.net/1/messages.json)
    echo "Response: ${resp}"
    if echo "${resp}" | grep -q '"status":1'; then
        echo "Success: notification delivered.";
        exit 0
    else
        echo "Failure: check response above and ensure device is online and Pushover app is logged in.";
        exit 2
    fi
elif command -v python >/dev/null 2>&1; then
    python - <<PY
import os, json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

token=os.environ.get('PUSHOVER_API_TOKEN')
user=os.environ.get('PUSHOVER_USER_KEY')
req = Request(
    "https://api.pushover.net/1/messages.json",
    data=urlencode({"token":token,"user":user,"title":"TrendForce Test (local)","message":"Local test message from mm-termux-node"}).encode(),
    method="POST"
)
req.add_header("Content-Type","application/x-www-form-urlencoded")
print(json.loads(urlopen(req, timeout=30).read().decode()))
PY
else
    echo "Error: neither 'curl' nor 'python' found. Install curl (e.g. apt/get/pkgs) or ensure python is available."
    exit 3
fi
