import re, math
from datetime import date, timedelta
import numpy as np
import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="賊大戰術 Pro 免費版", page_icon="📈", layout="wide")
FIN="https://api.finmindtrade.com/api/v4/data"
TWSE="https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX="https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
HEAD={"User-Agent":"Mozilla/5.0"}

st.markdown("""<style>
.stApp{background:#07111f;color:#eaf2ff}.block-container{max-width:1450px;padding-top:1rem}
[data-testid="stMetric"]{background:#0c1b2d;border:1px solid #24415f;border-radius:12px;padding:10px}
</style>""",unsafe_allow_html=True)

def num(x):
    if x is None:return np.nan
    s=str(x).replace(",","").replace("--","").replace("---","").replace("X","").strip()
    try:return float(s)
    except:return np.nan

def pick(row, keys):
    for k in keys:
        if k in row and str(row[k]).strip() not in ("","-","--"): return row[k]
    return None

@st.cache_data(ttl=900,show_spinner=False)
def market_snapshot():
    out=[]
    # 上市
    r=requests.get(TWSE,headers=HEAD,timeout=30);r.raise_for_status()
    for x in r.json():
        code=str(pick(x,["Code","證券代號","股票代號"]) or "").strip()
        name=str(pick(x,["Name","證券名稱","股票名稱"]) or "").strip()
        close=num(pick(x,["ClosingPrice","收盤價","Close"]))
        vol=num(pick(x,["TradeVolume","成交股數","Trading_Volume"]))
        val=num(pick(x,["TradeValue","成交金額","Trading_money"]))
        chg=num(pick(x,["Change","漲跌價差","ChangePrice"]))
        if re.fullmatch(r"\d{4}",code) and np.isfinite(close):
            out.append([code,name,"上市",close,vol,val,chg])
    # 上櫃
    r=requests.get(TPEX,headers=HEAD,timeout=30);r.raise_for_status()
    for x in r.json():
        code=str(pick(x,["SecuritiesCompanyCode","Code","證券代號","股票代號"]) or "").strip()
        name=str(pick(x,["CompanyName","SecuritiesCompanyName","Name","證券名稱","股票名稱"]) or "").strip()
        close=num(pick(x,["Close","ClosingPrice","收盤價"]))
        vol=num(pick(x,["TradingShares","TradeVolume","成交股數","成交量"]))
        val=num(pick(x,["TransactionAmount","TradeValue","成交金額"]))
        chg=num(pick(x,["Change","ChangePrice","漲跌價差"]))
        if re.fullmatch(r"\d{4}",code) and np.isfinite(close):
            out.append([code,name,"上櫃",close,vol,val,chg])
    d=pd.DataFrame(out,columns=["stock_id","stock_name","market","close","volume","value","change"])
    d=d.drop_duplicates("stock_id")
    d=d[~d.stock_name.str.contains("ETF|ETN|指數|債券|權證",case=False,na=False)]
    return d

def fin(dataset,code,start,end,token=""):
    p={"dataset":dataset,"data_id":code,"start_date":str(start),"end_date":str(end)}
    h={"Authorization":f"Bearer {token}"} if token else {}
    r=requests.get(FIN,params=p,headers=h,timeout=35);r.raise_for_status()
    j=r.json()
    if j.get("status") not in (200,None):raise RuntimeError(j.get("msg","API error"))
    return pd.DataFrame(j.get("data",[]))

@st.cache_data(ttl=3600,show_spinner=False)
def history(code,start,end,token):
    d=fin("TaiwanStockPrice",code,start,end,token)
    if d.empty:return d
    d["date"]=pd.to_datetime(d["date"])
    for c in ["open","max","min","close","Trading_Volume","Trading_money"]:
        if c in d:d[c]=pd.to_numeric(d[c],errors="coerce")
    return d.dropna(subset=["close"]).sort_values("date")

@st.cache_data(ttl=3600,show_spinner=False)
def chips(code,start,end,token):
    try:a=fin("TaiwanStockInstitutionalInvestorsBuySellWide",code,start,end,token)
    except:a=pd.DataFrame()
    try:m=fin("TaiwanStockMarginPurchaseShortSale",code,start,end,token)
    except:m=pd.DataFrame()
    return a,m

def rsi(s,n=14):
    z=s.diff();g=z.clip(lower=0).ewm(alpha=1/n,adjust=False).mean()
    l=(-z.clip(upper=0)).ewm(alpha=1/n,adjust=False).mean()
    return 100-100/(1+g/l.replace(0,np.nan))
def slope(s,n):
    y=s.dropna().tail(n).values
    return np.polyfit(range(len(y)),y,1)[0]/np.mean(y)*100 if len(y)>=n and np.mean(y) else np.nan
def slabel(x):
    if pd.isna(x):return "-"
    return "↑加速" if x>.7 else "↗上揚" if x>.12 else "↓下彎" if x<-.7 else "↘走弱" if x<-.12 else "→走平"
def pct(a,b):return (a/b-1)*100 if pd.notna(a) and pd.notna(b) and b else np.nan

def prep(d):
    d=d.copy()
    for n in [5,10,20,60,120,240]:d[f"ma{n}"]=d.close.rolling(n).mean()
    d["v20"]=d.Trading_Volume.rolling(20).mean();d["vr"]=d.Trading_Volume/d.v20.replace(0,np.nan)
    d["rsi"]=rsi(d.close)
    e12=d.close.ewm(span=12,adjust=False).mean();e26=d.close.ewm(span=26,adjust=False).mean()
    d["macd"]=e12-e26;d["signal"]=d.macd.ewm(span=9,adjust=False).mean();d["hist"]=d.macd-d.signal
    lo=d["min"].rolling(9).min();hi=d["max"].rolling(9).max()
    raw=(d.close-lo)/(hi-lo).replace(0,np.nan)*100
    d["k"]=raw.ewm(alpha=1/3,adjust=False).mean();d["kd"]=d.k.ewm(alpha=1/3,adjust=False).mean()
    d["obv"]=(np.sign(d.close.diff()).fillna(0)*d.Trading_Volume).cumsum()
    return d

def support_resistance(d):
    c=d.close.iloc[-1];cand=[]
    for n in [5,10,20,60,120,240]:
        v=d[f"ma{n}"].iloc[-1]
        if pd.notna(v):cand.append(float(v))
    for n in [20,40,60]:
        if len(d)>=n:cand += [float(d["min"].tail(n).min()),float(d["max"].tail(n).max())]
    s=sorted({round(v,2) for v in cand if v<c*.998},reverse=True)
    r=sorted({round(v,2) for v in cand if v>c*1.002})
    return (s+[np.nan,np.nan])[:2],(r+[np.nan,np.nan])[:2]

def patt(d):
    x=d.iloc[-1];c=x.close;hi20=d["max"].tail(20).max();lo20=d["min"].tail(20).min()
    r40=pct(c,d.close.iloc[-41]) if len(d)>41 else np.nan
    if c>=hi20*.995 and x.vr>=1.3:return "平台突破"
    if (hi20-lo20)/lo20<.10:return "箱型整理"
    if pd.notna(r40) and r40>25 and c<d["max"].tail(40).max()*.98 and c>x.ma20:return "強勢股拉回"
    if pd.notna(r40) and r40<0 and c>x.ma20 and x.vr>=1.5:return "跌深轉折"
    if x.ma5>x.ma10>x.ma20:return "多頭排列"
    return "整理觀察"

def chipnet(a):
    f=t=0
    if a.empty:return f,t
    q=a.tail(5).copy()
    for c in q.columns:
        if c not in ["date","stock_id"]:q[c]=pd.to_numeric(q[c],errors="coerce").fillna(0)
    if {"Foreign_Investor_buy","Foreign_Investor_sell"}<=set(q):f=float((q.Foreign_Investor_buy-q.Foreign_Investor_sell).sum())
    if {"Investment_Trust_buy","Investment_Trust_sell"}<=set(q):t=float((q.Investment_Trust_buy-q.Investment_Trust_sell).sum())
    return f,t

def analyze(raw,a=pd.DataFrame()):
    if len(raw)<65:return None
    d=prep(raw);x=d.iloc[-1];c=float(x.close);s,r=support_resistance(d)
    b5=pct(c,x.ma5);b20=pct(c,x.ma20);b60=pct(c,x.ma60)
    sl5=slope(d.ma5,5);sl20=slope(d.ma20,10);sl60=slope(d.ma60,15)
    r40=pct(c,d.close.iloc[-41]);hi40=d["max"].tail(40).max();fromhi=pct(c,hi40);f,t=chipnet(a)
    rr=(r[0]-c)/(c-s[0]) if pd.notna(r[0]) and pd.notna(s[0]) and c>s[0] else np.nan
    score=35;why=[];cond=[]
    for ok,pts,txt in [(c>x.ma5,5,"站5MA"),(c>x.ma20,8,"站20MA"),(c>x.ma60,6,"站60MA"),
                       (x.ma5>x.ma10>x.ma20,8,"多頭排列"),(sl20>.12,6,"20MA向上"),
                       (x.vr>=1.3,6,"量能放大"),(x.hist>d.hist.iloc[-2],4,"MACD改善"),
                       (x.k>x.kd,4,"KD偏多"),(f>0,5,"外資5日買超"),(t>0,5,"投信5日買超")]:
        if bool(ok):score+=pts;why.append(txt)
    if r40<22 and x.vr>=1.7 and c>=hi40*.99:cond.append("③剛起動")
    if r40>25 and -15<fromhi<-2 and x.vr<1.3:cond.append("④強勢拉回")
    if c>=d["max"].tail(20).max()*.995 and x.vr>=1.3:cond.append("②盤整突破")
    if r40>30 and c>=hi40*.99:cond.append("⑥強勢噴出")
    if r40<0 and x.vr>=1.8 and c>x.ma20:cond.append("⑦跌深轉折")
    if not cond:cond=["①強勢觀察" if c>x.ma20 else "整理觀察"]
    risk=0;ris=[]
    for ok,pts,txt in [(b5>8,20,"5MA乖離大"),(b20>15,20,"20MA乖離大"),(x.vr>2.8,15,"爆量"),
                       (c<x.ma20,20,"跌破20MA"),(sl20<-.12,15,"20MA下彎"),(pd.notna(rr) and rr<1,15,"風報比差"),
                       (x.rsi>80,10,"RSI過熱")]:
        if bool(ok):risk+=pts;ris.append(txt)
    score=max(0,min(100,round(score-risk*.12)))
    return {"close":c,"score":score,"condition":"、".join(cond),"pattern":patt(d),"risk":min(risk,100),
            "bias5":b5,"bias20":b20,"bias60":b60,"slope5":sl5,"slope20":sl20,"slope60":sl60,
            "slope20_text":slabel(sl20),"support1":s[0],"support2":s[1],"resistance1":r[0],"resistance2":r[1],
            "rr":rr,"rsi":x.rsi,"k":x.k,"kd":x.kd,"vr":x.vr,"foreign5":f,"trust5":t,
            "why":"、".join(why[:7]),"risk_text":"、".join(ris) or "低","data":d}

def chart(d,code,name):
    q=d.tail(140);fig=make_subplots(rows=2,cols=1,shared_xaxes=True,row_heights=[.75,.25],vertical_spacing=.03)
    fig.add_trace(go.Candlestick(x=q.date,open=q.open,high=q["max"],low=q["min"],close=q.close,name="K"),1,1)
    for n in [5,10,20,60]:fig.add_trace(go.Scatter(x=q.date,y=q[f"ma{n}"],name=f"MA{n}",line=dict(width=1)),1,1)
    fig.add_trace(go.Bar(x=q.date,y=q.Trading_Volume,name="量"),2,1)
    fig.update_layout(template="plotly_dark",height=620,title=f"{code} {name}",xaxis_rangeslider_visible=False)
    return fig

st.title("📈 賊大戰術 Pro｜免費全市場版")
st.caption("TWSE＋TPEx 官方免費行情掃全市場 → 免費逐檔歷史資料深度分析 → Top 10")
try:default_token=st.secrets["FINMIND_TOKEN"]
except:default_token=""
with st.sidebar:
    st.header("設定")
    token=st.text_input("FinMind 免費 Token（可留空）",default_token,type="password")
    minp=st.number_input("最低股價",1.,300.,5.)
    maxp=st.number_input("最高股價",10.,3000.,300.)
    minlots=st.number_input("最低當日成交量（張）",100,100000,500,100)
    candidates=st.slider("深度分析候選數",20,60,35)
    st.caption("免費版先掃全部上市櫃，再只對最活躍候選股抓歷史資料，避免免費 API 額度爆掉。")

if st.button("🚀 全市場盤後掃描",type="primary",use_container_width=True):
    try:
        snap=market_snapshot()
        snap["lots"]=snap.volume/1000
        snap=snap[(snap.close>=minp)&(snap.close<=maxp)&(snap.lots>=minlots)].copy()
        # 全市場初篩：成交金額優先；若官方欄位缺成交金額則用成交量*價格
        snap["activity"]=snap.value.where(snap.value.notna()&(snap.value>0),snap.volume*snap.close)
        snap["move"]=snap.change.abs().fillna(0)/snap.close.replace(0,np.nan)
        snap["pre"]=snap.activity.rank(pct=True)*.7+snap.move.rank(pct=True)*.3
        short=snap.sort_values("pre",ascending=False).head(candidates)
        rows=[];details={}
        bar=st.progress(0,text="抓取候選股歷史資料…")
        end=date.today();start=end-timedelta(days=390)
        for i,z in enumerate(short.itertuples()):
            try:
                h=history(z.stock_id,start,end,token)
                a,_=chips(z.stock_id,end-timedelta(days=35),end,token)
                an=analyze(h,a)
                if an:
                    details[z.stock_id]=an
                    rows.append({k:v for k,v in an.items() if k!="data"}|{"stock_id":z.stock_id,"stock_name":z.stock_name,"market":z.market})
            except Exception:pass
            bar.progress((i+1)/len(short),text=f"深度分析 {i+1}/{len(short)}")
        bar.empty()
        if not rows:raise RuntimeError("候選股歷史資料未取得；可能是免費 API 暫時限流，稍後再試。")
        st.session_state["result"]=pd.DataFrame(rows).sort_values(["score","risk"],ascending=[False,True])
        st.session_state["details"]=details
        st.session_state["snapshot_count"]=len(snap)
    except Exception as e:
        st.error("掃描失敗："+str(e))

if "result" in st.session_state:
    rd=st.session_state.result;top=rd.head(10).copy()
    a,b,c,d=st.columns(4)
    a.metric("全市場通過流動性初篩",st.session_state.snapshot_count)
    b.metric("完成深度分析",len(rd));c.metric("80分以上",int((rd.score>=80).sum()));d.metric("低風險≤30",int((rd.risk<=30).sum()))
    st.subheader("🏆 Top 10")
    show=top[["stock_id","stock_name","market","score","condition","pattern","close","bias5","bias20","slope20_text","support1","resistance1","risk","rr"]].copy()
    show.columns=["代號","名稱","市場","分數","賊大條件","型態","收盤","5MA乖離%","20MA乖離%","20MA斜率","第一支撐","第一壓力","風險係數","風報比"]
    st.dataframe(show,hide_index=True,use_container_width=True)
    st.subheader("點股票看走勢")
    cc=st.columns(2)
    for i,z in enumerate(top.itertuples()):
        if cc[i%2].button(f"{z.stock_id} {z.stock_name}｜{z.score}分｜{z.pattern}",key=z.stock_id,use_container_width=True):
            st.session_state["detail"]=z.stock_id
    code=st.session_state.get("detail")
    if code in st.session_state.details:
        x=st.session_state.details[code];z=top[top.stock_id==code].iloc[0]
        st.divider();st.header(f"🔎 {code} {z.stock_name}")
        m=st.columns(5)
        m[0].metric("分數",x["score"]);m[1].metric("風險",f'{x["risk"]}/100');m[2].metric("型態",x["pattern"])
        m[3].metric("第一支撐",f'{x["support1"]:.2f}' if pd.notna(x["support1"]) else "-")
        m[4].metric("第一壓力",f'{x["resistance1"]:.2f}' if pd.notna(x["resistance1"]) else "-")
        st.plotly_chart(chart(x["data"],code,z.stock_name),use_container_width=True)
        st.write(f"**斜率：** MA5 {slabel(x['slope5'])}｜MA20 {slabel(x['slope20'])}｜MA60 {slabel(x['slope60'])}")
        st.write(f"**乖離：** 5MA {x['bias5']:.1f}%｜20MA {x['bias20']:.1f}%｜60MA {x['bias60']:.1f}%")
        st.write(f"**技術：** RSI {x['rsi']:.1f}｜KD {x['k']:.1f}/{x['kd']:.1f}｜量比 {x['vr']:.2f}x")
        st.write(f"**籌碼：** 外資5日 {x['foreign5']:,.0f}｜投信5日 {x['trust5']:,.0f}")
        st.write(f"**賊大條件：** {x['condition']}　**風報比：** {x['rr']:.2f}" if pd.notna(x["rr"]) else f"**賊大條件：** {x['condition']}")
        st.write(f"**風險原因：** {x['risk_text']}　**加分：** {x['why']}")
        if x["risk"]<=30 and x["score"]>=80:st.success("操作劇本：偏強，等支撐確認或突破量價確認，避免高乖離追價。")
        elif x["risk"]>=60:st.error("操作劇本：風險偏高，先等乖離收斂與支撐確認。")
        else:st.warning("操作劇本：觀察，等量價、支撐與斜率進一步確認。")
st.caption("資料源：TWSE、TPEx 官方公開行情；候選股歷史與籌碼使用 FinMind 免費逐檔查詢。程式化型態/支撐壓力為估算，不代表投資建議。")
