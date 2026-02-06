# Deployment to Android/Termux

This directory contains scripts for deploying the TrendForce Alert Monitor to your Android phone running Termux.

## Prerequisites

### On Your Phone (Termux)

1. **Install Termux** from F-Droid (not Google Play)

2. **Install required packages:**
   ```bash
   pkg update
   pkg install python openssh
   ```

3. **Setup SSH server:**
   ```bash
   # Set a password for SSH
   passwd

   # Start SSH server
   sshd

   # SSH will run on port 8022 by default
   ```

4. **Find your phone's IP address:**
   ```bash
   ifconfig wlan0 | grep inet
   # Or use: ip addr show wlan0
   ```

### On Your Computer

1. **Update deployment configuration** in `deploy/push.sh`:
   ```bash
   export PHONE_IP="192.168.1.XXX"  # Your phone's IP
   export PHONE_PORT="8022"          # Termux SSH port (default)
   export PHONE_USER="u0_a259"       # Termux user (usually u0_a259)
   ```

## Deployment Steps

### 1. Initial Deployment

From your computer, run:

```bash
cd /path/to/mm-termux-node
chmod +x deploy/push.sh
./deploy/push.sh
```

This will:
- Create necessary directories on your phone
- Transfer scripts and configuration
- Set proper permissions

### 2. Setup Environment on Phone

SSH into your phone:

```bash
ssh -p 8022 u0_a259@YOUR_PHONE_IP
cd ~/mm-termux-node
```

Create `.env` file with your Pushover credentials:

```bash
cat > .env << 'EOF'
PUSHOVER_USER_KEY=your_actual_user_key
PUSHOVER_API_TOKEN=your_actual_api_token
EOF

chmod 600 .env
```

### 3. Test the Script

Run a dry-run test:

```bash
python scripts/fetch_trendforce.py --config config/industry_ids.yaml --dry-run --insecure
```

### 4. Setup Automated Scheduling

Run the cron setup script:

```bash
chmod +x deploy/setup_cron.sh
./deploy/setup_cron.sh
```

This will:
- Install cronie if needed
- Create a cron job to run daily at 02:05 AM
- Log output to `logs/scraper.log`

## Verification

### Check Cron Job

```bash
crontab -l
```

### View Logs

```bash
# Watch logs in real-time
tail -f ~/mm-termux-node/logs/scraper.log

# View recent logs
tail -n 50 ~/mm-termux-node/logs/scraper.log
```

### Manual Test Run

```bash
cd ~/mm-termux-node
python scripts/fetch_trendforce.py --config config/industry_ids.yaml --insecure >> logs/scraper.log 2>&1
```

## Updating After Changes

When you make changes to the code or configuration:

```bash
# From your computer
./deploy/push.sh
```

This will sync the latest files to your phone.

## Troubleshooting

### SSH Connection Issues

1. **Check phone's IP hasn't changed:**
   ```bash
   # On phone
   ifconfig wlan0 | grep inet
   ```

2. **Verify SSH is running:**
   ```bash
   # On phone
   sshd
   ```

3. **Test SSH connection:**
   ```bash
   # From computer
   ssh -p 8022 u0_a259@YOUR_PHONE_IP
   ```

### Script Errors

1. **Check Python version:**
   ```bash
   # On phone
   python --version  # Should be 3.7+
   ```

2. **Test script manually:**
   ```bash
   # On phone
   cd ~/mm-termux-node
   python scripts/fetch_trendforce.py --config config/industry_ids.yaml --dry-run --insecure
   ```

3. **Check logs:**
   ```bash
   # On phone
   tail -n 100 ~/mm-termux-node/logs/scraper.log
   ```

### Cron Not Running

1. **Verify cron service is running:**
   ```bash
   # On phone
   sv status crond
   ```

2. **Restart cron service:**
   ```bash
   # On phone
   sv restart crond
   ```

3. **Check crontab:**
   ```bash
   # On phone
   crontab -l
   ```

## File Structure on Phone

```
~/mm-termux-node/
├── scripts/
│   └── fetch_trendforce.py
├── config/
│   └── industry_ids.yaml
├── data/
│   └── state.json
├── logs/
│   └── scraper.log
├── deploy/
│   └── setup_cron.sh
└── .env
```

## Security Notes

- Keep your `.env` file secure (already chmod 600)
- The `.env` file is in `.gitignore` and won't be committed
- Consider using SSH keys instead of password authentication
- Your phone's IP may change if on DHCP - consider setting a static IP or using a hostname

## Environment Variables

You can override deployment settings:

```bash
# Custom settings
export PHONE_IP="192.168.1.150"
export PHONE_PORT="8022"
export PHONE_USER="u0_a259"
export REMOTE_DIR="/data/data/com.termux/files/home/custom-path"

# Then deploy
./deploy/push.sh
```
