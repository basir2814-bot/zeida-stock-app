import re
import time
from datetime import date
import numpy as np
import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="賊大戰術 Pro 免費版", page_icon="📈", layout="wide")

TWSE = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart"
HEAD = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1"}

st.markdown("""
<style>
.stApp{background:#07111f;color:#eaf2ff}
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

@st.cache_data(ttl=900, show_spinner=False)
def get_market_snapshot():
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
            if re.fullmatch(r"\d{4}", code) and np.isfinite(close):
                rows.append([code, name, "上市", close, vol, val, chg])
    except Exception as e:
        warnings.append(f"TWSE 暫時無法取得：{e}")

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
            if re.fullmatch(r"\d{4}", code) and np.isfinite(close):
                rows.append([code, name, "上櫃", close, vol, val, chg])
    except Exception as e:
        warnings.append(f"TPEx 暫時無法取得：{e}")

    d = pd.DataFrame(rows, columns=["stock_id","stock_name","market","close","volume","value","change"])
    if not d.empty:
        d = d.drop_duplicates("stock_id")
        d = d[~d.stock_name.astype(str).str.contains("ETF|ETN|指數|債券|權證", case=False, na=False)]
    return d, warnings

@st.cache_data(ttl=3600, show_spinner=False)
def yahoo_history(code, market):
    suffix = ".TW" if market == "上市" else ".TWO"
    url = f"{YAHOO}/{code}{suffix}"
    params = {"range": "1y", "interval": "1d", "includePrePost": "false", "events": "div,splits"}
    r = requests.get(url, params=params, headers=HEAD, timeout=25)
    r.raise_for_status()
    j = r.json()
    result = j.get("chart", {}).get("result")
    if not result:
        return pd.DataFrame()

    z = result[0]
    ts = z.get("timestamp") or []
    q = ((z.get("indicators", {}).get("quote") or [{}])[0])
    if not ts:
        return pd.DataFrame()

    n = len(ts)
    def arr(k):
        a = q.get(k) or []
        return (a + [None] * n)[:n]

    d = pd.DataFrame({
        "date": pd.to_datetime(ts, unit="s", utc=True).tz_convert("Asia/Taipei").tz_localize(None),
        "open": arr("open"),
        "max": arr("high"),
        "min": arr("low"),
        "close": arr("close"),
        "Trading_Volume": arr("volume"),
    })
    for c in ["open","max","min","close","Trading_Volume"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["Trading_money"] = d["close"] * d["Trading_Volume"]
    return d.dropna(subset=["open","max","min","close"]).sort_values("date")

def pct(a, b):
    return (a / b - 1) * 100 if pd.notna(a) and pd.notna(b) and b else np.nan

def rsi(s, n=14):
    z = s.diff()
    gain = z.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    loss = (-z.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100 / (1 + gain / loss.replace(0, np.nan))

def slope_pct(s, n):
    y = s.dropna().tail(n).to_numpy()
    if len(y) < n or np.nanmean(y) == 0:
        return np.nan
    return np.polyfit(np.arange(n), y, 1)[0] / np.nanmean(y) * 100

def slope_label(x):
    if pd.isna(x): return "-"
    if x >= .7: return "↑ 加速上揚"
    if x >= .12: return "↗ 緩升"
    if x <= -.7: return "↓ 加速下彎"
    if x <= -.12: return "↘ 緩跌"
    return "→ 走平"

def enrich(d):
    d = d.copy()
    for n in [5,10,20,60,120,240]:
        d[f"ma{n}"] = d.close.rolling(n).mean()
    d["v20"] = d.Trading_Volume.rolling(20).mean()
    d["vr"] = d.Trading_Volume / d.v20.replace(0, np.nan)
    d["rsi"] = rsi(d.close)
    e12 = d.close.ewm(span=12, adjust=False).mean()
    e26 = d.close.ewm(span=26, adjust=False).mean()
    d["macd"] = e12 - e26
    d["signal"] = d.macd.ewm(span=9, adjust=False).mean()
    d["hist"] = d.macd - d.signal
    lo = d["min"].rolling(9).min()
    hi = d["max"].rolling(9).max()
    raw = (d.close - lo) / (hi - lo).replace(0, np.nan) * 100
    d["k"] = raw.ewm(alpha=1/3, adjust=False).mean()
    d["d"] = d.k.ewm(alpha=1/3, adjust=False).mean()
    d["obv"] = (np.sign(d.close.diff()).fillna(0) * d.Trading_Volume.fillna(0)).cumsum()
    return d

def levels(d):
    c = float(d.close.iloc[-1])
    vals = []
    for n in [5,10,20,60,120,240]:
        v = d[f"ma{n}"].iloc[-1]
        if pd.notna(v): vals.append(float(v))
    for n in [20,40,60]:
        if len(d) >= n:
            vals += [float(d["min"].tail(n).min()), float(d["max"].tail(n).max())]
    supports = sorted({round(v,2) for v in vals if v < c*.998}, reverse=True)
    resist = sorted({round(v,2) for v in vals if v > c*1.002})
    return (supports + [np.nan,np.nan])[:2], (resist + [np.nan,np.nan])[:2]

def pattern_name(d):
    x = d.iloc[-1]
    c = x.close
    hi20 = d["max"].tail(20).max()
    lo20 = d["min"].tail(20).min()
    r40 = pct(c, d.close.iloc[-41]) if len(d) > 41 else np.nan
    if c >= hi20*.995 and x.vr >= 1.3: return "平台突破"
    if lo20 > 0 and (hi20-lo20)/lo20 < .10: return "箱型整理"
    if pd.notna(r40) and r40 > 25 and c < d["max"].tail(40).max()*.98 and c > x.ma20: return "強勢股拉回"
    if pd.notna(r40) and r40 < 0 and c > x.ma20 and x.vr >= 1.5: return "跌深轉折"
    if x.ma5 > x.ma10 > x.ma20: return "多頭排列"
    return "整理觀察"

def analyze(raw):
    if raw is None or len(raw) < 65:
        return None
    d = enrich(raw)
    x = d.iloc[-1]
    c = float(x.close)
    s, r = levels(d)
    b5, b20, b60 = pct(c,x.ma5), pct(c,x.ma20), pct(c,x.ma60)
    sl5, sl20, sl60 = slope_pct(d.ma5,5), slope_pct(d.ma20,10), slope_pct(d.ma60,15)
    r40 = pct(c,d.close.iloc[-41])
    hi40 = d["max"].tail(40).max()
    fromhi = pct(c,hi40)
    rr = (r[0]-c)/(c-s[0]) if pd.notna(r[0]) and pd.notna(s[0]) and c>s[0] else np.nan

    score = 35
    why = []
    for ok, pts, txt in [
        (c>x.ma5,5,"站5MA"), (c>x.ma20,8,"站20MA"),
        (pd.notna(x.ma60) and c>x.ma60,6,"站60MA"),
        (x.ma5>x.ma10>x.ma20,8,"多頭排列"),
        (sl20>.12,6,"20MA向上"), (x.vr>=1.3,6,"量能放大"),
        (x.hist>d.hist.iloc[-2],4,"MACD改善"), (x.k>x.d,4,"KD偏多"),
        (x.obv>d.obv.tail(20).mean(),4,"OBV偏多")
    ]:
        if bool(ok):
            score += pts
            why.append(txt)

    cond = []
    if r40 < 22 and x.vr >= 1.7 and c >= hi40*.99: cond.append("③剛起動")
    if r40 > 25 and -15 < fromhi < -2 and x.vr < 1.3: cond.append("④強勢拉回")
    if c >= d["max"].tail(20).max()*.995 and x.vr >= 1.3: cond.append("②盤整突破")
    if r40 > 30 and c >= hi40*.99: cond.append("⑥強勢噴出")
    if r40 < 0 and x.vr >= 1.8 and c > x.ma20: cond.append("⑦跌深轉折")
    if not cond: cond = ["①強勢觀察" if c>x.ma20 else "整理觀察"]

    risk = 0
    risks = []
    for ok, pts, txt in [
        (b5>8,20,"5MA乖離大"), (b20>15,20,"20MA乖離大"),
        (x.vr>2.8,15,"爆量"), (c<x.ma20,20,"跌破20MA"),
        (sl20<-.12,15,"20MA下彎"), (pd.notna(rr) and rr<1,15,"風報比差"),
        (x.rsi>80,10,"RSI過熱")
    ]:
        if bool(ok):
            risk += pts
            risks.append(txt)

    score = int(max(0, min(100, round(score-risk*.12))))
    return {
        "close":c, "score":score, "condition":"、".join(cond),
        "pattern":pattern_name(d), "risk":min(risk,100),
        "bias5":b5, "bias20":b20, "bias60":b60,
        "slope5":sl5, "slope20":sl20, "slope60":sl60,
        "slope20_text":slope_label(sl20),
        "support1":s[0], "support2":s[1],
        "resistance1":r[0], "resistance2":r[1],
        "rr":rr, "rsi":x.rsi, "k":x.k, "kd":x.d, "vr":x.vr,
        "why":"、".join(why[:7]), "risk_text":"、".join(risks) or "低",
        "data":d
    }

def chart(d, code, name):
    q = d.tail(140)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[.75,.25], vertical_spacing=.03)
    fig.add_trace(go.Candlestick(x=q.date,open=q.open,high=q["max"],low=q["min"],close=q.close,name="K線"),1,1)
    for n in [5,10,20,60]:
        fig.add_trace(go.Scatter(x=q.date,y=q[f"ma{n}"],name=f"MA{n}",line=dict(width=1)),1,1)
    fig.add_trace(go.Bar(x=q.date,y=q.Trading_Volume,name="成交量"),2,1)
    fig.update_layout(template="plotly_dark",height=620,title=f"{code} {name}",xaxis_rangeslider_visible=False)
    return fig

st.title("📈 賊大戰術 Pro｜免費全市場版")
st.caption("TWSE＋TPEx 官方免費行情掃全市場 → Yahoo 免費歷史K線 → Top 10")

with st.sidebar:
    st.header("掃描設定")
    minp = st.number_input("最低股價",1.0,300.0,5.0)
    maxp = st.number_input("最高股價",10.0,3000.0,300.0)
    minlots = st.number_input("最低當日成交量（張）",100,100000,500,100)
    candidates = st.slider("深度分析候選數",20,50,30)
    st.caption("此版不需要 FinMind 付費權限，也不需要輸入股票代號。")

if st.button("🚀 全市場盤後掃描", type="primary", use_container_width=True):
    try:
        snap, warns = get_market_snapshot()
        for w in warns:
            st.warning(w)
        if snap.empty:
            raise RuntimeError("TWSE 與 TPEx 今日行情皆未取得。")

        snap["lots"] = snap.volume/1000
        snap = snap[(snap.close>=minp)&(snap.close<=maxp)&(snap.lots>=minlots)].copy()
        if snap.empty:
            raise RuntimeError("依目前股價/成交量條件，沒有股票通過初篩。")

        snap["activity"] = snap.value.where(snap.value.notna()&(snap.value>0), snap.volume*snap.close)
        snap["move"] = snap.change.abs().fillna(0)/snap.close.replace(0,np.nan)
        snap["pre"] = snap.activity.rank(pct=True)*.75 + snap.move.rank(pct=True)*.25
        short = snap.sort_values("pre",ascending=False).head(candidates)

        rows, details, failed = [], {}, []
        bar = st.progress(0, text="抓取候選股免費歷史K線…")

        for i,z in enumerate(short.itertuples()):
            try:
                h = yahoo_history(z.stock_id,z.market)
                an = analyze(h)
                if an:
                    details[z.stock_id] = an
                    rows.append({k:v for k,v in an.items() if k!="data"} | {
                        "stock_id":z.stock_id, "stock_name":z.stock_name, "market":z.market
                    })
                else:
                    failed.append(z.stock_id)
            except Exception:
                failed.append(z.stock_id)

            if i < len(short)-1:
                time.sleep(0.08)
            bar.progress((i+1)/len(short), text=f"深度分析 {i+1}/{len(short)}")

        bar.empty()

        if not rows:
            raise RuntimeError("免費歷史K線目前沒有成功回傳；請稍後再試。")

        rd = pd.DataFrame(rows).sort_values(["score","risk"],ascending=[False,True])
        st.session_state["result"] = rd
        st.session_state["details"] = details
        st.session_state["snapshot_count"] = len(snap)
        st.session_state["failed_count"] = len(failed)

    except Exception as e:
        st.error("掃描失敗："+str(e))

if "result" in st.session_state:
    rd = st.session_state["result"]
    top = rd.head(10).copy()

    a,b,c,d = st.columns(4)
    a.metric("全市場通過流動性初篩",st.session_state["snapshot_count"])
    b.metric("完成深度分析",len(rd))
    c.metric("80分以上",int((rd.score>=80).sum()))
    d.metric("低風險≤30",int((rd.risk<=30).sum()))

    if st.session_state.get("failed_count",0):
        st.caption(f"有 {st.session_state['failed_count']} 檔候選股歷史資料暫時未取得，其餘股票仍正常排行。")

    st.subheader("🏆 Top 10")
    show = top[["stock_id","stock_name","market","score","condition","pattern","close",
                "bias5","bias20","slope20_text","support1","resistance1","risk","rr"]].copy()
    show.columns = ["代號","名稱","市場","分數","賊大條件","型態","收盤",
                    "5MA乖離%","20MA乖離%","20MA斜率","第一支撐","第一壓力","風險係數","風報比"]
    st.dataframe(show,hide_index=True,use_container_width=True)

    st.subheader("點股票看走勢")
    cols = st.columns(2)
    for i,z in enumerate(top.itertuples()):
        if cols[i%2].button(f"{z.stock_id} {z.stock_name}｜{z.score}分｜{z.pattern}",
                            key=f"stock_{z.stock_id}",use_container_width=True):
            st.session_state["detail_code"] = z.stock_id

    code = st.session_state.get("detail_code")
    if code in st.session_state["details"]:
        x = st.session_state["details"][code]
        z = top[top.stock_id==code].iloc[0]
        st.divider()
        st.header(f"🔎 {code} {z.stock_name}")

        m = st.columns(5)
        m[0].metric("分數",x["score"])
        m[1].metric("風險",f'{x["risk"]}/100')
        m[2].metric("型態",x["pattern"])
        m[3].metric("第一支撐",f'{x["support1"]:.2f}' if pd.notna(x["support1"]) else "-")
        m[4].metric("第一壓力",f'{x["resistance1"]:.2f}' if pd.notna(x["resistance1"]) else "-")

        st.plotly_chart(chart(x["data"],code,z.stock_name),use_container_width=True)
        st.write(f"**斜率：** MA5 {slope_label(x['slope5'])}｜MA20 {slope_label(x['slope20'])}｜MA60 {slope_label(x['slope60'])}")
        st.write(f"**乖離：** 5MA {x['bias5']:.1f}%｜20MA {x['bias20']:.1f}%｜60MA {x['bias60']:.1f}%")
        st.write(f"**技術：** RSI {x['rsi']:.1f}｜KD {x['k']:.1f}/{x['kd']:.1f}｜量比 {x['vr']:.2f}x")
        st.write(f"**賊大條件：** {x['condition']}")
        st.write(f"**風險原因：** {x['risk_text']}｜**加分：** {x['why']}")
        if pd.notna(x["rr"]):
            st.write(f"**風報比：** {x['rr']:.2f}")

        if x["risk"]<=30 and x["score"]>=80:
            st.success("操作劇本：偏強，等支撐確認或突破量價確認，避免高乖離追價。")
        elif x["risk"]>=60:
            st.error("操作劇本：風險偏高，先等乖離收斂與支撐確認。")
        else:
            st.warning("操作劇本：觀察，等量價、支撐與斜率進一步確認。")

st.caption("免費資料架構：TWSE、TPEx 官方公開盤後行情＋Yahoo 免費歷史K線。型態、支撐壓力、風險係數為程式化估算。")
