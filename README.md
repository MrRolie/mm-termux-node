# TrendForce Alert Monitor

Monitor TrendForce economic indicators and receive Pushover notifications when significant changes are detected. Built with Python stdlib only for maximum portability (works great on Termux/Android).

## Features

- **Incremental monitoring**: Detects new datapoints automatically (mostly monthly indicators)
- **Smart alerts**: Calculates growth rate vs historical average and alerts when thresholds are exceeded
- **Configurable per indicator**: Set custom thresholds and lookback periods
- **Pushover notifications**: Get instant alerts on your devices
- **Stdlib-only**: No external dependencies, works anywhere Python runs
- **Resilient**: Automatic retries with exponential backoff, SSL handling

## Quick Start

### 1. Setup Pushover

1. Sign up at [pushover.net](https://pushover.net/)
2. Copy your **User Key** from the dashboard
3. Create an application to get an **API Token**

### 2. Create Environment File

Copy `.env.example` to `.env` and add your Pushover credentials:

```bash
cp .env.example .env
# Edit .env with your actual credentials
```

`.env` contents:

```
PUSHOVER_USER_KEY=your_user_key_here
PUSHOVER_API_TOKEN=your_api_token_here
```

### 3. Configure Indicators

Edit [config/industry_ids.yaml](config/industry_ids.yaml):

```yaml
# Indicator list
indicator_ids:
  - 6106  # Mainstream NAND Flash Wafer Spot Price
  # - 1234  # Add more as needed

# Default alert parameters
default_threshold: 10.0     # Alert when growth differs by >10 percentage points from average
default_n_periods: 3        # Compare against 3-period average

# Per-indicator overrides (optional)
# indicator_6106_threshold: 15.0
# indicator_6106_n_periods: 6

# Connection settings
concurrency: 4
timeout: 30
retries: 3
backoff_base: 1.5

# Paths
state_file: data/state.json
env_file: .env
```

### 4. First Run (Initialize State)

```bash
python3 scripts/fetch_trendforce.py --config config/industry_ids.yaml --dry-run --insecure
```

This creates `data/state.json` with historical data. No alerts are sent on first run.

## How It Works

### Absolute Growth Rate Difference Calculation

The script calculates the **absolute growth rate difference** `(r_t - r̄_n) × 100`, which measures how many percentage points the current growth rate differs from the historical average.

**Why absolute?** This prevents explosive values when the historical trend is flat or near-zero, ensuring stable and interpretable signals across all market regimes. Unlike relative ratios, absolute differences maintain consistent scale regardless of historical volatility.

**Formula:**

```
abs_diff = (r_t - r̄_n) × 100
```

Where:

- `r_t = log(P_t) - log(P_{t-1})` (current period's growth rate)
- `r̄_n = (1/n) × [log(P_{t-1}) - log(P_{t-n})]` (average growth rate over n periods)
- `P_t` = new value (current price)
- `P_{t-1}` = most recent historical price
- `P_{t-n}` = price from n periods ago
- `log` = natural logarithm

**Example** (indicator 6106 with `n_periods=3`, `threshold=10%`):

- P_t = $15.13 (Dec 2025, new value)
- P_{t-1} = $10.69 (Nov 2025)
- P_{t-3} = $4.11 (Sep 2025)
- Current growth: r_t = log(15.13) - log(10.69) = 0.348 (34.8%)
- Average past growth: r̄_3 = (1/3) × [log(10.69) - log(4.11)] = 0.293 (29.3%)
- **Absolute difference: (0.348 - 0.293) × 100 = 5.5 percentage points**
- No alert sent (5.5 < 10% threshold)
- Interpretation: "Current growth is 5.5 percentage points above the 3-period average"

### Custom Composite Signals

In addition to individual indicators, the system supports **custom composite signals** that combine multiple indicators to detect structural market imbalances. Four signal types are available:

#### 1. Growth Diff (`growth_diff`)
Calculates the difference between two indicators' growth rates. Use to detect divergences (e.g., spot price accelerating while capex decelerates).

```yaml
signal_dram_golden_cross_type: growth_diff
signal_dram_golden_cross_indicator_a: 6105  # DRAM Spot Price
signal_dram_golden_cross_indicator_b: 205   # DRAM Capex
signal_dram_golden_cross_threshold: 15.0    # Alert if diff > 15 percentage points
```

#### 2. Ratio (`ratio`)
Calculates the ratio of two indicators' current values. Use for direct comparisons (e.g., price-to-capex ratio).

```yaml
signal_example_ratio_type: ratio
signal_example_ratio_numerator: 6105
signal_example_ratio_denominator: 205
signal_example_ratio_threshold_min: 0.5
signal_example_ratio_threshold_max: 2.0
```

#### 3. Composite Average (`composite_avg`)
Calculates the simple average of multiple indicators' growth rates. Use for equal-weighted sector indices.

```yaml
signal_example_avg_type: composite_avg
signal_example_avg_indicators:
  - 199  # DRAM Revenue
  - 273  # NAND Revenue
signal_example_avg_threshold: 20.0
```

#### 4. Weighted Average (`weighted_avg`)
Calculates the weighted average of multiple indicators' growth rates. Use for custom-weighted sector indices.

```yaml
signal_memory_market_composite_type: weighted_avg
signal_memory_market_composite_indicators:
  - 199  # Global DRAM Revenue
  - 273  # Global NAND Revenue
signal_memory_market_composite_weights:
  - 0.6  # 60% DRAM
  - 0.4  # 40% NAND
signal_memory_market_composite_threshold: 20.0
signal_memory_market_composite_n_periods: 3
```

**All growth-based signals** (growth_diff, composite_avg, weighted_avg) use the same absolute difference calculation as individual indicators, ensuring consistent interpretation across the entire system.

### State Management

The script maintains `data/state.json` to track:

- Last seen datapoint per indicator
- Historical values for growth calculation (trimmed to prevent unbounded growth)

**No datasets are stored** - only the minimal state needed for change detection.

## Usage

### Normal Run

```bash
python3 scripts/fetch_trendforce.py --config config/industry_ids.yaml --insecure
```

### Dry-Run (Testing)

```bash
python3 scripts/fetch_trendforce.py --config config/industry_ids.yaml --dry-run --insecure
```

Performs all checks but skips sending Pushover notifications.

### Command-Line Options

```
--config CONFIG          Path to YAML config file (default: config/industry_ids.yaml)
--concurrency N          Max parallel workers (default: 4)
--timeout SECONDS        Request timeout (default: 30)
--retries N              Retry count (default: 3)
--backoff-base SECONDS   Exponential backoff base (default: 1.5)
--base-url URL           API base URL override
--insecure               Disable SSL verification (use for certificate issues)
--dry-run                Skip sending notifications (for testing)
```

## Deployment to Android/Termux

This project is designed to run on Android via Termux with automated deployment scripts.

📱 **[Detailed Setup](deploy/README.md)**

**Quick deployment:**

```bash
# 1. On phone: Install Termux, setup SSH, get IP address
# 2. On computer: Edit deploy/push.sh with phone's IP
./deploy/push.sh

# 3. SSH to phone and setup cron
ssh -p 8022 u0_a259@YOUR_PHONE_IP
cd ~/mm-termux-node
./deploy/setup_cron.sh
```

**Deployment tools:**

- `deploy/push.sh` - Deploy/sync files to phone
- `deploy/setup_cron.sh` - Setup automated scheduling on phone
- `deploy/view_logs.sh` - View logs remotely from computer

## Scheduling with Cron

### Termux (Android)

**Automated setup (recommended):**

After deploying to your phone, SSH in and run:

```bash
cd ~/mm-termux-node
./deploy/setup_cron.sh
```

**Manual setup:**

```bash
# Install cron
pkg install cronie termux-services
sv-enable crond

# Edit crontab
crontab -e
```

Example entry (runs daily at 02:05):

```cron
5 2 * * * cd /data/data/com.termux/files/home/mm-termux-node && python scripts/fetch_trendforce.py --config config/industry_ids.yaml --insecure >> logs/scraper.log 2>&1
```

View logs:

```bash
tail -f ~/mm-termux-node/logs/scraper.log
```

### Linux/macOS

```bash
crontab -e
```

Example entry:

```cron
5 2 * * * cd /path/to/mm-termux-node && python3 scripts/fetch_trendforce.py --config config/industry_ids.yaml >> logs/scraper.log 2>&1
```

## Testing

### Simulate New Datapoint

1. Edit `data/state.json`: set `last_check_date` to an older date
2. Run with `--dry-run` to see what would happen
3. Check logs for growth calculation and alert decision

### Verify Alert Message

Example notification when threshold exceeded:

```
Title: TrendForce Alert: Mainstream NAND Flash Wafer Spot Price

Body:
Mainstream NAND Flash Wafer Spot Price increased by 35.2% (threshold: 10.0%)

New value: 15.134 USD
Date: 2025-12-31
```

Example custom signal alert:

```
Title: TrendForce Signal: Memory Market Composite: -16.7%

Body:
Signal: memory_market_composite (weighted_avg)
Diff: -16.74%
Config: threshold: 20.0%

Dependencies:
  Global Branded DRAM Manufacturers' Revenue: Total (199): 27012.5941 Millions of USD
  Global Branded NAND Flash Manufacturers' Revenue: Total (273): 13162.8201 Millions of USD
```

## Troubleshooting

### SSL Certificate Errors

If you see `[SSL: CERTIFICATE_VERIFY_FAILED]`, use the `--insecure` flag:

```bash
python3 scripts/fetch_trendforce.py --config config/industry_ids.yaml --insecure
```

### Missing .env File

```
[ERROR] Failed to load environment: Environment file not found: .env
```

Create `.env` file with Pushover credentials (see step 2 above).

### State File Corrupted

If `state.json` is corrupted, simply delete it and run again to reinitialize:

```bash
rm data/state.json
python3 scripts/fetch_trendforce.py --config config/industry_ids.yaml --dry-run --insecure
```

## Technical Details

- **Language**: Python 3.7+ (stdlib only)
- **API**: TrendForce DataTrack FinWhale API
- **Notification**: Pushover API
- **State Storage**: JSON file (atomic writes for safety)
- **Architecture**: Parallel fetching with ThreadPoolExecutor

## License

See [LICENSE](LICENSE) file.
