
import os
from datetime import date, timedelta
import numpy as np
import pandas as pd
import requests
import streamlit as st

API = "https://api.finmindtrade.com/api/v4/data"

st.set_page_config(page_title="賊大戰術 Pro", page_icon="📈", layout="wide")

st.markdown("""
<style>
.block-container{max-width:1180px;padding-top:1.2rem}
[data-testid="stMetricValue"]{font-size:1.6rem}
.small{color:#7b8499;font-size:.86rem}
.badge{display:inline-block;padding:.2rem .5rem;border-radius:.5rem;background:#eef2ff;margin-right:.25rem}
</style>
""", unsafe_allow_html=True)

st.title("📈 賊大戰術 Pro｜台股盤後選股")
st.caption("8 種資金行為＋K線七大重點＋籌碼。使用 FinMind 真實盤後資料。")

def api_get(dataset, data_id=None, start_date=None, end_date=None, token=""):
    params = {"dataset": dataset}
    if data_id:
        params["data_id"] = str(data_id)
    if start_date:
        params["start_date"] = str(start_date)
    if end_date:
        params["end_date"] = str(end_date)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = requests.get(API, params=params, headers=headers, timeout=40)
    r.raise_for_status()
    j = r.json()
    if j.get("status") not in (200, None):
        raise RuntimeError(j.get("msg", "API error"))
    return pd.DataFrame(j.get("data", []))

@st.cache_data(ttl=3600, show_spinner=False)
def get_info(token):
    df = api_get("TaiwanStockInfo", token=token)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.sort_values("date").drop_duplicates("stock_id", keep="last")
    return df[["stock_id","stock_name","industry_category","type","date"]]

@st.cache_data(ttl=1800, show_spinner=False)
def get_price(stock_id, start_date, end_date, token):
    df = api_get("TaiwanStockPrice", stock_id, start_date, end_date, token)
    if df.empty: return df
    df["date"] = pd.to_datetime(df["date"])
    for c in ["open","max","min","close","Trading_Volume","Trading_money"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[df["close"] > 0].sort_values("date")

@st.cache_data(ttl=1800, show_spinner=False)
def get_chip(stock_id, start_date, end_date, token):
    inst = api_get("TaiwanStockInstitutionalInvestorsBuySellWide", stock_id, start_date, end_date, token)
    margin = api_get("TaiwanStockMarginPurchaseShortSale", stock_id, start_date, end_date, token)
    if not inst.empty:
        inst["date"] = pd.to_datetime(inst["date"])
    if not margin.empty:
        margin["date"] = pd.to_datetime(margin["date"])
    return inst, margin

def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()

def rsi(s, n=14):
    d = s.diff()
    gain = d.clip(lower=0).rolling(n).mean()
    loss = (-d.clip(upper=0)).rolling(n).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100/(1+rs))

def kd(df, n=9):
    ll = df["min"].rolling(n).min()
    hh = df["max"].rolling(n).max()
    rsv = (df["close"]-ll)/(hh-ll).replace(0,np.nan)*100
    k = rsv.ewm(alpha=1/3, adjust=False).mean()
    d = k.ewm(alpha=1/3, adjust=False).mean()
    return k, d

def obv(df):
    direction = np.sign(df["close"].diff()).fillna(0)
    return (direction * df["Trading_Volume"].fillna(0)).cumsum()

def pct(a,b):
    if pd.isna(a) or pd.isna(b) or b == 0: return np.nan
    return (a/b - 1)*100

def safe_last(s, back=1):
    if len(s) < back: return np.nan
    return s.iloc[-back]

def score_one(price, inst=None, margin=None):
    if price is None or len(price) < 65:
        return None
    df = price.copy().reset_index(drop=True)
    c = df["close"]
    for n in [5,10,20,60,120,240]:
        df[f"ma{n}"] = c.rolling(n).mean()
    df["v20"] = df["Trading_Volume"].rolling(20).mean()
    df["vr"] = df["Trading_Volume"] / df["v20"]
    df["ema12"] = ema(c,12); df["ema26"] = ema(c,26)
    df["macd"] = df["ema12"] - df["ema26"]
    df["signal"] = ema(df["macd"],9); df["hist"] = df["macd"] - df["signal"]
    df["rsi14"] = rsi(c)
    df["k"],df["d"] = kd(df)
    df["obv"] = obv(df)

    x = df.iloc[-1]
    close = x["close"]
    hi20 = df["max"].tail(20).max()
    hi40 = df["max"].tail(40).max()
    r5 = pct(close, safe_last(c,6))
    r20 = pct(close, safe_last(c,21))
    r40 = pct(close, safe_last(c,41))
    from_hi = pct(close,hi40)
    vr = x["vr"]

    score = 0
    why = []
    risk = []
    cond = []

    # 趨勢 25
    if close > x["ma5"]: score += 4
    if close > x["ma10"]: score += 4
    if close > x["ma20"]: score += 4
    if pd.notna(x["ma60"]) and close > x["ma60"]: score += 4
    if x["ma5"] > x["ma10"] > x["ma20"]: score += 5; why.append("5>10>20MA")
    if pd.notna(x["ma60"]) and x["ma20"] > x["ma60"]: score += 4; why.append("20MA>60MA")

    # 量價/動能 30
    if pd.notna(vr) and vr >= 1.3: score += 6; why.append(f"量比{vr:.2f}x")
    if pd.notna(vr) and vr >= 1.8: score += 3
    if close >= hi20*0.995: score += 5; why.append("接近20日高")
    if close >= hi40*0.985: score += 4
    if x["hist"] > safe_last(df["hist"],2): score += 4; why.append("MACD動能改善")
    if x["obv"] > df["obv"].tail(20).mean(): score += 4; why.append("OBV偏多")
    if pd.notna(x["k"]) and pd.notna(x["d"]) and x["k"] > x["d"] and x["k"] < 85:
        score += 4; why.append("KD偏多")

    # 回檔/風報 15
    near5 = pd.notna(x["ma5"]) and abs(close-x["ma5"])/close < .025
    near10 = pd.notna(x["ma10"]) and abs(close-x["ma10"])/close < .035
    if near5 or near10: score += 5; why.append("靠近5/10MA")
    if pd.notna(from_hi) and -15 < from_hi < -2 and pd.notna(vr) and vr < 1.2:
        score += 6; why.append("高檔量縮回測")
    if pd.notna(x["rsi14"]) and 45 <= x["rsi14"] <= 72: score += 4

    # 法人籌碼 20
    foreign_net = trust_net = 0
    if inst is not None and not inst.empty:
        ii = inst.sort_values("date").tail(5).copy()
        for col in ii.columns:
            if col not in ["date","stock_id"]:
                ii[col] = pd.to_numeric(ii[col], errors="coerce").fillna(0)
        if {"Foreign_Investor_buy","Foreign_Investor_sell"}.issubset(ii.columns):
            foreign_net = float((ii["Foreign_Investor_buy"]-ii["Foreign_Investor_sell"]).sum())
        if {"Investment_Trust_buy","Investment_Trust_sell"}.issubset(ii.columns):
            trust_net = float((ii["Investment_Trust_buy"]-ii["Investment_Trust_sell"]).sum())
        if foreign_net > 0: score += 6; why.append("近5日外資買超")
        if trust_net > 0: score += 6; why.append("近5日投信買超")
        if foreign_net + trust_net > 0: score += 3

    margin_change = np.nan
    short_change = np.nan
    if margin is not None and not margin.empty:
        mm = margin.sort_values("date").tail(2).copy()
        for col in ["MarginPurchaseTodayBalance","ShortSaleTodayBalance"]:
            if col in mm.columns: mm[col]=pd.to_numeric(mm[col], errors="coerce")
        if len(mm) >= 2 and "MarginPurchaseTodayBalance" in mm.columns:
            margin_change = mm["MarginPurchaseTodayBalance"].iloc[-1]-mm["MarginPurchaseTodayBalance"].iloc[-2]
            if margin_change <= 0: score += 3; why.append("融資未增加")
        if len(mm) >= 2 and "ShortSaleTodayBalance" in mm.columns:
            short_change = mm["ShortSaleTodayBalance"].iloc[-1]-mm["ShortSaleTodayBalance"].iloc[-2]
            if short_change > 0: score += 2; why.append("融券增加")

    # 賊大條件分類
    c2 = close >= hi20*.995 and pd.notna(vr) and vr >= 1.3
    c3 = pd.notna(r20) and r20 < 22 and pd.notna(vr) and vr >= 1.7 and close >= hi40*.99
    c4 = pd.notna(r40) and r40 > 25 and pd.notna(from_hi) and -15 < from_hi < -2 and pd.notna(vr) and vr < 1.25 and (near5 or near10)
    c6 = pd.notna(r40) and r40 > 30 and close >= hi40*.99 and pd.notna(vr) and vr >= 1.2
    c7 = pd.notna(x["ma60"]) and ((x["ma60"] < df["ma60"].iloc[-10]) or (pd.notna(r40) and r40 < 0)) and pd.notna(vr) and vr >= 1.8 and close > x["ma5"]
    c8 = pd.notna(x["ma60"]) and abs(x["ma20"]/x["ma60"]-1)<.08 and pd.notna(vr) and vr>=1.1 and close>x["ma20"]
    if c2: cond.append("②盤整突破")
    if c3: cond.append("③第一波")
    if c4: cond.append("④第二波")
    if c6: cond.append("⑥強勢噴出")
    if c7: cond.append("⑦跌深反轉")
    if c8: cond.append("⑧整理吸籌")
    if not cond and close > x["ma20"]: cond.append("①強勢觀察")

    # 風險扣分
    if pd.notna(r5) and r5 > 12: score -= 7; risk.append("5日乖離偏大")
    if pd.notna(vr) and vr >= 2.8: score -= 5; risk.append("爆量")
    if close < x["ma20"]: score -= 7; risk.append("跌破20MA")
    if pd.notna(from_hi) and from_hi < -15: score -= 5; risk.append("回檔較深")
    if pd.notna(margin_change) and margin_change > 0: risk.append("融資增加")
    score = int(max(0,min(100,round(score))))

    if score >= 85: action = "A｜優先研究"
    elif score >= 75: action = "B｜觀察等待"
    else: action = "C｜暫不優先"

    return {
        "date": x["date"].date(),
        "close": close,
        "score": score,
        "condition": "、".join(cond),
        "action": action,
        "r5": r5,
        "vr": vr,
        "ma5": x["ma5"], "ma10": x["ma10"], "ma20": x["ma20"], "ma60": x["ma60"],
        "kd_k": x["k"], "kd_d": x["d"], "rsi": x["rsi14"],
        "foreign5": foreign_net, "trust5": trust_net,
        "margin_change": margin_change, "short_change": short_change,
        "why": "、".join(why[:7]) or "條件不足",
        "risk": "、".join(risk) or "未見明顯警訊",
    }

with st.sidebar:
    st.header("設定")
    token = st.text_input("FinMind Token（建議填）", value=st.secrets.get("FINMIND_TOKEN","") if hasattr(st, "secrets") else "", type="password")
    st.caption("不填也能測試，但官方無 Token 配額較低。")
    days = st.slider("歷史資料天數", 120, 500, 360, 30)
    min_score = st.slider("最低顯示分數", 50, 95, 70)
    use_chip = st.toggle("加入法人＋融資融券", value=True)

st.info("💡 免費模式建議先掃自選股。FinMind 全市場日資料不帶 stock_id 的查詢屬 Backer/Sponsor；免費 API 適合逐檔查詢。")

codes_text = st.text_input("股票代號（逗號分隔）", "6214,4576,8358,6173,2408")
c1,c2,c3 = st.columns([1,1,2])
with c1:
    scan = st.button("🔎 今日盤後掃描", type="primary", use_container_width=True)
with c2:
    st.button("清除快取", on_click=st.cache_data.clear, use_container_width=True)

if scan:
    codes = [x.strip() for x in codes_text.replace("，",",").split(",") if x.strip()]
    codes = list(dict.fromkeys(codes))[:60]
    if not codes:
        st.warning("請至少輸入一檔股票代號。")
        st.stop()

    end = date.today()
    start = end - timedelta(days=int(days))
    info = pd.DataFrame()
    try:
        info = get_info(token)
    except Exception:
        pass
    name_map = dict(zip(info["stock_id"], info["stock_name"])) if not info.empty else {}

    results = []
    errors = []
    bar = st.progress(0, text="開始下載盤後資料…")
    for i, code in enumerate(codes, 1):
        try:
            p = get_price(code,start,end,token)
            inst = margin = None
            if use_chip:
                inst, margin = get_chip(code, start, end, token)
            s = score_one(p,inst,margin)
            if s:
                s["stock_id"] = code
                s["stock_name"] = name_map.get(code,"")
                results.append(s)
            else:
                errors.append(f"{code}：歷史資料不足")
        except Exception as e:
            errors.append(f"{code}：{str(e)[:80]}")
        bar.progress(i/len(codes), text=f"掃描 {code}（{i}/{len(codes)}）")
    bar.empty()

    if results:
        rd = pd.DataFrame(results).sort_values(["score","vr"], ascending=False)
        rd = rd[rd["score"] >= min_score]

        a,b,c,d = st.columns(4)
        a.metric("符合最低分", len(rd))
        b.metric("A級", int((rd["score"]>=85).sum()))
        c.metric("第一波", int(rd["condition"].str.contains("③", na=False).sum()))
        d.metric("第二波", int(rd["condition"].str.contains("④", na=False).sum()))

        st.subheader("🏆 今日排名")
        show = rd[["stock_id","stock_name","score","condition","action","close","r5","vr","why","risk"]].copy()
        show.columns = ["代號","名稱","分數","賊大條件","判斷","收盤","5日%","量比","加分理由","風險"]
        st.dataframe(
            show,
            use_container_width=True,
            hide_index=True,
            column_config={
                "分數": st.column_config.ProgressColumn(min_value=0,max_value=100),
                "5日%": st.column_config.NumberColumn(format="%.1f%%"),
                "量比": st.column_config.NumberColumn(format="%.2fx"),
                "收盤": st.column_config.NumberColumn(format="%.2f"),
            }
        )

        st.subheader("🔍 前 5 名細看")
        for _,x in rd.head(5).iterrows():
            with st.expander(f"{x['stock_id']} {x['stock_name']}｜{x['score']}分｜{x['condition']}", expanded=False):
                q1,q2,q3,q4 = st.columns(4)
                q1.metric("收盤", f"{x['close']:.2f}")
                q2.metric("量比", f"{x['vr']:.2f}x" if pd.notna(x["vr"]) else "-")
                q3.metric("5日", f"{x['r5']:.1f}%" if pd.notna(x["r5"]) else "-")
                q4.metric("RSI", f"{x['rsi']:.1f}" if pd.notna(x["rsi"]) else "-")
                st.write("**加分：**", x["why"])
                st.write("**風險：**", x["risk"])
                st.write("**均線：**", f"5MA {x['ma5']:.2f}｜10MA {x['ma10']:.2f}｜20MA {x['ma20']:.2f}｜60MA {x['ma60']:.2f}" if pd.notna(x["ma60"]) else "資料不足")
                if x["score"] >= 85:
                    st.success("操作提示：優先等回測 5/10MA、突破後第一次回測，避免大幅跳空追價。")
                elif x["score"] >= 75:
                    st.warning("操作提示：先觀察，等量價或籌碼再確認。")
                else:
                    st.error("操作提示：暫不優先。")
        st.caption("分數是篩選排序，不代表預測漲跌或保證報酬。")
    else:
        st.warning("沒有成功取得足夠資料。請檢查代號或 API Token。")

    if errors:
        with st.expander("資料錯誤／未完成項目"):
            st.write("\n".join(errors))
