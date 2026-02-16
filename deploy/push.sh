#!/bin/bash
# Deployment script for TrendForce Alert Monitor to Android/Termux

set -e

# Load configuration from .env file
if [ -f "$(dirname "$0")/../.env" ]; then
    source "$(dirname "$0")/../.env"
else
    echo "Error: .env file not found in project root"
    exit 1
fi

# Use environment variables with fallbacks
PHONE_USER="${PHONE_USER:-u0_a259}"
PHONE_IP="${PHONE_IP:-192.168.1.100}"
PHONE_PORT="${PHONE_PORT:-8022}"
REMOTE_DIR="${REMOTE_DIR:-/data/data/com.termux/files/home/mm-termux-node}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== TrendForce Alert Monitor - Deployment ===${NC}"
echo ""

# Check if required files exist
if [ ! -f "scripts/fetch_trendforce.py" ]; then
    echo -e "${RED}Error: scripts/fetch_trendforce.py not found${NC}"
    echo "Please run this script from the project root directory"
    exit 1
fi

# Display configuration
echo "Configuration:"
echo "  Phone IP:   ${PHONE_IP}"
echo "  SSH Port:   ${PHONE_PORT}"
echo "  Remote Dir: ${REMOTE_DIR}"
echo "  User:       ${PHONE_USER}"
echo ""

# Confirm before proceeding
read -p "Proceed with deployment? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled."
    exit 0
fi

echo -e "${YELLOW}Creating remote directories...${NC}"
ssh -p ${PHONE_PORT} ${PHONE_USER}@${PHONE_IP} "mkdir -p ${REMOTE_DIR}/{scripts,config,data,logs,mm_termux_node}"

echo -e "${YELLOW}Transferring scripts...${NC}"
scp -P ${PHONE_PORT} scripts/fetch_trendforce.py ${PHONE_USER}@${PHONE_IP}:${REMOTE_DIR}/scripts/

echo -e "${YELLOW}Transferring modules...${NC}"
scp -P ${PHONE_PORT} -r mm_termux_node ${PHONE_USER}@${PHONE_IP}:${REMOTE_DIR}/

echo -e "${YELLOW}Transferring config...${NC}"
scp -P ${PHONE_PORT} config/industry_ids.yaml ${PHONE_USER}@${PHONE_IP}:${REMOTE_DIR}/config/

echo -e "${YELLOW}Transferring deploy scripts...${NC}"
scp -P ${PHONE_PORT} deploy/setup_cron.sh deploy/view_logs.sh deploy/test_pushover.sh ${PHONE_USER}@${PHONE_IP}:${REMOTE_DIR}/deploy/

echo -e "${YELLOW}Transferring .env (if exists)...${NC}"
if [ -f ".env" ]; then
    scp -P ${PHONE_PORT} .env ${PHONE_USER}@${PHONE_IP}:${REMOTE_DIR}/
else
    echo -e "${YELLOW}Warning: .env file not found. Remember to create it on the phone.${NC}"
fi

echo -e "${YELLOW}Setting permissions...${NC}"
ssh -p ${PHONE_PORT} ${PHONE_USER}@${PHONE_IP} "chmod +x ${REMOTE_DIR}/scripts/fetch_trendforce.py ${REMOTE_DIR}/deploy/*.sh"

echo ""
echo -e "${GREEN}Deployment completed successfully!${NC}"
echo ""
echo "Next steps on your phone (via SSH):"
echo "  1. ssh -p ${PHONE_PORT} ${PHONE_USER}@${PHONE_IP}"
echo "  2. cd ${REMOTE_DIR}"
echo "  3. Edit .env with your Pushover credentials (if not already done)"
echo "  4. Test: python scripts/fetch_trendforce.py --config config/industry_ids.yaml --dry-run --insecure"
echo "  5. Test Pushover: ./deploy/test_pushover.sh"
echo "  6. Setup cron: ./deploy/setup_cron.sh"
echo "  7. View logs: ./deploy/view_logs.sh"
echo ""
