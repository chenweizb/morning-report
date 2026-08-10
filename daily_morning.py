import os
import sys
import json
import requests
import akshare as ak
import pandas as pd
from datetime import datetime
import pytz

PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "")
HUNYUAN_API_KEY = os.environ.get("HUNYUAN_API_KEY", "")
# 免费AI开关：True开启混元研判；False关闭AI，节省免费额度
ENABLE_LLM = True
# 强制北京时间
TZ_CN = pytz.timezone("Asia/Shanghai")


def safe_block(name, func, *args, fallback="暂无（接口未返回，不推测）", **kwargs):
    try:
        r = func(*args, **kwargs)
        if r is None or (isinstance(r, pd.DataFrame) and r.empty):
            return fallback
        return r
    except Exception as e:
        print(f"⚠️ [{name}] 接口异常已隔离：{str(e)[:60]}")
        return fallback


def block_global():
    """【实时层+收盘层】全球资产 / A股T‑1市场快照（全部免费akshare接口）"""
    now_cn = datetime.now(TZ_CN)
    out = [f"### 🌍 全球资产 / A股T‑1快照（北京时间{now_cn:%H:%M}快照 · 全部免费公开数据源）"]

    # 美股三大指数（昨收盘）
    us = safe_block("美股", ak.stock_us_spot_em)
    if isinstance(us, pd.DataFrame):
        for n in ["道琼斯", "纳斯达克", "标普500"]:
            row = us[us["名称"] == n]
            if not row.empty:
                r = row.iloc[0]
                out.append(f"- **{n}**（昨收盘）：{r['最新价']} ｜ {r['涨跌幅']}%")
    else:
        out.append("- 美股：暂无")

    # 外盘期货
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
                out.append(f"- **{k}**（实时）：{r[pc]} ｜ {r[pct]}%")
    else:
        out.append("- 外盘期货：暂无")

    # 在岸人民币中间价
    cny = safe_block("人民币中间价", ak.currency_boc_safe)
    if isinstance(cny, pd.DataFrame):
        usd = [c for c in cny.columns if "美元" in c]
        if usd:
            out.append(f"- **美元兑CNY**（央行中间价）：{cny.iloc[-1][usd[0]]}")
    else:
        out.append("- 汇率中间价：暂无")

    # 两融余额 T‑1
    mg = safe_block("两融", ak.stock_margin_account_info)
    if isinstance(mg, pd.DataFrame) and not mg.empty:
        l = mg.iloc[-1]
        out.append(f"- **两融余额(T‑1)**：融资 {l.get('融资余额','N/A')}亿 ｜ 融券 {l.get('融券余额','N/A')}亿 ｜ 维持担保比 {l.get('平均维持担保比例','N/A')}")
    else:
        out.append("- 两融余额：暂无")

    # 美债利差，带转换保护
    ust = safe_block("美债", ak.bond_zh_us_rate)
    if isinstance(ust, pd.DataFrame) and not ust.empty:
        ten = [c for c in ust.columns if "10年" in c or "10Y" in c]
        two = [c for c in ust.columns if "2年" in c or "2Y" in c]
        if ten and two:
            try:
                v10 = float(ust.iloc[-1][ten[0]])
                v2 = float(ust.iloc[-1][two[0]])
                spread = v10 - v2
                tag = "【倒挂】" if spread < 0 else ""
                out.append(f"- **美债10Y‑2Y利差**（昨收盘）：{round(spread,2)}bp {tag}")
            except (ValueError, TypeError):
                out.append("- **美债10Y‑2Y利差**：数据缺失无法计算")
    else:
        out.append("- 美债利差：暂无")

    # 北向资金 T‑1
    hsgt = safe_block("北向资金", ak.stock_hsgt_hist_em)
    if isinstance(hsgt, pd.DataFrame) and not hsgt.empty:
        last = hsgt.iloc[-1]
        out.append(f"- **北向资金(T‑1)**：净流入 {last.get('北向合计','N/A')}亿")
    else:
        out.append("- 北向资金(T‑1)：暂无")

    # A股涨跌家数 T‑1：接口stock_a_spot_em已移除，禁用
    out.append("- **A股T‑1涨跌家数**：⚠️akshare该接口已移除，请网页手动查看。")

    # 1天期国债逆回购【修复完整缩进】
    try:
        repo_sh = safe_block("国债逆回购", ak.bond_repo_sh)
    except AttributeError as e:
        print(f"⚠️【国债逆回购模块异常】{e}，跳过该板块，不中断整体晨报任务")
        repo_sh = None

    if isinstance(repo_sh, pd.DataFrame) and not repo_sh.empty:
        row_1d = repo_sh[repo_sh["代码"] == "204001"]
        if not row_1d.empty:
            r = row_1d.iloc[0]
            out.append(f"- **1天期国债逆回购**：{r.get('最新价','N/A')}%（短期资金松紧）")
    else:
        out.append("- 国债逆回购：暂无")

    out.append("- **VIX恐慌指数**：暂无稳定免费接口，不冒充实时")
    return "\n".join(out)


def block_macro():
    out = ["### 🇨🇳 宏观与政策（最近披露期 · 免费公开数据源）"]
    cpi = safe_block("CPI", ak.macro_china_cpi_yearly)
    if isinstance(cpi, pd.DataFrame) and not cpi.empty:
        latest = cpi.iloc[-1]
        val = latest.get("cpi") or latest.get("value") or "N/A"
        out.append(f"- CPI同比（最新）：{val}%")
    else:
        out.append("- CPI：暂无")

    pmi = safe_block("PMI", ak.macro_china_pmi_yearly)
    if isinstance(pmi, pd.DataFrame) and not pmi.empty:
        mc = [c for c in pmi.columns if "制造业" in c or "pmi" in c.lower()]
        if mc:
            pmi_val = float(pmi.iloc[-1][mc[0]])
            tag = "【扩张＞50】" if pmi_val > 50 else "【收缩＜50】"
            out.append(f"- 制造业PMI（最新）：{pmi_val}% {tag}")
    else:
        out.append("- PMI：暂无")

    m2 = safe_block("M2", ak.macro_china_m2)
    if isinstance(m2, pd.DataFrame) and not m2.empty:
        latest = m2.iloc[-1]
        val = latest.get("m2") or latest.get("M2") or latest.get("value") or "N/A"
        out.append(f"- M2同比（最新）：{val}%")
    else:
        out.append("- M2：暂无")

    repo = safe_block("逆回购", ak.macro_china_open_market_operation)
    if isinstance(repo, pd.DataFrame) and not repo.empty:
        reverse = repo[repo["正/逆回购"].astype(str).str.contains("逆回购", na=False)]
        if not reverse.empty:
            l = reverse.iloc[-1]
            vol = l.get("交易量") or l.get("deal_amount") or "N/A"
            rate = l.get("中标利率") or l.get("rate") or "N/A"
            out.append(f"- 央行逆回购（最近一次）：{vol}亿 ｜ 利率 {rate}%")
        else:
            out.append("- 逆回购：近期无操作")
    else:
        out.append("- 逆回购：暂无（接口暂不可用）")
    return "\n".join(out)


def block_news():
    out = ["### 📰 隔夜时政 / 财经快讯（财联社 · 免费）"]
    # 重要：akshare新版本已经移除 stock_telegraph_cls 接口，不再自动抓取新闻，避免程序崩溃
    out.append("- ⚠️akshare接口`stock_telegraph_cls`已被官方移除，脚本不再自动抓取快讯。")
    out.append("- ✅盘前手动免费渠道：浏览器打开财联社网页，查看隔夜重大财经新闻。")
    return "\n".join(out)


def llm_view(snapshot: str):
    if not ENABLE_LLM or not HUNYUAN_API_KEY:
        return "### 🎯 研判（AI已关闭/无key，免费降级）\n- 依据上方真实数据自行研判；集合竞价确认方向，严控仓位。\n⚠️混元‑lite免费额度有限，可开关ENABLE_LLM节省额度。"
    sys_p = (
        "你是买方首席宏观策略师，遵循第二层思维。硬性规则：\n"
        "1) 仅基于提供的真实快照分析，禁止编造未提供的数据、禁止预测确定涨跌；\n"
        "2) 每条事件必须写『传导链』：事件 → 受影响主体 → 具体经济行为 → 可观测后验信号；\n"
        "3) 指出市场共识已定价部分 vs 未被定价隐性风险；\n"
        "4) 提出3条尖锐反向质疑；\n"
        "5) 末句给市场状态判定。Markdown，≤260字，冷峻。"
    )
    try:
        r = requests.post(
            "https://api.hunyuan.cloud.tencent.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {HUNYUAN_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "hunyuan-lite",
                "messages": [
                    {"role": "system", "content": sys_p},
                    {"role": "user", "content": f"快照：\n{snapshot[:2400]}"}
                ],
                "temperature": 0.8,
                "max_tokens": 500
            },
            timeout=55
        )
        resp_json = r.json()
        choices = resp_json.get("choices", [])
        if not choices:
            return "### 🎯 研判生成失败（降级）\n‑ 大模型返回空，免费额度可能耗尽。"
        content = choices[0]["message"].get("content", "")
        return "### 🎯 智能研判（混元‑lite免费版，仅供思考辅助，非决策依据）\n" + content
    except Exception as e:
        return f"### 🎯 研判生成失败（降级）\n‑ 异常：{str(e)[:40]}，免费额度或网络问题。"


def push(content):
    if not PUSHPLUS_TOKEN:
        print("❌ 未配置PUSHPLUS_TOKEN")
        return
    try:
        now_cn = datetime.now(TZ_CN)
        r = requests.post("https://www.pushplus.plus/send", json={
            "token": PUSHPLUS_TOKEN,
            "title": f"盘前晨报 · {now_cn:%Y‑%m‑%d}【免费数据源】",
            "content": content,
            "template": "markdown"
        }, timeout=30)
        print(f"✅ 推送：{r.json().get('msg')}")
    except Exception as e:
        print(f"❌ 推送异常（已落盘）：{str(e)[:50]}")


def main():
    now_cn = datetime.now(TZ_CN)
    print("=" * 55)
    print(f"启动：{now_cn:%Y‑%m‑%d %H:%M:%S CST} | akshare {ak.__version__} | ENABLE_LLM={ENABLE_LLM}")
    print("=" * 55)
    b1, b2, b3 = block_global(), block_news(), block_macro()
    raw_snapshot_text = "\n".join([b1, b2, b3])
    snapshot = raw_snapshot_text[:2600]
    view = llm_view(snapshot)
    content = f"# 📈 盘前晨报 · {now_cn:%Y年%m月%d日}【全部免费公开数据源】\n\n" + "\n\n".join([b1, b2, b3, view])
    content += "\n\n---\n*源：AkShare/财联社/央行 · 免费公开数据，存在延迟与接口失效风险；缺失不补；**不构成投资建议**。*"

    push(content)
    # 按日期输出，不覆盖历史报告
    fn = f"morning_report_{now_cn:%Y%m%d}.md"
    try:
        with open(fn, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ 本地报告保存至：{fn}")
    except IOError as e:
        print(f"⚠️ 文件写入失败：{str(e)}")
    print("✅ 执行完毕")
    sys.exit(0)


if __name__ == "__main__":
    main()
