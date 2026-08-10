import os
import json
import requests
from datetime import datetime
import akshare as ak

PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "")

def get_global():
    try:
        try:
            df = ak.futures_global_spot_em()
        except AttributeError:
            df = ak.futures_global_em()
        if not df.empty:
            cols = df.columns.tolist()
            name_col = [c for c in cols if "名称" in c or "name" in c.lower()][0]
            price_col = [c for c in cols if "最新价" in c or "price" in c.lower()][0]
            pct_col = [c for c in cols if "涨跌幅" in c or "pct" in c.lower()][0]
            a50 = df[df[name_col].str.contains("A50|富时", na=False)].iloc[0]
            oil = df[df[name_col].str.contains("原油|WTI", na=False)].iloc[0]
            gold = df[df[name_col].str.contains("黄金|COMEX", na=False)].iloc[0]
            return f'''### 🌍 外围行情
| 品种 | 最新价 | 涨跌幅 |
| ---- | ---- | ---- |
| {a50[name_col]} | {a50[price_col]} | {a50[pct_col]}% |
| {oil[name_col]} | {oil[price_col]} | {oil[pct_col]}% |
| {gold[name_col]} | {gold[price_col]} | {gold[pct_col]}% |'''
    except Exception as e:
        return f"### 🌍 外围行情\n⚠️ 抓取失败：{str(e)[:30]}"

def get_macro():
    try:
        df = ak.macro_china_cpi()
        latest = df.iloc[-1]
        return f'''### 🇨🇳 宏观数据
| 指标 | 数值 |
| ---- | ---- |
| CPI同比 | {latest['cpi']}% |
| CPI环比 | {latest['cpi_huanbi']}% |'''
    except Exception as e:
        return f"### 🇨🇳 宏观数据\n⚠️ 抓取失败：{str(e)[:30]}"

def get_news():
    try:
        df = ak.cls_telegraph()
        news = df[df['content'].str.contains("盘前|早间|隔夜", na=False)].head(3)['content'].tolist()
        if news:
            return "### 📰 盘前快讯\n" + "\n".join([f"- {n}" for n in news])
        return "### 📰 盘前快讯\n- 暂无最新快讯"
    except Exception as e:
        return f"### 📰 盘前快讯\n⚠️ 抓取失败：{str(e)[:30]}"

def push(content):
    if not PUSHPLUS_TOKEN:
        print("❌ 未配置PUSHPLUS_TOKEN")
        return
    try:
        resp = requests.post(
            "https://www.pushplus.plus/send",
            json={"token": PUSHPLUS_TOKEN, "title": f"买方Alpha早参·{datetime.now().strftime('%Y-%m-%d')}", "content": content, "template": "markdown"},
            timeout=30
        )
        print(f"✅ 推送结果：{resp.json().get('msg')}")
    except Exception as e:
        print(f"❌ 推送失败：{str(e)[:30]}")

def main():
    print(f"启动时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"AkShare版本：{ak.__version__}")
    content = f"# 📈 买方Alpha早参 · {datetime.now().strftime('%Y年%m月%d日')}\n\n{get_global()}\n\n{get_macro()}\n\n{get_news()}\n\n---\n*数据来源：交易所/央行/财联社 | 不构成投资建议*"
    push(content)
    with open("raw_news.txt", "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    main()
