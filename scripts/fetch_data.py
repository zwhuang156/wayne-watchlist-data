"""
Daily watchlist fetcher.

Reads WATCHLIST below, pulls 1-year daily history for every ticker via
yfinance, derives price/MA/RSI/return fields, and writes:
    docs/latest.json
    docs/{YYYY-MM-DD}.json
    docs/index.html

Single-ticker failures are caught and retried once. The script never
exits non-zero unless something catastrophic happens (so GitHub Actions
still commits a partial result rather than dropping the whole day).
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf


WATCHLIST: dict[str, list[str]] = {
    "ai_compute":         ["NVDA", "AVGO", "MU", "SNDK", "AMD", "TSM", "MRVL", "ANET", "CIEN", "COHR", "SMCI", "DELL"],
    "power_chain":        ["GEV", "VRT", "VST", "CEG", "OKLO", "POWL", "MYRG", "PRIM", "STRL", "ETN", "NVT", "BE"],
    "energy_fuel":        ["CCJ", "UEC", "NXE", "DNN", "LEU", "UUUU", "FCX", "SCCO", "TECK", "COPX", "XOM", "CVX"],
    "critical_minerals":  ["ALB", "SQM", "LIT", "MP", "USAR", "LAC", "SGML", "LYC.AX", "ARRY"],
    "defense_aero":       ["RKLB", "KTOS", "AVAV", "ONDS", "LMT", "RTX", "NOC", "ACHR", "JOBY", "LDOS", "BWXT", "SPCE"],
    "china_edge_apps":    ["QCOM", "AAPL", "KWEB", "BABA", "BIDU", "PDD", "ARM", "NTNX", "PSTG", "SYM", "IONQ"],
    "breadth_macro":      ["SPY", "QQQ", "IWM", "^VIX", "^SOX", "SMH", "DX-Y.NYB", "^TNX", "HG=F", "CL=F", "GLD", "BTC-USD"],
    "portfolio":          ["NVDA", "TSLA", "TEM", "GOOG", "PLTR", "INTC", "VST", "COPX", "ARKX", "QQQ", "CRCL"],
}

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"


def _round(x, ndigits=4):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return None
    return round(float(x), ndigits)


def _pct_from_offset(close: pd.Series, offset_days: int) -> float | None:
    """Return % change from the latest trading day on/before (last_date - offset_days)."""
    last_date = close.index[-1].date()
    target = last_date - timedelta(days=offset_days)
    earlier = close[close.index.date <= target]
    if earlier.empty:
        return None
    return float((close.iloc[-1] / earlier.iloc[-1] - 1.0) * 100.0)


def _pct_from_ytd(close: pd.Series) -> float | None:
    """% change from first trading day of the current year."""
    last_date = close.index[-1].date()
    jan1 = datetime(last_date.year, 1, 1).date()
    in_year = close[close.index.date >= jan1]
    if in_year.empty:
        return None
    return float((close.iloc[-1] / in_year.iloc[0] - 1.0) * 100.0)


def _rsi_14(close: pd.Series) -> float | None:
    """Wilder's RSI(14). Needs at least 15 closes to be meaningful."""
    if len(close) < 15:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / 14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / 14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    val = rsi.iloc[-1]
    if pd.isna(val):
        return None
    return float(val)


def fetch_one(symbol: str) -> dict:
    t = yf.Ticker(symbol)
    hist = t.history(period="1y", auto_adjust=False)
    if hist.empty:
        raise RuntimeError("history() returned empty DataFrame")

    close = hist["Close"].dropna()
    if close.empty:
        raise RuntimeError("no Close prices")

    info = {}
    try:
        info = t.info or {}
    except Exception:
        info = {}

    price = info.get("regularMarketPrice")
    if price is None:
        price = float(close.iloc[-1])
    price = float(price)

    volume_today = int(hist["Volume"].iloc[-1]) if not pd.isna(hist["Volume"].iloc[-1]) else None
    avg_volume_30d = float(hist["Volume"].tail(30).mean()) if len(hist) >= 1 else None
    if avg_volume_30d is not None and not np.isfinite(avg_volume_30d):
        avg_volume_30d = None

    high_52w = float(hist["High"].max())
    low_52w = float(hist["Low"].min())
    ath_distance_pct = (price - high_52w) / high_52w * 100.0 if high_52w else None

    ma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
    ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
    ma50_distance_pct = (price - ma50) / ma50 * 100.0 if ma50 else None
    ma200_distance_pct = (price - ma200) / ma200 * 100.0 if ma200 else None

    return {
        "ticker": symbol,
        "name": info.get("shortName") or info.get("longName"),
        "price": _round(price),
        "volume": volume_today,
        "avg_volume_30d": _round(avg_volume_30d, 0),
        "market_cap": info.get("marketCap"),
        "ath_52w": _round(high_52w),
        "low_52w": _round(low_52w),
        "ath_distance_pct": _round(ath_distance_pct, 2),
        "ma50": _round(ma50),
        "ma200": _round(ma200),
        "ma50_distance_pct": _round(ma50_distance_pct, 2),
        "ma200_distance_pct": _round(ma200_distance_pct, 2),
        "1m_pct": _round(_pct_from_offset(close, 30), 2),
        "3m_pct": _round(_pct_from_offset(close, 90), 2),
        "ytd_pct": _round(_pct_from_ytd(close), 2),
        "1y_pct": _round(_pct_from_offset(close, 365), 2),
        "rsi_14": _round(_rsi_14(close), 2),
    }


def fetch_all(symbols: list[str]) -> tuple[dict[str, dict], list[dict]]:
    """Fetch each symbol once, retry failures one more time."""
    results: dict[str, dict] = {}
    errors: list[dict] = []
    total = len(symbols)

    failed: list[str] = []
    for i, sym in enumerate(symbols, start=1):
        try:
            results[sym] = fetch_one(sym)
        except Exception as e:
            failed.append(sym)
            print(f"  [error] {sym}: {e}", flush=True)
        if i % 10 == 0 or i == total:
            print(f"  progress: {i}/{total} done  (ok={len(results)}, failed={len(failed)})", flush=True)

    if failed:
        print(f"\nRetrying {len(failed)} failed tickers: {failed}", flush=True)
        time.sleep(2)
        for sym in failed:
            try:
                results[sym] = fetch_one(sym)
                print(f"  [retry-ok] {sym}", flush=True)
            except Exception as e:
                errors.append({"ticker": sym, "error": str(e)})
                print(f"  [retry-fail] {sym}: {e}", flush=True)

    return results, errors


def build_payload(all_data: dict[str, dict], errors: list[dict]) -> dict:
    groups: dict[str, dict[str, dict]] = {}
    for group_name, tickers in WATCHLIST.items():
        groups[group_name] = {tic: all_data[tic] for tic in tickers if tic in all_data}

    now = datetime.now(timezone.utc)
    warning = None
    if len(errors) >= 5:
        failed_syms = [e["ticker"] for e in errors]
        warning = f"{len(errors)} tickers failed: {failed_syms}"

    return {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": now.strftime("%Y-%m-%d"),
        "warning": warning,
        "errors": errors,
        "groups": groups,
        "all": all_data,
    }


INDEX_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Wayne Watchlist Data</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 720px; margin: 3rem auto; padding: 0 1rem; color: #222; }}
  code {{ background: #f4f4f4; padding: 0.1rem 0.3rem; border-radius: 3px; }}
  a {{ color: #0066cc; }}
</style>
</head>
<body>
<h1>Wayne Watchlist Data</h1>
<p>Daily snapshot of a multi-group equity watchlist for AI consumption.</p>
<p><strong>Last update:</strong> {generated_at}</p>
<ul>
  <li><a href="latest.json">latest.json</a> &mdash; latest snapshot (always current)</li>
  <li><a href="{date}.json">{date}.json</a> &mdash; today's archived snapshot</li>
</ul>
<p>Groups: {group_count}. Tickers (unique): {ticker_count}. Errors: {error_count}.</p>
<p>See <a href="https://github.com/zwhuang156/wayne-watchlist-data">repo</a> for schema and source.</p>
</body>
</html>
"""


def write_outputs(payload: dict) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    latest_path = DOCS_DIR / "latest.json"
    dated_path = DOCS_DIR / f"{payload['date']}.json"
    with latest_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    with dated_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

    html = INDEX_HTML_TEMPLATE.format(
        generated_at=payload["generated_at"],
        date=payload["date"],
        group_count=len(payload["groups"]),
        ticker_count=len(payload["all"]),
        error_count=len(payload["errors"]),
    )
    (DOCS_DIR / "index.html").write_text(html, encoding="utf-8")

    print(f"\nWrote: {latest_path}")
    print(f"Wrote: {dated_path}")
    print(f"Wrote: {DOCS_DIR / 'index.html'}")


def main() -> int:
    unique_symbols = sorted({sym for tickers in WATCHLIST.values() for sym in tickers})
    print(f"Fetching {len(unique_symbols)} unique tickers across {len(WATCHLIST)} groups...\n", flush=True)

    started = time.time()
    all_data, errors = fetch_all(unique_symbols)
    elapsed = time.time() - started

    payload = build_payload(all_data, errors)
    write_outputs(payload)

    print(
        f"\nDone in {elapsed:.1f}s. ok={len(all_data)}, errors={len(errors)}"
        + (f", WARNING={payload['warning']}" if payload["warning"] else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
