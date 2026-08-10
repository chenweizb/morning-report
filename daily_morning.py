import os
import requests
import json
import akshare as ak
from datetime import datetime

# 读取环境变量
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN")

def get_global_overnight():
    """获取外围行情（3重备用接口，最大化数据量）"""
    print("[Step 1/3] 抓取外围行情...")
    result_lines = ["### 🌏 外围全景"]
    
    # 1. 外盘期货（东财+新浪双兜底）
    df_futures = None
    try:
        df_futures = ak.futures_global_spot_em()
        print("  ✅ 外盘期货（东财接口）抓取成功")
    except:
        try:
            df_futures = ak.futures_global_em()
            print("  ✅ 外盘期货（旧接口）抓取成功")
        except:
            print("  ⚠️ 外盘期货接口失效")
    
    if df_futures is not None and not df_futures.empty:
        # 动态适配列名
        cols = df_futures.columns.tolist()
        name_col = [c for c in cols if "名称" in c or "name" in c.lower()][0]
        price_col = [c for c in cols if "最新价" in c or "price" in c.lower()][0]
        pct_col = [c for c in cols if "涨跌幅" in c or "pct" in c.lower()][0]
        
        # 筛选核心品种
        targets = ["A50", "富时中国A50", "原油", "WTI", "黄金", "COMEX", "道琼斯", "纳斯达克", "标普500"]
        filtered = df_futures[df_futures[name_col].str.contains("|".join(targets), na=False)].head(6)
        
        if not filtered.empty:
            result_lines.append("| 品种 | 最新价 | 涨跌幅 |")
            result_lines.append("| :--- | :--- | :--- |")
            for _, row in filtered.iterrows():
                result_lines.append(f"| {row[name_col]} | {row[price_col]} | {row[pct_col]}% |")

    # 2. 离岸人民币（备用接口）
    try:
        cnh_df = ak.currency_boc_safe()
        if cnh_df is not None and not cnh_df.empty:
            usd_cols = [c for c in cnh_df.columns if "美元" in c]
            if usd_cols:
                result_lines.append(f"\n| 离岸人民币 | 1美元兑{cnh_df.iloc[0][usd_cols[0]]}CNH | - |")
    except:
        pass

    if len(result_lines) == 1:
        result_lines.append("| ⚠️ 外围数据暂不可用 | - | - |")
    return "\n".join(result_lines)

def get_macro_data():
    """获取宏观数据（3重备用接口，最大化数据量）"""
    print("[Step 2/3] 抓取宏观数据...")
    result_lines = ["### 🇨🇳 宏观脉搏"]
    
    # 1. CPI+PMI双数据
    macro_items = []
    try:
        cpi_df = ak.macro_china_cpi_yearly()
        if cpi_df is not None and not cpi_df.empty:
            latest = cpi_df.iloc[-1]
            prev = cpi_df.iloc[-2] if len(cpi_df) > 1 else None
            macro_items.append(f"| CPI同比 | {latest['value']}% | 前值：{prev['value'] if prev else 'N/A'}% |")
    except:
        pass
    
    try:
        pmi_df = ak.macro_china_pmi_yearly()
        if pmi_df is not None and not pmi_df.empty:
            mfg_cols = [c for c in pmi_df.columns if "制造业" in c]
            if mfg_cols:
                latest = pmi_df.iloc[-1]
                prev = pmi_df.iloc[-2] if len(pmi_df) > 1 else None
                macro_items.append(f"| 制造业PMI | {latest[mfg_cols[0]]}% | 前值：{prev[mfg_cols[0]] if prev else 'N/A'}% |")
    except:
        pass
    
    # 2. 央行逆回购
    try:
        repo_df = ak.macro_china_gksccz()
        if repo_df is not None and not repo_df.empty:
            latest = repo_df.iloc[-1]
            macro_items.append(f"| 央行逆回购 | {latest.get('交易量', 'N/A')}亿 | 利率：{latest.get('中标利率', 'N/A')}% |")
    except:
        pass

    if macro_items:
        result_lines.append("| 指标 | 最新值 | 前值/备注 |")
        result_lines.append("| :--- | :--- | :--- |")
        result_lines.extend(macro_items)
    else:
        result_lines.append("| ⚠️ 宏观数据暂不可用 | - | - |")
    return "\n".join(result_lines)

def get_cls_news():
    """获取财联社快讯（多关键词过滤，最大化有效内容）"""
    print("[Step 3/3] 抓取盘前快讯...")
    result_lines = ["### 📰 盘前快讯"]
    try:
        # 财联社电报接口
        df = ak.cls_telegraph()
        if df is not None and not df.empty:
            # 过滤盘前相关有效内容
            keywords = ["盘前", "早间", "隔夜", "央行", "A股", "政策", "利好", "利空"]
            filtered = df[df["content"].str.contains("|".join(keywords), na=False)].head(8)
            if not filtered.empty:
                for _, row in filtered.iterrows():
                    content = row["content"]
                    if len(content) > 80:
                        content = content[:80] + "..."
                    result_lines.append(f"- {content}")
            else:
                result_lines.append("- 暂无盘前相关快讯")
        else:
            result_lines.append("- 暂无快讯数据")
    except:
        result_lines.append("- ⚠️ 快讯接口暂不可用")
    return "\n".join(result_lines)

def push_to_wechat(content):
    """推送至微信（带状态提示）"""
    if not PUSHPLUS_TOKEN:
        print("❌ 未配置PUSHPLUS_TOKEN，跳过推送")
        return
    try:
        resp = requests.post(
            "https://www.pushplus.plus/send",
            json={
                "token": PUSHPLUS_TOKEN,
                "title": f"买方Alpha早参 · {datetime.now().strftime('%Y-%m-%d')}",
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
    
    # 组装完整内容
    content = f"# 📈 买方Alpha早参 · {datetime.now().strftime('%Y年%m月%d日')}\n\n"
    content += get_global_overnight() + "\n\n"
    content += get_macro_data() + "\n\n"
    content += get_cls_news() + "\n\n"
    content += "---\n*数据来源：交易所/央行/财联社 | 不构成投资建议*"
    
    # 推送+落盘
    push_to_wechat(content)
    with open("raw_news.txt", "w", encoding="utf-8") as f:
        f.write(content)
    print("✅ 原始数据已落盘")
    print("=" * 50)

if __name__ == "__main__":
    main()
