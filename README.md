# LEAP/SCAN — Top 50 Long Call Scanner

GEX-first LEAP scanner with 2-pass architecture. Scores every qualifying long call on 6 profitability factors and ranks the top 50.

## Scoring model (100 pts total)
- **GEX put wall proximity** — 28pts (primary)
- **Low IV at entry** — 20pts (buy cheap, sell expanded)
- **Stock off 52w high** — 18pts (upside runway)
- **Extrinsic quality** — 15pts (< 15% hard cap)
- **OI liquidity** — 10pts (500+ minimum)
- **Spread tightness** — 9pts (< 2% ideal)

## Browser version (GitHub Pages)
Open `index.html` — select baskets, hit SCAN. Uses 2-pass:
- Pass 1: batch quote fetch for all tickers → filter by price action score
- Pass 2: LEAP chain pull for top candidates only

This gets 1,400 tickers scanned in 5–15 minutes vs 90+ minutes for a naive full scan.

## Python script (overnight / full scan)

```bash
pip install requests pandas

# Core basket (quick test)
python3 leap_scanner.py

# Specific basket
python3 leap_scanner.py --basket defense
python3 leap_scanner.py --basket semis

# Custom tickers
python3 leap_scanner.py --tickers NVDA,PLTR,MRVL,MU,AMZN

# Full 1,400+ ticker scan (20–40 minutes)
python3 leap_scanner.py --all

# Full scan, show top 100, tighter IV gate
python3 leap_scanner.py --all --top 100 --max-iv 0.65

# Run overnight via cron (8pm CT daily)
# 0 20 * * 1-5 cd ~/leap-scanner && python3 leap_scanner.py --all > scan_$(date +%Y%m%d).log 2>&1
```

## Output
- Console table: rank, score, ticker, strike, expiry, DTE, premium, delta, IV, extrinsic, OI, % off 52w high, GEX put wall, tags
- CSV file: `leap_scan_YYYYMMDD_HHMM.csv` with all columns

## LEAP filter defaults
| Setting | Default | Notes |
|---|---|---|
| Min DTE | 365 | 365+ = LEAP |
| Prefer DTE | 420–600 | best time/risk balance |
| Delta range | 0.72–0.88 | 0.75–0.85 sweet spot |
| Max extrinsic | 20% | 15% ideal |
| Max IV | 85% | buy low IV |
| Min OI | 200 | 500+ preferred |
| Max spread | 4% | 2% ideal |
| Pass 1 top N | 120 | stocks sent to chain scan |

## Tags
- `GEX` — strike within $10 of GEX put wall (structural support)
- `UOA` — unusual open interest ratio (institutional activity)
- `VOL` — stock volume 2x+ daily average
- `IV↑` — above 80% IV gate (elevated, consider waiting)

## Switch to production Tradier API
Change line in script:
```python
TRADIER_BASE = "https://api.tradier.com/v1"
TRADIER_TOKEN = "YOUR_PRODUCTION_TOKEN"
```
