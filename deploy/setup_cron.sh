#!/data/data/com.termux/files/usr/bin/bash
# Setup cron job on Termux for TrendForce Alert Monitor
# Run this script ON THE PHONE after deployment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== TrendForce Alert Monitor - Cron Setup ===${NC}"
echo ""

# Check if we're running in Termux
if [ ! -d "/data/data/com.termux" ]; then
    echo -e "${RED}Error: This script must be run in Termux on Android${NC}"
    exit 1
fi

# Get project directory (assume script is in deploy/ subdirectory)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "Project directory: ${PROJECT_DIR}"
echo ""

# Check if cronie is installed
if ! command -v crontab &> /dev/null; then
    echo -e "${YELLOW}Installing cronie...${NC}"
    pkg install cronie termux-services -y
    sv-enable crond
    echo -e "${GREEN}Cronie installed and enabled${NC}"
fi

# Create logs directory
mkdir -p "${PROJECT_DIR}/logs"

# Create cron job entry
CRON_ENTRY="5 2 * * * cd ${PROJECT_DIR} && python scripts/fetch_trendforce.py --config config/industry_ids.yaml --insecure >> logs/scraper.log 2>&1"

echo "Proposed cron entry:"
echo "  ${CRON_ENTRY}"
echo ""
echo "This will run daily at 02:05 AM"
echo ""

read -p "Add this cron job? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cron setup cancelled."
    exit 0
fi

# Add to crontab
(crontab -l 2>/dev/null || true; echo "${CRON_ENTRY}") | crontab -

echo ""
echo -e "${GREEN}Cron job added successfully!${NC}"
echo ""
echo "To verify:"
echo "  crontab -l"
echo ""
echo "To view logs:"
echo "  tail -f ${PROJECT_DIR}/logs/scraper.log"
echo ""
echo "To test the script manually:"
echo "  cd ${PROJECT_DIR}"
echo "  python scripts/fetch_trendforce.py --config config/industry_ids.yaml --dry-run --insecure"
echo ""
