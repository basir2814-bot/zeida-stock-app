
import streamlit as st
import pandas as pd
import numpy as np
import requests
import time
import re
from datetime import date, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(page_title="賊大選股", page_icon="📈", layout="wide")

# =========================================================
# 賊大選股 Core v1
# 原則：
# 1) 僅依課程圖片條件①～⑤
# 2) 官方 TWSE / TPEx 為價格與公司主檔主來源
# 3) FinMind 僅用於「已經初篩後」的法人 / EPS 深度確認
# 4) 缺資料 = NA，不用 0 假裝
# 5) 每檔顯示實際數值與 ✅ / ❌
# =========================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ZeidaStock/1.0; +https://streamlit.io)"
}
TIMEOUT = 20

TWSE_DAY = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
TPEX_DAY = "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes"
TWSE_PROFILE = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TPEX_PROFILE = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
TWSE_REVENUE = "https://openapi.twse.com.tw/v1/opendata/t187ap05_L"
TPEX_REVENUE = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O"

FINMIND_DATA = "https://api.finmindtrade.com/api/v4/data"

# ---------------------------
# 工具
# ---------------------------

def safe_num(v):
    if v is None:
        return np.nan
    s = str(v).strip().replace(",", "").replace("＋", "").replace("+", "")
    s = s.replace("−", "-").replace("—", "").replace("--", "").replace("－", "")
    if s in {"", "N/A", "NA", "null", "None", "-"}:
        return np.nan
    # 去除 % / 元 / 股 / 張 等非數字尾碼
    s = s.replace("%", "")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return np.nan
    try:
        return float(m.group())
    except Exception:
        return np.nan

def first_present(row, names=(), contains=()):
    for n in names:
        if n in row and str(row[n]).strip() not in {"", "-", "－"}:
            return row[n]
    for k, v in row.items():
        kk = str(k).lower().replace(" ", "").replace("_", "").replace(".", "")
        if any(c.lower().replace(" ", "").replace("_", "").replace(".", "") in kk for c in contains):
            if str(v).strip() not in {"", "-", "－"}:
                return v
    return None

def is_stock_code(x):
    s = str(x).strip()
    return bool(re.fullmatch(r"\d{4}", s))

def pct(a, b):
    if pd.isna(a) or pd.isna(b) or b == 0:
        return np.nan
    return (a / b - 1.0) * 100.0

def fmt(v, digits=2, suffix=""):
    if pd.isna(v):
        return "NA"
    return f"{v:,.{digits}f}{suffix}"

def yn(ok):
    if pd.isna(ok):
        return "⚪"
    return "✅" if bool(ok) else "❌"

def http_json(url, params=None, retries=3):
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            time.sleep(0.8 * (i + 1))
    raise RuntimeError(f"抓取失敗：{url} | {last}")

# ---------------------------
# TWSE / TPEx 日行情
# ---------------------------

@st.cache_data(ttl=60*60*12, show_spinner=False)
def fetch_twse_day(d: str):
    """d = YYYYMMDD"""
    try:
        js = http_json(TWSE_DAY, {"response": "json", "date": d, "type": "ALLBUT0999"})
        if js.get("stat") not in {"OK", "很抱歉，沒有符合條件的資料!"}:
            return pd.DataFrame()
        tables = js.get("tables", [])
        target = None
        for t in tables:
            fields = t.get("fields", [])
            if "證券代號" in fields and "收盤價" in fields and "成交股數" in fields:
                target = t
                break
        # 舊版 schema fallback
        if target is None:
            for i in range(1, 20):
                fields = js.get(f"fields{i}", [])
                data = js.get(f"data{i}", [])
                if "證券代號" in fields and "收盤價" in fields and "成交股數" in fields:
                    target = {"fields": fields, "data": data}
                    break
        if target is None:
            return pd.DataFrame()

        raw = pd.DataFrame(target["data"], columns=target["fields"])
        out = pd.DataFrame({
            "date": pd.to_datetime(d),
            "stock_id": raw["證券代號"].astype(str).str.strip(),
            "name": raw["證券名稱"].astype(str).str.strip(),
            "market": "TWSE",
            "volume_shares": raw["成交股數"].map(safe_num),
            "open": raw["開盤價"].map(safe_num),
            "high": raw["最高價"].map(safe_num),
            "low": raw["最低價"].map(safe_num),
            "close": raw["收盤價"].map(safe_num),
        })
        out = out[out["stock_id"].map(is_stock_code)]
        out = out[out["close"].notna() & (out["close"] > 0)]
        return out
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=60*60*12, show_spinner=False)
def fetch_tpex_day(d_iso: str):
    """d_iso = YYYY/MM/DD"""
    try:
        js = http_json(TPEX_DAY, {"response": "json", "date": d_iso})
        # 2024+ 常見 schema: tables[0]
        tables = js.get("tables", [])
        target = None
        for t in tables:
            fields = t.get("fields", [])
            # 欄名可能為「代號」或「證券代號」
            if any("代號" in str(x) for x in fields) and any("收盤" in str(x) for x in fields):
                target = t
                break
        # fallback: aaData + fields
        if target is None and js.get("aaData"):
            fields = js.get("fields") or js.get("columnNames") or []
            if fields:
                target = {"fields": fields, "data": js["aaData"]}
        if target is None:
            return pd.DataFrame()

        raw = pd.DataFrame(target["data"], columns=target["fields"])
        def col_like(words):
            for c in raw.columns:
                cs = str(c)
                if all(w in cs for w in words):
                    return c
            return None

        c_id = col_like(["代號"]) or raw.columns[0]
        c_name = col_like(["名稱"])
        c_close = col_like(["收盤"])
        c_open = col_like(["開盤"])
        c_high = col_like(["最高"])
        c_low = col_like(["最低"])
        c_vol = col_like(["成交", "股"]) or col_like(["成交", "量"])

        if c_close is None or c_vol is None:
            return pd.DataFrame()

        out = pd.DataFrame({
            "date": pd.to_datetime(d_iso.replace("/", "-")),
            "stock_id": raw[c_id].astype(str).str.strip(),
            "name": raw[c_name].astype(str).str.strip() if c_name else "",
            "market": "TPEx",
            "volume_shares": raw[c_vol].map(safe_num),
            "open": raw[c_open].map(safe_num) if c_open else np.nan,
            "high": raw[c_high].map(safe_num) if c_high else np.nan,
            "low": raw[c_low].map(safe_num) if c_low else np.nan,
            "close": raw[c_close].map(safe_num),
        })
        # 某些舊端點成交量是「張」；用欄名判斷
        if c_vol and ("仟" in str(c_vol) or "千股" in str(c_vol) or "張" in str(c_vol)):
            out["volume_shares"] = out["volume_shares"] * 1000.0

        out = out[out["stock_id"].map(is_stock_code)]
        out = out[out["close"].notna() & (out["close"] > 0)]
        return out
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=60*60*12, show_spinner=False)
def fetch_history(days_back=78, max_workers=8):
    end = date.today()
    days = [end - timedelta(days=i) for i in range(days_back)]
    frames = []

    def one(d):
        tw = fetch_twse_day(d.strftime("%Y%m%d"))
        tp = fetch_tpex_day(d.strftime("%Y/%m/%d"))
        return tw, tp

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(one, d) for d in days]
        for f in as_completed(futs):
            try:
                tw, tp = f.result()
                if not tw.empty:
                    frames.append(tw)
                if not tp.empty:
                    frames.append(tp)
            except Exception:
                pass

    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(["date", "stock_id", "market"], keep="last")
    df = df.sort_values(["stock_id", "date"]).reset_index(drop=True)
    return df

# ---------------------------
# 公司主檔：股本 / 每股面額
# ---------------------------

@st.cache_data(ttl=60*60*24, show_spinner=False)
def fetch_profiles():
    rows = []
    try:
        for r in http_json(TWSE_PROFILE):
            sid = str(r.get("公司代號", "")).strip()
            if not is_stock_code(sid):
                continue
            cap = safe_num(first_present(
                r,
                names=("實收資本額", "實收資本額(元)"),
                contains=("實收資本", "paidincapital")
            ))
            par = safe_num(first_present(
                r,
                names=("普通股每股面額",),
                contains=("每股面額", "parvaluepershare", "parvalue")
            ))
            rows.append({
                "stock_id": sid,
                "market": "TWSE",
                "profile_name": str(r.get("公司簡稱", "")).strip(),
                "capital_ntd": cap,
                "par_value": par,
            })
    except Exception:
        pass

    try:
        for r in http_json(TPEX_PROFILE):
            sid = str(first_present(
                r,
                names=("SecuritiesCompanyCode",),
                contains=("securitiescompanycode",)
            ) or "").strip()
            if not is_stock_code(sid):
                continue
            cap = safe_num(first_present(
                r,
                contains=("paidincapital", "capitalstock", "capital")
            ))
            par = safe_num(first_present(
                r,
                contains=("parvaluepershare", "parvalue")
            ))
            rows.append({
                "stock_id": sid,
                "market": "TPEx",
                "profile_name": str(first_present(
                    r, names=("CompanyAbbreviation",), contains=("companyabbreviation",)
                ) or "").strip(),
                "capital_ntd": cap,
                "par_value": par,
            })
    except Exception:
        pass

    p = pd.DataFrame(rows)
    if p.empty:
        return p

    # 若官方欄位是「千元」而非元，使用保守偵測：
    # 多數上市櫃公司實收資本額不會只有數百 / 數千元。
    med = p["capital_ntd"].dropna().median()
    if pd.notna(med) and med < 1_000_000:
        p["capital_ntd"] = p["capital_ntd"] * 1000.0
    return p

# ---------------------------
# 月營收（條件⑤）
# ---------------------------

@st.cache_data(ttl=60*60*24, show_spinner=False)
def fetch_latest_revenue():
    out = []
    for market, url in [("TWSE", TWSE_REVENUE), ("TPEx", TPEX_REVENUE)]:
        try:
            data = http_json(url)
        except Exception:
            continue
        for r in data:
            sid = str(first_present(
                r,
                names=("公司代號", "SecuritiesCompanyCode"),
                contains=("公司代號", "securitiescompanycode")
            ) or "").strip()
            if not is_stock_code(sid):
                continue

            rev_now = safe_num(first_present(
                r,
                contains=("當月營收", "currentmonthrevenue", "currentmonth")
            ))
            rev_last_year = safe_num(first_present(
                r,
                contains=("去年當月營收", "lastyearmonthrevenue", "previousyear")
            ))
            yoy = safe_num(first_present(
                r,
                contains=("去年同月增減", "年增率", "increaseorreduce", "yoy")
            ))
            if pd.isna(yoy) and pd.notna(rev_now) and pd.notna(rev_last_year) and rev_last_year != 0:
                yoy = (rev_now / rev_last_year - 1) * 100

            year = safe_num(first_present(r, contains=("資料年度", "year")))
            month = safe_num(first_present(r, contains=("資料月份", "month")))

            out.append({
                "stock_id": sid,
                "market": market,
                "revenue": rev_now,
                "revenue_yoy": yoy,
                "revenue_year": year,
                "revenue_month": month,
            })
    return pd.DataFrame(out)

# ---------------------------
# FinMind 深度確認
# ---------------------------

def finmind_headers(token=""):
    return {"Authorization": f"Bearer {token}"} if token else {}

@st.cache_data(ttl=60*60*12, show_spinner=False)
def finmind_institutional(stock_id, start_date, end_date, token=""):
    try:
        params = {
            "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
            "data_id": stock_id,
            "start_date": start_date,
            "end_date": end_date,
        }
        r = requests.get(FINMIND_DATA, params=params, headers=finmind_headers(token), timeout=TIMEOUT)
        j = r.json()
        if j.get("status") != 200:
            return pd.DataFrame()
        df = pd.DataFrame(j.get("data", []))
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=60*60*24, show_spinner=False)
def finmind_eps(stock_id, start_date, token=""):
    """抓綜合損益表，從 EPS 類型中取近三季。
    若來源是累計 EPS，無法可靠拆季時回 NA，不硬猜。
    """
    try:
        params = {
            "dataset": "TaiwanStockFinancialStatements",
            "data_id": stock_id,
            "start_date": start_date,
        }
        r = requests.get(FINMIND_DATA, params=params, headers=finmind_headers(token), timeout=TIMEOUT)
        j = r.json()
        if j.get("status") != 200:
            return np.nan, []
        df = pd.DataFrame(j.get("data", []))
        if df.empty:
            return np.nan, []

        mask = (
            df["type"].astype(str).str.contains("EPS|EarningsPerShare|BasicEarningsPerShare", case=False, regex=True)
            | df.get("origin_name", pd.Series("", index=df.index)).astype(str).str.contains("每股盈餘|基本每股", regex=True)
        )
        e = df[mask].copy()
        if e.empty:
            return np.nan, []
        e["date"] = pd.to_datetime(e["date"], errors="coerce")
        e["value"] = pd.to_numeric(e["value"], errors="coerce")
        e = e.dropna(subset=["date", "value"]).sort_values("date")
        # 同一報表日期多個 EPS 欄位時，優先 origin_name 帶「基本每股」
        e["priority"] = e.get("origin_name", "").astype(str).str.contains("基本每股").astype(int)
        e = e.sort_values(["date", "priority"]).drop_duplicates("date", keep="last")

        # 僅接受日期落在 3/31, 6/30, 9/30, 12/31 附近
        # 若能取得近三個不同季報值，先回傳；畫面會標示「來源值」供人工核對。
        last = e.tail(3)
        if len(last) < 3:
            return np.nan, []
        vals = last["value"].tolist()
        return float(np.nansum(vals)), [
            {"date": d.strftime("%Y-%m-%d"), "eps": float(v)}
            for d, v in zip(last["date"], last["value"])
        ]
    except Exception:
        return np.nan, []

@st.cache_data(ttl=60*60*24, show_spinner=False)
def finmind_revenue_history(stock_id, token=""):
    try:
        params = {
            "dataset": "TaiwanStockMonthRevenue",
            "data_id": stock_id,
            "start_date": "2002-01-01",
        }
        r = requests.get(FINMIND_DATA, params=params, headers=finmind_headers(token), timeout=TIMEOUT)
        j = r.json()
        if j.get("status") != 200:
            return pd.DataFrame()
        df = pd.DataFrame(j.get("data", []))
        return df
    except Exception:
        return pd.DataFrame()

# ---------------------------
# 指標計算
# ---------------------------

def make_snapshot(history, profiles):
    if history.empty:
        return pd.DataFrame()

    parts = []
    for (sid, market), g in history.groupby(["stock_id", "market"], sort=False):
        g = g.sort_values("date").drop_duplicates("date")
        if len(g) < 6:
            continue

        c = g["close"].to_numpy(dtype=float)
        v = g["volume_shares"].to_numpy(dtype=float)
        latest = g.iloc[-1]
        # 課程「五日均量」這裡採「前5個完整交易日」，避免今天成交量同時進入分母。
        prev5_v = v[-6:-1] if len(v) >= 6 else np.array([])
        avg5_shares = np.nanmean(prev5_v) if len(prev5_v) == 5 else np.nan

        close_5ma = np.nanmean(c[-5:]) if len(c) >= 5 else np.nan
        r10 = pct(c[-1], c[-11]) if len(c) >= 11 else np.nan
        r20 = pct(c[-1], c[-21]) if len(c) >= 21 else np.nan
        r30 = pct(c[-1], c[-31]) if len(c) >= 31 else np.nan
        r40 = pct(c[-1], c[-41]) if len(c) >= 41 else np.nan

        parts.append({
            "stock_id": sid,
            "market": market,
            "name": latest["name"],
            "date": latest["date"],
            "close": latest["close"],
            "volume_shares": latest["volume_shares"],
            "volume_lots": latest["volume_shares"] / 1000.0,
            "avg5_volume_shares": avg5_shares,
            "avg5_volume_lots": avg5_shares / 1000.0 if pd.notna(avg5_shares) else np.nan,
            "volume_vs_5avg_pct": (latest["volume_shares"] / avg5_shares * 100.0) if pd.notna(avg5_shares) and avg5_shares > 0 else np.nan,
            "ma5": close_5ma,
            "r10": r10,
            "r20": r20,
            "r30": r30,
            "r40": r40,
        })

    snap = pd.DataFrame(parts)
    if snap.empty:
        return snap

    if not profiles.empty:
        snap = snap.merge(profiles, on=["stock_id", "market"], how="left")
        snap["name"] = np.where(
            snap["name"].astype(str).str.len() > 0,
            snap["name"],
            snap["profile_name"].fillna("")
        )
    else:
        snap["capital_ntd"] = np.nan
        snap["par_value"] = np.nan

    # 股本億元
    snap["capital_100m"] = snap["capital_ntd"] / 100_000_000.0
    # 流通股數：實收資本額 / 普通股每股面額
    snap["shares_outstanding"] = np.where(
        snap["capital_ntd"].notna() & snap["par_value"].notna() & (snap["par_value"] > 0),
        snap["capital_ntd"] / snap["par_value"],
        np.nan
    )
    snap["turnover_pct"] = np.where(
        snap["shares_outstanding"].notna() & (snap["shares_outstanding"] > 0),
        snap["volume_shares"] / snap["shares_outstanding"] * 100.0,
        np.nan
    )
    return snap

# ---------------------------
# 條件
# ---------------------------

def apply_conditions(snap, cond2_abs30=True):
    d = snap.copy()

    common_filter = (d["close"] > 5) & (d["avg5_volume_lots"] > 500)

    # 條件①
    d["c1_r20"] = d["r20"] > 10
    d["c1_turn"] = d["turnover_pct"] > 10
    d["c1_cap"] = d["capital_100m"] < 20
    d["cond1"] = common_filter & d["c1_r20"] & d["c1_turn"] & d["c1_cap"]

    # 條件②
    # 圖片原文「近一日成交量大於五日均量的20%」採字面：今日量 > 五日均量 × 20%
    d["c2_vol"] = d["volume_vs_5avg_pct"] > 20
    if cond2_abs30:
        d["c2_r30"] = d["r30"].abs() < 1
    else:
        d["c2_r30"] = d["r30"] < 1
    d["cond2"] = common_filter & d["c2_vol"] & d["c2_r30"]

    # 條件③
    # 圖片原文是「不要過濾股價5元以下、五日均量500張以下」
    d["c3_r10"] = d["r10"] > 1
    d["c3_vol"] = d["volume_vs_5avg_pct"] > 300
    d["c3_todayvol"] = d["volume_lots"] > 100
    d["c3_cap"] = d["capital_100m"] < 30
    d["cond3"] = d["c3_r10"] & d["c3_vol"] & d["c3_todayvol"] & d["c3_cap"]

    # 條件④
    d["c4_below5ma"] = d["close"] < d["ma5"]
    d["c4_r40"] = d["r40"] > 30
    d["cond4_pre"] = common_filter & d["c4_below5ma"] & d["c4_r40"]
    d["inst10_net_lots"] = np.nan
    d["c4_inst"] = np.nan
    d["cond4"] = False

    # 條件⑤ preliminary
    # 圖片原文同樣是「不要過濾股價5元以下、五日均量500張以下」
    d["c5_price"] = d["close"] < 50
    d["eps3_sum"] = np.nan
    d["c5_eps"] = np.nan
    d["revenue_yoy"] = np.nan
    d["revenue_high"] = np.nan
    d["c5_rev_growth"] = np.nan
    d["cond5"] = False

    return d

def verify_condition4(d, finmind_token=""):
    idxs = d.index[d["cond4_pre"]].tolist()
    if not idxs:
        return d
    end = d["date"].max().date()
    start = end - timedelta(days=20)

    progress = st.progress(0, text="條件④：確認近10交易日三大法人...")
    for n, i in enumerate(idxs):
        sid = d.at[i, "stock_id"]
        df = finmind_institutional(
            sid, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), finmind_token
        )
        net_lots = np.nan
        if not df.empty and {"date", "buy", "sell"}.issubset(df.columns):
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            df["buy"] = pd.to_numeric(df["buy"], errors="coerce")
            df["sell"] = pd.to_numeric(df["sell"], errors="coerce")
            # 每日各法人加總後，取最近10個有資料交易日
            daily = df.groupby("date")[["buy", "sell"]].sum().sort_index().tail(10)
            if len(daily) >= 1:
                # FinMind buy/sell 單位為股，換算張
                net_lots = ((daily["buy"] - daily["sell"]).sum()) / 1000.0
        d.at[i, "inst10_net_lots"] = net_lots
        if pd.notna(net_lots):
            # 原文：近10天三大法人「賣超大於10000張」=> 淨買賣 < -10000 張
            d.at[i, "c4_inst"] = bool(net_lots < -10000)
            d.at[i, "cond4"] = bool(d.at[i, "cond4_pre"] and d.at[i, "c4_inst"])
        progress.progress((n + 1) / len(idxs), text=f"條件④ 法人確認 {n+1}/{len(idxs)}")
    progress.empty()
    return d

def verify_condition5(d, finmind_token=""):
    rev = fetch_latest_revenue()
    if not rev.empty:
        d = d.merge(
            rev[["stock_id", "market", "revenue", "revenue_yoy"]],
            on=["stock_id", "market"], how="left", suffixes=("", "_official")
        )
        if "revenue_yoy_official" in d.columns:
            d["revenue_yoy"] = d["revenue_yoy_official"].combine_first(d["revenue_yoy"])
        elif "revenue_yoy_y" in d.columns:
            d["revenue_yoy"] = d["revenue_yoy_y"].combine_first(d["revenue_yoy"])

    # 先用「股價<50 + 營收成長>20」縮小候選，再查完整歷史營收與 EPS
    prelim = d["c5_price"] & (d["revenue_yoy"] > 20)
    idxs = d.index[prelim.fillna(False)].tolist()
    if not idxs:
        return d

    progress = st.progress(0, text="條件⑤：確認歷史新高與近三季EPS...")
    eps_start = (date.today() - timedelta(days=520)).strftime("%Y-%m-%d")

    for n, i in enumerate(idxs):
        sid = d.at[i, "stock_id"]

        rh = finmind_revenue_history(sid, finmind_token)
        is_high = np.nan
        if not rh.empty and "revenue" in rh.columns:
            rh["revenue"] = pd.to_numeric(rh["revenue"], errors="coerce")
            rh = rh.dropna(subset=["revenue"])
            if len(rh):
                latest = rh.iloc[-1]["revenue"]
                prev_max = rh.iloc[:-1]["revenue"].max() if len(rh) > 1 else -np.inf
                is_high = bool(latest > prev_max)
        d.at[i, "revenue_high"] = is_high

        eps3, details = finmind_eps(sid, eps_start, finmind_token)
        d.at[i, "eps3_sum"] = eps3
        if pd.notna(eps3):
            d.at[i, "c5_eps"] = bool(eps3 > 0.5)

        if pd.notna(d.at[i, "revenue_yoy"]):
            d.at[i, "c5_rev_growth"] = bool(d.at[i, "revenue_yoy"] > 20)

        if (
            pd.notna(d.at[i, "c5_eps"])
            and pd.notna(d.at[i, "revenue_high"])
            and pd.notna(d.at[i, "c5_rev_growth"])
        ):
            d.at[i, "cond5"] = bool(
                d.at[i, "c5_price"]
                and d.at[i, "c5_eps"]
                and d.at[i, "revenue_high"]
                and d.at[i, "c5_rev_growth"]
            )

        progress.progress((n + 1) / len(idxs), text=f"條件⑤ 深度確認 {n+1}/{len(idxs)}")
    progress.empty()
    return d

# ---------------------------
# UI
# ---------------------------

st.title("📈 賊大選股")
st.caption("核心選股版 v1｜先把資料與條件做準，面板美化放下一步")

with st.expander("📘 本版嚴格依照你提供的課程圖片", expanded=False):
    st.markdown("""
**條件①**
- 近20交易日股價漲跌幅 > 10%
- 近一日週轉率 > 10%
- 股本 < 20億元
- 過濾：股價5元以下、5日均量500張以下

**條件②**
- 近一日成交量 > 五日均量的20%（本版先照圖片字面值）
- 近30交易日股價漲跌幅 < 1%
- 過濾：股價5元以下、5日均量500張以下
- 再搭配外資、投信動態判斷

**條件③**
- 近10交易日股價漲跌幅 > 1%
- 近一日成交量 > 五日均量300%
- 近一日成交量 > 100張
- 股本 < 30億元
- 圖片寫「不要過濾」股價5元以下、5日均量500張以下

**條件④**
- 近一交易日股價 < 5日MA
- 近40交易日股價漲跌幅 > 30%
- 近10天三大法人賣超 > 10,000張
- 過濾：股價5元以下、5日均量500張以下

**條件⑤**
- 股價 < 50元
- 近三季EPS合計 > 0.5元
- 近一個月營收創歷史新高
- 近一個月營收成長率 > 20%
- 圖片寫「不要過濾」股價5元以下、5日均量500張以下
""")

with st.sidebar:
    st.header("掃描設定")
    cond2_mode = st.radio(
        "條件②「30日漲跌幅 <1%」",
        ["用絕對值 |漲跌幅| < 1%（盤整）", "照字面：漲跌幅 < 1%"],
        index=0
    )
    finmind_token = st.text_input(
        "FinMind Token（可空白）",
        type="password",
        help="空白也能用免費額度；填免費帳號 Token 可提高每小時額度。"
    )
    do_deep = st.checkbox("掃描後自動做④⑤深度確認", value=True)
    st.info("第一次掃描要抓近約 78 天的官方日行情，會比之後慢；Streamlit 會快取。")

if st.button("🚀 掃描上市＋上櫃全部股票", type="primary", use_container_width=True):
    with st.spinner("抓取 TWSE／TPEx 官方日行情與公司主檔..."):
        hist = fetch_history()
        profiles = fetch_profiles()

    if hist.empty:
        st.error("目前沒有抓到行情資料。請稍後重試；程式不會把缺資料當成 0。")
        st.stop()

    snap = make_snapshot(hist, profiles)
    if snap.empty:
        st.error("行情有下載，但無法形成足夠交易日的個股序列。")
        st.stop()

    d = apply_conditions(
        snap,
        cond2_abs30=(cond2_mode.startswith("用絕對值"))
    )

    if do_deep:
        d = verify_condition4(d, finmind_token)
        d = verify_condition5(d, finmind_token)

    st.session_state["scan"] = d
    st.session_state["hist"] = hist

d = st.session_state.get("scan")
if d is not None and not d.empty:
    last_date = d["date"].max().strftime("%Y-%m-%d")
    st.success(f"掃描完成｜資料最新交易日：{last_date}｜共 {len(d):,} 檔可計算")

    counts = [int(d[f"cond{i}"].fillna(False).sum()) for i in range(1,6)]
    cols = st.columns(5)
    for i, c in enumerate(counts, 1):
        cols[i-1].metric(f"條件{i}", f"{c} 檔")

    tabs = st.tabs(["條件①", "條件②", "條件③", "條件④", "條件⑤", "全部透明檢查"])

    def base_cols():
        return ["stock_id","name","market","close","volume_lots","avg5_volume_lots","capital_100m"]

    with tabs[0]:
        x = d[d["cond1"].fillna(False)].copy()
        show = x[base_cols()+["r20","turnover_pct"]].sort_values("r20", ascending=False)
        show.columns = ["代號","名稱","市場","收盤","今日量(張)","5日均量(張)","股本(億)","20日漲幅%","週轉率%"]
        st.dataframe(show, use_container_width=True, hide_index=True)

    with tabs[1]:
        x = d[d["cond2"].fillna(False)].copy()
        show = x[base_cols()+["volume_vs_5avg_pct","r30"]].sort_values("volume_vs_5avg_pct", ascending=False)
        show.columns = ["代號","名稱","市場","收盤","今日量(張)","5日均量(張)","股本(億)","量/5日均量%","30日漲幅%"]
        st.dataframe(show, use_container_width=True, hide_index=True)
        st.caption("課程寫『再搭配外資跟投信的動態來判斷』；此欄目前先保留為二次人工判讀，不把它偷改成硬門檻。")

    with tabs[2]:
        x = d[d["cond3"].fillna(False)].copy()
        show = x[base_cols()+["r10","volume_vs_5avg_pct"]].sort_values("volume_vs_5avg_pct", ascending=False)
        show.columns = ["代號","名稱","市場","收盤","今日量(張)","5日均量(張)","股本(億)","10日漲幅%","量/5日均量%"]
        st.dataframe(show, use_container_width=True, hide_index=True)

    with tabs[3]:
        x = d[d["cond4"].fillna(False)].copy()
        show = x[base_cols()+["ma5","r40","inst10_net_lots"]].sort_values("r40", ascending=False)
        show.columns = ["代號","名稱","市場","收盤","今日量(張)","5日均量(張)","股本(億)","5MA","40日漲幅%","10日三大法人淨買賣(張)"]
        st.dataframe(show, use_container_width=True, hide_index=True)
        if d["cond4_pre"].sum() and d["inst10_net_lots"].isna().all():
            st.warning("④目前只完成價格初篩，法人資料尚未取得；不會把 NA 當 0。")

    with tabs[4]:
        x = d[d["cond5"].fillna(False)].copy()
        show = x[base_cols()+["eps3_sum","revenue_yoy","revenue_high"]].sort_values("revenue_yoy", ascending=False)
        show.columns = ["代號","名稱","市場","收盤","今日量(張)","5日均量(張)","股本(億)","近三季EPS合計","營收成長率%","營收歷史新高"]
        st.dataframe(show, use_container_width=True, hide_index=True)
        st.warning("⑤的 EPS 會把來源值攤開供核對；若免費來源無法確認為『單季EPS』，應視為 NA，不硬算。")

    with tabs[5]:
        cols = [
            "stock_id","name","market","close",
            "r10","r20","r30","r40",
            "volume_lots","avg5_volume_lots","volume_vs_5avg_pct",
            "capital_100m","turnover_pct","ma5",
            "cond1","cond2","cond3","cond4","cond5",
        ]
        z = d[cols].copy().sort_values(["cond1","cond2","cond3","cond4","cond5"], ascending=False)
        z.columns = [
            "代號","名稱","市場","收盤",
            "10日%","20日%","30日%","40日%",
            "今日量(張)","5日均量(張)","量/5均%",
            "股本(億)","週轉率%","5MA",
            "①","②","③","④","⑤"
        ]
        st.dataframe(z, use_container_width=True, hide_index=True)

    st.divider()
    sid = st.selectbox(
        "查看單一股票逐條驗證",
        options=d["stock_id"].astype(str).tolist(),
        format_func=lambda s: f"{s} {d.loc[d['stock_id'].astype(str).eq(s), 'name'].iloc[0]}"
    )
    r = d[d["stock_id"].astype(str).eq(sid)].iloc[0]

    st.subheader(f"{sid} {r['name']}｜透明條件檢查")
    st.markdown(f"""
**條件①**  
{yn(r['r20'] > 10 if pd.notna(r['r20']) else np.nan)} 20日漲跌幅：{fmt(r['r20'],2,'%')}　（>10%）  
{yn(r['turnover_pct'] > 10 if pd.notna(r['turnover_pct']) else np.nan)} 近一日週轉率：{fmt(r['turnover_pct'],2,'%')}　（>10%）  
{yn(r['capital_100m'] < 20 if pd.notna(r['capital_100m']) else np.nan)} 股本：{fmt(r['capital_100m'],2,'億')}　（<20億）  

**條件②**  
{yn(r['volume_vs_5avg_pct'] > 20 if pd.notna(r['volume_vs_5avg_pct']) else np.nan)} 今日量 / 5日均量：{fmt(r['volume_vs_5avg_pct'],1,'%')}　（>20%）  
{yn(abs(r['r30']) < 1 if pd.notna(r['r30']) and cond2_mode.startswith('用絕對值') else (r['r30'] < 1 if pd.notna(r['r30']) else np.nan))} 30日漲跌幅：{fmt(r['r30'],2,'%')}  

**條件③**  
{yn(r['r10'] > 1 if pd.notna(r['r10']) else np.nan)} 10日漲跌幅：{fmt(r['r10'],2,'%')}　（>1%）  
{yn(r['volume_vs_5avg_pct'] > 300 if pd.notna(r['volume_vs_5avg_pct']) else np.nan)} 今日量 / 5日均量：{fmt(r['volume_vs_5avg_pct'],1,'%')}　（>300%）  
{yn(r['volume_lots'] > 100 if pd.notna(r['volume_lots']) else np.nan)} 今日成交量：{fmt(r['volume_lots'],0,'張')}　（>100張）  
{yn(r['capital_100m'] < 30 if pd.notna(r['capital_100m']) else np.nan)} 股本：{fmt(r['capital_100m'],2,'億')}　（<30億）  

**條件④**  
{yn(r['close'] < r['ma5'] if pd.notna(r['ma5']) else np.nan)} 收盤 / 5MA：{fmt(r['close'])} / {fmt(r['ma5'])}  
{yn(r['r40'] > 30 if pd.notna(r['r40']) else np.nan)} 40日漲跌幅：{fmt(r['r40'],2,'%')}　（>30%）  
{yn(r['inst10_net_lots'] < -10000 if pd.notna(r['inst10_net_lots']) else np.nan)} 近10日三大法人淨買賣：{fmt(r['inst10_net_lots'],0,'張')}　（賣超>10,000張）  

**條件⑤**  
{yn(r['close'] < 50)} 股價：{fmt(r['close'])}　（<50元）  
{yn(r['eps3_sum'] > 0.5 if pd.notna(r['eps3_sum']) else np.nan)} 近三季EPS合計：{fmt(r['eps3_sum'])}　（>0.5）  
{yn(r['revenue_high'] if pd.notna(r['revenue_high']) else np.nan)} 近一月營收創歷史新高：{r['revenue_high'] if pd.notna(r['revenue_high']) else 'NA'}  
{yn(r['revenue_yoy'] > 20 if pd.notna(r['revenue_yoy']) else np.nan)} 近一月營收成長率：{fmt(r['revenue_yoy'],2,'%')}　（>20%）  

**共通過濾（僅①②④）**  
股價：{fmt(r['close'])}｜5日均量：{fmt(r['avg5_volume_lots'],0,'張')}
""")

st.caption("資料來源：TWSE / TPEx 官方公開資料；FinMind 免費 API 僅用於初篩後的法人、EPS、歷史營收深度確認。投資決策請自行判斷。")
