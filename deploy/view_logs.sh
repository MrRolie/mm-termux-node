#!/bin/bash
# View logs from the phone remotely

# Configuration
PHONE_USER="${PHONE_USER:-u0_a259}"
PHONE_IP="${PHONE_IP:-192.168.1.100}"
PHONE_PORT="${PHONE_PORT:-8022}"
REMOTE_DIR="${REMOTE_DIR:-/data/data/com.termux/files/home/mm-termux-node}"
LOG_FILE="logs/scraper.log"

# Default to tail mode
MODE="${1:-tail}"
LINES="${2:-50}"

case $MODE in
    tail)
        echo "Following logs (Ctrl+C to exit)..."
        ssh -p ${PHONE_PORT} ${PHONE_USER}@${PHONE_IP} "tail -f ${REMOTE_DIR}/${LOG_FILE}"
        ;;
    last)
        echo "Last ${LINES} lines:"
        ssh -p ${PHONE_PORT} ${PHONE_USER}@${PHONE_IP} "tail -n ${LINES} ${REMOTE_DIR}/${LOG_FILE}"
        ;;
    all)
        echo "All logs:"
        ssh -p ${PHONE_PORT} ${PHONE_USER}@${PHONE_IP} "cat ${REMOTE_DIR}/${LOG_FILE}"
        ;;
    *)
        echo "Usage: $0 [tail|last|all] [lines]"
        echo ""
        echo "Examples:"
        echo "  $0 tail          # Follow logs in real-time"
        echo "  $0 last 100      # Show last 100 lines"
        echo "  $0 all           # Show all logs"
        exit 1
        ;;
esac
