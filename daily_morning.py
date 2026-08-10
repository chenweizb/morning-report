import os
import sys
import json
import requests
import akshare as ak
import pandas as pd
from datetime import datetime

# 密钥从GitHub Secrets读取，不要硬编码！
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "")
HUNYUAN_API_KEY = os.environ.get("HUNYUAN_API_KEY", "")

def safe_block(name, func, *args, fallback="暂无（接口未返回，不推测）", **kwargs):
    """单块容错：接口报错/空数据直接返回fallback，不中断整体流程"""
    try:
        r = func(*args, **kwargs)
        if r is None or (isinstance(r, pd.DataFrame) and r.empty):
            return fallback
        return r
    except Exception as e:
        print(f"⚠️ [{name}] 接口异常已隔离：{str(e)[:60]}")
        return fallback

def block_global():
    """全球资产+杠杆+流动性（全最新接口）"""
    out = ["### 🌍 全球资产 / 杠杆 / 流动性（截至北京时间07:30）"]
    
    # 美股三大指数
    us = safe_block("美股", ak.stock_us_spot_em)
    if isinstance(us, pd.DataFrame):
        for n in ["道琼斯", "纳斯达克", "标普500"]:
            row = us[us["名称"] == n]
            if not row.empty:
                r = row.iloc[0]
                out.append(f"- **{n}**：{r['最新价']} ｜ {r['涨跌幅']}%")
    else:
        out.append("- 美股：暂无")
    
    # 外盘期货（原油/黄金/A50/铜）
    fx = safe_block("外盘期货", ak.futures_global_spot_em)
    if isinstance(fx, pd.DataFrame):
        cols = fx.columns.tolist()
        nc = [c for c in cols if "名称" in c or "name" in c.lower()][0]
        pc = [c for c in cols if "最新价" in c or "price" in c.lower()][0]
        pct = [c for c in cols if "涨跌幅" in c or "pct" in c.lower()][0]
        for k in ["WTI原油", "布伦特原油", "COMEX黄金", "富时中国A50", "LME铜"]:
            row = fx[fx[nc].str.contains(k, na=False)]
            if not row.empty:
                r = row.iloc[0]
                out.append(f"- **{k}**：{r[pc]} ｜ {r[pct]}%")
    else:
        out.append("- 外盘期货：暂无")
    
    # 离岸人民币
    cnh = safe_block("离岸人民币", ak.currency_boc_safe)
    if isinstance(cnh, pd.DataFrame):
        usd = [c for c in cnh.columns if "美元" in c]
        if usd:
            out.append(f"- **美元兑CNH**：{cnh.iloc[-1][usd[0]]}")
    else:
        out.append("- 汇率：暂无")
    
    # 两融余额
    mg = safe_block("两融", ak.stock_margin_account_info)
    if isinstance(mg, pd.DataFrame) and not mg.empty:
        l = mg.iloc[-1]
        out.append(f"- **两融余额**：融资 {l.get('融资余额','N/A')}亿 ｜ 融券 {l.get('融券余额','N/A')}亿 ｜ 维持担保比 {l.get('平均维持担保比例','N/A')}")
    else:
        out.append("- 两融余额：暂无")
    
    # 美债10Y-2Y利差
    ust = safe_block("美债", ak.bond_zh_us_rate)
    if isinstance(ust, pd.DataFrame) and not ust.empty:
        ten = [c for c in ust.columns if "10年" in c or "10Y" in c]
        two = [c for c in ust.columns if "2年" in c or "2Y" in c]
        if ten and two:
            spread = float(ust.iloc[-1][ten[0]]) - float(ust.iloc[-1][two[0]])
            out.append(f"- **美债10Y-2Y利差**：{round(spread,2)}bp（倒挂=衰退预期）")
    else:
        out.append("- 美债利差：暂无")
    
    # VIX恐慌指数（最新官方接口）
    vix = safe_block("VIX", ak.index_option_300etf_qvix)
    if isinstance(vix, pd.DataFrame) and not vix.empty:
        out.append(f"- **VIX恐慌指数**：{vix.iloc[-1].get('qvix', 'N/A')}")
    else:
        out.append("- VIX：暂无")
    
    return "\n".join(out)

def block_macro():
    """宏观与政策（全最新接口）"""
    out = ["### 🇨🇳 宏观与政策"]
    
    # CPI同比
    cpi = safe_block("CPI", ak.macro_china_cpi_yearly)
    if isinstance(cpi, pd.DataFrame) and not cpi.empty:
        latest = cpi.iloc[-1]
        val = latest.get("cpi") or latest.get("value") or "N/A"
        out.append(f"- CPI同比（最新）：{val}%")
    else:
        out.append("- CPI：暂无")
    
    # 制造业PMI
    pmi = safe_block("PMI", ak.macro_china_pmi_yearly)
    if isinstance(pmi, pd.DataFrame) and not pmi.empty:
        mc = [c for c in pmi.columns if "制造业" in c or "pmi" in c.lower()]
        if mc:
            out.append(f"- 制造业PMI（最新）：{pmi.iloc[-1][mc[0]]}%")
    else:
        out.append("- PMI：暂无")
    
    # 央行逆回购
    repo = safe_block("逆回购", ak.macro_china_gksccz)
    if isinstance(repo, pd.DataFrame) and not repo.empty:
        l = repo.iloc[-1]
        out.append(f"- 央行逆回购：{l.get('交易量','N/A')}亿 ｜ 利率 {l.get('中标利率','N/A')}%")
    else:
        out.append("- 逆回购：暂无")
    
    return "\n".join(out)

def block_news():
    """财联社快讯（最新官方接口，无旧版兼容）"""
    out = ["### 📰 隔夜时政 / 财经快讯（财联社）"]
    df = safe_block("财联社", ak.stock_info_global_cls)
    if isinstance(df, pd.DataFrame) and "content" in df.columns:
        kw = ["美联储","央行","国务院","发改委","证监会","地缘","关税","制裁","非农","CPI","降息","降准","逆回购","汇率","A股","港股","美股","两融"]
        f = df[df["content"].str.contains("|".join(kw), na=False)]
        f = f[f["content"].notna()]
        if not f.empty:
            for c in f.head(10)["content"]:
                out.append(f"- {c[:90]}")
        else:
            out.append("- 隔夜无匹配重大事件（不编造）")
    else:
        out.append("- 财联社数据获取中，请稍后查看")
    return "\n".join(out)

def llm_view(snapshot: str):
    """混元永久免费版反向研判（无消耗）"""
    if not HUNYUAN_API_KEY:
        return "### 🎯 研判（未配置HUNYUAN_API_KEY，静态降级）\n- 依据上方真实数据自行研判；集合竞价确认方向，严控仓位。"
    sys_p = (
        "你是买方首席宏观策略师，遵循第二层思维。硬性规则：\n"
        "1) 仅基于提供的真实快照分析，禁止编造未提供的数据、禁止预测确定涨跌；\n"
        "2) 每条事件必须写『传导链』：事件 → 受影响主体 → 具体经济行为 → 可观测后验信号；\n"
        "3) 指出市场共识已定价部分 vs 未被定价隐性风险（全球杠杆脆弱点、流动性拐点、跨市场错杀、政策时滞）；\n"
        "4) 提出3条尖锐反向质疑；\n"
        "5) 末句给市场状态判定（钝化/脆弱/假突破/流动性陷阱等）。Markdown，≤300字，冷峻。"
    )
    try:
        r = requests.post(
            "https://api.hunyuan.cloud.tencent.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {HUNYUAN_API_KEY}", "Content-Type": "application/json"},
            json={"model": "hunyuan-lite",
                  "messages": [{"role": "system", "content": sys_p},
                               {"role": "user", "content": f"快照：\n{snapshot}"}],
                  "temperature": 0.8, "max_tokens": 600},
            timeout=60
        )
        return "### 🎯 智能研判（混元·hunyuan-lite 免费版·事件传导+反向质疑）\n" + r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"### 🎯 研判生成失败（降级）\n- 异常：{str(e)[:40]}"

def push(content):
    """推送至微信（PushPlus）"""
    if not PUSHPLUS_TOKEN:
        print("❌ 未配置PUSHPLUS_TOKEN")
        return
    try:
        r = requests.post("https://www.pushplus.plus/send", json={
            "token": PUSHPLUS_TOKEN,
            "title": f"07:30 全球晨报 · {datetime.now().strftime('%Y-%m-%d')}",
            "content": content, "template": "markdown"
        }, timeout=30)
        print(f"✅ 推送：{r.json().get('msg')}")
    except Exception as e:
        print(f"❌ 推送异常（已落盘）：{str(e)[:50]}")

def main():
    print("=" * 50)
    print(f"启动：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | akshare {ak.__version__}")
    print("=" * 50)
    
    b1, b2, b3 = block_global(), block_news(), block_macro()
    snapshot = json.dumps({"全球资产/杠杆": b1, "新闻": b2, "宏观": b3}, ensure_ascii=False)[:3000]
    view = llm_view(snapshot)
    
    content = f"# 📈 07:30 全球晨报 · {datetime.now().strftime('%Y年%m月%d日')}\n\n" + "\n\n".join([b1, b2, b3, view])
    content += "\n\n---\n*源：AkShare/财联社/央行 · 允许跨市场时差 · 缺失不补 · 不构成投资建议*"
    
    push(content)
    try:
        with open("raw_news.txt", "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        pass
    print("✅ 执行完毕")
    sys.exit(0)  # 强制正常退出，GitHub Actions不会标红

if __name__ == "__main__":
    main()