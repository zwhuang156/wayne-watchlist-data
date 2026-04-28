"""
Step 1 sanity check: 確認 yfinance 在 trade conda env 能正常抓資料。
跑法:
    C:\\Users\\zwhua\\anaconda3\\envs\\trade\\python.exe test_yfinance.py
"""
import sys
import yfinance as yf

TICKERS = ["NVDA", "ALB", "USAR", "ONDS", "COPX"]


def probe(symbol: str) -> None:
    t = yf.Ticker(symbol)

    info = {}
    try:
        info = t.info or {}
    except Exception as e:
        print(f"  [warn] info() failed: {e}")

    price = info.get("regularMarketPrice")

    hist = t.history(period="1y", auto_adjust=False)
    if hist.empty:
        raise RuntimeError("history() returned empty DataFrame")

    if price is None:
        price = float(hist["Close"].iloc[-1])

    high_52w = float(hist["High"].max())
    low_52w = float(hist["Low"].min())
    first_date = hist.index[0].date()
    last_date = hist.index[-1].date()

    print(f"{symbol}")
    print(f"  name        : {info.get('shortName') or info.get('longName')}")
    print(f"  price       : {price:.2f}")
    print(f"  52w high    : {high_52w:.2f}")
    print(f"  52w low     : {low_52w:.2f}")
    print(f"  rows        : {len(hist)}  ({first_date} → {last_date})")
    print()


def main() -> int:
    print(f"yfinance version: {yf.__version__}\n")
    failures = []
    for sym in TICKERS:
        try:
            probe(sym)
        except Exception as e:
            print(f"{sym}  FAILED: {e}\n")
            failures.append(sym)
    if failures:
        print(f"FAILED tickers: {failures}")
        return 1
    print("All tickers OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
