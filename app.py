import math
from datetime import date, timedelta
import numpy as np
import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

API = "https://api.finmindtrade.com/api/v4/data"
st.set_page_config(page_title="賊大戰術 Pro", page_icon="📈", layout="wide")

st.markdown("""
<style>
.stApp{background:#07111f;color:#eaf2ff}
.block-container{max-width:1450px;padding-top:1rem}
[data-testid="stMetric"]{background:#0c1b2d;border:1px solid #1e3a5f;border-radius:12px;padding:10px}
[data-testid="stMetricValue"]{font-size:1.55rem}
h1,h2,h3{color:#f2f7ff}
div[data-testid="stDataFrame"]{border:1px solid #1e3a5f;border-radius:10px}
</style>
""", unsafe_allow_html=True)

def api_get(dataset, data_id=None, start_date=None, end_date=None, token=""):
    p={"dataset":dataset}
    if data_id: p["data_id"]=str(data_id)
    if start_date: p["start_date"]=str(start_date)
    if end_date: p["end_date"]=str(end_date)
    h={"Authorization":f"Bearer {token}"} if token else {}
    r=requests.get(API,params=p,headers=h,timeout=60)
    r.raise_for_status()
    j=r.json()
    if j.get("status") not in (200,None):
        raise RuntimeError(j.get("msg","FinMind API error"))
    return pd.DataFrame(j.get("data",[]))

@st.cache_data(ttl=21600,show_spinner=False)
def stock_info(token):
    d=api_get("TaiwanStockInfo",token=token)
    if d.empty:return d
    d["date"]=pd.to_datetime(d["date"],errors="coerce")
    d=d.sort_values("date").drop_duplicates("stock_id",keep="last")
    return d

@st.cache_data(ttl=1800,show_spinner=False)
def price_one(code,start,end,token):
    d=api_get("TaiwanStockPrice",code,start,end,token)
    return clean_price(d)

@st.cache_data(ttl=1800,show_spinner=False)
def price_all(start,end,token):
    # 真正全市場查詢：FinMind Backer/Sponsor 才支援不帶 data_id
    d=api_get("TaiwanStockPrice",None,start,end,token)
    return clean_price(d)

@st.cache_data(ttl=1800,show_spinner=False)
def chip_one(code,start,end,token):
    a=api_get("TaiwanStockInstitutionalInvestorsBuySellWide",code,start,end,token)
    m=api_get("TaiwanStockMarginPurchaseShortSale",code,start,end,token)
    for d in (a,m):
        if not d.empty and "date" in d:d["date"]=pd.to_datetime(d["date"])
    return a,m

def clean_price(d):
    if d.empty:return d
    d["date"]=pd.to_datetime(d["date"])
    for c in ["open","max","min","close","Trading_Volume","Trading_money","Trading_turnover"]:
        if c in d:d[c]=pd.to_numeric(d[c],errors="coerce")
    return d[d["close"]>0].sort_values("date")

def ema(s,n):return s.ewm(span=n,adjust=False).mean()
def pct(a,b):return (a/b-1)*100 if pd.notna(a) and pd.notna(b) and b else np.nan
def rsi(s,n=14):
    x=s.diff();g=x.clip(lower=0).ewm(alpha=1/n,adjust=False).mean()
    l=(-x.clip(upper=0)).ewm(alpha=1/n,adjust=False).mean()
    return 100-100/(1+g/l.replace(0,np.nan))
def kd(d,n=9):
    lo=d["min"].rolling(n).min();hi=d["max"].rolling(n).max()
    r=(d["close"]-lo)/(hi-lo).replace(0,np.nan)*100
    k=r.ewm(alpha=1/3,adjust=False).mean();dd=k.ewm(alpha=1/3,adjust=False).mean()
    return k,dd
def obv(d):
    return (np.sign(d["close"].diff()).fillna(0)*d["Trading_Volume"].fillna(0)).cumsum()
def slope_pct(s,n):
    y=s.dropna().tail(n).values
    if len(y)<n or np.nanmean(y)==0:return np.nan
    return np.polyfit(np.arange(n),y,1)[0]/np.nanmean(y)*100
def slope_text(x):
    if pd.isna(x):return "-"
    if x>=.7:return "↑ 加速上揚"
    if x>=.12:return "↗ 緩升"
    if x<=-.7:return "↓ 加速下彎"
    if x<=-.12:return "↘ 緩跌"
    return "→ 走平"

def enrich(d):
    d=d.copy().reset_index(drop=True);c=d["close"]
    for n in [5,10,20,60,120,240]:d[f"ma{n}"]=c.rolling(n).mean()
    d["v20"]=d["Trading_Volume"].rolling(20).mean()
    d["vr"]=d["Trading_Volume"]/d["v20"].replace(0,np.nan)
    d["rsi"]=rsi(c);d["k"],d["d"]=kd(d)
    d["ema12"]=ema(c,12);d["ema26"]=ema(c,26);d["macd"]=d["ema12"]-d["ema26"]
    d["signal"]=ema(d["macd"],9);d["hist"]=d["macd"]-d["signal"];d["obv"]=obv(d)
    return d

def levels(d):
    close=float(d["close"].iloc[-1]);sup=[];res=[]
    for n in [5,10,20,60,120,240]:
        v=d[f"ma{n}"].iloc[-1]
        if pd.notna(v):(sup if v<close else res).append(float(v))
    for n in [20,40,60,120]:
        if len(d)>=n:
            sup.append(float(d["min"].tail(n).min()));res.append(float(d["max"].tail(n).max()))
    x=d.tail(90).reset_index(drop=True)
    for i in range(2,len(x)-2):
        if x.loc[i,"min"]==x.loc[i-2:i+2,"min"].min():sup.append(float(x.loc[i,"min"]))
        if x.loc[i,"max"]==x.loc[i-2:i+2,"max"].max():res.append(float(x.loc[i,"max"]))
    def merge(a,side):
        a=sorted([v for v in a if np.isfinite(v) and v>0])
        z=[]
        for v in a:
            if not z or abs(v-z[-1])/close>.012:z.append(v)
            else:z[-1]=(z[-1]+v)/2
        z=[v for v in z if (v<close*.999 if side=="s" else v>close*1.001)]
        return (sorted(z,reverse=True) if side=="s" else sorted(z))[:3]
    return merge(sup,"s"),merge(res,"r")

def pattern(d):
    if len(d)<60:return "資料不足"
    c=d["close"];h=d["max"];l=d["min"];x=d.iloc[-1]
    hi20=h.tail(20).max();lo20=l.tail(20).min();hi60=h.tail(60).max();lo60=l.tail(60).min()
    range20=(hi20-lo20)/max(lo20,1)
    r40=pct(c.iloc[-1],c.iloc[-41])
    if range20<.08 and c.iloc[-1]>=hi20*.985:return "箱型整理・接近突破"
    if c.iloc[-1]>=hi60*.99 and x["vr"]>=1.3:return "平台突破"
    if r40>25 and pct(c.iloc[-1],hi60)<-2 and c.iloc[-1]>x["ma20"]:return "強勢股拉回"
    if r40<0 and c.iloc[-1]>x["ma20"] and x["vr"]>=1.5:return "跌深轉折"
    # 簡易雙底：前後兩個20日低點接近，現價站回頸線區
    a=l.iloc[-60:-30].min();b=l.iloc[-30:].min()
    if abs(a-b)/max(a,b)<.05 and c.iloc[-1]>c.tail(30).mean():return "雙底雛形"
    if x["ma5"]>x["ma10"]>x["ma20"]:return "多頭排列"
    return "整理／未明確"

def chip_summary(inst,margin):
    foreign=trust=0;mc=sc=np.nan
    if inst is not None and not inst.empty:
        q=inst.sort_values("date").tail(5).copy()
        for c in q.columns:
            if c not in ["date","stock_id"]:q[c]=pd.to_numeric(q[c],errors="coerce").fillna(0)
        if {"Foreign_Investor_buy","Foreign_Investor_sell"}.issubset(q):
            foreign=float((q["Foreign_Investor_buy"]-q["Foreign_Investor_sell"]).sum())
        if {"Investment_Trust_buy","Investment_Trust_sell"}.issubset(q):
            trust=float((q["Investment_Trust_buy"]-q["Investment_Trust_sell"]).sum())
    if margin is not None and len(margin)>=2:
        q=margin.sort_values("date").tail(2).copy()
        for c in ["MarginPurchaseTodayBalance","ShortSaleTodayBalance"]:
            if c in q:q[c]=pd.to_numeric(q[c],errors="coerce")
        if "MarginPurchaseTodayBalance" in q:mc=float(q[c].iloc[-1]-q[c].iloc[-2]) if False else float(q["MarginPurchaseTodayBalance"].iloc[-1]-q["MarginPurchaseTodayBalance"].iloc[-2])
        if "ShortSaleTodayBalance" in q:sc=float(q["ShortSaleTodayBalance"].iloc[-1]-q["ShortSaleTodayBalance"].iloc[-2])
    return foreign,trust,mc,sc

def analyze(raw,inst=None,margin=None):
    if raw is None or len(raw)<65:return None
    d=enrich(raw);x=d.iloc[-1];close=float(x["close"])
    s,r=levels(d);s1=s[0] if s else np.nan;r1=r[0] if r else np.nan
    rr=((r1-close)/(close-s1)) if pd.notna(s1) and pd.notna(r1) and close>s1 else np.nan
    bias5=pct(close,x["ma5"]);bias20=pct(close,x["ma20"]);bias60=pct(close,x["ma60"])
    sl5=slope_pct(d["ma5"],5);sl20=slope_pct(d["ma20"],10);sl60=slope_pct(d["ma60"],15)
    hi20=d["max"].tail(20).max();hi40=d["max"].tail(40).max()
    r5=pct(close,d["close"].iloc[-6]);r20=pct(close,d["close"].iloc[-21]);r40=pct(close,d["close"].iloc[-41])
    fromhi=pct(close,hi40);vr=float(x["vr"]) if pd.notna(x["vr"]) else np.nan
    foreign,trust,mc,sc=chip_summary(inst,margin)
    score=0;why=[];risk=0;risks=[];conds=[]
    if close>x["ma5"]:score+=4
    if close>x["ma10"]:score+=4
    if close>x["ma20"]:score+=5
    if pd.notna(x["ma60"]) and close>x["ma60"]:score+=5
    if x["ma5"]>x["ma10"]>x["ma20"]:score+=7;why.append("5>10>20MA")
    if sl20>.12:score+=5;why.append("20MA斜率向上")
    if pd.notna(vr) and vr>=1.3:score+=6;why.append(f"量比{vr:.2f}x")
    if close>=hi20*.995:score+=6;why.append("接近20日高")
    if x["hist"]>d["hist"].iloc[-2]:score+=4;why.append("MACD改善")
    if x["k"]>x["d"] and x["k"]<85:score+=4;why.append("KD偏多")
    if x["obv"]>d["obv"].tail(20).mean():score+=4;why.append("OBV偏多")
    if 45<=x["rsi"]<=72:score+=4
    if foreign>0:score+=5;why.append("外資5日買超")
    if trust>0:score+=5;why.append("投信5日買超")
    if pd.notna(rr) and rr>=2:score+=5;why.append("風報比佳")
    if pd.notna(r40) and r40<22 and pd.notna(vr) and vr>=1.7 and close>=hi40*.99:conds.append("③第一波")
    if pd.notna(r40) and r40>25 and -15<fromhi<-2 and vr<1.25:conds.append("④第二波")
    if close>=hi20*.995 and pd.notna(vr) and vr>=1.3:conds.append("②盤整突破")
    if pd.notna(r40) and r40>30 and close>=hi40*.99:conds.append("⑥強勢噴出")
    if pd.notna(x["ma60"]) and pd.notna(vr) and vr>=1.8 and close>x["ma20"] and r40<0:conds.append("⑦跌深轉折")
    if pd.notna(x["ma60"]) and abs(x["ma20"]/x["ma60"]-1)<.08 and close>x["ma20"]:conds.append("⑧整理轉強")
    if not conds and close>x["ma20"]:conds=["①強勢觀察"]
    # 風險係數 0~100，越高越危險
    if pd.notna(bias5) and bias5>8:risk+=20;risks.append("5MA乖離大")
    if pd.notna(bias20) and bias20>15:risk+=20;risks.append("20MA乖離大")
    if pd.notna(vr) and vr>=2.8:risk+=15;risks.append("爆量")
    if close<x["ma20"]:risk+=20;risks.append("跌破20MA")
    if sl20<-.12:risk+=15;risks.append("20MA下彎")
    if pd.notna(rr) and rr<1:risk+=15;risks.append("風報比差")
    if pd.notna(x["rsi"]) and x["rsi"]>80:risk+=10;risks.append("RSI過熱")
    risk=min(100,risk)
    score=int(max(0,min(100,round(score-risk*.12))))
    return dict(date=x["date"].date(),close=close,score=score,condition="、".join(conds),
      pattern=pattern(d),risk_factor=risk,risk_text="、".join(risks) or "低",
      bias5=bias5,bias20=bias20,bias60=bias60,vr=vr,rsi=x["rsi"],k=x["k"],dd=x["d"],
      slope5=sl5,slope20=sl20,slope60=sl60,slope5_text=slope_text(sl5),
      slope20_text=slope_text(sl20),slope60_text=slope_text(sl60),
      support1=s1,support2=s[1] if len(s)>1 else np.nan,resistance1=r1,resistance2=r[1] if len(r)>1 else np.nan,
      rr=rr,foreign5=foreign,trust5=trust,margin_change=mc,short_change=sc,why="、".join(why[:7]),data=d)

def chart(d,code,name):
    q=d.tail(140)
    fig=make_subplots(rows=2,cols=1,shared_xaxes=True,vertical_spacing=.03,row_heights=[.75,.25])
    fig.add_trace(go.Candlestick(x=q.date,open=q.open,high=q["max"],low=q["min"],close=q.close,name="K線"),row=1,col=1)
    for n in [5,10,20,60]:
        fig.add_trace(go.Scatter(x=q.date,y=q[f"ma{n}"],name=f"MA{n}",line=dict(width=1)),row=1,col=1)
    fig.add_trace(go.Bar(x=q.date,y=q.Trading_Volume,name="成交量"),row=2,col=1)
    fig.update_layout(height=620,title=f"{code} {name}｜日K走勢",xaxis_rangeslider_visible=False,
                      template="plotly_dark",margin=dict(l=10,r=10,t=45,b=10))
    return fig

def fmt(v,d=2):
    return "-" if pd.isna(v) else f"{v:.{d}f}"

try: default_token=st.secrets["FINMIND_TOKEN"]
except Exception: default_token=""

st.title("📈 賊大戰術 Pro｜全市場智能選股")
st.caption("全市場掃描・賊大①～⑧・型態・斜率・乖離・支撐壓力・風險係數・風報比・個股K線")

with st.sidebar:
    st.header("掃描設定")
    token=st.text_input("FinMind Token",value=default_token,type="password")
    min_price=st.number_input("最低股價",1.0,300.0,5.0,1.0)
    max_price=st.number_input("最高股價",10.0,3000.0,300.0,10.0)
    min_vol=st.number_input("最低5日均量（張）",100,100000,500,100)
    min_score=st.slider("最低分數",40,95,65)
    chip_top=st.slider("Top幾檔再抓籌碼",0,30,10)
    st.caption("籌碼逐檔查詢較耗 API 配額。")

st.info("真正「上市＋上櫃全部股票」需要 FinMind Backer/Sponsor 的全市場日價權限；程式會直接嘗試全市場資料，若帳號沒有權限會明確提示，不會假裝已掃全部。")

if "detail_code" not in st.session_state:st.session_state.detail_code=None
scan=st.button("🚀 全市場盤後掃描",type="primary",use_container_width=True)

if scan:
    end=date.today();start=end-timedelta(days=380)
    try:
        with st.spinner("下載全市場歷史日價…"):
            allp=price_all(start,end,token)
        if allp.empty or "stock_id" not in allp.columns:
            raise RuntimeError("沒有取得全市場股票資料")
        info=stock_info(token)
        # 只留一般4碼股票，排除ETF/權證等
        allp["stock_id"]=allp["stock_id"].astype(str)
        codes=[c for c in allp["stock_id"].unique() if len(c)==4 and c.isdigit()]
        if not info.empty:
            info["stock_id"]=info["stock_id"].astype(str)
            # TaiwanStockInfo type欄位若可辨識股票，優先排除名稱中的ETF/ETN
            bad_words="ETF|ETN|債|反1|正2"
            bad=set(info[info["stock_name"].astype(str).str.contains(bad_words,regex=True,na=False)]["stock_id"])
            codes=[c for c in codes if c not in bad]
        name_map=dict(zip(info["stock_id"],info["stock_name"])) if not info.empty else {}
        rows=[];detail={}
        bar=st.progress(0,text="技術面初篩…")
        for i,code in enumerate(codes):
            p=allp[allp.stock_id==code].copy()
            if len(p)<65:continue
            p=clean_price(p)
            last=p.iloc[-1]
            if not(min_price<=last.close<=max_price):continue
            if p.Trading_Volume.tail(5).mean()/1000<min_vol:continue
            a=analyze(p)
            if a:
                detail[code]=a
                rows.append({k:v for k,v in a.items() if k!="data"}|{"stock_id":code,"stock_name":name_map.get(code,"")})
            if i%25==0:bar.progress((i+1)/max(len(codes),1),text=f"技術面初篩 {i+1}/{len(codes)}")
        bar.empty()
        rd=pd.DataFrame(rows)
        if rd.empty:st.warning("沒有符合基本流動性條件的股票。");st.stop()
        rd=rd.sort_values(["score","risk_factor"],ascending=[False,True])
        # Top N 補籌碼後重算
        if chip_top>0:
            with st.spinner(f"補抓前 {min(chip_top,len(rd))} 檔法人／融資融券…"):
                for code in rd.head(chip_top).stock_id.tolist():
                    try:
                        p=allp[allp.stock_id==code].copy()
                        inst,mar=chip_one(code,end-timedelta(days=35),end,token)
                        a=analyze(clean_price(p),inst,mar);detail[code]=a
                        for k,v in a.items():
                            if k!="data":rd.loc[rd.stock_id==code,k]=v
                    except Exception:pass
        rd=rd[rd.score>=min_score].sort_values(["score","risk_factor"],ascending=[False,True])
        st.session_state["scan_df"]=rd
        st.session_state["detail"]=detail
        st.session_state["scan_date"]=str(end)
    except Exception as e:
        st.error("全市場掃描沒有成功。")
        st.warning("最常見原因：目前 FinMind 帳號沒有 Backer/Sponsor 的「不帶 stock_id 全市場日價」權限。")
        st.code(str(e))
        st.stop()

if "scan_df" in st.session_state:
    rd=st.session_state["scan_df"]
    if rd.empty:
        st.warning("本次沒有股票達到最低分數。")
    else:
        a,b,c,d=st.columns(4)
        a.metric("入選",len(rd));b.metric("90分以上",int((rd.score>=90).sum()))
        c.metric("低風險 ≤30",int((rd.risk_factor<=30).sum()))
        d.metric("風報比 ≥2",int((rd.rr>=2).sum()))
        st.subheader("🏆 Top 10")
        top=rd.head(10).copy()
        show=top[["stock_id","stock_name","score","condition","pattern","close","bias5","bias20","slope20_text",
                  "support1","resistance1","risk_factor","rr"]].copy()
        show.columns=["代號","名稱","分數","賊大條件","型態","收盤","5MA乖離%","20MA乖離%","20MA斜率",
                      "第一支撐","第一壓力","風險係數","風報比"]
        st.dataframe(show,use_container_width=True,hide_index=True,column_config={
            "分數":st.column_config.ProgressColumn(min_value=0,max_value=100),
            "風險係數":st.column_config.ProgressColumn(min_value=0,max_value=100),
            "5MA乖離%":st.column_config.NumberColumn(format="%.1f%%"),
            "20MA乖離%":st.column_config.NumberColumn(format="%.1f%%"),
            "風報比":st.column_config.NumberColumn(format="%.2f"),
        })
        st.markdown("### 👆 點進個股看走勢")
        cols=st.columns(2)
        for i,(_,x) in enumerate(top.iterrows()):
            if cols[i%2].button(f"{x.stock_id} {x.stock_name}｜{int(x.score)}分｜{x.pattern}",key=f"b{x.stock_id}",use_container_width=True):
                st.session_state.detail_code=x.stock_id
        code=st.session_state.detail_code
        if code and code in st.session_state["detail"]:
            x=st.session_state["detail"][code]
            name=top.loc[top.stock_id==code,"stock_name"].iloc[0] if code in top.stock_id.values else ""
            st.divider();st.header(f"🔎 {code} {name} 詳細分析")
            m1,m2,m3,m4,m5=st.columns(5)
            m1.metric("收盤",fmt(x["close"]));m2.metric("分數",x["score"])
            m3.metric("風險係數",f'{x["risk_factor"]}/100');m4.metric("風報比",fmt(x["rr"]))
            m5.metric("型態",x["pattern"])
            st.plotly_chart(chart(x["data"],code,name),use_container_width=True)
            t1,t2,t3=st.tabs(["型態・斜率・乖離","支撐壓力・風險","技術指標・籌碼"])
            with t1:
                st.write(f"**型態：** {x['pattern']}")
                st.write(f"**MA5斜率：** {x['slope5_text']}（{fmt(x['slope5'],3)}%/日）")
                st.write(f"**MA20斜率：** {x['slope20_text']}（{fmt(x['slope20'],3)}%/日）")
                st.write(f"**MA60斜率：** {x['slope60_text']}（{fmt(x['slope60'],3)}%/日）")
                st.write(f"**乖離：** 5MA {fmt(x['bias5'])}%｜20MA {fmt(x['bias20'])}%｜60MA {fmt(x['bias60'])}%")
            with t2:
                st.write(f"**第一支撐：** {fmt(x['support1'])}　**第二支撐：** {fmt(x['support2'])}")
                st.write(f"**第一壓力：** {fmt(x['resistance1'])}　**第二壓力：** {fmt(x['resistance2'])}")
                st.write(f"**風險係數：** {x['risk_factor']}/100｜{x['risk_text']}")
                st.write(f"**風報比：** {fmt(x['rr'])}（第一壓力 ÷ 第一支撐風險估算）")
            with t3:
                st.write(f"**RSI：** {fmt(x['rsi'],1)}｜**KD：** K {fmt(x['k'],1)} / D {fmt(x['dd'],1)}｜**量比：** {fmt(x['vr'])}x")
                st.write(f"**近5日外資淨額：** {x['foreign5']:,.0f}｜**投信淨額：** {x['trust5']:,.0f}")
                st.write(f"**賊大條件：** {x['condition']}")
                st.write(f"**加分理由：** {x['why'] or '—'}")
            if x["risk_factor"]<=30 and x["score"]>=80:
                st.success("劇本：偏強勢，但仍以回測支撐、突破後確認量價為主，避免離均線過遠追價。")
            elif x["risk_factor"]>=60:
                st.error("劇本：風險偏高，優先等待乖離收斂、支撐確認或型態重新轉強。")
            else:
                st.warning("劇本：觀察區，等待支撐／量價／斜率進一步確認。")

st.caption("⚠️ 本工具是盤後篩選與研究工具，不是買賣保證。支撐、壓力、型態與風險係數皆為程式化估算。")
