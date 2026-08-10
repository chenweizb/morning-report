import os
import json
import requests
import akshare as ak
import pandas as pd
from datetime import datetime

# 读取环境变量（严格匹配GitHub Secrets名称）
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "")

def get_global_overnight():
    """获取外围行情（双重兜底+空值过滤，避免nan）"""
    print("[Step 1/3] 抓取外围行情...")
    result = ["### 🌏 外围全景"]
    
    # 尝试1：东财外盘接口（当前akshare1.18+可用）
    df = None
    try:
        df = ak.futures_global_em()
        if not df.empty:
            print(f"✅ 东财外盘接口返回{len(df)}条数据")
    except Exception as e:
        print(f"⚠️ 东财接口失败：{str(e)[:30]}")
    
    # 尝试2：新浪外盘接口（兜底）
    if df is None or df.empty:
        try:
            symbols = ak.futures_foreign_commodity_subscribe_exchange_symbol()
            if symbols:
                df = ak.futures_foreign_commodity_realtime(symbols)
                if not df.empty:
                    print(f"✅ 新浪外盘接口返回{len(df)}条数据")
        except Exception as e:
            print(f"⚠️ 新浪接口失败：{str(e)[:30]}")
    
    # 数据清洗：过滤空值和无效数据
    if df is not None and not df.empty:
        # 统一列名适配
        cols = df.columns.tolist()
        name_col = [c for c in cols if "名称" in c or "name" in c.lower()][0]
        price_col = [c for c in cols if "最新价" in c or "price" in c.lower()][0]
        pct_col = [c for c in cols if "涨跌幅" in c or "pct" in c.lower()][0]
        
        # 筛选核心品种（可根据需求增减）
        targets = ["A50", "富时中国A50", "原油", "WTI", "黄金", "COMEX", "道琼斯", "纳斯达克", "标普500"]
        filtered = df[df[name_col].str.contains("|".join(targets), na=False)]
        # 过滤价格为空的行
        filtered = filtered[filtered[price_col].notna()]
        
        if not filtered.empty:
            result.append("| 品种 | 最新价 | 涨跌幅 |")
            result.append("| :--- | :--- | :--- |")
            for _, row in filtered.head(6).iterrows():
                price = row[price_col] if pd.notna(row[price_col]) else "暂无"
                pct = row[pct_col] if pd.notna(row[pct_col]) else "0.00"
                result.append(f"| {row[name_col]} | {price} | {pct}% |")
            return "\n".join(result)
    
    result.append("| ⚠️ 外围数据暂不可用 | - | - |")
    return "\n".join(result)

def get_macro_data():
    """获取宏观数据（双重兜底+空值过滤）"""
    print("[Step 2/3] 抓取宏观数据...")
    result = ["### 🇨🇳 宏观脉搏"]
    
    macro_items = []
    # 尝试1：CPI数据
    try:
        cpi_df = ak.macro_china_cpi_yearly()
        if not cpi_df.empty:
            latest = cpi_df.iloc[-1]
            prev = cpi_df.iloc[-2] if len(cpi_df) > 1 else None
            val = latest["value"] if pd.notna(latest["value"]) else "暂无"
            prev_val = prev["value"] if prev and pd.notna(prev["value"]) else "暂无"
            macro_items.append(f"| CPI同比 | {val}% | 前值：{prev_val}% |")
    except Exception as e:
        print(f"⚠️ CPI接口失败：{str(e)[:30]}")
    
    # 尝试2：PMI数据
    try:
        pmi_df = ak.macro_china_pmi_yearly()
        if not pmi_df.empty:
            mfg_cols = [c for c in pmi_df.columns if "制造业" in c]
            if mfg_cols:
                latest = pmi_df.iloc[-1]
                prev = pmi_df.iloc[-2] if len(pmi_df) > 1 else None
                val = latest[mfg_cols[0]] if pd.notna(latest[mfg_cols[0]]) else "暂无"
                prev_val = prev[mfg_cols[0]] if prev and pd.notna(prev[mfg_cols[0]]) else "暂无"
                macro_items.append(f"| 制造业PMI | {val}% | 前值：{prev_val}% |")
    except Exception as e:
        print(f"⚠️ PMI接口失败：{str(e)[:30]}")
    
    # 尝试3：央行逆回购
    try:
        repo_df = ak.macro_china_gksccz()
        if not repo_df.empty:
            latest = repo_df.iloc[-1]
            amt = latest.get("交易量", "暂无")
            rate = latest.get("中标利率", "暂无")
            macro_items.append(f"| 央行逆回购 | {amt}亿 | 利率：{rate}% |")
    except Exception as e:
        print(f"⚠️ 逆回购接口失败：{str(e)[:30]}")
    
    if macro_items:
        result.append("| 指标 | 最新值 | 前值/备注 |")
        result.append("| :--- | :--- | :--- |")
        result.extend(macro_items)
    else:
        result.append("| ⚠️ 宏观数据暂不可用 | - | - |")
    return "\n".join(result)

def get_cls_news():
    """获取财联社快讯（关键词过滤+空值校验）"""
    print("[Step 3/3] 抓取盘前快讯...")
    result = ["### 📰 盘前快讯"]
    try:
        # 财联社电报接口
        df = ak.cls_telegraph()
        if not df.empty:
            # 过滤有效内容
            keywords = ["盘前", "早间", "隔夜", "央行", "A股", "政策", "利好", "利空"]
            filtered = df[df["content"].str.contains("|".join(keywords), na=False)]
            filtered = filtered[filtered["content"].notna()]
            
            if not filtered.empty:
                for _, row in filtered.head(8).iterrows():
                    content = row["content"]
                    if len(content) > 80:
                        content = content[:80] + "..."
                    result.append(f"- {content}")
                return "\n".join(result)
    except Exception as e:
        print(f"⚠️ 快讯接口失败：{str(e)[:30]}")
    
    result.append("- 暂无盘前相关快讯")
    return "\n".join(result)

def push_to_wechat(content):
    """微信推送（带状态校验）"""
    if not PUSHPLUS_TOKEN:
        print("❌ 未配置PUSHPLUS_TOKEN，跳过推送")
        return False
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
            return True
        else:
            print(f"❌ 推送失败：{res.get('msg')}")
            return False
    except Exception as e:
        print(f"❌ 推送异常：{str(e)[:50]}")
        return False

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
