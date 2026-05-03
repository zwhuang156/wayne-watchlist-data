# wayne-watchlist-data

每日抓取一份股票 watchlist(~80 支標的)的價格與技術指標,寫成 JSON 後透過
GitHub Pages 公開,供另一個 AI(Claude Routine)以固定 URL 消費。

## 公開端點

```
https://zwhuang156.github.io/wayne-watchlist-data/latest.json
```

- `latest.json` — 永遠是最新一次成功的抓取結果
- `YYYY-MM-DD.json` — 當日歸檔(可拿來做時序回看)
- `index.html` — 簡單列出最後更新時間與檔案連結

## 排程

GitHub Actions 每個工作日跑兩次,確保全年都對到盤後 17:30 ET:
- `30 21 * * 1-5`(UTC 21:30)= ET 17:30 夏令 / 16:30 冬令
- `30 22 * * 1-5`(UTC 22:30)= ET 18:30 夏令 / 17:30 冬令

第二次的結果會覆蓋第一次,所以 `latest.json` 一律反映較晚那次的資料(也就是真正盤後 30 分結算後)。
代價是每個工作日多一次 commit,可接受。

## 手動操作

### 本地手動跑(用 trade conda env)
```powershell
C:\Users\zwhua\anaconda3\envs\trade\python.exe scripts\fetch_data.py
```
會覆寫 `docs/latest.json`、`docs/{今天}.json`、`docs/index.html`。本機跑只是 dry run,
要讓 Pages 對外更新仍需 commit + push。

### 手動 trigger GitHub Actions
Repo 頁面 → **Actions** → 左側 **daily-fetch** → 右上 **Run workflow** → 選 `main` → Run。
1~2 分鐘後 Actions 會自己 commit `docs/` 並 push,Pages 隨後重新 deploy。

## latest.json schema(給 Claude Routine 讀)

頂層:
| key | 型別 | 說明 |
|---|---|---|
| `generated_at` | string | ISO 8601 UTC,如 `2026-04-28T14:37:12Z` |
| `date` | string | `YYYY-MM-DD`(UTC),抓取當日 |
| `warning` | string \| null | 失敗 ticker ≥ 5 時,內容是失敗清單摘要;否則 null |
| `errors` | array | 每個元素 `{ticker, error}`,代表單一 ticker 抓取失敗 |
| `groups` | object | key = group 名稱,value = `{ticker: tickerData}` |
| `all` | object | 所有成功 ticker 的扁平 dict,key = ticker,value = tickerData |

`groups[*]` 內若某 ticker 抓取失敗,該 ticker 不會出現(只在 `errors` 看得到);
`all` 同理。所以 `groups` 的鍵集合是「該群定義 ticker ∩ 抓取成功」。

每個 ticker 物件(`tickerData`):
| key | 型別 | 單位 / 含義 |
|---|---|---|
| `ticker` | string | 標的代號(等同物件的 key) |
| `name` | string \| null | 公司 / ETF / 指數名稱(由 yfinance `.info` 提供,偶爾為 null) |
| `price` | float | 最新收盤(或 regularMarketPrice) |
| `volume` | int \| null | 最新一日成交量(指數類為 0) |
| `avg_volume_30d` | float \| null | 近 30 個交易日平均量(從歷史自算) |
| `market_cap` | int \| null | 市值(USD)。指數、期貨、外匯等沒有市值的會是 null |
| `ath_52w` | float | 過去 1 年最高(High.max) |
| `low_52w` | float | 過去 1 年最低(Low.min) |
| `ath_distance_pct` | float \| null | `(price - ath_52w) / ath_52w * 100`。負值代表距高點下跌幅度,0 代表創高 |
| `ma50` | float \| null | 50 日均線。資料 < 50 天時為 null |
| `ma200` | float \| null | 200 日均線。資料 < 200 天時為 null |
| `ma50_distance_pct` | float \| null | `(price - ma50) / ma50 * 100`。正 = 在 ma50 之上 |
| `ma200_distance_pct` | float \| null | 同上,基準 ma200 |
| `1d_pct` | float \| null | 1 日漲跌幅(%),即今日相對前一交易日收盤(週一則為相對上週五) |
| `1w_pct` | float \| null | 7 日漲跌幅(%) |
| `1m_pct` | float \| null | 30 日漲跌幅(%) |
| `3m_pct` | float \| null | 90 日漲跌幅(%) |
| `ytd_pct` | float \| null | 年初至今漲跌幅(%) |
| `1y_pct` | float \| null | 約 1 年漲跌幅(%);以 1y 歷史首筆 close 為基準,實際約 252 交易日 |
| `rsi_14` | float \| null | 14 日 RSI(Wilder's smoothing),0–100。資料 < 15 天時為 null |

⚠️ **注意**:`1m_pct` / `3m_pct` / `ytd_pct` / `1y_pct` 以數字開頭,JS / Python 取值要用 bracket
notation(`obj["1m_pct"]`),不是 `obj.1m_pct`。

### 範例
```json
{
  "ticker": "NVDA",
  "name": "NVIDIA Corporation",
  "price": 210.96,
  "volume": 61107813,
  "avg_volume_30d": 156620607,
  "market_cap": 5127383023616,
  "ath_52w": 216.83,
  "low_52w": 104.08,
  "ath_distance_pct": -2.71,
  "ma50": 186.1812,
  "ma200": 183.3395,
  "ma50_distance_pct": 13.31,
  "ma200_distance_pct": 15.07,
  "1d_pct": 0.84,
  "1w_pct": 3.21,
  "1m_pct": 25.92,
  "3m_pct": 10.14,
  "ytd_pct": 11.7,
  "1y_pct": 94.0,
  "rsi_14": 67.93
}
```

## Watchlist

單一 group `watchlist`,共 95 支標的(無重複;Claude Routine 直接讀 `groups.watchlist` 或 `all` 都行,內容相同)。

```
^SOX, ^TNX, ^VIX,
000660.KS, 002050.SZ, 005930.KS, 042700.KS,
ACHR, ALNT, AMD, AMZN, ANET, APP, AVAV, AVGO,
BE, BESIY, BOTT, BTC-USD, BWXT,
CAMT, CEG, CGNX, CIEN, CL=F, CMI, COHR, CRM, CRWD, CRWV,
DDOG, DELL, DLR, DX-Y.NYB,
EQIX, ETN,
FANUY, FORM,
GEV, GLD, GNRC, GOOG,
HG=F,
ISRG, IWM,
JOBY,
KEYS, KLAC, KLIC, KTOS,
LDOS, LMT,
MDB, META, MKSI, MOG-A, MRVL, MSFT, MU, MYRG,
NBIS, NJDCY, NOC, NOW, NVDA, NVT,
OKLO, ONDS, ONTO, ORCL, OUST,
PLTR, POWL,
QQQ,
RKLB, ROK, RTX,
SMCI, SMH, SNDK, SNOW, SPCE, SPY, STRL, STX, SYM,
TEM, TER, TSLA, TSM,
VIAV, VICR, VRT, VST,
WDC
```

⚠️ **計價幣別**:`price` / `ath_52w` / `low_52w` 等以 Yahoo 原始幣別輸出。美股 = USD,韓股(`*.KS`)= KRW,陸股(`*.SZ`)= CNY,加密貨幣(`BTC-USD`)= USD。需要跨市場比較請自行換匯。

## 更新 watchlist

直接編輯 [`scripts/fetch_data.py`](scripts/fetch_data.py) 最上方的 `WATCHLIST` 常數即可,
推上去後下次 Actions 自動套用。Yahoo 上找不到的代號會被記錄到 `errors` 並從 `groups` 移除,
不會中斷整體抓取。常見坑:
- 澳洲股要加 `.AX`(例如 `LYC.AX`)
- 期貨要對的 Yahoo 代號(`HG=F`、`CL=F`)
- 美元指數是 `DX-Y.NYB`、VIX 是 `^VIX`、10Y 殖利率是 `^TNX`

## 失敗處理

- 單一 ticker 失敗:try/except 收集起來,**整體再 retry 一次**
- 最終失敗 ≥ 5 個:`warning` 欄位填寫摘要(下游可據此判斷要不要忽略今天的資料)
- workflow 整體失敗(例如 yfinance 套件壞掉):GitHub 預設會 email repo owner

## 檔案結構

```
.
├── .github/workflows/daily-fetch.yml   # 每日排程
├── scripts/fetch_data.py               # 主程式
├── docs/                               # GitHub Pages source(/docs)
│   ├── latest.json
│   ├── YYYY-MM-DD.json                 # 每日歸檔
│   └── index.html
├── test_yfinance.py                    # Step 1 sanity check(可刪)
├── .gitignore
└── README.md
```
