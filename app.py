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
HEAD = {"User-Agent":"Mozilla/5.0"}

st.markdown("""
<style>
.stApp{background:#07111f;color:#eef5ff}
.block-container{max-width:1450px;padding-top:1rem}
[data-testid="stMetric"]{background:#0c1b2d;border:1px solid #24415f;border-radius:12px;padding:10px}
</style>
""", unsafe_allow_html=True)

def n(v):
    if v is None: return np.nan
    s=str(v).replace(",","").replace("--","").replace("---","").replace("X","").strip()
    try:return float(s)
    except:return np.nan

def pick(r, ks):
    for k in ks:
        if k in r and str(r[k]).strip() not in ("","-","--","None"):
            return r[k]
    return None

@st.cache_data(ttl=900, show_spinner=False)
def snapshot():
    rows=[]; warns=[]
    try:
        x=requests.get(TWSE,headers=HEAD,timeout=30); x.raise_for_status()
        for r in x.json():
            code=str(pick(r,["Code","證券代號","股票代號"]) or "").strip()
            name=str(pick(r,["Name","證券名稱","股票名稱"]) or "").strip()
            close=n(pick(r,["ClosingPrice","收盤價","Close"]))
            vol=n(pick(r,["TradeVolume","成交股數","Trading_Volume"]))
            val=n(pick(r,["TradeValue","成交金額","Trading_money"]))
            chg=n(pick(r,["Change","漲跌價差","ChangePrice"]))
            if re.fullmatch(r"\d{4}",code) and np.isfinite(close):
                rows.append([code,name,"上市",close,vol,val,chg])
    except Exception as e: warns.append("上市資料暫時無法取得")

    try:
        x=requests.get(TPEX,headers=HEAD,timeout=30); x.raise_for_status()
        for r in x.json():
            code=str(pick(r,["SecuritiesCompanyCode","Code","證券代號","股票代號"]) or "").strip()
            name=str(pick(r,["CompanyName","SecuritiesCompanyName","Name","證券名稱","股票名稱"]) or "").strip()
            close=n(pick(r,["Close","ClosingPrice","收盤價"]))
            vol=n(pick(r,["TradingShares","TradeVolume","成交股數","成交量"]))
            val=n(pick(r,["TransactionAmount","TradeValue","成交金額"]))
            chg=n(pick(r,["Change","ChangePrice","漲跌價差"]))
            if re.fullmatch(r"\d{4}",code) and np.isfinite(close):
                rows.append([code,name,"上櫃",close,vol,val,chg])
    except Exception as e: warns.append("上櫃資料暫時無法取得")

    d=pd.DataFrame(rows,columns=["stock_id","stock_name","market","close","volume","value","change"])
    if not d.empty:
        d=d.drop_duplicates("stock_id")
        d=d[~d.stock_name.astype(str).str.contains("ETF|ETN|權證|指數|債",case=False,na=False)]
    return d,warns

@st.cache_data(ttl=3600, show_spinner=False)
def hist(code, market):
    suffix=".TW" if market=="上市" else ".TWO"
    for host in YAHOO_HOSTS:
        try:
            u=f"{host}/{code}{suffix}"
            r=requests.get(u,params={"range":"1y","interval":"1d","includePrePost":"false"},headers=HEAD,timeout=20)
            if r.status_code!=200: continue
            j=r.json(); result=j.get("chart",{}).get("result")
            if not result: continue
            z=result[0]; ts=z.get("timestamp") or []
            q=(z.get("indicators",{}).get("quote") or [{}])[0]
            if len(ts)<65: continue
            L=len(ts)
            def a(k): return ((q.get(k) or [])+[None]*L)[:L]
            d=pd.DataFrame({
                "date":pd.to_datetime(ts,unit="s",utc=True).tz_convert("Asia/Taipei").tz_localize(None),
                "open":a("open"),"max":a("high"),"min":a("low"),"close":a("close"),
                "volume":a("volume")
            })
            for c in ["open","max","min","close","volume"]:
                d[c]=pd.to_numeric(d[c],errors="coerce")
            d=d.dropna(subset=["open","max","min","close"]).sort_values("date")
            if len(d)>=65:return d
        except: pass
    return pd.DataFrame()

def pct(a,b): return (a/b-1)*100 if pd.notna(a) and pd.notna(b) and b else np.nan

def rsi(s,n=14):
    z=s.diff(); g=z.clip(lower=0).ewm(alpha=1/n,adjust=False).mean()
    l=(-z.clip(upper=0)).ewm(alpha=1/n,adjust=False).mean()
    return 100-100/(1+g/l.replace(0,np.nan))

def slope(s,n):
    y=s.dropna().tail(n).to_numpy()
    if len(y)<n or np.nanmean(y)==0:return np.nan
    return np.polyfit(np.arange(n),y,1)[0]/np.nanmean(y)*100

def slabel(x):
    if pd.isna(x):return "-"
    if x>=.7:return "↑ 加速上揚"
    if x>=.12:return "↗ 緩升"
    if x<=-.7:return "↓ 加速下彎"
    if x<=-.12:return "↘ 緩跌"
    return "→ 走平"

def analyze(d):
    d=d.copy()
    for k in [5,10,20,60,120,240]: d[f"ma{k}"]=d.close.rolling(k).mean()
    d["v20"]=d.volume.rolling(20).mean(); d["vr"]=d.volume/d.v20.replace(0,np.nan)
    d["rsi"]=rsi(d.close)
    e12=d.close.ewm(span=12,adjust=False).mean(); e26=d.close.ewm(span=26,adjust=False).mean()
    d["macd"]=e12-e26; d["sig"]=d.macd.ewm(span=9,adjust=False).mean(); d["hist"]=d.macd-d.sig
    lo=d["min"].rolling(9).min(); hi=d["max"].rolling(9).max()
    raw=(d.close-lo)/(hi-lo).replace(0,np.nan)*100
    d["k"]=raw.ewm(alpha=1/3,adjust=False).mean(); d["kd"]=d.k.ewm(alpha=1/3,adjust=False).mean()
    x=d.iloc[-1]; c=float(x.close)
    b5,b20,b60=pct(c,x.ma5),pct(c,x.ma20),pct(c,x.ma60)
    s5,s20,s60=slope(d.ma5,5),slope(d.ma20,10),slope(d.ma60,15)
    vals=[]
    for k in [5,10,20,60,120,240]:
        v=x[f"ma{k}"]
        if pd.notna(v):vals.append(float(v))
    for k in [20,40,60]:
        vals += [float(d["min"].tail(k).min()),float(d["max"].tail(k).max())]
    sup=sorted({round(v,2) for v in vals if v<c*.998},reverse=True)
    res=sorted({round(v,2) for v in vals if v>c*1.002})
    s1=sup[0] if sup else np.nan; r1=res[0] if res else np.nan
    rr=(r1-c)/(c-s1) if pd.notna(s1) and pd.notna(r1) and c>s1 else np.nan
    hi20=d["max"].tail(20).max(); lo20=d["min"].tail(20).min()
    r40=pct(c,d.close.iloc[-41])
    if c>=hi20*.995 and x.vr>=1.3: pattern="平台突破"
    elif lo20>0 and (hi20-lo20)/lo20<.10: pattern="箱型整理"
    elif r40>25 and c<d["max"].tail(40).max()*.98 and c>x.ma20: pattern="強勢股拉回"
    elif r40<0 and c>x.ma20 and x.vr>=1.5: pattern="跌深轉折"
    elif x.ma5>x.ma10>x.ma20: pattern="多頭排列"
    else: pattern="整理觀察"
    score=50
    for ok,p in [(c>x.ma5,5),(c>x.ma20,10),(pd.notna(x.ma60) and c>x.ma60,5),
                 (x.ma5>x.ma10>x.ma20,10),(s20>.12,8),(x.vr>=1.3,6),(x.hist>d["hist"].iloc[-2],6)]:
        if bool(ok):score+=p
    risk=0
    for ok,p in [(b5>8,20),(b20>15,20),(x.vr>2.8,15),(c<x.ma20,20),(s20<-.12,15),(x.rsi>80,10)]:
        if bool(ok):risk+=p
    cond="①強勢觀察"
    if r40<22 and x.vr>=1.7 and c>=d["max"].tail(40).max()*.99:cond="③剛起動"
    elif r40>25 and -15<pct(c,d["max"].tail(40).max())<-2 and x.vr<1.3:cond="④強勢拉回"
    elif c>=hi20*.995 and x.vr>=1.3:cond="②盤整突破"
    elif r40>30 and c>=d["max"].tail(40).max()*.99:cond="⑥強勢噴出"
    elif r40<0 and x.vr>=1.8 and c>x.ma20:cond="⑦跌深轉折"
    return {"score":min(100,int(score-risk*.1)),"risk":min(100,risk),"pattern":pattern,"condition":cond,
            "bias5":b5,"bias20":b20,"bias60":b60,"s5":s5,"s20":s20,"s60":s60,
            "support":s1,"resistance":r1,"rr":rr,"rsi":x.rsi,"k":x.k,"d":x.kd,"vr":x.vr,"data":d}

def chart(d, code, name):
    q=d.tail(140)
    fig=make_subplots(rows=2,cols=1,shared_xaxes=True,row_heights=[.75,.25],vertical_spacing=.03)
    fig.add_trace(go.Candlestick(x=q.date,open=q.open,high=q["max"],low=q["min"],close=q.close,name="K線"),1,1)
    for k in [5,10,20,60]:
        fig.add_trace(go.Scatter(x=q.date,y=q[f"ma{k}"],name=f"MA{k}",line=dict(width=1)),1,1)
    fig.add_trace(go.Bar(x=q.date,y=q.volume,name="成交量"),2,1)
    fig.update_layout(template="plotly_dark",height=600,title=f"{code} {name}",xaxis_rangeslider_visible=False)
    return fig

st.title("📈 賊大戰術 Pro｜免費穩定版")
st.caption("全市場一定先出名單；歷史K線成功時再補完整技術分析，不會因單一免費來源失敗讓整個掃描失敗。")

with st.sidebar:
    minp=st.number_input("最低股價",1.0,300.0,5.0)
    maxp=st.number_input("最高股價",10.0,3000.0,300.0)
    minlots=st.number_input("最低成交量（張）",100,100000,500,100)
    deep=st.slider("嘗試補歷史K線檔數",5,20,10)

if st.button("🚀 全市場盤後掃描",type="primary",use_container_width=True):
    d,w=snapshot()
    for x in w:st.warning(x)
    if d.empty:
        st.error("目前 TWSE/TPEx 官方盤後資料都沒有回傳，請稍後再試。")
    else:
        d["lots"]=d.volume/1000
        d=d[(d.close>=minp)&(d.close<=maxp)&(d.lots>=minlots)].copy()
        d["activity"]=d.value.where(d.value.notna()&(d.value>0),d.volume*d.close)
        d["chg_pct"]=(d.change/d.close*100).replace([np.inf,-np.inf],np.nan).fillna(0)
        # 今日版分數：流動性、漲跌強度、成交量
        d["score_today"]=(50 + d.activity.rank(pct=True)*25 + d.lots.rank(pct=True)*15 + d.chg_pct.clip(-10,10)*1).clip(0,100)
        d=d.sort_values(["score_today","activity"],ascending=False)
        top=d.head(max(10,deep)).copy()
        details={}
        rows=[]
        bar=st.progress(0,text="補抓歷史K線（失敗也不影響Top 10）…")
        for i,z in enumerate(top.head(deep).itertuples()):
            h=hist(z.stock_id,z.market)
            a=analyze(h) if not h.empty else None
            if a:details[z.stock_id]=a
            rows.append(z.stock_id)
            time.sleep(.05)
            bar.progress((i+1)/deep,text=f"補抓 {i+1}/{deep}")
        bar.empty()
        st.session_state["snap"]=d
        st.session_state["details"]=details

if "snap" in st.session_state:
    d=st.session_state["snap"]; details=st.session_state["details"]; top=d.head(10).copy()
    st.success("✅ 全市場掃描完成")
    a,b,c=st.columns(3)
    a.metric("通過基本條件",len(d))
    b.metric("Top 10",10 if len(d)>=10 else len(d))
    c.metric("已取得完整歷史分析",len(details))
    st.subheader("🏆 Top 10")
    table=top[["stock_id","stock_name","market","close","lots","chg_pct","score_today"]].copy()
    table.columns=["代號","名稱","市場","收盤","成交量(張)","今日漲跌強度%","今日初篩分數"]
    st.dataframe(table,hide_index=True,use_container_width=True)

    st.caption("「今日初篩分數」先保證全市場可產生排行；取得歷史K線的股票，點進去會看到完整賊大分析。")
    cols=st.columns(2)
    for i,z in enumerate(top.itertuples()):
        mark="✅完整" if z.stock_id in details else "○今日"
        if cols[i%2].button(f"{z.stock_id} {z.stock_name}｜{mark}",key=f"x{z.stock_id}",use_container_width=True):
            st.session_state["sel"]=z.stock_id

    code=st.session_state.get("sel")
    if code:
        z=top[top.stock_id==code]
        if not z.empty:
            z=z.iloc[0]
            st.divider();st.header(f"🔎 {code} {z.stock_name}")
            if code not in details:
                with st.spinner("單獨重試這檔歷史K線…"):
                    h=hist(code,z.market)
                    if not h.empty:
                        a=analyze(h); st.session_state["details"][code]=a; details[code]=a
            if code in details:
                x=details[code]
                m=st.columns(5)
                m[0].metric("賊大分數",x["score"]);m[1].metric("風險",f'{x["risk"]}/100')
                m[2].metric("型態",x["pattern"])
                m[3].metric("第一支撐",f'{x["support"]:.2f}' if pd.notna(x["support"]) else "-")
                m[4].metric("第一壓力",f'{x["resistance"]:.2f}' if pd.notna(x["resistance"]) else "-")
                st.plotly_chart(chart(x["data"],code,z.stock_name),use_container_width=True)
                st.write(f"**賊大條件：** {x['condition']}")
                st.write(f"**均線斜率：** MA5 {slabel(x['s5'])}｜MA20 {slabel(x['s20'])}｜MA60 {slabel(x['s60'])}")
                st.write(f"**乖離：** 5MA {x['bias5']:.1f}%｜20MA {x['bias20']:.1f}%｜60MA {x['bias60']:.1f}%")
                st.write(f"**RSI：** {x['rsi']:.1f}｜**KD：** {x['k']:.1f}/{x['d']:.1f}｜**量比：** {x['vr']:.2f}x")
                if pd.notna(x["rr"]):st.write(f"**風報比：** {x['rr']:.2f}")
            else:
                st.warning("這檔免費歷史K線目前取不到；但全市場排行仍可正常使用，不會整個掃描失敗。")

st.caption("免費穩定版：TWSE/TPEx 官方盤後行情負責全市場排行；免費歷史K線只做加值分析，不再成為整體失敗點。")
