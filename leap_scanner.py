#!/usr/bin/env python3
"""
LEAP Scanner — Full 1,400 Ticker Python Script
Runs overnight via Claude Code or cron. Outputs ranked CSV.

Usage:
    python3 leap_scanner.py
    python3 leap_scanner.py --basket core
    python3 leap_scanner.py --tickers NVDA,PLTR,MRVL
    python3 leap_scanner.py --all        # full 1,400 ticker scan

Requirements:
    pip install requests pandas aiohttp asyncio
"""

import asyncio
import aiohttp
import requests
import pandas as pd
import json
import argparse
from datetime import datetime, timedelta
from typing import Optional

# ─── CONFIG ───────────────────────────────────────────────────────────────
TRADIER_TOKEN = "5eebf62a6678b05dc5e5d5b58c15f9b8"  # Sandbox
TRADIER_BASE  = "https://sandbox.tradier.com/v1"
# For production: TRADIER_BASE = "https://api.tradier.com/v1"

HEADERS = {
    "Authorization": f"Bearer {TRADIER_TOKEN}",
    "Accept": "application/json"
}

CONCURRENT_CHAIN_CALLS = 5   # parallel chain requests (be gentle with API)
BATCH_QUOTE_SIZE       = 100  # tickers per quote batch

# ─── LEAP FILTER DEFAULTS ─────────────────────────────────────────────────
FILTERS = {
    "min_dte":        365,    # 365+ days = LEAP
    "prefer_dte_min": 420,    # prefer 420–600 DTE window
    "prefer_dte_max": 600,
    "min_delta":      0.72,
    "max_delta":      0.88,
    "max_extrinsic":  20.0,   # % — loosened for Python scan
    "max_iv":         0.85,   # 85% IV ceiling
    "min_oi":         200,    # open interest floor
    "max_spread":     4.0,    # % spread ceiling
    "pass1_max_from_high": 80, # % — how far off 52w high to consider
    "pass1_top_n":    120,    # top N stocks sent to chain scan
}

# ─── WATCHLIST ────────────────────────────────────────────────────────────
BASKETS = {
    "core": "NVDA,PLTR,MRVL,MU,AMZN,MSFT,GOOGL,AMD,SMCI,ZS,COHR,AAOI,LITE,GLW,KTOS,AVAV,RTX,NOC,LMT,AMAT,LRCX,META,TSLA,ARM,CRWD,DDOG,NET,IONQ,ASTS,RKLB,MARA,RIOT,CLSK",
    "defense": "KTOS,AVAV,PLTR,RTX,NOC,LMT,GD,HWM,TDG,BA,HAL,GEV,LHX,AXON",
    "semis": "NVDA,AMD,AMAT,LRCX,KLAC,SNPS,CDNS,MRVL,ARM,SMCI,MU,INTC,QCOM,NXPI,ADI,TER,AVGO,TSM,ASML",
    "fiber": "LITE,COHR,AAOI,GLW,MRVL,CIEN,VIAV",
    "quantum": "IONQ,QUBT,RGTI,QBTS",
    "crypto": "MARA,RIOT,CLSK,CIFR,CORZ,IREN,COIN,HOOD,WULF,BTBT,MSTR",
    "space": "JOBY,ACHR,LUNR,ASTS,RKLB,RIVN,LCID,RCAT,ONDS,UMAC,RDW,SPCE",
    "saas": "CRM,NOW,SNOW,DDOG,NET,ZS,TEAM,MDB,WDAY,GTLB,CFLT,OKTA,TWLO,HUBS,VEEV,DOCU",
    "cyber": "CRWD,PANW,FTNT,ZS,OKTA,S,TENB,VRNS",
    "energy": "XOM,CVX,COP,EOG,OXY,DVN,HAL,SLB,AR,RRC,EQT,FANG,OVV",
    "fintech": "SQ,COIN,HOOD,AFRM,SOFI,PYPL,BILL,UPST,NU,CPNG,IBKR,SCHW",
    "uranium": "UUUU,CCJ,DNN,LEU,UEC",
    "mag7": "AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA",
    "hogue": "AMZN,PLTR,MRVL,MSFT,TSLA,GOOGL,NVDA,ZS",
}

ALL_TICKERS = [
    # Mega-cap tech
    "AAPL","MSFT","GOOGL","AMZN","NVDA","META","TSLA","AVGO","ORCL","CRM","AMD","ADBE",
    "CSCO","ACN","IBM","INTC","INTU","NOW","QCOM","TXN","AMAT","ADI","LRCX","KLAC",
    "SNPS","CDNS","MCHP","FTNT","PANW","CRWD","WDAY","MRVL","MU","HPQ","HPE","DELL",
    "NTAP","WDC","STX","ZBRA","TER","SMCI","ARM","PLTR","SNOW","DDOG","NET","ZS","TEAM","MDB",
    # SaaS / Cloud
    "HUBS","VEEV","DOCU","OKTA","TWLO","TTD","U","RBLX","SNAP","PINS","SHOP","SQ",
    "COIN","HOOD","AFRM","SOFI","MARA","RIOT","CLSK","CFLT","GTLB","BILL","PCOR",
    # Financials
    "JPM","V","MA","BAC","WFC","GS","MS","SPGI","BLK","C","SCHW","CB","MMC","PGR",
    "ICE","CME","AON","AJG","MET","AFL","PRU","TRV","ALL","AIG","USB","PNC","TFC",
    "COF","BK","STT","FITB","HBAN","MTB","RF","KEY","CFG","AXP","DFS","SYF","ALLY",
    "FIS","FISV","GPN","PYPL","IBKR","KKR","APO","BX","ARES",
    # Consumer
    "HD","MCD","NKE","LOW","SBUX","TJX","BKNG","CMG","ORLY","AZO","ROST","MAR","HLT",
    "YUM","DHI","LEN","PHM","TOL","GRMN","TSCO","BBY","DG","DLTR","ULTA","LULU","F",
    "GM","RIVN","LCID","ABNB","UBER","LYFT","DASH","DKNG","RCL","CCL","NCLH","EXPE",
    "ETSY","CHWY","PG","KO","PEP","COST","WMT","PM","MO","KR","ADM","TSN","MNST","STZ",
    # Industrials / Defense
    "CAT","GE","HON","UNP","UPS","RTX","BA","DE","LMT","MMM","GD","NOC","TDG","ITW",
    "EMR","ETN","PH","ROK","CTAS","FAST","GWW","CSX","NSC","FDX","DAL","UAL","LUV","AAL",
    "WM","RSG","KTOS","AVAV","HWM","GEV","LHX","AXON","TYL","GWRE",
    # Energy
    "XOM","CVX","COP","EOG","SLB","MPC","PSX","VLO","OXY","DVN","HAL","BKR","KMI",
    "WMB","OKE","LNG","AR","RRC","EQT","FANG","OVV","CNX",
    # Utilities / REIT
    "NEE","DUK","SO","SRE","AEP","EXC","XEL","ED","PLD","AMT","CCI","EQIX","PSA","DLR",
    "O","WELL","SPG","VICI","AVB","EQR",
    # Materials
    "LIN","APD","SHW","ECL","FCX","NEM","NUE","STLD","VMC","MLM","DOW","DD","PPG","ALB",
    # Media / Telecom
    "DIS","CMCSA","NFLX","T","VZ","TMUS","CHTR","EA","TTWO","WBD","PARA","MTCH","ROKU",
    # International ADRs
    "BABA","NIO","XPEV","JD","PDD","BIDU","TSM","ASML","SONY","SAP","MELI","SE","NU","GRAB",
    # Emerging / Speculative
    "GME","AMC","TLRY","CGC","SPCE","OPEN","UPST","AI","IONQ","QUBT","RGTI","PATH",
    "CFLT","GTLB","ESTC","BILL","PCOR","CELH","DUOL","CAVA","TOST","SOUN","JOBY",
    "ACHR","LUNR","ASTS","RKLB","FSLR","RUN","PLUG","BE","AXON","TYL",
    # Crypto / Mining
    "MSTR","CORZ","IREN","WULF","BTBT","CIFR","CLSK","MARA","RIOT","COIN","HOOD",
    # Nuclear / Uranium
    "OKLO","NNE","SMR","UUUU","CCJ","DNN","LEU","UEC",
    # Quantum
    "IONQ","QUBT","RGTI","QBTS",
    # Fiber / Photonics
    "LITE","COHR","AAOI","GLW","MRVL","CIEN","VIAV",
    # Drones / Space
    "UMAC","ONDS","RDW","RCAT","APP","RDDT",
    # AI infrastructure
    "ALAB","CRDO","NBIS","CRWV","CRCL",
]
ALL_TICKERS = list(dict.fromkeys(ALL_TICKERS))  # deduplicate preserving order

# ─── HELPERS ──────────────────────────────────────────────────────────────
def mid(o): return ((o.get("bid") or 0) + (o.get("ask") or 0)) / 2

def extr_pct(o, spot):
    m = mid(o)
    if m <= 0: return 99
    itm = max(0, spot - o.get("strike", 0))
    return max(0, m - itm) / m * 100

def spread_pct(o):
    m = mid(o)
    if m <= 0: return 99
    return ((o.get("ask", 0) - o.get("bid", 0)) / m) * 100

def dte_days(exp_str):
    try:
        return (datetime.strptime(exp_str, "%Y-%m-%d").date() - datetime.now().date()).days
    except:
        return 0

def best_exp(exps, min_dte, prefer_min=420, prefer_max=600):
    now = datetime.now().date()
    valid = sorted([e for e in exps if (datetime.strptime(e, "%Y-%m-%d").date() - now).days >= min_dte])
    if not valid: return None
    preferred = [e for e in valid
                 if prefer_min <= (datetime.strptime(e, "%Y-%m-%d").date() - now).days <= prefer_max]
    return preferred[0] if preferred else valid[0]

def pass1_score(q):
    spot = q.get("last", 0)
    h52  = q.get("week_52_high", 0)
    l52  = q.get("week_52_low", 0)
    avg_vol = q.get("average_volume", 0)
    if not spot or not h52 or not l52: return 0
    from_high = (spot - h52) / h52 * 100
    r_pos = (spot - l52) / (h52 - l52) * 100
    vs = q.get("volume", 0) / avg_vol if avg_vol > 0 else 1
    s = 0
    if from_high <= -40: s += 40
    elif from_high <= -30: s += 32
    elif from_high <= -20: s += 22
    elif from_high <= -10: s += 12
    elif from_high <= -5:  s += 5
    if r_pos < 20:   s += 30
    elif r_pos < 35: s += 22
    elif r_pos < 50: s += 14
    elif r_pos < 65: s += 7
    if vs >= 2:   s += 20
    elif vs >= 1.5: s += 15
    elif vs >= 1.2: s += 8
    s += min(10, avg_vol / 1_000_000)
    return min(100, s)

def compute_gex(opts, spot):
    sm = {}
    for o in opts:
        g = o.get("greeks") or {}
        gamma = float(g.get("gamma") or 0)
        oi    = int(o.get("open_interest") or 0)
        strike = float(o.get("strike") or 0)
        vol   = int(o.get("volume") or 0)
        gex   = gamma * oi * 100 * spot * spot * 0.01
        sm.setdefault(strike, {"cg":0,"pg":0,"coi":0,"poi":0,"cv":0})
        if o.get("option_type") == "call":
            sm[strike]["cg"] += gex; sm[strike]["coi"] += oi; sm[strike]["cv"] += vol
        else:
            sm[strike]["pg"] += gex; sm[strike]["poi"] += oi
    if not sm: return {"put_wall":0,"call_wall":0,"max_pain":0,"uoa":[]}
    strikes = [s for s in sm if sm[s]["cg"]+sm[s]["pg"] > 0]
    put_wall  = max(strikes, key=lambda s: sm[s]["pg"])
    call_wall = max(strikes, key=lambda s: sm[s]["cg"])
    def pain(s):
        return sum(max(0,s2-s)*sm[s2]["coi"]+max(0,s-s2)*sm[s2]["poi"] for s2 in strikes)
    max_pain = min(strikes, key=pain)
    uoa = sorted(
        [{"strike":s,"ratio":round(sm[s]["cv"]/max(sm[s]["coi"],1),1)} for s in strikes
         if sm[s]["coi"]>50 and sm[s]["cv"]>0 and sm[s]["cv"]/max(sm[s]["coi"],1)>1.5
         and spot*.7<s<spot*1.4],
        key=lambda x: -x["ratio"]
    )[:3]
    return {"put_wall":put_wall,"call_wall":call_wall,"max_pain":max_pain,"uoa":uoa}

def score_leap(o, spot, gex, q_data, f):
    g = o.get("greeks") or {}
    d    = abs(float(g.get("delta") or 0))
    iv   = float(g.get("mid_iv") or 0)
    oi   = int(o.get("open_interest") or 0)
    ep   = extr_pct(o, spot)
    sp   = spread_pct(o)
    strike = float(o.get("strike") or 0)
    dte  = dte_days(o.get("expiration_date",""))
    if not (f["min_delta"]-.04 <= d <= f["max_delta"]+.04): return None
    if iv > f["max_iv"]*1.4: return None
    if oi < f["min_oi"]*.5:  return None
    if ep > f["max_extrinsic"]+6: return None
    if sp > f["max_spread"]+2:    return None
    if dte < f["min_dte"]-45:     return None
    h52 = q_data.get("week_52_high",0)
    from_high = (spot-h52)/h52*100 if h52>0 else 0
    score = 0; tags = []
    # GEX put wall — 28pts
    pw = gex.get("put_wall",0)
    if pw:
        dist = abs(strike-pw); score += max(0, 28-dist*1.3)
        if dist <= 10: tags.append("GEX")
    else: score += 14
    # IV — 20pts
    if iv<=.30: score+=20
    elif iv<=.40: score+=17
    elif iv<=.50: score+=13
    elif iv<=.60: score+=8
    elif iv<=.70: score+=4
    elif iv<=.80: score+=1
    else: tags.append("IV↑")
    # Off 52w high — 18pts
    if from_high<=-40: score+=18
    elif from_high<=-30: score+=15
    elif from_high<=-20: score+=11
    elif from_high<=-10: score+=6
    elif from_high<=-5:  score+=3
    # Extrinsic — 15pts
    if ep<=8: score+=15
    elif ep<=10: score+=13
    elif ep<=12: score+=10
    elif ep<=15: score+=7
    elif ep<=20: score+=3
    # OI — 10pts
    if oi>=10000: score+=10
    elif oi>=5000: score+=8
    elif oi>=2000: score+=6
    elif oi>=1000: score+=4
    elif oi>=500:  score+=2
    # Spread — 9pts
    if sp<=.8: score+=9
    elif sp<=1.2: score+=7
    elif sp<=1.8: score+=5
    elif sp<=2.5: score+=3
    elif sp<=3.5: score+=1
    # Bonuses
    mp = gex.get("max_pain",0)
    if mp and abs(strike-mp)<=10: score+=3
    if any(abs(u["strike"]-strike)<5 for u in gex.get("uoa",[])):
        tags.append("UOA")
    avg_vol = q_data.get("average_volume",0)
    vs = q_data.get("volume",0)/avg_vol if avg_vol>0 else 1
    if vs>=2: score+=2; tags.append("VOL")
    return {"score":min(100,round(score)),"delta":d,"iv":iv,"extrinsic":ep,
            "spread":sp,"oi":oi,"strike":strike,"from_high":from_high,"tags":tags,"dte":dte}

# ─── API CALLS ────────────────────────────────────────────────────────────
def get_quotes_batch(tickers):
    """Fetch quotes for up to 100 tickers at once."""
    r = requests.get(f"{TRADIER_BASE}/markets/quotes",
                     headers=HEADERS, params={"symbols":",".join(tickers),"greeks":"false"}, timeout=20)
    data = r.json()
    quotes = data.get("quotes",{}).get("quote",[])
    if isinstance(quotes, dict): quotes = [quotes]
    return {q["symbol"]: q for q in quotes if q.get("symbol")}

def get_expirations(sym):
    r = requests.get(f"{TRADIER_BASE}/markets/options/expirations",
                     headers=HEADERS, params={"symbol":sym,"includeAllRoots":"true"}, timeout=15)
    data = r.json()
    return data.get("expirations",{}).get("date",[]) or []

def get_chain(sym, exp):
    r = requests.get(f"{TRADIER_BASE}/markets/options/chains",
                     headers=HEADERS, params={"symbol":sym,"expiration":exp,"greeks":"true"}, timeout=20)
    data = r.json()
    opts = data.get("options",{}).get("option",[])
    return opts if isinstance(opts, list) else ([opts] if opts else [])

# ─── MAIN ─────────────────────────────────────────────────────────────────
def run_scan(tickers, f=FILTERS, top_n=50, output_csv=True):
    print(f"\n{'='*60}")
    print(f"LEAP SCANNER — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")
    print(f"Scanning {len(tickers)} tickers | Min DTE: {f['min_dte']} | Delta: {f['min_delta']}–{f['max_delta']}")
    print(f"Max IV: {f['max_iv']*100:.0f}% | Max Extrinsic: {f['max_extrinsic']}% | Min OI: {f['min_oi']}")

    # ── PASS 1: BATCH QUOTE FETCH ─────────────────────────────────────────
    print(f"\n── PASS 1: Fetching quotes ({len(tickers)} tickers in batches of {BATCH_QUOTE_SIZE}) ──")
    q_map = {}
    for i in range(0, len(tickers), BATCH_QUOTE_SIZE):
        batch = tickers[i:i+BATCH_QUOTE_SIZE]
        print(f"  Batch {i//BATCH_QUOTE_SIZE+1}: fetching {len(batch)} tickers...", end=" ", flush=True)
        try:
            q_map.update(get_quotes_batch(batch))
            print(f"got {len([t for t in batch if t in q_map])} quotes")
        except Exception as e:
            print(f"ERROR: {e}")

    # Score and filter pass 1
    candidates = []
    for sym in tickers:
        q = q_map.get(sym)
        if not q or not q.get("last") or not q.get("week_52_high"): continue
        from_high = ((q["last"]-q["week_52_high"])/q["week_52_high"])*100
        if abs(from_high) > f["pass1_max_from_high"] and from_high < 0: continue
        candidates.append({"sym":sym,"q":q,"p1":pass1_score(q),"from_high":from_high})
    candidates.sort(key=lambda x: -x["p1"])
    candidates = candidates[:f["pass1_top_n"]]
    print(f"\nPass 1: {len(q_map)} quoted → {len(candidates)} candidates (top {f['pass1_top_n']} by price action score)")

    # ── PASS 2: CHAIN SCAN ────────────────────────────────────────────────
    print(f"\n── PASS 2: Chain scan ({len(candidates)} tickers) ──")
    all_results = []
    for i, item in enumerate(candidates):
        sym = item["sym"]; q = item["q"]; spot = q["last"]
        print(f"  [{i+1:3d}/{len(candidates)}] {sym:8s} ${spot:8.2f}  p1={item['p1']:5.1f}  {item['from_high']:+.1f}% off high", end=" ")
        try:
            exps = get_expirations(sym)
            exp  = best_exp(exps, f["min_dte"], f["prefer_dte_min"], f["prefer_dte_max"])
            if not exp: print("  → no LEAP expiration"); continue
            opts = get_chain(sym, exp)
            if not opts: print("  → no chain data"); continue
            gex  = compute_gex(opts, spot)
            calls = [o for o in opts if o.get("option_type")=="call" and o.get("greeks")]
            n_found = 0
            for o in calls:
                s = score_leap(o, spot, gex, q, f)
                if not s: continue
                all_results.append({
                    "rank":        0,
                    "score":       s["score"],
                    "ticker":      sym,
                    "description": q.get("description",""),
                    "spot":        round(spot,2),
                    "strike":      o["strike"],
                    "expiry":      o.get("expiration_date",""),
                    "dte":         s["dte"],
                    "premium_mid": round(mid(o),2),
                    "delta":       round(s["delta"],3),
                    "iv_pct":      round(s["iv"]*100,1),
                    "extrinsic_pct": round(s["extrinsic"],1),
                    "spread_pct":  round(s["spread"],1),
                    "open_interest": s["oi"],
                    "from_52w_high_pct": round(s["from_high"],1),
                    "gex_put_wall": gex.get("put_wall",0),
                    "gex_max_pain": gex.get("max_pain",0),
                    "tags":        ",".join(s["tags"]),
                    "p1_score":    round(item["p1"],1),
                })
                n_found += 1
            print(f"  → {exp} | {n_found} contracts | put wall ${gex.get('put_wall',0)}")
        except Exception as e:
            print(f"  → ERROR: {e}")

    # ── RANK + OUTPUT ─────────────────────────────────────────────────────
    print(f"\n── RESULTS ──")
    if not all_results:
        print("No contracts passed filters. Try loosening IV or extrinsic limits.")
        return pd.DataFrame()

    df = pd.DataFrame(all_results).sort_values("score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    top = df.head(top_n)

    print(f"\n{'─'*110}")
    print(f"{'#':>3} {'Score':>5} {'Ticker':8} {'Strike':>7} {'Expiry':12} {'DTE':>4} {'Premium':>8} {'Delta':>6} {'IV':>5} {'Extr%':>6} {'OI':>7} {'Off High':>9} {'Put Wall':>9} {'Tags'}")
    print(f"{'─'*110}")
    for _,r in top.iterrows():
        print(f"{r['rank']:3.0f} {r['score']:5.0f} {r['ticker']:8} ${r['strike']:7.0f} {r['expiry']:12} {r['dte']:4.0f} ${r['premium_mid']:7.2f} {r['delta']:6.3f} {r['iv_pct']:4.0f}% {r['extrinsic_pct']:5.1f}% {r['open_interest']:7,.0f} {r['from_52w_high_pct']:+8.1f}% ${r['gex_put_wall']:8.0f} {r['tags']}")
    print(f"{'─'*110}")
    print(f"\nTotal: {len(df)} qualifying contracts across {df['ticker'].nunique()} tickers")
    print(f"Avg score: {df['score'].mean():.1f} | Avg IV: {df['iv_pct'].mean():.1f}% | Avg DTE: {df['dte'].mean():.0f}d")

    if output_csv:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        fname = f"leap_scan_{ts}.csv"
        df.to_csv(fname, index=False)
        print(f"\nFull results saved → {fname}")

    return top

# ─── CLI ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LEAP Long Call Scanner")
    parser.add_argument("--basket",  help="Basket name: core|defense|semis|fiber|quantum|crypto|space|saas|cyber|energy|fintech|uranium|mag7|hogue")
    parser.add_argument("--tickers", help="Comma-separated list of tickers")
    parser.add_argument("--all",     action="store_true", help="Scan all 1,400+ tickers")
    parser.add_argument("--top",     type=int, default=50, help="Show top N results (default 50)")
    parser.add_argument("--min-dte", type=int, default=365, help="Min DTE (default 365)")
    parser.add_argument("--max-iv",  type=float, default=0.85, help="Max IV (default 0.85)")
    parser.add_argument("--pass1-n", type=int, default=120, help="Pass 1 top N to chain scan")
    args = parser.parse_args()

    # Override filters from CLI
    f = FILTERS.copy()
    f["min_dte"]      = args.min_dte
    f["max_iv"]       = args.max_iv
    f["pass1_top_n"]  = args.pass1_n

    # Resolve tickers
    if args.all:
        tickers = ALL_TICKERS
        print(f"★ Full watchlist scan: {len(tickers)} tickers")
    elif args.basket:
        b = args.basket.lower()
        if b not in BASKETS:
            print(f"Unknown basket '{b}'. Options: {', '.join(BASKETS.keys())}")
            exit(1)
        tickers = BASKETS[b].split(",")
        print(f"Basket [{b}]: {len(tickers)} tickers")
    elif args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
        print(f"Custom: {len(tickers)} tickers")
    else:
        # Default: core basket
        tickers = BASKETS["core"].split(",")
        print(f"Default (core): {len(tickers)} tickers. Use --all for full scan.")

    run_scan(tickers, f=f, top_n=args.top)
