#!/usr/bin/env python3
"""Debug script to fetch and manually verify memory_market_composite signal."""

import json
import math
import sys
from urllib.request import Request, urlopen

BASE_URL = "https://datatrack-finwhale.trendforce.com:8000/api/v1"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

def fetch_indicator(indicator_id):
    """Fetch indicator data from API."""
    url = f"{BASE_URL}/data/column?fields={indicator_id}"
    request = Request(url, headers=HEADERS)
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        print(f"ERROR fetching {indicator_id}: {e}")
        return None

def calculate_growth(new_value, history, n_periods):
    """Calculate absolute growth rate difference (percentage points)."""
    if len(history) < n_periods:
        print(f"  Insufficient history: need {n_periods}, have {len(history)}")
        return None

    P_t = float(new_value)
    P_t_minus_1 = float(history[-1]["value"])
    P_t_minus_n = float(history[-n_periods]["value"])

    if P_t <= 0 or P_t_minus_1 <= 0 or P_t_minus_n <= 0:
        print(f"  Invalid values (≤0): P_t={P_t}, P_t-1={P_t_minus_1}, P_t-n={P_t_minus_n}")
        return None

    # Current period's growth rate (log-return)
    r_t = math.log(P_t) - math.log(P_t_minus_1)
    
    # Average historical growth rate (log-return)
    r_bar_n = (1 / n_periods) * (math.log(P_t_minus_1) - math.log(P_t_minus_n))

    # Absolute difference × 100 for percentage points
    abs_diff = (r_t - r_bar_n) * 100
    return abs_diff

def main():
    print("=" * 70)
    print("DEBUG: memory_market_composite Signal Calculation")
    print("=" * 70)
    
    # Fetch indicators
    indicators = {
        199: "Global DRAM Revenue",
        273: "Global NAND Revenue"
    }
    weights = [0.6, 0.4]
    n_periods = 3
    
    data = {}
    all_dates = set()
    
    for ind_id, name in indicators.items():
        print(f"\n[Fetching {ind_id}: {name}]")
        payload = fetch_indicator(ind_id)
        
        if not payload:
            print(f"  FAILED to fetch {ind_id}")
            return 1
        
        # Parse payload
        for indicator_name, series in payload.items():
            if not isinstance(series, dict):
                continue
            data_points = series.get("data") or {}
            
            rows = []
            for date_str, value in data_points.items():
                rows.append({"date": date_str, "value": value})
                all_dates.add(date_str)
            
            rows.sort(key=lambda r: r["date"])
            data[ind_id] = {
                "name": indicator_name,
                "unit": series.get("unit", ""),
                "rows": rows,
            }
            
            print(f"  Fetched {len(rows)} data points")
            print(f"  Date range: {rows[0]['date']} to {rows[-1]['date']}")
            print(f"  Latest 5 values:")
            for row in rows[-5:]:
                print(f"    {row['date']}: {row['value']}")
    
    # Calculate growth for each indicator
    print("\n" + "=" * 70)
    print("GROWTH CALCULATION (n_periods=3)")
    print("=" * 70)
    
    growth_rates = {}
    
    for ind_id, weight in zip([199, 273], weights):
        if ind_id not in data:
            print(f"Missing data for {ind_id}")
            return 1
        
        rows = data[ind_id]["rows"]
        print(f"\n[{data[ind_id]['name']} (ID: {ind_id}, weight: {weight})]")
        
        # Take last 4 values for n_periods=3 calculation
        last_rows = rows[-4:]
        
        print(f"  Using last {len(last_rows)} values:")
        for row in last_rows:
            print(f"    {row['date']}: {row['value']}")
        
        if len(last_rows) < 4:  # Need at least n_periods + 1
            print(f"  ERROR: Not enough rows (have {len(rows)}, need {n_periods + 1})")
            return 1
        
        new_value = float(last_rows[-1]["value"])
        history = last_rows[:-1]
        
        print(f"\n  Growth calculation:")
        print(f"    P_t (latest): {new_value}")
        print(f"    P_t-1 (prev): {history[-1]['value']}")
        print(f"    P_t-n (3 back): {history[-(n_periods)]['value']}")
        
        growth = calculate_growth(new_value, history, n_periods)
        
        if growth is not None:
            print(f"    Growth rate: {growth:+.2f}%")
            growth_rates[ind_id] = growth
        else:
            print(f"    Growth rate: NONE (insufficient history)")
    
    # Calculate weighted average
    if len(growth_rates) == 2:
        print("\n" + "=" * 70)
        print("WEIGHTED AVERAGE")
        print("=" * 70)
        
        weighted_sum = sum(
            growth_rates[ind_id] * weight 
            for ind_id, weight in zip([199, 273], weights)
        )
        total_weight = sum(weights)
        weighted_avg = weighted_sum / total_weight
        
        print(f"\nGrowth rates:")
        print(f"  Indicator 199 (DRAM): {growth_rates[199]:+.2f}% × 0.6 = {growth_rates[199] * 0.6:+.2f}%")
        print(f"  Indicator 273 (NAND): {growth_rates[273]:+.2f}% × 0.4 = {growth_rates[273] * 0.4:+.2f}%")
        print(f"\nWeighted Average: {weighted_avg:+.2f}%")
        
        if abs(weighted_avg) > 20.0:
            print(f"\n✓ THRESHOLD HIT: {abs(weighted_avg):.2f}% > 20.0%")
        else:
            print(f"\n✗ No alert: {abs(weighted_avg):.2f}% ≤ 20.0%")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
