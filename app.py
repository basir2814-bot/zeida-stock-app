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
        resistance = resistances[0] if resistances else np.nan
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
            "support": support, "resistance": resistance, "rr": rr,
            "rsi": rsi_now, "k": k_now, "d": d_now, "vr": vr,
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

st.title("📈 賊大戰術 Pro｜免費穩定版 v2")
st.caption("全市場先出 Top 10；任何單一股票的歷史K線分析失敗，都不會讓整個 App 當掉。")

with st.sidebar:
    minp = st.number_input("最低股價",1.0,300.0,5.0)
    maxp = st.number_input("最高股價",10.0,3000.0,300.0)
    minlots = st.number_input("最低成交量（張）",100,100000,500,100)
    deep = st.slider("補完整技術分析檔數",3,15,8)

if st.button("🚀 全市場盤後掃描", type="primary", use_container_width=True):
    snap, warnings = snapshot()
    for w in warnings:
        st.warning(w)

    if snap.empty:
        st.error("TWSE/TPEx 官方行情目前沒有取得，請稍後再試。")
    else:
        snap["lots"] = pd.to_numeric(snap["volume"],errors="coerce").fillna(0)/1000
        snap = snap[
            (snap["close"]>=minp)&(snap["close"]<=maxp)&(snap["lots"]>=minlots)
        ].copy()

        if snap.empty:
            st.warning("目前沒有股票通過你設定的股價/成交量條件。")
        else:
            snap["activity"] = snap["value"].where(
                snap["value"].notna()&(snap["value"]>0),
                snap["volume"]*snap["close"]
            )
            snap["chg_pct"] = (
                pd.to_numeric(snap["change"],errors="coerce").fillna(0) /
                snap["close"].replace(0,np.nan) * 100
            ).replace([np.inf,-np.inf],np.nan).fillna(0)

            snap["score_today"] = (
                50
                + snap["activity"].rank(pct=True)*25
                + snap["lots"].rank(pct=True)*15
                + snap["chg_pct"].clip(-10,10)
            ).clip(0,100)

            snap = snap.sort_values(["score_today","activity"],ascending=False).reset_index(drop=True)

            details = {}
            bar = st.progress(0,text="補完整技術分析…")
            target = snap.head(deep)

            for i,z in enumerate(target.itertuples(index=False)):
                try:
                    h = hist(z.stock_id,z.market)
                    a = analyze(h) if not h.empty else None
                    if a is not None:
                        details[z.stock_id] = a
                except:
                    pass
                bar.progress((i+1)/max(len(target),1), text=f"補分析 {i+1}/{len(target)}")
                time.sleep(.05)

            bar.empty()
            st.session_state["snap"] = snap
            st.session_state["details"] = details

if "snap" in st.session_state:
    snap = st.session_state["snap"]
    details = st.session_state.get("details",{})
    top = snap.head(10).copy()

    st.success("✅ 全市場掃描完成")
    c1,c2,c3 = st.columns(3)
    c1.metric("通過基本條件",len(snap))
    c2.metric("Top 10",len(top))
    c3.metric("已補完整技術分析",len(details))

    st.subheader("🏆 Top 10")
    table = top[["stock_id","stock_name","market","close","lots","chg_pct","score_today"]].copy()
    table.columns = ["代號","名稱","市場","收盤","成交量(張)","今日漲跌%","今日初篩分數"]
    st.dataframe(table,hide_index=True,use_container_width=True)

    st.caption("Top 10 一定先顯示；標示「完整」的股票可以直接看 K 線、型態、斜率、乖離、支撐壓力與風險。")
    cols = st.columns(2)
    for i,z in enumerate(top.itertuples(index=False)):
        tag = "✅完整" if z.stock_id in details else "○今日"
        if cols[i%2].button(
            f"{z.stock_id} {z.stock_name}｜{tag}",
            key=f"stock_{z.stock_id}",
            use_container_width=True
        ):
            st.session_state["selected"] = z.stock_id

    code = st.session_state.get("selected")
    if code:
        row = top[top["stock_id"]==code]
        if not row.empty:
            row = row.iloc[0]
            if code not in details:
                try:
                    with st.spinner("單獨補抓這檔歷史K線…"):
                        h = hist(code,row["market"])
                        a = analyze(h) if not h.empty else None
                        if a is not None:
                            details[code] = a
                            st.session_state["details"] = details
                except:
                    pass

            st.divider()
            st.header(f"🔎 {code} {row['stock_name']}")

            if code in details:
                x = details[code]
                m = st.columns(5)
                m[0].metric("賊大分數",x["score"])
                m[1].metric("風險",f'{x["risk"]}/100')
                m[2].metric("型態",x["pattern"])
                m[3].metric("第一支撐",f'{x["support"]:.2f}' if finite(x["support"]) else "-")
                m[4].metric("第一壓力",f'{x["resistance"]:.2f}' if finite(x["resistance"]) else "-")

                st.plotly_chart(chart(x["data"],code,row["stock_name"]),use_container_width=True)
                st.write(f"**賊大條件：** {x['condition']}")
                st.write(f"**均線斜率：** MA5 {slope_label(x['s5'])}｜MA20 {slope_label(x['s20'])}｜MA60 {slope_label(x['s60'])}")
                st.write(
                    f"**乖離：** 5MA {x['bias5']:.1f}%｜20MA {x['bias20']:.1f}%｜60MA {x['bias60']:.1f}%"
                    if finite(x["bias5"]) and finite(x["bias20"]) and finite(x["bias60"])
                    else "**乖離：** 資料不足"
                )
                st.write(f"**RSI：** {x['rsi']:.1f}｜**KD：** {x['k']:.1f}/{x['d']:.1f}｜**量比：** {x['vr']:.2f}x")
                if finite(x["rr"]):
                    st.write(f"**風報比：** {x['rr']:.2f}")
            else:
                st.info("這檔的免費歷史K線目前取不到，但全市場 Top 10 仍正常可用。")

st.caption("免費穩定版 v2：TWSE/TPEx 官方盤後行情負責全市場排行；免費歷史K線僅做個股加值分析。")
