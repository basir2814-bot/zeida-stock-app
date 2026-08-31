import re, time
import numpy as np
import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="賊大戰術 Pro 免費版", page_icon="📈", layout="wide")

TWSE = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
YAHOO_HOSTS = [
    "https://query1.finance.yahoo.com/v8/finance/chart",
    "https://query2.finance.yahoo.com/v8/finance/chart",
]
HEAD = {"User-Agent": "Mozilla/5.0"}

st.markdown("""
<style>
.stApp{background:#07111f;color:#eef5ff}
.block-container{max-width:1450px;padding-top:1rem}
[data-testid="stMetric"]{background:#0c1b2d;border:1px solid #24415f;border-radius:12px;padding:10px}
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
            vol = to_num(pick(x, ["TradeVolume", "成交股數", "Trading_Volume"]))
            val = to_num(pick(x, ["TradeValue", "成交金額", "Trading_money"]))
            chg = to_num(pick(x, ["Change", "漲跌價差", "ChangePrice"]))
            if re.fullmatch(r"\d{4}", code) and finite(close):
                rows.append([code, name, "上市", close, vol, val, chg])
    except Exception as e:
        warnings.append(f"上市資料暫時無法取得：{type(e).__name__}")

    try:
        r = requests.get(TPEX, headers=HEAD, timeout=30)
        r.raise_for_status()
        for x in r.json():
            code = str(pick(x, ["SecuritiesCompanyCode", "Code", "證券代號", "股票代號"]) or "").strip()
            name = str(pick(x, ["CompanyName", "SecuritiesCompanyName", "Name", "證券名稱", "股票名稱"]) or "").strip()
            close = to_num(pick(x, ["Close", "ClosingPrice", "收盤價"]))
            vol = to_num(pick(x, ["TradingShares", "TradeVolume", "成交股數", "成交量"]))
            val = to_num(pick(x, ["TransactionAmount", "TradeValue", "成交金額"]))
            chg = to_num(pick(x, ["Change", "ChangePrice", "漲跌價差"]))
            if re.fullmatch(r"\d{4}", code) and finite(close):
                rows.append([code, name, "上櫃", close, vol, val, chg])
    except Exception as e:
        warnings.append(f"上櫃資料暫時無法取得：{type(e).__name__}")

    d = pd.DataFrame(rows, columns=["stock_id","stock_name","market","close","volume","value","change"])
    if not d.empty:
        d = d.drop_duplicates("stock_id")
        d = d[~d.stock_name.astype(str).str.contains("ETF|ETN|權證|指數|債", case=False, na=False)]
    return d, warnings

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

        risk = 0
        risk_checks = [
            (finite(b5) and b5 > 8, 20),
            (finite(b20) and b20 > 15, 20),
            (vr > 2.8, 15),
            (lt(c, ma20), 20),
            (finite(s20) and s20 < -.12, 15),
            (rsi_now > 80, 10),
            (finite(rr) and rr < 1, 15),
        ]
        for ok, pts in risk_checks:
            if ok:
                risk += pts

        cond = "①強勢觀察" if gt(c, ma20) else "整理觀察"
        if finite(r40) and r40 < 22 and vr >= 1.7 and c >= hi40*.99:
            cond = "③剛起動"
        elif finite(r40) and r40 > 25 and finite(from_hi) and -15 < from_hi < -2 and vr < 1.3:
            cond = "④強勢拉回"
        elif c >= hi20*.995 and vr >= 1.3:
            cond = "②盤整突破"
        elif finite(r40) and r40 > 30 and c >= hi40*.99:
            cond = "⑥強勢噴出"
        elif finite(r40) and r40 < 0 and vr >= 1.8 and gt(c, ma20):
            cond = "⑦跌深轉折"

        return {
            "score": int(max(0,min(100,round(score-risk*.1)))),
            "risk": min(100,risk),
            "pattern": pattern,
            "condition": cond,
            "bias5": b5, "bias20": b20, "bias60": b60,
            "s5": s5, "s20": s20, "s60": s60,
            "support": support, "support2": support2,
            "resistance": resistance, "resistance2": resistance2, "rr": rr,
            "rsi": rsi_now, "k": k_now, "d": d_now, "vr": vr,
            "r20": pct(c, d["close"].iloc[-21]) if len(d) > 21 else np.nan,
            "ma60_up": gt(c, ma60),
            "macd_positive": hist_now > 0,
            "kd_golden": k_now > d_now,
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

            target = snap.head(min(35,len(snap)))
            details, inst = {}, {}
            bar = st.progress(0,text="進行賊大①～⑧與技術分析…")
            for i,z in enumerate(target.itertuples(index=False)):
                try:
                    h = hist(z.stock_id,z.market)
                    a = analyze(h) if not h.empty else None
                    if a is not None:
                        # Apply the historical filters from the mockup.
                        pass_month = (not finite(a["r20"])) or a["r20"] >= min_month
                        pass_season = season_rule=="不限" or bool(a["ma60_up"])
                        pass_kd = kd_rule=="不限" or bool(a["kd_golden"])
                        if pass_month and pass_season and pass_kd:
                            details[z.stock_id] = a
                            inst[z.stock_id] = institutional_5d(z.stock_id)
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

if "snap" in st.session_state:
    snap=st.session_state["snap"]
    details=st.session_state.get("details",{})
    inst=st.session_state.get("inst",{})
    top=snap.head(10).copy()
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

    st.markdown('<div class="panel"><div class="panel-title">Top 10 強勢股 <span style="font-size:12px;color:#9fb1c2">（依綜合評分排序）</span></div>', unsafe_allow_html=True)

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
        trs.append(f"""
        <tr>
          <td class="rank">{rank}</td><td class="code">{z.stock_id}</td><td>{z.stock_name}</td>
          <td class="price">{price2(z_close)}</td><td class="{cls}">{signed_pct(z_chg)}</td>
          <td>{money_yi(z_activity)}</td><td class="volr">{f2(vr)}</td>
          <td>{flagtxt}</td><td>{tech:.1f}</td><td>{chip:.1f}</td>
          <td class="volr">{f2(bias)}%</td>
          <td>{f1(s1)}</td><td>{f1(s2)}</td><td>{f1(r1)}</td><td>{f1(r2)}</td>
          <td class="{risk_class(risk)}">{'-' if not finite(risk) else int(risk)}</td>
          <td class="rr">{f2(rr)}</td><td class="grade">{grade}</td>
        </tr>
        """)

    st.markdown("""
    <div class="table-wrap"><table class="stock-table"><thead><tr>
      <th>排名</th><th>代號</th><th>名稱</th><th>股價</th><th>漲跌幅</th><th>成交金額(億)</th><th>量比</th>
      <th>賊大戰術 ①～⑧</th><th>技術分(60%)</th><th>籌碼分(20%)</th><th>乖離率(離季線)</th>
      <th>支撐1</th><th>支撐2</th><th>壓力1</th><th>壓力2</th><th>風險係數</th><th>風報比</th><th>評等</th>
    </tr></thead><tbody>
    """+"".join(trs)+"""
    </tbody></table></div>
    """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("""
    <div class="legend-grid">
      <div class="legend"><h4>賊大戰術 ①～⑧ 說明</h4>
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
