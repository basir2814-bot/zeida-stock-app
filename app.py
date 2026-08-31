import re, time
import numpy as np
import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="賊大戰術 Pro 免費版", page_icon="📈", layout="wide")

# ===== 選股邏輯版本 =====
# 每次核心分類規則更新就更換版本；避免 Streamlit Session State 繼續顯示舊掃描結果。
APP_LOGIC_VERSION = "2026-08-31-v7-cond2-cond3-balanced"

if st.session_state.get("_logic_version") != APP_LOGIC_VERSION:
    for _k in [
        "snap", "details", "inst", "fundamentals", "shorts", "chips",
        "top_show_n", "zeida_show_n"
    ]:
        st.session_state.pop(_k, None)
    st.session_state["_logic_version"] = APP_LOGIC_VERSION
    st.session_state["_logic_updated_notice"] = True




if st.session_state.pop("_logic_updated_notice", False):
    st.info("選股分類規則已更新，舊掃描結果已自動清除。請按一次「執行全市場掃描」重新計算。")

st.markdown(r'''
<style>
/* ===== 賊大戰術 Pro：深色統一主題 v2 ===== */
:root{
  --z-bg:#050b14;
  --z-bg2:#07131f;
  --z-panel:#0b1826;
  --z-panel2:#0e2032;
  --z-line:#1d4262;
  --z-line2:#2a5f87;
  --z-text:#edf6ff;
  --z-muted:#98aec3;
  --z-blue:#38a8ff;
  --z-cyan:#4fdcff;
  --z-green:#38d987;
  --z-yellow:#ffc14f;
  --z-orange:#ff9f35;
  --z-red:#ff6469;
  --z-purple:#b881ff;
}

html,body,[data-testid="stAppViewContainer"],.stApp{
  background:
    radial-gradient(circle at 12% 0%,rgba(24,90,148,.22),transparent 28%),
    radial-gradient(circle at 88% 0%,rgba(53,41,120,.13),transparent 24%),
    linear-gradient(180deg,#040a12 0%,#06111c 45%,#071522 100%)!important;
  color:var(--z-text)!important;
}

[data-testid="stHeader"]{
  background:rgba(4,10,18,.88)!important;
  backdrop-filter:blur(8px);
}
[data-testid="stToolbar"]{
  background:transparent!important;
}
[data-testid="stDecoration"]{display:none!important;}

.block-container{
  max-width:1500px!important;
  padding-top:1rem!important;
}

/* 一般文字 */
h1,h2,h3,h4,h5,h6,p,span,label,div{
  color:inherit;
}
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li{
  color:#d8e5f1;
}

/* Streamlit 原生卡片/區塊 */
[data-testid="stVerticalBlockBorderWrapper"]{
  background:rgba(8,22,35,.76)!important;
  border-color:#1f4565!important;
  border-radius:12px!important;
}

/* Selectbox / NumberInput / TextInput */
div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div,
[data-testid="stNumberInput"] input,
[data-testid="stTextInput"] input{
  background:#091827!important;
  color:#eef7ff!important;
  border-color:#28516f!important;
}
div[data-baseweb="select"] svg{fill:#9dc8e9!important;}
div[data-baseweb="popover"]{
  background:#0a1928!important;
}
div[role="listbox"]{
  background:#0a1928!important;
  border:1px solid #2a5578!important;
}
div[role="option"]{
  background:#0a1928!important;
  color:#eaf5ff!important;
}
div[role="option"]:hover{
  background:#12304b!important;
}

/* 按鈕 */
.stButton > button{
  background:linear-gradient(180deg,#1c9fff,#0b72d4)!important;
  color:#fff!important;
  border:1px solid #53baff!important;
  box-shadow:0 0 16px rgba(32,150,255,.16)!important;
}
.stButton > button:hover{
  background:linear-gradient(180deg,#35adff,#1280e8)!important;
  border-color:#86ceff!important;
}

/* Checkbox / Toggle */
[data-testid="stCheckbox"] label,
[data-testid="stToggle"] label{
  color:#dce9f4!important;
}

/* Dataframe：把原本白色表格改成深色 */
[data-testid="stDataFrame"],
[data-testid="stDataFrameResizable"]{
  background:#081522!important;
  border:1px solid #214866!important;
  border-radius:10px!important;
  overflow:hidden!important;
}
[data-testid="stDataFrame"] iframe{
  background:#081522!important;
}

/* Streamlit dataframe 目前使用 Glide Data Grid，直接覆蓋 CSS variables */
[data-testid="stDataFrame"]{
  --gdg-bg-cell:#091827!important;
  --gdg-bg-cell-medium:#0d2032!important;
  --gdg-bg-header:#10283d!important;
  --gdg-bg-header-hovered:#163650!important;
  --gdg-bg-header-has-focus:#173b59!important;
  --gdg-text-dark:#eef7ff!important;
  --gdg-text-medium:#c8d7e5!important;
  --gdg-text-light:#91a7ba!important;
  --gdg-accent-color:#38a8ff!important;
  --gdg-accent-light:rgba(56,168,255,.18)!important;
  --gdg-border-color:#244965!important;
}

/* Alert / info */
[data-testid="stAlert"]{
  background:#0c2133!important;
  border:1px solid #27577b!important;
  color:#dcecff!important;
}
[data-testid="stAlert"] p{color:#dcecff!important;}

/* Expander */
[data-testid="stExpander"]{
  background:#091827!important;
  border:1px solid #214663!important;
  border-radius:10px!important;
}
[data-testid="stExpander"] summary{
  color:#eaf5ff!important;
}

/* Tabs */
[data-baseweb="tab-list"]{
  background:#081522!important;
  border:1px solid #1e4362!important;
  border-radius:9px!important;
  padding:4px!important;
}
[data-baseweb="tab"]{
  color:#afc4d7!important;
  background:transparent!important;
}
[aria-selected="true"][data-baseweb="tab"]{
  color:#64bcff!important;
  background:#0d2c47!important;
  border-radius:7px!important;
}

/* Plotly 圖表外框 */
[data-testid="stPlotlyChart"]{
  background:#081522!important;
  border:1px solid #214761!important;
  border-radius:10px!important;
  padding:4px!important;
}

/* Metric */
[data-testid="stMetric"]{
  background:linear-gradient(180deg,#0c1c2c,#081522)!important;
  border:1px solid #214965!important;
  border-radius:10px!important;
  padding:12px!important;
}
[data-testid="stMetricLabel"]{color:#9fb5c8!important;}
[data-testid="stMetricValue"]{color:#f4f9ff!important;}

/* 手機版 */
@media(max-width:900px){
  .block-container{padding-left:.55rem!important;padding-right:.55rem!important;}
  [data-testid="stDataFrame"]{font-size:12px!important;}
  .summary-card{background:linear-gradient(180deg,#0c1b2a,#071521)!important;}
  .hero{background:linear-gradient(180deg,#0b1b2b,#07131f)!important;}
  .panel,.section,.filterbox,.detail-card,.legend{
    background:#081624!important;
  }
}
</style>
''', unsafe_allow_html=True)


TWSE = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
YAHOO_HOSTS = [
    "https://query1.finance.yahoo.com/v8/finance/chart",
    "https://query2.finance.yahoo.com/v8/finance/chart",
]
HEAD = {"User-Agent": "Mozilla/5.0"}

st.markdown("""

<style>
:root{
  --bg:#07111d;
  --panel:#0b1725;
  --panel2:#0e1d2e;
  --line:#1c3a58;
  --line2:#23517a;
  --text:#eef6ff;
  --muted:#9fb1c2;
  --blue:#2d9cff;
  --green:#35d07f;
  --orange:#ffad32;
  --red:#ff5e63;
  --purple:#b36cff;
  --cyan:#45d6ff;
}
html, body, [class*="css"] {font-family: -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans TC",sans-serif;}
.stApp{
  background:
    radial-gradient(circle at 20% 0%, rgba(28,86,140,.18), transparent 30%),
    linear-gradient(180deg,#06101b 0%,#081522 100%);
  color:var(--text);
}
.block-container{max-width:1480px;padding-top:1.2rem;padding-bottom:2rem;}
[data-testid="stHeader"]{background:transparent;}
[data-testid="stToolbar"]{right:12px;}

.hero{
  display:flex;align-items:center;justify-content:space-between;
  padding:18px 22px;border:1px solid var(--line2);border-radius:12px;
  background:linear-gradient(180deg,rgba(13,30,47,.96),rgba(7,20,33,.96));
  box-shadow:0 12px 28px rgba(0,0,0,.22);
  margin-bottom:10px;
}
.hero-left{display:flex;align-items:center;gap:14px;}
.hero-icon{font-size:38px;filter:drop-shadow(0 0 10px rgba(45,156,255,.25));}
.hero-title{font-size:30px;font-weight:900;letter-spacing:.4px;color:#fff;}
.hero-title .pro{color:var(--orange);}
.hero-sub{font-size:14px;color:#c6d4e3;margin-top:4px;}
.hero-meta{text-align:right;font-size:13px;color:#b8c6d5;line-height:1.7;}
.badge-live{color:#6df3a6;font-weight:700;}

.navbar{
  display:grid;grid-template-columns:repeat(5,1fr);
  border:1px solid var(--line);border-radius:10px;overflow:hidden;
  background:#0a1725;margin-bottom:12px;
}
.navitem{padding:12px 10px;text-align:center;border-right:1px solid #18324d;color:#c8d5e3;font-weight:700;}
.navitem:last-child{border-right:none;}
.navitem.active{background:linear-gradient(180deg,#0b3156,#0a2440);color:#68baff;box-shadow:inset 0 -2px 0 #1f9dff;}

.section{
  border:1px solid var(--line);border-radius:12px;background:rgba(9,23,37,.92);
  padding:14px;margin:12px 0;
}
.section-title{
  font-size:18px;font-weight:900;color:#5eb6ff;margin:0 0 12px 0;
  display:flex;align-items:center;gap:8px;
}
.summary-grid{
  display:grid;grid-template-columns:repeat(6,minmax(150px,1fr));gap:10px;
}
.summary-card{
  min-height:118px;border:1px solid #21435f;border-radius:10px;
  background:linear-gradient(180deg,#0c1b2a,#091624);
  padding:12px 14px;display:flex;flex-direction:column;justify-content:center;
}
.summary-card .label{font-size:14px;color:#d5e0eb;margin-bottom:8px;}
.summary-card .big{font-size:28px;font-weight:900;letter-spacing:.4px;}
.summary-card .small{font-size:12px;color:#9eb1c4;margin-top:6px;line-height:1.5;}
.summary-card.green{border-color:#1f694d;background:linear-gradient(180deg,#0c2a24,#081b1b);}.summary-card.green .big{color:var(--green);}
.summary-card.orange{border-color:#6d4b22;background:linear-gradient(180deg,#2b2112,#17170f);}.summary-card.orange .big{color:var(--orange);}
.summary-card.purple{border-color:#594077;background:linear-gradient(180deg,#211b31,#151225);}.summary-card.purple .big{color:var(--purple);}
.summary-card.red{border-color:#ad3f48;box-shadow:0 0 0 1px rgba(255,94,99,.12);}
.summary-card.red .big{color:var(--red);}
.summary-card.blue{border-color:#28577b;background:linear-gradient(180deg,#0b2237,#081724);}.summary-card.blue .big{color:#49a8ff;}

.filterbox{
  border:1px solid var(--line);border-radius:12px;background:#091725;padding:14px 14px 4px;margin:12px 0;
}
[data-testid="stSelectbox"] label, [data-testid="stNumberInput"] label{font-size:12px!important;color:#b8c8d8!important;}
.stSelectbox div[data-baseweb="select"]>div{background:#0b1b2c;border-color:#274a6b;color:#eef6ff;}
.stButton>button{
  background:linear-gradient(180deg,#1591ff,#0873d1);color:white;border:1px solid #4cb2ff;
  border-radius:8px;font-weight:800;min-height:40px;
}
.stButton>button:hover{border-color:#88caff;color:#fff;}

.panel{
  border:1px solid var(--line);border-radius:12px;background:#091725;
  padding:12px 12px 14px;margin:12px 0;
}
.panel-title{font-size:19px;font-weight:900;color:#5eb6ff;margin-bottom:10px;}

.table-wrap{overflow-x:auto;border:1px solid #1d3d59;border-radius:9px;background:#07131f;}
.stock-table{border-collapse:separate;border-spacing:0;width:100%;min-width:1500px;font-size:12px;color:#dbe8f5;}
.stock-table th{
  position:sticky;top:0;z-index:2;background:#0e2235;color:#d8e6f4;
  padding:9px 7px;border-right:1px solid #24445f;border-bottom:1px solid #355b79;white-space:nowrap;
}
.stock-table td{
  padding:8px 7px;border-right:1px solid #18334b;border-bottom:1px solid #173148;
  white-space:nowrap;text-align:center;
}
.stock-table tr:hover td{background:#0d2031;}
.stock-table .rank{font-weight:900;color:#fff;}
.stock-table .code{color:#77bbff;font-weight:800;}
.stock-table .price{font-weight:900;color:#ffd36a;}
.stock-table .up{color:#ff696f;font-weight:900;}
.stock-table .down{color:#5ad68a;font-weight:900;}
.stock-table .volr{color:#ffb34a;font-weight:800;}
.stock-table .rr{color:#ffd45b;font-weight:900;}
.stock-table .grade{color:#7af1af;font-weight:900;}
.risk-low{color:#69e79f;font-weight:900;}
.risk-mid{color:#ffbb4d;font-weight:900;}
.risk-high{color:#ff6d73;font-weight:900;}

.legend-grid{
  display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:12px;
}
.legend{
  border:1px solid #1d3d59;border-radius:10px;background:#0b1826;padding:12px;
  min-height:210px;
}
.legend h4{margin:0 0 10px;color:#62b8ff;font-size:16px;}
.legend p,.legend li{font-size:12px;line-height:1.7;color:#c5d2df;}

.detail-grid{
  display:grid;grid-template-columns:minmax(0,2.1fr) minmax(240px,.9fr) minmax(240px,.9fr);
  gap:10px;
}
.detail-card{border:1px solid #1d3d59;border-radius:10px;background:#0b1826;padding:12px;}
.metric-row{display:flex;justify-content:space-between;border-bottom:1px solid #173248;padding:7px 0;font-size:13px;}
.metric-row:last-child{border-bottom:none;}
.metric-row .k{color:#9eb0c2}.metric-row .v{font-weight:800;color:#eef6ff}

@media(max-width:900px){
  .block-container{padding-left:.6rem;padding-right:.6rem;}
  .hero{padding:14px;align-items:flex-start}
  .hero-title{font-size:24px}.hero-icon{font-size:30px}
  .hero-meta{font-size:11px}
  .navbar{grid-template-columns:repeat(5,minmax(110px,1fr));overflow-x:auto}
  .navitem{font-size:12px}
  .summary-grid{grid-template-columns:repeat(2,1fr)}
  .summary-card{min-height:105px}
  .legend-grid{grid-template-columns:1fr}
  .detail-grid{grid-template-columns:1fr}
}
</style>

""", unsafe_allow_html=True)

def to_num(v):
    if v is None:
        return np.nan
    s = str(v).replace(",", "").replace("--", "").replace("---", "").replace("X", "").strip()
    try:
        return float(s)
    except:
        return np.nan

def pick(row, keys):
    for k in keys:
        if k in row:
            v = row[k]
            if str(v).strip() not in ("", "-", "--", "None"):
                return v
    return None

def finite(v):
    try:
        return bool(np.isfinite(float(v)))
    except:
        return False

def gt(a, b):
    return finite(a) and finite(b) and float(a) > float(b)

def ge(a, b):
    return finite(a) and finite(b) and float(a) >= float(b)

def lt(a, b):
    return finite(a) and finite(b) and float(a) < float(b)

@st.cache_data(ttl=900, show_spinner=False)
def snapshot():
    rows, warnings = [], []

    try:
        r = requests.get(TWSE, headers=HEAD, timeout=30)
        r.raise_for_status()
        for x in r.json():
            code = str(pick(x, ["Code", "證券代號", "股票代號"]) or "").strip()
            name = str(pick(x, ["Name", "證券名稱", "股票名稱"]) or "").strip()
            close = to_num(pick(x, ["ClosingPrice", "收盤價", "Close"]))
            opn = to_num(pick(x, ["OpeningPrice", "開盤價", "Open"]))
            high = to_num(pick(x, ["HighestPrice", "最高價", "High"]))
            low = to_num(pick(x, ["LowestPrice", "最低價", "Low"]))
            vol = to_num(pick(x, ["TradeVolume", "成交股數", "Trading_Volume"]))
            val = to_num(pick(x, ["TradeValue", "成交金額", "Trading_money"]))
            chg = to_num(pick(x, ["Change", "漲跌價差", "ChangePrice"]))
            if re.fullmatch(r"\d{4}", code) and finite(close):
                rows.append([code, name, "上市", close, opn, high, low, vol, val, chg])
    except Exception as e:
        warnings.append(f"上市資料暫時無法取得：{type(e).__name__}")

    # 上櫃資料：TPEx 主來源 + 官方備援
    tpex_ok = False
    tpex_urls = [
        TPEX,
        "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes",
    ]

    for _url in tpex_urls:
        try:
            r = requests.get(_url, headers=HEAD, timeout=30)
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, list) or len(data) == 0:
                continue

            before = len(rows)
            for x in data:
                code = str(pick(x, [
                    "SecuritiesCompanyCode", "SecuritiesCode", "Code",
                    "證券代號", "股票代號"
                ]) or "").strip()
                name = str(pick(x, [
                    "CompanyName", "SecuritiesCompanyName", "Name",
                    "證券名稱", "股票名稱"
                ]) or "").strip()
                close = to_num(pick(x, ["Close", "ClosingPrice", "收盤價"]))
                opn = to_num(pick(x, ["Open", "OpeningPrice", "開盤價"]))
                high = to_num(pick(x, ["High", "HighestPrice", "最高價"]))
                low = to_num(pick(x, ["Low", "LowestPrice", "最低價"]))
                vol = to_num(pick(x, ["TradingShares", "TradeVolume", "成交股數", "成交量"]))
                val = to_num(pick(x, ["TransactionAmount", "TradeValue", "成交金額"]))
                chg = to_num(pick(x, ["Change", "ChangePrice", "漲跌價差"]))

                if re.fullmatch(r"\d{4}", code) and finite(close):
                    rows.append([code, name, "上櫃", close, opn, high, low, vol, val, chg])

            if len(rows) > before:
                tpex_ok = True
                break
        except Exception:
            continue

    if not tpex_ok:
        warnings.append("上櫃資料暫時無法取得（TPEx 主來源與備援皆失敗）")

    d = pd.DataFrame(rows, columns=["stock_id","stock_name","market","close","open_today","high_today","low_today","volume","value","change"])
    if not d.empty:
        d = d.drop_duplicates("stock_id")
        d = d[~d.stock_name.astype(str).str.contains("ETF|ETN|權證|指數|債", case=False, na=False)]
    return d, warnings


def merge_today_bar(h, z):
    """
    Yahoo 日K有時盤中/盤後尚未包含今天。
    用 TWSE/TPEx 官方今日快照補上今天，避免分類仍在看昨天。
    """
    if h is None or h.empty:
        return h
    try:
        d = h.copy()
        today = pd.Timestamp.now(tz="Asia/Taipei").tz_localize(None).normalize()

        close = float(z.close) if finite(z.close) else np.nan
        if not finite(close):
            return d

        prev_close = close - float(z.change) if finite(z.change) else close
        opn = float(z.open_today) if hasattr(z, "open_today") and finite(z.open_today) else prev_close
        high = float(z.high_today) if hasattr(z, "high_today") and finite(z.high_today) else max(opn, close)
        low = float(z.low_today) if hasattr(z, "low_today") and finite(z.low_today) else min(opn, close)
        vol = float(z.volume) if finite(z.volume) else 0.0

        bar = {
            "date": today,
            "open": opn,
            "max": high,
            "min": low,
            "close": close,
            "volume": vol,
        }

        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        same = d["date"].dt.normalize() == today
        if same.any():
            for k,v in bar.items():
                d.loc[same, k] = v
        else:
            d = pd.concat([d, pd.DataFrame([bar])], ignore_index=True)

        return d.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
    except Exception:
        return h

@st.cache_data(ttl=3600, show_spinner=False)
def hist(code, market):
    suffix = ".TW" if market == "上市" else ".TWO"
    for host in YAHOO_HOSTS:
        try:
            url = f"{host}/{code}{suffix}"
            r = requests.get(
                url,
                params={"range":"1y","interval":"1d","includePrePost":"false"},
                headers=HEAD,
                timeout=20
            )
            if r.status_code != 200:
                continue
            j = r.json()
            result = j.get("chart", {}).get("result")
            if not result:
                continue

            z = result[0]
            ts = z.get("timestamp") or []
            quote = (z.get("indicators", {}).get("quote") or [{}])[0]
            if len(ts) < 65:
                continue

            L = len(ts)
            def arr(k):
                a = quote.get(k) or []
                return (a + [None] * L)[:L]

            d = pd.DataFrame({
                "date": pd.to_datetime(ts, unit="s", utc=True).tz_convert("Asia/Taipei").tz_localize(None),
                "open": arr("open"),
                "max": arr("high"),
                "min": arr("low"),
                "close": arr("close"),
                "volume": arr("volume"),
            })
            for c in ["open","max","min","close","volume"]:
                d[c] = pd.to_numeric(d[c], errors="coerce")
            d = d.dropna(subset=["open","max","min","close"]).sort_values("date").reset_index(drop=True)
            if len(d) >= 65:
                return d
        except:
            continue
    return pd.DataFrame()

def pct(a, b):
    if not finite(a) or not finite(b) or float(b) == 0:
        return np.nan
    return (float(a) / float(b) - 1) * 100

def rsi(s, n=14):
    z = s.diff()
    gain = z.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    loss = (-z.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100 / (1 + gain / loss.replace(0, np.nan))

def slope_pct(s, n):
    y = pd.to_numeric(s, errors="coerce").dropna().tail(n).to_numpy(dtype=float)
    if len(y) < n or np.nanmean(y) == 0:
        return np.nan
    return float(np.polyfit(np.arange(n), y, 1)[0] / np.nanmean(y) * 100)

def slope_label(x):
    if not finite(x): return "-"
    x = float(x)
    if x >= .7: return "↑ 加速上揚"
    if x >= .12: return "↗ 緩升"
    if x <= -.7: return "↓ 加速下彎"
    if x <= -.12: return "↘ 緩跌"
    return "→ 走平"

def analyze(raw):
    try:
        if raw is None or len(raw) < 65:
            return None

        d = raw.copy()
        for k in [5,10,20,60,120,240]:
            d[f"ma{k}"] = d["close"].rolling(k).mean()

        d["v20"] = d["volume"].rolling(20).mean()
        d["vr"] = d["volume"] / d["v20"].replace(0, np.nan)
        d["rsi"] = rsi(d["close"])

        e12 = d["close"].ewm(span=12, adjust=False).mean()
        e26 = d["close"].ewm(span=26, adjust=False).mean()
        d["macd"] = e12 - e26
        d["signal"] = d["macd"].ewm(span=9, adjust=False).mean()
        d["hist"] = d["macd"] - d["signal"]

        lo = d["min"].rolling(9).min()
        hi = d["max"].rolling(9).max()
        raw_k = (d["close"] - lo) / (hi - lo).replace(0, np.nan) * 100
        d["k"] = raw_k.ewm(alpha=1/3, adjust=False).mean()
        d["kd"] = d["k"].ewm(alpha=1/3, adjust=False).mean()

        x = d.iloc[-1]
        c = float(x["close"])
        ma5, ma10, ma20, ma60 = x["ma5"], x["ma10"], x["ma20"], x["ma60"]
        b5, b20, b60 = pct(c, ma5), pct(c, ma20), pct(c, ma60)
        s5 = slope_pct(d["ma5"], 5)
        s20 = slope_pct(d["ma20"], 10)
        s60 = slope_pct(d["ma60"], 15)

        vals = []
        for k in [5,10,20,60,120,240]:
            v = x[f"ma{k}"]
            if finite(v): vals.append(float(v))
        for k in [20,40,60]:
            if len(d) >= k:
                vals += [float(d["min"].tail(k).min()), float(d["max"].tail(k).max())]

        supports = sorted({round(v,2) for v in vals if v < c*.998}, reverse=True)
        resistances = sorted({round(v,2) for v in vals if v > c*1.002})
        support = supports[0] if supports else np.nan
        support2 = supports[1] if len(supports) > 1 else np.nan
        resistance = resistances[0] if resistances else np.nan
        resistance2 = resistances[1] if len(resistances) > 1 else np.nan
        rr = ((resistance-c)/(c-support)
              if finite(support) and finite(resistance) and c > float(support) else np.nan)

        hi20 = float(d["max"].tail(20).max())
        lo20 = float(d["min"].tail(20).min())
        hi40 = float(d["max"].tail(40).max())
        r40 = pct(c, d["close"].iloc[-41])
        from_hi = pct(c, hi40)
        vr = float(x["vr"]) if finite(x["vr"]) else 0.0
        rsi_now = float(x["rsi"]) if finite(x["rsi"]) else 50.0
        k_now = float(x["k"]) if finite(x["k"]) else 50.0
        d_now = float(x["kd"]) if finite(x["kd"]) else 50.0
        hist_now = float(x["hist"]) if finite(x["hist"]) else 0.0
        hist_prev = float(d["hist"].iloc[-2]) if finite(d["hist"].iloc[-2]) else 0.0

        if c >= hi20*.995 and vr >= 1.3:
            pattern = "平台突破"
        elif lo20 > 0 and (hi20-lo20)/lo20 < .10:
            pattern = "箱型整理"
        elif finite(r40) and r40 > 25 and c < hi40*.98 and gt(c, ma20):
            pattern = "強勢股拉回"
        elif finite(r40) and r40 < 0 and gt(c, ma20) and vr >= 1.5:
            pattern = "跌深轉折"
        elif gt(ma5, ma10) and gt(ma10, ma20):
            pattern = "多頭排列"
        else:
            pattern = "整理觀察"

        score = 50
        checks = [
            (gt(c, ma5), 5),
            (gt(c, ma20), 10),
            (gt(c, ma60), 5),
            (gt(ma5, ma10) and gt(ma10, ma20), 10),
            (finite(s20) and s20 > .12, 8),
            (vr >= 1.3, 6),
            (hist_now > hist_prev, 6),
        ]
        for ok, pts in checks:
            if ok:
                score += pts

        # 風險係數 0~100：波動度30% + 20日最大回撤25% + 量能穩定20% + 訊號一致性25%
        prev_close = d["close"].shift(1)
        tr = pd.concat([
            d["max"]-d["min"],
            (d["max"]-prev_close).abs(),
            (d["min"]-prev_close).abs()
        ], axis=1).max(axis=1)
        atr14 = tr.rolling(14).mean().iloc[-1]
        atr_pct = float(atr14/c*100) if finite(atr14) and c else np.nan

        peak20 = d["close"].tail(20).cummax()
        dd20_series = (d["close"].tail(20)/peak20-1)*100
        max_dd20 = abs(float(dd20_series.min())) if not dd20_series.dropna().empty else np.nan

        vol20 = pd.to_numeric(d["volume"].tail(20),errors="coerce").dropna()
        vol_cv = float(vol20.std()/vol20.mean()) if len(vol20)>=5 and vol20.mean()>0 else np.nan

        signal_checks = [
            gt(c,ma20), gt(c,ma60), gt(ma5,ma10), gt(ma10,ma20),
            finite(s20) and s20>0, hist_now>0, rsi_now>=50
        ]
        consistency = sum(bool(v) for v in signal_checks)/len(signal_checks)

        risk_vol = min(30, max(0, (atr_pct if finite(atr_pct) else 3.0)/6.0*30))
        risk_dd = min(25, max(0, (max_dd20 if finite(max_dd20) else 10.0)/20.0*25))
        risk_volume = min(20, max(0, (vol_cv if finite(vol_cv) else .6)/1.2*20))
        risk_signal = max(0, (1-consistency)*25)
        risk = int(round(min(100, risk_vol+risk_dd+risk_volume+risk_signal)))

        # 賊大 8 大選股分類（資金生命週期）
        # 這裡只做「價格 / 成交量 / 均線」階段判讀。
        # ⑤基本面、⑥/⑧融券確認會在外部資料抓回後再補強。
        zeida_tags = []

        day_chg = pct(c, d["close"].iloc[-2]) if len(d) >= 2 else np.nan
        r20_now = pct(c, d["close"].iloc[-21]) if len(d) > 21 else np.nan
        bias20_now = pct(c, ma20)
        bias60_now = pct(c, ma60)
        range20 = ((hi20 - lo20) / lo20 * 100) if lo20 > 0 else np.nan

        hi60 = float(d["max"].tail(min(60,len(d))).max())
        lo60 = float(d["min"].tail(min(60,len(d))).min())
        r60 = pct(c, d["close"].iloc[-61]) if len(d) > 61 else np.nan
        from_hi60 = pct(c, hi60) if finite(hi60) else np.nan

        ma5_series = d["close"].rolling(5).mean()
        prev5_below = False
        if len(d) >= 6:
            _recent_close = d["close"].iloc[-6:-1]
            _recent_ma5 = ma5_series.iloc[-6:-1]
            prev5_below = bool((_recent_close < _recent_ma5).fillna(False).any())
        reclaimed_ma5 = prev5_below and gt(c, ma5)

        # ⑦ 跌深轉折：先要求真的「跌深」，避免一般整理誤判成底部反轉。
        deep_decline = (
            (finite(r60) and r60 <= -20)
            or (finite(from_hi60) and from_hi60 <= -25)
        )
        near_ma20_after_turn = (
            finite(bias20_now)
            and -3 <= bias20_now <= 10
        )
        if (
            deep_decline
            and gt(c, ma20)
            and near_ma20_after_turn
            and vr >= 1.60
            and hist_now >= hist_prev
            and (not finite(day_chg) or day_chg > 0)
        ):
            zeida_tags.append("⑦跌深轉折")

        # ② 盤整待突破：真的要有一段橫盤，且尚未進入大漲狀態。
        long_base = (
            finite(range20) and range20 <= 15
            and finite(r20_now) and abs(r20_now) <= 12
            and finite(bias20_now) and abs(bias20_now) <= 8
        )
        if (
            long_base
            and c >= hi20 * .955
            and 0.90 <= vr <= 2.00
            and not (finite(day_chg) and day_chg >= 6)
        ):
            zeida_tags.append("②盤整待突破")

        # ⑧ 整理轉強：站上中期均線、整理收斂、剛開始轉強，不能已噴出。
        not_extended = (
            finite(r40) and r40 < 20
            and finite(r20_now) and r20_now < 12
            and finite(bias20_now) and bias20_now < 7
            and finite(bias60_now) and bias60_now < 12
        )
        still_consolidating = finite(range20) and range20 <= 16
        if (
            gt(c, ma60) and gt(c, ma20)
            and finite(s20) and s20 > 0
            and not_extended and still_consolidating
            and 0.90 <= vr < 1.70
            and not (finite(day_chg) and day_chg >= 6)
        ):
            zeida_tags.append("⑧整理轉強")

        # ③ 剛起動：前面漲幅不能大，現在才第一次放量攻擊。
        prior20_ret = pct(d["close"].iloc[-2], d["close"].iloc[-22]) if len(d) > 22 else np.nan

        # 近5日若已經出現2根以上「大漲K」，視為已經發動一段，不再算③第一次發動。
        _chg5 = d["close"].pct_change() * 100
        big_up_count_5 = int((_chg5.tail(5) >= 5).sum())

        first_launch = (
            finite(prior20_ret) and prior20_ret < 12
            and finite(r40) and r40 < 22
            and big_up_count_5 <= 1
            and vr >= 1.35
            and c >= hi20 * .97
            and (not finite(day_chg) or day_chg >= 1.5)
        )
        if first_launch:
            zeida_tags.append("③剛起動")

        # ②/③ 接近成立候選：差一點點時也保留觀察，不與正式成立混淆。
        near_tags = []

        near_2 = (
            finite(range20) and range20 <= 18
            and finite(r20_now) and abs(r20_now) <= 15
            and finite(bias20_now) and abs(bias20_now) <= 10
            and c >= hi20 * .94
            and 0.80 <= vr <= 2.20
            and not (finite(day_chg) and day_chg >= 7)
            and "②盤整待突破" not in zeida_tags
        )
        if near_2:
            near_tags.append("②接近突破")

        near_3 = (
            finite(prior20_ret) and prior20_ret < 15
            and finite(r40) and r40 < 25
            and big_up_count_5 <= 1
            and vr >= 1.20
            and c >= hi20 * .95
            and (not finite(day_chg) or day_chg >= 1.0)
            and "③剛起動" not in zeida_tags
        )
        if near_3:
            near_tags.append("③接近起動")

        # ① 強勢熱門：已形成短中期多頭，但不要離20MA過遠，避免把噴出段仍當「初期」。
        if (
            gt(ma5, ma10) and gt(ma10, ma20) and gt(c, ma20)
            and finite(r20_now) and 5 <= r20_now <= 28
            and finite(bias20_now) and bias20_now <= 12
            and vr >= 1.15 and c >= hi20 * .95
        ):
            zeida_tags.append("①強勢熱門")

        # ④ 強勢股拉回：前40日已漲一大段，近期曾跌破5MA，現在處於洗盤/重新站回階段。
        if (
            finite(r40) and r40 >= 28
            and finite(from_hi) and -16 <= from_hi <= -2
            and gt(c, ma20)
            and vr <= 1.55
            and (prev5_below or reclaimed_ma5 or (finite(b5) and -4 <= b5 <= 4))
        ):
            zeida_tags.append("④強勢股拉回")

        # ⑥ 強勢噴出：已脫離整理區、逼近40日高，避免再歸到⑧。
        if (
            finite(r40) and r40 >= 25
            and c >= hi40 * .98
            and (
                vr >= 1.25
                or (finite(bias20_now) and bias20_now >= 12)
                or (finite(day_chg) and day_chg >= 6)
            )
        ):
            zeida_tags.append("⑥強勢噴出")

        # 同一檔可有次要標籤，但「主階段」採優先順序避免 3450 類型被前面的①/⑧蓋掉。
        primary_priority = [
            "⑥強勢噴出",
            "④強勢股拉回",
            "③剛起動",
            "⑦跌深轉折",
            "①強勢熱門",
            "⑧整理轉強",
            "②盤整待突破",
        ]
        primary_stage = next((x for x in primary_priority if x in zeida_tags), None)

        cond = primary_stage if primary_stage else ("①強勢觀察" if gt(c, ma20) else "整理觀察")

        return {
            "score": int(max(0,min(100,round(score-risk*.1)))),
            "risk": min(100,risk),
            "pattern": pattern,
            "condition": cond,
            "zeida_tags": zeida_tags,
            "near_tags": near_tags,
            "primary_stage": primary_stage,
            "bias5": b5, "bias20": b20, "bias60": b60,
            "s5": s5, "s20": s20, "s60": s60,
            "support": support, "support2": support2,
            "resistance": resistance, "resistance2": resistance2, "rr": rr,
            "rsi": rsi_now, "k": k_now, "d": d_now, "vr": vr,
            "r20": pct(c, d["close"].iloc[-21]) if len(d) > 21 else np.nan,
            "ma60_up": gt(c, ma60),
            "macd_positive": hist_now > 0,
            "kd_golden": k_now > d_now,
            "atr_pct": atr_pct,
            "max_dd20": max_dd20,
            "vol_cv": vol_cv,
            "signal_consistency": consistency*100,
            "data": d
        }
    except Exception:
        return None

def chart(d, code, name):
    q = d.tail(140)
    fig = make_subplots(rows=2,cols=1,shared_xaxes=True,row_heights=[.75,.25],vertical_spacing=.03)
    fig.add_trace(go.Candlestick(
        x=q["date"],open=q["open"],high=q["max"],low=q["min"],close=q["close"],name="K線"
    ),1,1)
    for k in [5,10,20,60]:
        fig.add_trace(go.Scatter(x=q["date"],y=q[f"ma{k}"],name=f"MA{k}",line=dict(width=1)),1,1)
    fig.add_trace(go.Bar(x=q["date"],y=q["volume"],name="成交量"),2,1)
    fig.update_layout(template="plotly_dark",height=600,title=f"{code} {name}",xaxis_rangeslider_visible=False)
    return fig


FINMIND = "https://api.finmindtrade.com/api/v4/data"

@st.cache_data(ttl=3600, show_spinner=False)
def institutional_5d(code):
    try:
        end = pd.Timestamp.today().date()
        start = end - pd.Timedelta(days=35)
        r = requests.get(
            FINMIND,
            params={
                "dataset":"TaiwanStockInstitutionalInvestorsBuySellWide",
                "data_id":str(code),
                "start_date":str(start),
                "end_date":str(end),
            },
            headers=HEAD,
            timeout=18
        )
        if r.status_code != 200:
            return 0.0
        j = r.json()
        if j.get("status") not in (200, None):
            return 0.0
        d = pd.DataFrame(j.get("data", []))
        if d.empty:
            return 0.0
        d = d.tail(5).copy()
        total = 0.0
        pairs = [
            ("Foreign_Investor_buy","Foreign_Investor_sell"),
            ("Investment_Trust_buy","Investment_Trust_sell"),
            ("Dealer_self_buy","Dealer_self_sell"),
            ("Dealer_Hedging_buy","Dealer_Hedging_sell"),
        ]
        used = False
        for b,s in pairs:
            if b in d.columns and s in d.columns:
                total += (
                    pd.to_numeric(d[b],errors="coerce").fillna(0)
                    - pd.to_numeric(d[s],errors="coerce").fillna(0)
                ).sum()
                used = True
        return float(total) if used else 0.0
    except:
        return 0.0


@st.cache_data(ttl=21600, show_spinner=False)
def finmind_dataset(dataset, code, start_days=500):
    """FinMind 安全讀取器：失敗就回空表，不讓整個 App 掛掉。"""
    try:
        end = pd.Timestamp.today().date()
        start = end - pd.Timedelta(days=start_days)
        r = requests.get(
            FINMIND,
            params={
                "dataset": dataset,
                "data_id": str(code),
                "start_date": str(start),
                "end_date": str(end),
            },
            headers=HEAD,
            timeout=18,
        )
        if r.status_code != 200:
            return pd.DataFrame()
        j = r.json()
        if j.get("status") not in (200, None):
            return pd.DataFrame()
        return pd.DataFrame(j.get("data", []))
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=21600, show_spinner=False)
def chip_detail_5d(code):
    """外資 / 投信 / 自營商近5日買賣超。"""
    d = finmind_dataset("TaiwanStockInstitutionalInvestorsBuySellWide", code, 45)
    out = {"foreign":0.0, "trust":0.0, "dealer":0.0, "total":0.0}
    if d.empty:
        return out
    d = d.tail(5).copy()

    def net(buy_col, sell_col):
        if buy_col not in d.columns or sell_col not in d.columns:
            return 0.0
        return float(
            (
                pd.to_numeric(d[buy_col], errors="coerce").fillna(0)
                - pd.to_numeric(d[sell_col], errors="coerce").fillna(0)
            ).sum()
        )

    out["foreign"] = net("Foreign_Investor_buy","Foreign_Investor_sell")
    out["trust"] = net("Investment_Trust_buy","Investment_Trust_sell")
    out["dealer"] = (
        net("Dealer_self_buy","Dealer_self_sell")
        + net("Dealer_Hedging_buy","Dealer_Hedging_sell")
    )
    out["total"] = out["foreign"] + out["trust"] + out["dealer"]
    return out


@st.cache_data(ttl=21600, show_spinner=False)
def short_interest_5d(code):
    """融券餘額與近5日變化；欄位不存在時安全回傳空值。"""
    d = finmind_dataset("TaiwanStockMarginPurchaseShortSale", code, 60)
    if d.empty:
        return {"balance":np.nan, "change5":np.nan}
    # FinMind 常見欄位名稱；同時做多個候選欄位相容。
    balance_cols = [
        "ShortSaleTodayBalance",
        "ShortSaleBalance",
        "short_sale_balance",
        "short_balance",
    ]
    bal_col = next((c for c in balance_cols if c in d.columns), None)
    if bal_col is None:
        return {"balance":np.nan, "change5":np.nan}
    s = pd.to_numeric(d[bal_col], errors="coerce").dropna()
    if s.empty:
        return {"balance":np.nan, "change5":np.nan}
    now = float(s.iloc[-1])
    prev = float(s.iloc[-6]) if len(s) >= 6 else float(s.iloc[0])
    return {"balance":now, "change5":now-prev}


@st.cache_data(ttl=21600, show_spinner=False)
def fundamental_growth(code):
    """
    條件⑤：營運成長潛力。
    優先看月營收 YoY + 最近EPS；資料不足時降低信心，不硬造數字。
    """
    out = {
        "revenue_yoy":np.nan, "revenue_3m_yoy":np.nan,
        "eps":np.nan, "eps_prev":np.nan, "eps_growth":np.nan,
        "pass":False, "confidence":"低", "note":"基本面資料不足"
    }

    rev = finmind_dataset("TaiwanStockMonthRevenue", code, 900)
    if not rev.empty and "revenue" in rev.columns:
        r = rev.copy()
        r["revenue"] = pd.to_numeric(r["revenue"], errors="coerce")
        if "date" in r.columns:
            r["date"] = pd.to_datetime(r["date"], errors="coerce")
            r = r.sort_values("date")
        r = r.dropna(subset=["revenue"]).tail(30).reset_index(drop=True)

        yoy_list = []
        if "revenue_year" in r.columns and "revenue_month" in r.columns:
            r["revenue_year"] = pd.to_numeric(r["revenue_year"], errors="coerce")
            r["revenue_month"] = pd.to_numeric(r["revenue_month"], errors="coerce")
            lookup = {
                (int(y),int(m)):float(v)
                for y,m,v in zip(r["revenue_year"],r["revenue_month"],r["revenue"])
                if finite(y) and finite(m) and finite(v)
            }
            for y,m,v in zip(r["revenue_year"],r["revenue_month"],r["revenue"]):
                if not (finite(y) and finite(m) and finite(v)):
                    yoy_list.append(np.nan); continue
                pv = lookup.get((int(y)-1,int(m)))
                yoy_list.append(((float(v)/pv)-1)*100 if pv not in (None,0) else np.nan)
        else:
            # 如果只有日期，按年月做同月去年比較
            if "date" in r.columns:
                lookup = {(x.year,x.month):float(v) for x,v in zip(r["date"],r["revenue"]) if pd.notna(x) and finite(v)}
                for x,v in zip(r["date"],r["revenue"]):
                    pv = lookup.get((x.year-1,x.month)) if pd.notna(x) else None
                    yoy_list.append(((float(v)/pv)-1)*100 if pv not in (None,0) else np.nan)

        if yoy_list:
            r["yoy"] = yoy_list
            ys = pd.to_numeric(r["yoy"], errors="coerce").dropna()
            if not ys.empty:
                out["revenue_yoy"] = float(ys.iloc[-1])
                out["revenue_3m_yoy"] = float(ys.tail(3).mean())

    fs = finmind_dataset("TaiwanStockFinancialStatements", code, 1200)
    if not fs.empty:
        # 兼容 type / origin_name / name 等不同欄位
        text_cols = [c for c in ["type","origin_name","name","item"] if c in fs.columns]
        val_col = next((c for c in ["value","amount"] if c in fs.columns), None)
        if text_cols and val_col:
            mask = pd.Series(False, index=fs.index)
            for c in text_cols:
                txt = fs[c].astype(str)
                mask = mask | txt.str.contains("EPS|EarningsPerShare|每股盈餘", case=False, regex=True, na=False)
            e = fs.loc[mask].copy()
            if "date" in e.columns:
                e["date"] = pd.to_datetime(e["date"], errors="coerce")
                e = e.sort_values("date")
            ev = pd.to_numeric(e[val_col], errors="coerce").dropna()
            if len(ev) >= 1:
                out["eps"] = float(ev.iloc[-1])
            if len(ev) >= 2:
                out["eps_prev"] = float(ev.iloc[-2])
                if out["eps_prev"] != 0:
                    out["eps_growth"] = (out["eps"]/out["eps_prev"]-1)*100

    rev_ok = finite(out["revenue_yoy"]) and finite(out["revenue_3m_yoy"]) and out["revenue_yoy"] >= 10 and out["revenue_3m_yoy"] >= 10
    eps_known = finite(out["eps"])
    eps_ok = eps_known and out["eps"] > 0 and (not finite(out["eps_growth"]) or out["eps_growth"] >= 0)

    if rev_ok and eps_ok:
        out["pass"] = True
        out["confidence"] = "高"
        out["note"] = "營收YoY與EPS同向成長"
    elif rev_ok and not eps_known and out["revenue_yoy"] >= 15 and out["revenue_3m_yoy"] >= 15:
        out["pass"] = True
        out["confidence"] = "中"
        out["note"] = "營收成長強，但EPS資料暫未取得"
    elif rev_ok:
        out["confidence"] = "中"
        out["note"] = "營收成長，EPS尚未同步確認"

    return out


def _backtest_signals(d):
    """用與即時分類相同的核心技術條件回測，避免即時一套、回測另一套。"""
    x = d.copy().reset_index(drop=True)
    for k in [5,10,20,60]:
        x[f"ma{k}"] = x["close"].rolling(k).mean()
    x["v20"] = x["volume"].rolling(20).mean()
    x["vr"] = x["volume"] / x["v20"].replace(0,np.nan)
    x["hi20"] = x["max"].rolling(20).max()
    x["lo20"] = x["min"].rolling(20).min()
    x["hi40"] = x["max"].rolling(40).max()
    x["hi60"] = x["max"].rolling(60).max()
    x["r20"] = (x["close"]/x["close"].shift(20)-1)*100
    x["r40"] = (x["close"]/x["close"].shift(40)-1)*100
    x["r60"] = (x["close"]/x["close"].shift(60)-1)*100
    x["prior20"] = (x["close"].shift(1)/x["close"].shift(21)-1)*100
    x["daychg"] = (x["close"]/x["close"].shift(1)-1)*100
    x["from_hi40"] = (x["close"]/x["hi40"]-1)*100
    x["from_hi60"] = (x["close"]/x["hi60"]-1)*100
    x["range20"] = (x["hi20"]-x["lo20"]) / x["lo20"].replace(0,np.nan) * 100
    x["bias20"] = (x["close"]/x["ma20"]-1)*100
    x["bias60"] = (x["close"]/x["ma60"]-1)*100
    x["ma20_slope10"] = (x["ma20"]/x["ma20"].shift(10)-1)*100

    e12=x["close"].ewm(span=12,adjust=False).mean()
    e26=x["close"].ewm(span=26,adjust=False).mean()
    hist=(e12-e26)-(e12-e26).ewm(span=9,adjust=False).mean()

    ma5 = x["ma5"]
    prev_below5 = pd.Series(False,index=x.index)
    for shift_n in range(1,6):
        prev_below5 = prev_below5 | (x["close"].shift(shift_n) < ma5.shift(shift_n))

    sig = {}
    sig["⑦跌深轉折"] = (
        ((x["r60"]<=-20)|(x["from_hi60"]<=-25))
        & (x["close"]>x["ma20"])
        & x["bias20"].between(-3,10)
        & (x["vr"]>=1.60)
        & (hist>=hist.shift(1)) & (x["daychg"]>0)
    )
    sig["②盤整待突破"] = (
        (x["range20"]<=15) & (x["r20"].abs()<=12)
        & (x["bias20"].abs()<=8) & (x["close"]>=x["hi20"]*.955)
        & x["vr"].between(.9,2.0) & (x["daychg"]<6)
    )
    sig["⑧整理轉強"] = (
        (x["close"]>x["ma60"]) & (x["close"]>x["ma20"])
        & (x["ma20_slope10"]>0)
        & (x["r40"]<20) & (x["r20"]<12)
        & (x["bias20"]<7) & (x["bias60"]<12)
        & (x["range20"]<=16) & x["vr"].between(.9,1.7)
        & (x["daychg"]<6)
    )
    x["bigup5"] = (
        (x["daychg"]>=5).astype(int)
        .rolling(5, min_periods=1).sum()
    )
    sig["③剛起動"] = (
        (x["prior20"]<12) & (x["r40"]<22)
        & (x["bigup5"]<=1)
        & (x["vr"]>=1.35) & (x["close"]>=x["hi20"]*.97)
        & (x["daychg"]>=1.5)
    )
    sig["①強勢熱門"] = (
        (x["ma5"]>x["ma10"])&(x["ma10"]>x["ma20"])&(x["close"]>x["ma20"])
        & x["r20"].between(5,28) & (x["bias20"]<=12)
        & (x["vr"]>=1.15) & (x["close"]>=x["hi20"]*.95)
    )
    sig["④強勢股拉回"] = (
        (x["r40"]>=28) & x["from_hi40"].between(-16,-2)
        & (x["close"]>x["ma20"]) & (x["vr"]<=1.55)
        & (prev_below5 | (x["bias20"].abs()<=4))
    )
    sig["⑥強勢噴出"] = (
        (x["r40"]>=25) & (x["close"]>=x["hi40"]*.98)
        & ((x["vr"]>=1.25)|(x["bias20"]>=12)|(x["daychg"]>=6))
    )
    return x, sig


def backtest_one_history(raw):
    """回傳各策略訊號後 1/5/10 日績效與10日最大不利幅度。"""
    if raw is None or len(raw) < 90:
        return []
    x, sigs = _backtest_signals(raw)
    rows = []
    for name, mask in sigs.items():
        idxs = np.where(mask.fillna(False).to_numpy())[0]
        for i in idxs:
            if i + 10 >= len(x):
                continue
            entry = float(x.loc[i,"close"])
            if not finite(entry) or entry <= 0:
                continue
            r1 = (float(x.loc[i+1,"close"])/entry-1)*100
            r5 = (float(x.loc[i+5,"close"])/entry-1)*100
            r10 = (float(x.loc[i+10,"close"])/entry-1)*100
            future_low = pd.to_numeric(x.loc[i+1:i+10,"min"],errors="coerce").min()
            mae10 = (float(future_low)/entry-1)*100 if finite(future_low) else np.nan
            rows.append({"策略":name,"1日":r1,"5日":r5,"10日":r10,"MAE10":mae10})
    return rows


def backtest_summary(details):
    all_rows = []
    for a in details.values():
        try:
            all_rows.extend(backtest_one_history(a.get("data")))
        except Exception:
            pass
    if not all_rows:
        return pd.DataFrame()
    d = pd.DataFrame(all_rows)
    out = []
    order = ["①強勢熱門","②盤整待突破","③剛起動","④強勢股拉回","⑤營運成長潛力","⑥強勢噴出","⑦跌深轉折","⑧整理轉強"]
    for name in order:
        z = d[d["策略"]==name]
        if z.empty:
            out.append({"策略":name,"樣本數":0,"隔日勝率%":np.nan,"5日勝率%":np.nan,"10日勝率%":np.nan,"平均5日%":np.nan,"平均10日%":np.nan,"10日最大不利%":np.nan})
            continue
        out.append({
            "策略":name,
            "樣本數":len(z),
            "隔日勝率%":float((z["1日"]>0).mean()*100),
            "5日勝率%":float((z["5日"]>0).mean()*100),
            "10日勝率%":float((z["10日"]>0).mean()*100),
            "平均5日%":float(z["5日"].mean()),
            "平均10日%":float(z["10日"].mean()),
            "10日最大不利%":float(z["MAE10"].min()) if z["MAE10"].notna().any() else np.nan,
        })
    return pd.DataFrame(out)

def grade_for(score):
    if score >= 90: return "S"
    if score >= 80: return "A+"
    if score >= 70: return "A"
    if score >= 60: return "A-"
    if score >= 50: return "B"
    return "C"

def risk_class(v):
    if not finite(v): return ""
    return "risk-low" if float(v) <= 30 else "risk-mid" if float(v) <= 60 else "risk-high"

def f1(v, dash="-"):
    return dash if not finite(v) else f"{float(v):.1f}"

def f2(v, dash="-"):
    return dash if not finite(v) else f"{float(v):.2f}"

def money_yi(v):
    return "-" if not finite(v) else f"{float(v)/1e8:.1f}"

def signed_pct(v):
    return "-" if not finite(v) else f"{float(v):+.2f}%"

def price2(v):
    return "-" if not finite(v) else f"{float(v):,.2f}"


@st.cache_data(ttl=600, show_spinner=False)
def taiex_history():
    """台股加權指數 ^TWII，失敗回空表，避免影響個股掃描。"""
    for host in YAHOO_HOSTS:
        try:
            r = requests.get(
                f"{host}/%5ETWII",
                params={"range":"1y","interval":"1d","includePrePost":"false"},
                headers=HEAD, timeout=20
            )
            if r.status_code != 200:
                continue
            j = r.json()
            result = j.get("chart", {}).get("result")
            if not result:
                continue
            z = result[0]
            ts = z.get("timestamp") or []
            q = (z.get("indicators", {}).get("quote") or [{}])[0]
            L = len(ts)
            if L < 60:
                continue
            def arr(k):
                a = q.get(k) or []
                return (a + [None]*L)[:L]
            d = pd.DataFrame({
                "date": pd.to_datetime(ts, unit="s", utc=True).tz_convert("Asia/Taipei").tz_localize(None),
                "open": arr("open"),
                "max": arr("high"),
                "min": arr("low"),
                "close": arr("close"),
                "volume": arr("volume"),
            })
            for c in ["open","max","min","close","volume"]:
                d[c] = pd.to_numeric(d[c], errors="coerce")
            d = d.dropna(subset=["open","max","min","close"]).sort_values("date").reset_index(drop=True)
            if len(d) >= 60:
                return d
        except Exception:
            continue
    return pd.DataFrame()

@st.cache_data(ttl=600, show_spinner=False)
def twse_foreign_flow():
    """TWSE 三大法人：外資及陸資(不含外資自營商)買進、賣出、買賣超。"""
    urls = [
        "https://www.twse.com.tw/rwd/zh/fund/BFI82U?response=json",
        "https://www.twse.com.tw/fund/BFI82U?response=json",
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=HEAD, timeout=20)
            if r.status_code != 200:
                continue
            j = r.json()
            for row in j.get("data", []):
                name = str(row[0]).replace(" ", "")
                if "外資及陸資" in name and "自營商" not in name:
                    nums = []
                    for x in row[1:]:
                        try:
                            nums.append(float(str(x).replace(",", "")))
                        except Exception:
                            nums.append(np.nan)
                    return {
                        "buy": nums[0] if len(nums) > 0 else np.nan,
                        "sell": nums[1] if len(nums) > 1 else np.nan,
                        "net": nums[-1] if nums else np.nan,
                        "date": j.get("date", "")
                    }
        except Exception:
            continue
    return {"buy":np.nan, "sell":np.nan, "net":np.nan, "date":""}

def taiex_levels(d):
    if d is None or d.empty or len(d) < 60:
        return {}
    x = d.copy()
    x["ma20"] = x["close"].rolling(20).mean()
    x["ma60"] = x["close"].rolling(60).mean()
    c = float(x["close"].iloc[-1])
    prev = float(x["close"].iloc[-2])
    vals = [
        float(x["min"].tail(20).min()),
        float(x["min"].tail(60).min()),
        float(x["ma20"].iloc[-1]),
        float(x["ma60"].iloc[-1]),
        float(x["max"].tail(20).max()),
        float(x["max"].tail(60).max()),
    ]
    supports = sorted({round(v,2) for v in vals if finite(v) and v < c}, reverse=True)
    resist = sorted({round(v,2) for v in vals if finite(v) and v > c})
    return {
        "close": c,
        "chg_pct": ((c/prev)-1)*100 if prev else np.nan,
        "s1": supports[0] if supports else np.nan,
        "s2": supports[1] if len(supports)>1 else np.nan,
        "r1": resist[0] if resist else np.nan,
        "r2": resist[1] if len(resist)>1 else np.nan,
    }

def billion(v):
    return "-" if not finite(v) else f"{float(v)/1e8:,.1f} 億"

st.markdown("""
<style>
:root{
  --bg:#07111d;--panel:#091827;--panel2:#0c1e30;--line:#25435f;--line2:#28577c;
  --text:#ecf4fb;--muted:#94a9bc;--blue:#2d9dff;--green:#61d78c;--yellow:#f2b238;
  --orange:#ff9c42;--red:#ff625f;
}
.stApp{background:radial-gradient(circle at top left,#0c1b32 0%,#07111d 44%,#050b12 100%);color:var(--text)}
.block-container{max-width:1520px;padding-top:.45rem;padding-left:.65rem;padding-right:.65rem;padding-bottom:2rem}
[data-testid="stHeader"]{background:transparent}
[data-testid="stSidebar"]{display:none}
.stButton>button{min-height:43px;border-radius:7px;border:1px solid #2575bb;background:#0d2b4a;color:#edf7ff;font-weight:850}
.stButton>button:hover{border-color:#55b4ff;color:#fff}
.hero{background:#081421;border:1px solid #203a55;border-radius:8px;padding:13px 15px;margin:5px 0 8px}
.hero-title{font-size:31px;font-weight:950;line-height:1.05}.hero-title .pro{color:#ffc04a}
.hero-sub{font-size:14px;color:#bdcddd;margin-top:5px}
.nav{display:grid;grid-template-columns:repeat(5,1fr);border:1px solid #203b58;border-radius:7px;overflow:hidden;margin:0 0 10px}
.nav div{background:#0a1724;padding:11px 5px;text-align:center;color:#d2dee9;font-weight:800;border-right:1px solid #203b58}
.nav div:first-child{color:#5fb7ff;background:#0d2945;box-shadow:inset 0 0 0 1px #2b86d1}.nav div:last-child{border-right:0}
.panel{background:#071522;border:1px solid #203b58;border-radius:8px;padding:11px 12px;margin:9px 0}
.panel-title{color:#51adf5;font-size:18px;font-weight:900;margin-bottom:10px}
.overview{display:grid;grid-template-columns:repeat(5,minmax(160px,1fr));gap:9px}
.ov{background:linear-gradient(180deg,#0a1928,#08141f);border:1px solid #27425d;border-radius:7px;text-align:center;padding:15px 9px;min-height:120px}
.ov .t{font-size:14px;color:#d2dde7}.ov .v{font-size:31px;font-weight:950;margin-top:10px}.ov .s{font-size:13px;margin-top:5px;color:#9cb0c2}
.ov.green .v,.ov.green .s{color:#67dc88}.ov.orange .v,.ov.orange .s{color:#f5aa37}.ov.red{border-color:#b33d40;box-shadow:inset 0 0 0 1px #8a2d30}.ov.red .v,.ov.red .s{color:#ff6c62}
.filter-head{color:#4fa9ee;font-size:17px;font-weight:900}
.table-wrap{overflow-x:auto;background:#06131f;border:1px solid #25445f;border-radius:7px}
.stock-table{border-collapse:collapse;width:100%;min-width:1500px;font-size:12px}
.stock-table th{background:#0e2235;color:#e6eef5;padding:8px 5px;border-right:1px solid #294a66;border-bottom:1px solid #2a506e;white-space:nowrap}
.stock-table td{padding:8px 5px;text-align:center;border-right:1px solid #1c3449;border-bottom:1px solid #183047;color:#e9f0f7;white-space:nowrap}
.stock-table tr:hover td{background:#0a1d2e}
.rank{font-weight:900}.code{color:#74bbff;font-weight:900}.price{color:#ffc052;font-weight:900}.up{color:#ff7770;font-weight:900}.down{color:#61d78c;font-weight:900}
.volr{color:#ff8556;font-weight:850}.risk-low{color:#69dc8d;font-weight:950}.risk-mid{color:#f1b13c;font-weight:950}.risk-high{color:#ff645e;font-weight:950}.rr{color:#f6a33e;font-weight:900}.grade{font-weight:950}
.legend-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:9px;margin-top:10px}
.legend{background:#071522;border:1px solid #203b58;border-radius:7px;padding:12px 13px;min-height:225px}.legend h4{color:#54aff4;margin:0 0 9px;font-size:17px}.legend p{color:#c7d4df;font-size:13px;line-height:1.5;margin:6px 0}
.detail-grid{display:grid;grid-template-columns:1.5fr .9fr .9fr .9fr;gap:9px}.detail-box{background:#071522;border:1px solid #203b58;border-radius:7px;padding:11px}.detail-box h4{color:#54aff4;margin:0 0 8px}.detail-box p{color:#c8d5df;font-size:13px;line-height:1.55;margin:6px 0}
.note{text-align:center;color:#94a9ba;font-size:12px;margin-top:12px}
@media(max-width:900px){
 .overview{grid-template-columns:repeat(2,1fr)} .legend-grid{grid-template-columns:1fr} .detail-grid{grid-template-columns:1fr}
 .nav{grid-template-columns:1fr 1fr}.nav div{border-bottom:1px solid #203b58}.hero-title{font-size:27px}
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
 <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap">
  <div><div class="hero-title">🥷 賊大戰術 <span class="pro">Pro</span></div><div class="hero-sub">全市場智能選股系統（上市＋上櫃）</div></div>
  <div style="color:#a1b3c4;font-size:13px">資料時間：盤後最新資料</div>
 </div>
</div>
<div class="nav">
 <div>🚀 全市場掃描</div><div>📊 大盤儀表板</div><div>◎ 自選股監控</div><div>⚙ 系統設定</div><div>❔ 使用說明</div>
</div>
""", unsafe_allow_html=True)

st.markdown(
    """<div class="navbar">
      <div class="navitem active">🚀 全市場掃描</div>
      <div class="navitem">📊 大盤儀表板</div>
      <div class="navitem">◎ 自選股監控</div>
      <div class="navitem">⚙ 系統設定</div>
      <div class="navitem">❔ 使用說明</div>
    </div>""",
    unsafe_allow_html=True
)


# ===== 大盤儀表板：支撐 / 壓力 / 外資買賣 =====
_mkt = taiex_history()
_lv = taiex_levels(_mkt)
_fx = twse_foreign_flow()

st.markdown('<div class="panel"><div class="panel-title">📊 大盤儀表板</div>', unsafe_allow_html=True)

if _lv:
    _net = _fx.get("net", np.nan)
    _net_word = "買超" if finite(_net) and _net >= 0 else "賣超"
    _net_color = "#ff6b70" if finite(_net) and _net >= 0 else "#56d388"

    st.markdown(
        f'<div class="overview">'
        f'<div class="ov"><div class="k">加權指數</div><div class="v">{_lv["close"]:,.2f}</div><div class="s">{_lv["chg_pct"]:+.2f}%</div></div>'
        f'<div class="ov"><div class="k">支撐 1</div><div class="v" style="color:#54d78a">{price2(_lv["s1"])}</div><div class="s">最近支撐</div></div>'
        f'<div class="ov"><div class="k">支撐 2</div><div class="v" style="color:#54d78a">{price2(_lv["s2"])}</div><div class="s">第二支撐</div></div>'
        f'<div class="ov"><div class="k">壓力 1</div><div class="v" style="color:#ffb14a">{price2(_lv["r1"])}</div><div class="s">最近壓力</div></div>'
        f'<div class="ov"><div class="k">壓力 2</div><div class="v" style="color:#ff6b70">{price2(_lv["r2"])}</div><div class="s">第二壓力</div></div>'
        f'</div>',
        unsafe_allow_html=True
    )

    if finite(_net):
        st.markdown(
            f'<div class="detail-box" style="margin-top:9px">'
            f'<h4>🌐 外資買賣（上市）</h4>'
            f'<p>外資今日：<b style="color:{_net_color};font-size:20px">{_net_word} {abs(float(_net))/1e8:,.1f} 億</b></p>'
            f'<p>買進：{billion(_fx.get("buy"))}　｜　賣出：{billion(_fx.get("sell"))}</p>'
            f'</div>',
            unsafe_allow_html=True
        )
    else:
        st.info("外資買賣資料目前未取得。")

    try:
        _p = _mkt.tail(90).copy()
        fig_idx = go.Figure()
        fig_idx.add_trace(go.Candlestick(
            x=_p["date"], open=_p["open"], high=_p["max"],
            low=_p["min"], close=_p["close"], name="TAIEX"
        ))
        for _name, _val in [("支撐1",_lv["s1"]),("支撐2",_lv["s2"]),("壓力1",_lv["r1"]),("壓力2",_lv["r2"])]:
            if finite(_val):
                fig_idx.add_hline(y=float(_val), line_dash="dot",
                                  annotation_text=f"{_name} {float(_val):,.0f}")
        fig_idx.update_layout(
            height=330, margin=dict(l=8,r=8,t=28,b=8),
            paper_bgcolor="#071522", plot_bgcolor="#071522",
            font=dict(color="#dce9f4"), xaxis_rangeslider_visible=False,
            title="加權指數近 90 日｜支撐 / 壓力"
        )
        fig_idx.update_xaxes(gridcolor="#173248")
        fig_idx.update_yaxes(gridcolor="#173248")
        st.plotly_chart(fig_idx, use_container_width=True)
    except Exception:
        pass
else:
    st.info("目前沒有取得加權指數資料；不影響個股全市場掃描。")

st.markdown("</div>", unsafe_allow_html=True)


# Scan filters - shaped like the mockup.
st.markdown('<div class="panel"><div class="filter-head">初篩條件 <span style="font-size:12px;color:#9fb1c2">（可調整）</span></div></div>', unsafe_allow_html=True)
col_money,col_price,col_day,col_month,col_season,col_kd = st.columns(6)
min_money = col_money.selectbox("成交金額", [0.5,1.0,2.0,5.0], index=1, format_func=lambda x:f"≥ {x:g} 億")
min_price = col_price.selectbox("股價", [5.0,10.0,20.0,50.0], index=0, format_func=lambda x:f"≥ {x:g} 元")
min_day = col_day.selectbox("日漲跌幅", [0.0,1.0,2.0,3.0], index=1, format_func=lambda x:f"≥ {x:g}%")
min_month = col_month.selectbox("月漲跌幅", [0.0,3.0,5.0,10.0], index=2, format_func=lambda x:f"≥ {x:g}%")
season_rule = col_season.selectbox("季線位置", ["不限","站上季線"], index=1)
kd_rule = col_kd.selectbox("KD 指標", ["不限","KD 黃金交叉"], index=1)

scan = st.button("🔍 執行全市場掃描", type="primary", use_container_width=True)

if scan:
    snap, warnings = snapshot()
    for w in warnings:
        st.warning(w)

    if snap.empty:
        st.error("TWSE/TPEx 官方行情目前沒有取得。")
    else:
        for _c in ["close","volume","value","change"]:
            snap[_c] = pd.to_numeric(snap[_c], errors="coerce")
        snap["close"] = snap["close"].fillna(0.0)
        snap["volume"] = snap["volume"].fillna(0.0)
        snap["value"] = snap["value"].fillna(0.0)
        snap["change"] = snap["change"].fillna(0.0)

        snap["lots"] = snap["volume"]/1000.0
        snap["activity"] = np.where(
            snap["value"] > 0,
            snap["value"],
            snap["volume"] * snap["close"]
        ).astype(float)
        snap["chg_pct"] = (
            pd.to_numeric(snap["change"],errors="coerce").fillna(0) /
            snap["close"].replace(0,np.nan) * 100
        ).replace([np.inf,-np.inf],np.nan).fillna(0)

        # Official snapshot filters that can be applied across the whole market.
        snap = snap[
            (snap["close"] >= min_price)
            & (snap["activity"] >= min_money*1e8)
            & (snap["chg_pct"] >= min_day)
        ].copy()

        if snap.empty:
            st.warning("目前沒有股票通過初篩條件。")
        else:
            # Rank broad market first; then deep-analyze the strongest 35 so month/MA/KD conditions can be used.
            snap["broad_score"] = (
                45
                + snap["activity"].rank(pct=True)*25
                + snap["lots"].rank(pct=True)*15
                + snap["chg_pct"].clip(-10,10)*1.5
            ).clip(0,100)
            snap = snap.sort_values(["broad_score","activity"],ascending=False).reset_index(drop=True)

            target = snap.head(min(60,len(snap)))
            details, inst, fundamentals, shorts, chips = {}, {}, {}, {}, {}
            bar = st.progress(0,text="進行賊大①～⑧與技術分析…")
            for i,z in enumerate(target.itertuples(index=False)):
                try:
                    h = hist(z.stock_id,z.market)
                    h = merge_today_bar(h, z) if not h.empty else h
                    a = analyze(h) if not h.empty else None
                    if a is not None:
                        # 賊大①～⑧分類必須先完整保留，不能被全域月漲幅/季線/KD先刪掉，
                        # 否則④拉回與⑦跌深轉折會被系統性漏掉。
                        fund = fundamental_growth(z.stock_id)
                        sh = short_interest_5d(z.stock_id)
                        cp = chip_detail_5d(z.stock_id)

                        # ⑤營運成長：基本面獨立成立，不拿技術面冒充。
                        if fund.get("pass") and "⑤營運成長潛力" not in a["zeida_tags"]:
                            a["zeida_tags"].append("⑤營運成長潛力")

                        a["short_balance"] = sh.get("balance", np.nan)
                        a["short_change5"] = sh.get("change5", np.nan)
                        a["foreign5"] = cp.get("foreign", 0.0)
                        a["trust5"] = cp.get("trust", 0.0)
                        a["dealer5"] = cp.get("dealer", 0.0)
                        a["fundamental"] = fund

                        # ⑧原圖要求「融券增加」：若融券資料有取得但沒有增加，移除⑧。
                        if "⑧整理轉強" in a["zeida_tags"] and finite(a["short_change5"]) and a["short_change5"] <= 0:
                            a["zeida_tags"].remove("⑧整理轉強")

                        # ⑥標記是否有軋空跡象；沒有融券資料時只當「強勢噴出」，不硬說軋空。
                        a["squeeze_confirmed"] = bool(
                            "⑥強勢噴出" in a["zeida_tags"]
                            and finite(a["short_balance"])
                            and a["short_balance"] > 0
                        )

                        # 防呆：③不能是已經連續發動多日的股票。
                        _a_data = a.get("data")
                        if _a_data is not None and not _a_data.empty and "③剛起動" in a["zeida_tags"]:
                            _recent_chg = _a_data["close"].pct_change().tail(5) * 100
                            if int((_recent_chg >= 5).sum()) >= 2:
                                a["zeida_tags"].remove("③剛起動")
                                if "①強勢熱門" not in a["zeida_tags"] and "⑥強勢噴出" not in a["zeida_tags"]:
                                    a["zeida_tags"].append("①強勢熱門")

                        # 防呆：⑧整理轉強不允許當日已經大漲 ≥6%。
                        # 新規則正常情況下本來就不會進⑧；這裡防止舊/異常資料污染。
                        _today_chg = float(z.chg_pct) if finite(z.chg_pct) else np.nan
                        if "⑧整理轉強" in a["zeida_tags"] and finite(_today_chg) and _today_chg >= 6:
                            a["zeida_tags"].remove("⑧整理轉強")
                            if "⑥強勢噴出" not in a["zeida_tags"]:
                                a["zeida_tags"].append("⑥強勢噴出")

                        # 防呆：⑦跌深轉折如果已經明顯高於20MA超過15%，不再視為「底部剛發動」。
                        if "⑦跌深轉折" in a["zeida_tags"] and finite(a.get("bias20")) and a["bias20"] > 15:
                            a["zeida_tags"].remove("⑦跌深轉折")

                        # 重新決定主階段
                        _prio = ["⑥強勢噴出","④強勢股拉回","③剛起動","⑦跌深轉折","①強勢熱門","⑧整理轉強","②盤整待突破","⑤營運成長潛力"]
                        a["primary_stage"] = next((x for x in _prio if x in a["zeida_tags"]), a.get("primary_stage"))

                        # 使用者畫面上的可調條件只影響「強勢排行」，不影響賊大分類是否被保留。
                        a["ui_filter_pass"] = (
                            ((not finite(a["r20"])) or a["r20"] >= min_month)
                            and (season_rule=="不限" or bool(a["ma60_up"]))
                            and (kd_rule=="不限" or bool(a["kd_golden"]))
                        )

                        details[z.stock_id] = a
                        inst[z.stock_id] = cp.get("total", 0.0)
                        fundamentals[z.stock_id] = fund
                        shorts[z.stock_id] = sh
                        chips[z.stock_id] = cp
                except:
                    pass
                bar.progress((i+1)/max(len(target),1),text=f"深度分析 {i+1}/{len(target)}")
                time.sleep(.04)
            bar.empty()

            # Prefer full analyses; keep fallback rows so Top 10 still appears.
            scored=[]
            for z in snap.itertuples(index=False):
                a=details.get(z.stock_id)
                if a:
                    tech = min(60, round(a["score"]*0.60,1))
                    chip_raw = inst.get(z.stock_id,0.0)
                    chip = 20.0 if chip_raw>0 else 10.0 if chip_raw==0 else 4.0
                    risk_bonus = max(0,20-a["risk"]*0.20)
                    final = tech+chip+risk_bonus
                else:
                    final = (float(z.broad_score) if finite(z.broad_score) else 0.0)*0.72
                scored.append(final)
            snap["final_score"]=scored
            snap=snap.sort_values(["final_score","activity"],ascending=False).reset_index(drop=True)

            st.session_state["snap"]=snap
            st.session_state["details"]=details
            st.session_state["inst"]=inst
            st.session_state["fundamentals"]=fundamentals
            st.session_state["shorts"]=shorts
            st.session_state["chips"]=chips

if "snap" in st.session_state:
    snap=st.session_state["snap"]
    details=st.session_state.get("details",{})
    inst=st.session_state.get("inst",{})
    fundamentals=st.session_state.get("fundamentals",{})
    shorts=st.session_state.get("shorts",{})
    chips=st.session_state.get("chips",{})
    _ranked_all = snap.copy()
    _show_n = st.selectbox(
        "強勢股顯示數量",
        [10, 20, 50, "全部"],
        index=0,
        key="top_show_n",
        help="Top 10 只是精選；可切換看 20、50 或全部候選股。"
    )
    top = _ranked_all.copy() if _show_n == "全部" else _ranked_all.head(int(_show_n)).copy()
    for _c in ["close","chg_pct","activity","final_score"]:
        if _c in top.columns:
            top[_c] = pd.to_numeric(top[_c], errors="coerce")

    market_all,_=snapshot()
    total=len(market_all)
    qualified=len(snap)
    full=len(details)
    strong=sum(1 for k,v in details.items() if finite(v.get("score")) and float(v.get("score"))>=80)

    st.markdown('<div class="panel"><div class="panel-title">市場總覽</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="overview">
      <div class="ov"><div class="t">上市＋上櫃 總檔數</div><div class="v">{total:,}</div><div class="s">全市場股票</div></div>
      <div class="ov green"><div class="t">符合初篩檔數</div><div class="v">{qualified}</div><div class="s">{qualified/max(total,1)*100:.1f}%</div></div>
      <div class="ov orange"><div class="t">進入賊大①～⑧檔數</div><div class="v">{full}</div><div class="s">{full/max(total,1)*100:.1f}%</div></div>
      <div class="ov orange"><div class="t">強勢候選檔數</div><div class="v">{strong}</div><div class="s">深度分析80分以上</div></div>
      <div class="ov red"><div class="t">🔥 Top 10 推薦</div><div class="v">{len(top)}</div><div class="s">🏆 今日精選</div></div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # ===== 賊大選股：直接把 8 大條件的股票全部選出來 =====
    st.caption(f"選股邏輯版本：{APP_LOGIC_VERSION}")
    st.markdown(
        '<div class="panel"><div class="panel-title">🥷 賊大選股 '
        '<span style="font-size:12px;color:#9fb1c2">（直接掃出條件一～八）</span></div>',
        unsafe_allow_html=True
    )

    zeida_labels = [
        "① 強勢熱門小型股",
        "② 盤整待突破股",
        "③ 剛起動的中小型股",
        "④ 強勢股拉回股",
        "⑤ 營運成長潛力股",
        "⑥ 強勢噴出股（軋空中）",
        "⑦ 跌深轉折出量股",
        "⑧ 整理轉強股（軋空前）",
    ]

    # 對應 analyze() 內部標籤
    tag_map = {
        "① 強勢熱門小型股": "①強勢熱門",
        "② 盤整待突破股": "②盤整待突破",
        "③ 剛起動的中小型股": "③剛起動",
        "④ 強勢股拉回股": "④強勢股拉回",
        "⑤ 營運成長潛力股": "⑤營運成長潛力",
        "⑥ 強勢噴出股（軋空中）": "⑥強勢噴出",
        "⑦ 跌深轉折出量股": "⑦跌深轉折",
        "⑧ 整理轉強股（軋空前）": "⑧整理轉強",
    }

    category_rows = {label: [] for label in zeida_labels}

    _zeida_show_n = st.selectbox(
        "每個賊大條件顯示數量",
        [5, 10, 20, "全部"],
        index=1,
        key="zeida_show_n",
        help="每個條件可直接看 5、10、20 或全部符合股票。"
    )

    # 直接依目前深度分析結果分桶，不再要求使用者自己選條件
    for z in snap.itertuples(index=False):
        a = details.get(z.stock_id)
        if not a:
            continue

        tags = a.get("zeida_tags", [])
        primary = a.get("primary_stage")
        for label in zeida_labels:
            target_tag = tag_map[label]
            # ⑤是獨立基本面條件可額外顯示；其他①②③④⑥⑦⑧只放主階段，避免重複誤導。
            if target_tag == "⑤營運成長潛力":
                if target_tag not in tags:
                    continue
            else:
                if primary != target_tag:
                    continue

            category_rows[label].append({
                "代號": str(z.stock_id),
                "名稱": str(z.stock_name),
                "股價": float(z.close) if finite(z.close) else np.nan,
                "漲跌幅%": float(z.chg_pct) if finite(z.chg_pct) else np.nan,
                "成交金額(億)": float(z.activity)/1e8 if finite(z.activity) else np.nan,
                "綜合分": float(z.final_score) if finite(z.final_score) else 0.0,
                "風險": int(a["risk"]) if finite(a.get("risk")) else None,
                "風報比": round(float(a["rr"]), 2) if finite(a.get("rr")) else None,
                "型態": a.get("pattern", "-"),
                "外資5日": round(float(a.get("foreign5",0.0)),0) if finite(a.get("foreign5",0.0)) else 0,
                "融券5日變化": round(float(a.get("short_change5",np.nan)),0) if finite(a.get("short_change5",np.nan)) else np.nan,
                "營收YoY%": round(float(a.get("fundamental",{}).get("revenue_yoy",np.nan)),1) if finite(a.get("fundamental",{}).get("revenue_yoy",np.nan)) else np.nan,
                "EPS": round(float(a.get("fundamental",{}).get("eps",np.nan)),2) if finite(a.get("fundamental",{}).get("eps",np.nan)) else np.nan,
            })


    # 每個條件直接顯示最強前 5 檔
    for label in zeida_labels:
        rows = category_rows[label]

        st.markdown(
            f'<div style="margin-top:14px;font-size:18px;font-weight:700">{label}</div>',
            unsafe_allow_html=True
        )

        if not rows:
            st.caption("目前沒有符合條件的股票。")
            continue

        df_cat = pd.DataFrame(rows)
        df_cat = df_cat.sort_values(
            ["綜合分", "風報比", "成交金額(億)"],
            ascending=[False, False, False]
        )
        if _zeida_show_n != "全部":
            df_cat = df_cat.head(int(_zeida_show_n))

        st.dataframe(
            df_cat,
            use_container_width=True,
            hide_index=True,
            column_config={
                "股價": st.column_config.NumberColumn(format="%.2f"),
                "漲跌幅%": st.column_config.NumberColumn(format="%+.2f%%"),
                "成交金額(億)": st.column_config.NumberColumn(format="%.1f"),
                "綜合分": st.column_config.NumberColumn(format="%.1f"),
                "風報比": st.column_config.NumberColumn(format="%.2f"),
                "外資5日": st.column_config.NumberColumn(format="%.0f"),
                "融券5日變化": st.column_config.NumberColumn(format="%.0f"),
                "營收YoY%": st.column_config.NumberColumn(format="%.1f"),
                "EPS": st.column_config.NumberColumn(format="%.2f"),
            },
        )
        st.caption(f"符合 {len(rows)} 檔，目前顯示 {len(df_cat)} 檔。")


    # ② / ③ 接近成立候選
    near_rows = []
    for z in snap.itertuples(index=False):
        a = details.get(z.stock_id)
        if not a:
            continue
        for tag in a.get("near_tags", []):
            near_rows.append({
                "狀態": tag,
                "代號": str(z.stock_id),
                "名稱": str(z.stock_name),
                "股價": float(z.close) if finite(z.close) else np.nan,
                "漲跌幅%": float(z.chg_pct) if finite(z.chg_pct) else np.nan,
                "成交金額(億)": float(z.activity)/1e8 if finite(z.activity) else np.nan,
                "綜合分": float(z.final_score) if finite(z.final_score) else 0.0,
                "風險": int(a["risk"]) if finite(a.get("risk")) else None,
                "風報比": round(float(a["rr"]),2) if finite(a.get("rr")) else None,
            })

    if near_rows:
        st.markdown(
            '<div style="margin-top:18px;font-size:18px;font-weight:800;color:#ffbf52">🟡 ②／③ 接近成立候選</div>',
            unsafe_allow_html=True
        )
        near_df = pd.DataFrame(near_rows).sort_values(
            ["狀態","綜合分","風報比"], ascending=[True,False,False]
        )
        st.dataframe(
            near_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "股價": st.column_config.NumberColumn(format="%.2f"),
                "漲跌幅%": st.column_config.NumberColumn(format="%+.2f%%"),
                "成交金額(億)": st.column_config.NumberColumn(format="%.1f"),
                "綜合分": st.column_config.NumberColumn(format="%.1f"),
                "風報比": st.column_config.NumberColumn(format="%.2f"),
            },
        )
        st.caption("黃色候選＝接近條件，但尚未正式成立；避免因規則太嚴完全漏股。")

    st.markdown(
        '<div style="margin-top:14px;font-size:13px;line-height:1.8;color:#9fb1c2">'
        '資金生命週期：⑤ → ② → ⑧ → ③ → ① → ④ → ⑥；⑦為跌深反轉另一條路徑。'
        '</div>',
        unsafe_allow_html=True
    )
    st.markdown("</div>", unsafe_allow_html=True)


    # ===== 策略回測 =====
    st.markdown(
        '<div class="panel"><div class="panel-title">🧪 賊大戰術回測 '
        '<span style="font-size:12px;color:#9fb1c2">（目前深度分析股票的近一年歷史訊號）</span></div>',
        unsafe_allow_html=True
    )
    bt = backtest_summary(details)
    if bt.empty:
        st.info("目前回測樣本不足。")
    else:
        # 樣本太少時不要讓勝率看起來過度精確
        bt_show = bt.copy()
        bt_show["可信度"] = bt_show["樣本數"].apply(
            lambda n: "高" if n >= 50 else "中" if n >= 20 else "低"
        )
        st.dataframe(
            bt_show,
            use_container_width=True,
            hide_index=True,
            column_config={
                "隔日勝率%": st.column_config.NumberColumn(format="%.1f%%"),
                "5日勝率%": st.column_config.NumberColumn(format="%.1f%%"),
                "10日勝率%": st.column_config.NumberColumn(format="%.1f%%"),
                "平均5日%": st.column_config.NumberColumn(format="%+.2f%%"),
                "平均10日%": st.column_config.NumberColumn(format="%+.2f%%"),
                "10日最大不利%": st.column_config.NumberColumn(format="%+.2f%%"),
            }
        )
        valid_bt = bt[bt["樣本數"] >= 10].copy()
        if not valid_bt.empty:
            best5 = valid_bt.sort_values(["5日勝率%","平均5日%"], ascending=False).iloc[0]
            best10 = valid_bt.sort_values(["10日勝率%","平均10日%"], ascending=False).iloc[0]
            st.markdown(
                f'<div class="overview" style="margin-top:8px">'
                f'<div class="ov green"><div class="t">5日勝率最佳</div><div class="v">{best5["策略"]}</div><div class="s">{best5["5日勝率%"]:.1f}%｜樣本 {int(best5["樣本數"])}</div></div>'
                f'<div class="ov orange"><div class="t">10日勝率最佳</div><div class="v">{best10["策略"]}</div><div class="s">{best10["10日勝率%"]:.1f}%｜樣本 {int(best10["樣本數"])}</div></div>'
                f'</div>',
                unsafe_allow_html=True
            )
        st.caption("回測不是未來保證；⑤基本面策略需要完整歷史財報時間對齊，目前只做即時選股，不納入歷史勝率。")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        f'<div class="panel"><div class="panel-title">🏆 強勢股排名 '
        f'<span style="font-size:12px;color:#9fb1c2">（依綜合評分排序｜目前顯示 {len(top)} 檔）</span></div>',
        unsafe_allow_html=True
    )

    trs=[]
    for rank,z in enumerate(top.itertuples(index=False),1):
        a=details.get(z.stock_id)
        inst5=float(inst.get(z.stock_id,0.0)) if finite(inst.get(z.stock_id,0.0)) else 0.0
        z_chg = float(z.chg_pct) if finite(z.chg_pct) else 0.0
        z_final = float(z.final_score) if finite(z.final_score) else 0.0
        z_close = float(z.close) if finite(z.close) else np.nan
        z_activity = float(z.activity) if finite(z.activity) else np.nan
        if a:
            dlast=a["data"].iloc[-1]
            flags=[
                finite(dlast.get("ma5")) and finite(dlast.get("ma10")) and finite(dlast.get("ma20")) and float(dlast["ma5"])>float(dlast["ma10"])>float(dlast["ma20"]),
                bool(a["ma60_up"]),
                finite(a.get("vr")) and float(a.get("vr"))>=1.3,
                bool(a["kd_golden"]),
                finite(a.get("rsi")) and float(a.get("rsi"))>50,
                bool(a["macd_positive"]),
                inst5>0,
                finite(a.get("risk")) and float(a.get("risk"))<=40,
            ]
            flagtxt=" ".join("🟢" if x else "🔴" for x in flags)
            _score=float(a.get("score")) if finite(a.get("score")) else 0.0
            tech=min(60,round(_score*.60,1))
            chip=20.0 if inst5>0 else 10.0 if inst5==0 else 4.0
            bias=a["bias60"]
            s1,s2=a["support"],a["support2"]
            r1,r2=a["resistance"],a["resistance2"]
            risk=a["risk"]; rr=a["rr"]
            grade=grade_for(_score)
            vr=float(a.get("vr")) if finite(a.get("vr")) else np.nan
        else:
            flagtxt="⚪ ⚪ ⚪ ⚪ ⚪ ⚪ ⚪ ⚪"
            tech=round(z_final*.60,1); chip=0.0
            bias=s1=s2=r1=r2=risk=rr=np.nan; grade="觀察"; vr=np.nan

        cls="up" if z_chg >= 0 else "down"
        trs.append(
            f'<tr>'
            f'<td class="rank">{rank}</td><td class="code">{z.stock_id}</td><td>{z.stock_name}</td>'
            f'<td class="price">{price2(z_close)}</td><td class="{cls}">{signed_pct(z_chg)}</td>'
            f'<td>{money_yi(z_activity)}</td><td class="volr">{f2(vr)}</td>'
            f'<td>{flagtxt}</td><td>{tech:.1f}</td><td>{chip:.1f}</td>'
            f'<td class="volr">{f2(bias)}%</td>'
            f'<td>{f1(s1)}</td><td>{f1(s2)}</td><td>{f1(r1)}</td><td>{f1(r2)}</td>'
            f'<td class="{risk_class(risk)}">{"-" if not finite(risk) else int(risk)}</td>'
            f'<td class="rr">{f2(rr)}</td><td class="grade">{grade}</td>'
            f'</tr>'
        )

    # HTML 前面不能保留 4 個以上空白，否則 Markdown 會把它當成程式碼區塊顯示原始 <td>。
    table_html = (
        '<div class="table-wrap"><table class="stock-table"><thead><tr>'
        '<th>排名</th><th>代號</th><th>名稱</th><th>股價</th><th>漲跌幅</th><th>成交金額(億)</th><th>量比</th>'
        '<th>8項技術/籌碼檢核</th><th>技術分(60%)</th><th>籌碼分(20%)</th><th>乖離率(離季線)</th>'
        '<th>支撐1</th><th>支撐2</th><th>壓力1</th><th>壓力2</th><th>風險係數</th><th>風報比</th><th>評等</th>'
        '</tr></thead><tbody>'
        + ''.join(trs) +
        '</tbody></table></div>'
    )
    st.markdown(table_html, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("""
    <div class="legend-grid">
      <div class="legend"><h4>8項技術／籌碼檢核燈號</h4>
        <p>① 均線多頭排列（短＞中＞長）</p><p>② 股價站上季線</p><p>③ 成交量放大（大於20日均量）</p><p>④ KD 黃金交叉</p>
        <p>⑤ RSI ＞ 50</p><p>⑥ MACD 柱狀體 ＞ 0</p><p>⑦ 法人近5日買超</p><p>⑧ 風險係數 ≤ 40</p>
      </div>
      <div class="legend"><h4>乖離率（離季線）說明</h4>
        <p><span class="red">+5%以上：</span>強勢過熱</p><p><span class="orange">+2%～+5%：</span>偏強</p>
        <p><span class="green">-2%～+2%：</span>合理區間</p><p><span class="orange">-2%～-5%：</span>偏弱</p><p><span class="red">-5%以下：</span>超跌</p>
      </div>
      <div class="legend"><h4>風險係數說明（0～100）</h4>
        <p><span class="green">● 0～30</span>　風險低（安全區）</p><p><span class="orange">● 31～60</span>　風險中（注意區）</p>
        <p><span class="red">● 61～100</span>　風險高（警戒區）</p><p>評估：乖離、爆量、20MA、斜率、RSI、風報比。</p>
      </div>
      <div class="legend"><h4>風報比說明</h4>
        <p>風報比＝預估上漲空間 ÷ 預估下跌風險</p><p>數值越高，報酬相對風險越好。</p>
        <p><span class="green">S 90～100</span> 極強</p><p><span class="orange">A+ 80～89</span> 很強</p><p>A 70～79｜A- 60～69｜B 50～59｜C &lt;50</p>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="panel"><div class="panel-title">個股詳細分析</div>', unsafe_allow_html=True)
    options=[f"{z.stock_id} {z.stock_name}" for z in top.itertuples(index=False)]
    selected=st.selectbox("選擇股票",options,index=0)
    code=selected.split()[0]
    row=top[top["stock_id"]==code].iloc[0]

    if code not in details:
        try:
            with st.spinner("補抓這檔完整歷史資料…"):
                h=hist(code,row["market"])
                a=analyze(h) if not h.empty else None
                if a is not None:
                    details[code]=a
                    inst[code]=institutional_5d(code)
                    st.session_state["details"]=details
                    st.session_state["inst"]=inst
            st.session_state["fundamentals"]=fundamentals
            st.session_state["shorts"]=shorts
            st.session_state["chips"]=chips
        except:
            pass

    if code in details:
        a=details[code]
        left,right=st.columns([1.55,1])
        with left:
            st.plotly_chart(chart(a["data"],code,row["stock_name"]),use_container_width=True)
        with right:
            st.markdown(f"""
            <div class="detail-box"><h4>技術指標</h4>
              <p>型態：{a["pattern"]}</p><p>KD：{"黃金交叉" if a["kd_golden"] else "整理"}</p>
              <p>RSI(14)：{a["rsi"]:.1f}</p><p>量比：{a["vr"]:.2f}x</p>
              <p>MA5：{slope_label(a["s5"])}</p><p>MA20：{slope_label(a["s20"])}</p><p>MA60：{slope_label(a["s60"])}</p>
            </div>
            <div class="detail-box"><h4>支撐 / 壓力</h4>
              <p>支撐1：{f2(a["support"])}</p><p>支撐2：{f2(a["support2"])}</p><p>壓力1：{f2(a["resistance"])}</p><p>壓力2：{f2(a["resistance2"])}</p>
            </div>
            <div class="detail-box"><h4>乖離 / 風險</h4>
              <p>離季線：{f2(a["bias60"])}%</p><p>風險係數：{a["risk"]}/100</p><p>風報比：{f2(a["rr"])}</p>
              <p>法人5日淨額：{inst.get(code,0):,.0f}</p>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("這檔目前無法取得完整歷史 K 線，但 Top 10 排行仍可正常使用。")
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown('<div class="note">＊本系統僅提供盤後研究參考，投資請自行評估風險，盈虧自負。</div>', unsafe_allow_html=True)


st.markdown(r'''
<style>
/* ===== Reference-matched dashboard skin ===== */
:root{
  --bg:#06101a;
  --panel:#0a1622;
  --panel2:#0c1b29;
  --border:#1b3953;
  --border-hi:#235b87;
  --text:#eef5fb;
  --muted:#9cb0c2;
  --blue:#35a7ff;
  --green:#4bd37b;
  --orange:#ffad2f;
  --red:#ff5a5f;
  --yellow:#ffc94d;
}

.stApp{
  background:#06101a!important;
  color:var(--text)!important;
}
.block-container{
  max-width:1420px!important;
  padding:14px 14px 28px!important;
}

/* header */
.hero{
  min-height:72px;
  padding:10px 8px 12px!important;
  border:none!important;
  border-radius:0!important;
  background:transparent!important;
  box-shadow:none!important;
  margin-bottom:4px!important;
}
.hero-left{gap:10px!important}
.hero-icon{font-size:34px!important}
.hero-title{font-size:28px!important;font-weight:900!important;line-height:1!important}
.hero-sub{font-size:13px!important;color:#b8c6d5!important;margin-top:7px!important}
.hero-meta{font-size:12px!important;color:#aebdcc!important}
.hero-title .pro{color:#ffad2f!important}

/* top nav: flatter and more like the reference */
.navbar{
  margin:2px 0 10px!important;
  border:1px solid #1a3550!important;
  border-radius:7px!important;
  background:#091522!important;
}
.navitem{
  padding:10px 8px!important;
  font-size:13px!important;
  background:#0a1724!important;
  border-right:1px solid #18314a!important;
}
.navitem.active{
  color:#57b7ff!important;
  background:#0c2740!important;
  box-shadow:inset 0 0 0 1px #2c8bd0!important;
}

/* section shells */
.section,.panel,.filterbox{
  background:#091521!important;
  border:1px solid #1b3852!important;
  border-radius:8px!important;
  box-shadow:none!important;
}
.section{padding:10px!important;margin:9px 0!important}
.panel{padding:0!important;margin:9px 0!important;overflow:hidden}
.filterbox{padding:10px 10px 4px!important;margin:9px 0!important}
.section-title,.panel-title{
  font-size:16px!important;
  font-weight:800!important;
  color:#48adff!important;
}
.panel-title{
  margin:0!important;
  padding:9px 12px!important;
  border-bottom:1px solid #1b3852!important;
  background:#0a1724!important;
}

/* summary row exactly 5 columns on desktop */
.summary-grid{
  grid-template-columns:repeat(5,1fr)!important;
  gap:8px!important;
}
.summary-card{
  min-height:114px!important;
  padding:12px 10px!important;
  text-align:center!important;
  align-items:center!important;
  border-radius:6px!important;
  background:#0b1825!important;
  border:1px solid #21425e!important;
}
.summary-card .label{font-size:13px!important;color:#d4dee7!important}
.summary-card .big{font-size:30px!important;line-height:1.05!important}
.summary-card .small{font-size:11px!important;color:#a4b5c6!important}
.summary-card.red{border-color:#bd4046!important}
.summary-card.green .big{color:#54db82!important}
.summary-card.orange .big{color:#ffad2f!important}
.summary-card.purple .big{color:#ffb22f!important}
.summary-card.red .big{color:#ff6166!important}
.summary-card.blue .big{color:#ffffff!important}

/* filter inputs */
[data-testid="stSelectbox"] label{font-size:11px!important;color:#b8c6d4!important}
div[data-baseweb="select"]>div{
  min-height:38px!important;
  background:#081522!important;
  border:1px solid #294760!important;
  border-radius:5px!important;
  color:#edf5fb!important;
}
.stButton>button{
  min-height:38px!important;
  border-radius:5px!important;
  background:#157fe0!important;
  border:1px solid #2d9cff!important;
  font-size:13px!important;
  font-weight:800!important;
}

/* top10 table: compact and high-density */
.table-wrap{
  border:none!important;
  border-radius:0!important;
  background:#08131e!important;
}
.stock-table{
  min-width:1320px!important;
  font-size:11px!important;
}
.stock-table th{
  background:#0c1a27!important;
  padding:7px 5px!important;
  border-color:#28445b!important;
  font-weight:800!important;
}
.stock-table td{
  padding:7px 5px!important;
  background:#091521!important;
  border-color:#18344a!important;
}
.stock-table tr:nth-child(even) td{background:#0a1824!important}
.stock-table tr:hover td{background:#102336!important}
.stock-table .price{color:#ffd05c!important}
.stock-table .up{color:#ff696f!important}
.stock-table .down{color:#56d388!important}
.stock-table .volr{color:#ffb33b!important}
.stock-table .grade{color:#dcecff!important}

/* legends in 4 equal cards */
.legend-grid{
  grid-template-columns:repeat(4,1fr)!important;
  gap:8px!important;
  margin-top:8px!important;
}
.legend{
  min-height:250px!important;
  padding:11px!important;
  border-radius:6px!important;
  background:#0a1724!important;
  border:1px solid #1e3a52!important;
}
.legend h4{font-size:15px!important;color:#4eb1ff!important}
.legend p,.legend li{font-size:11px!important;line-height:1.75!important}

/* dataframe/other native widgets */
[data-testid="stDataFrame"],[data-testid="stDataFrameResizable"]{
  background:#091521!important;
  border:1px solid #1e3e58!important;
  border-radius:6px!important;
}
[data-testid="stAlert"]{
  background:#0a1b29!important;
  border-color:#24516f!important;
}

/* mobile */
@media(max-width:900px){
  .block-container{padding:8px 7px 20px!important}
  .hero-title{font-size:23px!important}
  .hero-sub{font-size:11px!important}
  .hero-meta{display:none!important}
  .navbar{grid-template-columns:repeat(5,118px)!important;overflow-x:auto!important}
  .summary-grid{grid-template-columns:repeat(2,1fr)!important}
  .summary-card{min-height:104px!important}
  .legend-grid{grid-template-columns:1fr!important}
}
</style>
''', unsafe_allow_html=True)
