import os
import json
import requests
import akshare as ak
import pandas as pd
from datetime import datetime

# 读取环境变量（严格匹配GitHub Secrets名称）
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "")
HUNYUAN_API_KEY = os.environ.get("HUNYUAN_API_KEY", "")

def safe(func, *a, default="暂无（接口未返回，不推测）", **kw):
    """安全调用接口，无数据/报错时返回默认值，绝不编造"""
    try:
        r = func(*a, **kw)
        if r is None or (isinstance(r, pd.DataFrame) and r.empty):
            return default
        return r
    except Exception as e:
        return default

# 1. 全球资产+杠杆+流动性快照（07:30可获取的官方披露数据）
def block_global():
    out = ["### 🌍 全球资产 / 杠杆 / 流动性（截至北京时间07:30）"]
    
    # 美股三大指数（前一交易日收盘，官方披露）
    us = safe(ak.stock_us_spot_em)
    if isinstance(us, pd.DataFrame):
        for n in ["道琼斯", "纳斯达克", "标普500"]:
            row = us[us["名称"] == n]
            if not row.empty:
                r = row.iloc[0]
                out.append(f"- **{n}**：{r['最新价']} ｜ {r['涨跌幅']}%")
    else:
        out.append("- 美股：暂无")
    
    # 外盘期货（原油/黄金/A50/铜，07:30最新报价）
    fx = safe(ak.futures_global_em)
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
    
    # 离岸人民币（央行官方汇率）
    cnh = safe(ak.currency_boc_safe)
    if isinstance(cnh, pd.DataFrame):
        usd = [c for c in cnh.columns if "美元" in c]
        if usd:
            out.append(f"- **美元兑CNH**：{cnh.iloc[-1][usd[0]]}")
    else:
        out.append("- 汇率：暂无")
    
    # 两融余额（内资杠杆，前一交易日数据）
    mg = safe(ak.stock_margin_account_info)
    if isinstance(mg, pd.DataFrame) and not mg.empty:
        l = mg.iloc[-1]
        out.append(f"- **两融余额**：融资 {l.get('融资余额','N/A')}亿 ｜ 融券 {l.get('融券余额','N/A')}亿 ｜ 维持担保比 {l.get('平均维持担保比例','N/A')}")
    else:
        out.append("- 两融余额：暂无")
    
    # 美债10Y-2Y利差（衰退预期指标）
    ust = safe(ak.bond_zh_us_rate)
    if isinstance(ust, pd.DataFrame) and not ust.empty:
        ten = [c for c in ust.columns if "10年" in c or "10Y" in c]
        two = [c for c in ust.columns if "2年" in c or "2Y" in c]
        if ten and two:
            spread = float(ust.iloc[-1][ten[0]]) - float(ust.iloc[-1][two[0]])
            out.append(f"- **美债10Y-2Y利差**：{round(spread,2)}bp（倒挂=衰退预期）")
    else:
        out.append("- 美债利差：暂无")
    
    # VIX恐慌指数（全球避险情绪）
    vix = safe(ak.index_vix)
    if isinstance(vix, pd.DataFrame) and not vix.empty:
        out.append(f"- **VIX恐慌指数**：{vix.iloc[-1]['收盘价']}")
    else:
        out.append("- VIX：暂无")
    
    # 内盘期货主连（原油/沪金/铁矿/螺纹）
    dm = safe(ak.futures_zh_spot)
    if isinstance(dm, pd.DataFrame):
        out.append("- 内盘期货主连：已获取，详见 raw_news.txt 落盘")
    return "\n".join(out)

# 2. 宏观与政策（官方披露，无小道消息）
def block_macro():
    out = ["### 🇨🇳 宏观与政策"]
    
    # CPI同比
    cpi = safe(ak.macro_china_cpi_yearly)
    if isinstance(cpi, pd.DataFrame) and not cpi.empty:
        out.append(f"- CPI同比（最新）：{cpi.iloc[-1]['value']}% ｜ 前值 {cpi.iloc[-2]['value'] if len(cpi)>1 else 'N/A'}%")
    else:
        out.append("- CPI：暂无")
    
    # 制造业PMI
    pmi = safe(ak.macro_china_pmi_yearly)
    if isinstance(pmi, pd.DataFrame) and not pmi.empty:
        mc = [c for c in pmi.columns if "制造业" in c]
        if mc:
            out.append(f"- 制造业PMI（最新）：{pmi.iloc[-1][mc[0]]}% ｜ 前值 {pmi.iloc[-2][mc[0]] if len(pmi)>1 else 'N/A'}%")
    else:
        out.append("- PMI：暂无")
    
    # 央行逆回购
    repo = safe(ak.macro_china_gksccz)
    if isinstance(repo, pd.DataFrame) and not repo.empty:
        l = repo.iloc[-1]
        out.append(f"- 央行逆回购：{l.get('交易量','N/A')}亿 ｜ 利率 {l.get('中标利率','N/A')}%")
    else:
        out.append("- 逆回购：暂无")
    
    # 宏观杠杆率
    lev = safe(ak.macro_cnbs)
    if isinstance(lev, pd.DataFrame) and not lev.empty:
        col = [c for c in lev.columns if "杠杆率" in c or "非金融" in c]
        if col:
            out.append(f"- 宏观杠杆率（最新）：{lev.iloc[-1][col[0]]}")
    return "\n".join(out)

# 3. 隔夜时政/财经快讯（财联社官方电报，过滤重大事件）
def block_news():
    out = ["### 📰 隔夜时政 / 财经快讯（财联社）"]
    df = safe(ak.cls_telegraph)
    if isinstance(df, pd.DataFrame) and "content" in df.columns:
        # 只保留重大事件关键词，过滤杂音
        kw = ["美联储","央行","国务院","发改委","证监会","地缘","关税","制裁","非农","CPI","降息","降准","逆回购","汇率","A股","港股","美股","两融"]
        f = df[df["content"].str.contains("|".join(kw), na=False)]
        f = f[f["content"].notna()]
        if not f.empty:
            for c in f.head(10)["content"]:
                out.append(f"- {c[:90]}")
        else:
            out.append("- 隔夜无匹配重大事件（不编造）")
    else:
        out.append("- 新闻源：暂无")
    return "\n".join(out)

# 4. 永久免费混元lite反向研判（0成本，不消耗体验包）
def llm_view(snapshot: str):
    if not HUNYUAN_API_KEY:
        return "### 🎯 研判（未配置HUNYUAN_API_KEY，静态降级）\n- 依据上方真实数据自行研判；集合竞价确认方向，严控仓位。"
    
    sys_prompt = (
        "你是买方首席宏观策略师，遵循第二层思维。硬性规则：\n"
        "1) 仅基于提供的真实快照分析，禁止编造未提供的数据、禁止预测确定涨跌；\n"
        "2) 每条事件必须写『传导链』：事件 → 受影响主体（居民/企业/银行/外资/财政）→ 具体经济行为（消费/资本开支/信贷/跨境流动/避险）→ 可观测后验信号；\n"
        "3) 指出市场共识已定价部分 vs 未被定价隐性风险（全球杠杆脆弱点、流动性拐点、跨市场错杀、政策时滞）；\n"
        "4) 提出3条尖锐反向质疑；\n"
        "5) 末句给市场状态判定（钝化/脆弱/假突破/流动性陷阱等）。Markdown，≤300字，冷峻。"
    )
    
    try:
        resp = requests.post(
            "https://api.hunyuan.cloud.tencent.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {HUNYUAN_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "hunyuan-lite",  # 永久免费，不扣费
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": f"快照：\n{snapshot}"}
                ],
                "temperature": 0.8,
                "max_tokens": 600
            },
            timeout=60
        )
        return "### 🎯 智能研判（混元·hunyuan-lite 免费版·事件传导+反向质疑）\n" + resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"### 🎯 研判生成失败（降级）\n- 异常：{str(e)[:40]}"

def push(content):
    """推送至微信（PushPlus）"""
    if not PUSHPLUS_TOKEN:
        print("❌ 未配置PUSHPLUS_TOKEN")
        return
    try:
        resp = requests.post(
            "https://www.pushplus.plus/send",
            json={
                "token": PUSHPLUS_TOKEN,
                "title": f"07:30 全球晨报 · {datetime.now().strftime('%Y-%m-%d')}",
                "content": content,
                "template": "markdown"
            },
            timeout=30
        )
        res = resp.json()
        if res.get("code") == 200:
            print("✅ 微信推送成功！请查看公众号「pushplus 推送加」")
        else:
            print(f"❌ 推送失败：{res.get('msg')}")
    except Exception as e:
        print(f"❌ 推送异常：{str(e)[:50]}")

def main():
    print("=" * 50)
    print(f"启动时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"AkShare版本：{ak.__version__}")
    print("=" * 50)
    
    # 组装各模块内容
    b1, b2, b3 = block_global(), block_news(), block_macro()
    # 快照截断到3000字符，适配免费模型上下文限制
    snapshot = json.dumps({"全球资产/杠杆": b1, "新闻": b2, "宏观": b3}, ensure_ascii=False)[:3000]
    view = llm_view(snapshot)
    
    # 组装最终推送内容
    content = f"# 📈 07:30 全球晨报 · {datetime.now().strftime('%Y年%m月%d日')}\n\n" + "\n\n".join([b1, b2, b3, view])
    content += "\n\n---\n*源：AkShare/财联社/央行 · 允许跨市场时差 · 缺失不补 · 不构成投资建议*"
    
    # 推送+落盘
    push(content)
    with open("raw_news.txt", "w", encoding="utf-8") as f:
        f.write(content)
    print("✅ 原始数据已落盘")
    print("=" * 50)

if __name__ == "__main__":
    main()
