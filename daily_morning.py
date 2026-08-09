# -*- coding: utf-8 -*-
# B2.1 买方Alpha早参 · 最终稳定版（接口名全部核实/云端锁版本/不误发告警）
import os
import time
import random
import requests
from datetime import datetime
import akshare as ak
import pandas as pd
from typing import Any, List

class Config:
    PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "")
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Referer": "https://www.cls.cn/"
    }
    TIMEOUT = 30
    RETRY_TIMES = 3
    DELAY_RANGE = (1, 3)

cfg = Config()

class SafeFetcher:
    """多候选接口兜底：挨个试，全失败才返回默认文本，绝不抛异常"""
    @staticmethod
    def fetch_multi(label: str, funcs: List[tuple], default_return="暂无数据") -> Any:
        for func, args, kwargs in funcs:
            for attempt in range(cfg.RETRY_TIMES + 1):
                try:
                    time.sleep(random.uniform(*cfg.DELAY_RANGE))
                    result = func(*args, **kwargs)
                    if result is None or (isinstance(result, pd.DataFrame) and result.empty):
                        raise ValueError("空数据")
                    print(f"✅ [{label}] 抓取成功（接口：{func.__name__}）")
                    return result
                except Exception as e:
                    if attempt == cfg.RETRY_TIMES:
                        print(f"⚠️ [{label}] 接口 {func.__name__} 失败：{str(e)[:40]}")
                    else:
                        time.sleep(1)
        return default_return

class DataFetcher:
    @classmethod
    def get_global_overnight(cls) -> str:
        res = ["🌍 **【外围全景】**"]
        # 外盘期货（真实接口）
        df = SafeFetcher.fetch_multi("外盘期货", [
            (ak.futures_global_spot_em, (), {}),
            (ak.futures_global_em, (), {}),  # 老接口兜底
        ])
        if isinstance(df, pd.DataFrame):
            cmap = {}
            for c in df.columns:
                cl = c.lower()
                if any(k in cl for k in ["symbol", "代码"]): cmap[c] = "代码"
                elif any(k in cl for k in ["name", "名称"]): cmap[c] = "名称"
                elif any(k in cl for k in ["price", "最新价", "last"]): cmap[c] = "最新价"
                elif any(k in cl for k in ["pct", "涨跌幅", "chg"]): cmap[c] = "涨跌幅"
            if cmap: df = df.rename(columns=cmap)
            if "名称" in df.columns:
                a50 = df[df["名称"].str.contains("A50|富时中国A50", case=False, na=False)]
                if not a50.empty: res.append(f"  - **A50期货**：{a50.iloc[0]['最新价']}（{a50.iloc[0]['涨跌幅']}%）")
                oil = df[df["名称"].str.contains("原油|WTI", case=False, na=False)]
                gold = df[df["名称"].str.contains("黄金|COMEX", case=False, na=False)]
                if not oil.empty: res.append(f"  - **美油**：{oil.iloc[0]['最新价']}美元/桶")
                if not gold.empty: res.append(f"  - **COMEX黄金**：{gold.iloc[0]['最新价']}美元/盎司")
        else:
            res.append("  - 外盘期货暂无数据")

        # 美股
        us = SafeFetcher.fetch_multi("美股", [(ak.stock_us_spot_em, (), {})])
        if isinstance(us, pd.DataFrame) and "名称" in us.columns:
            idx = us[us["名称"].isin(["道琼斯", "纳斯达克", "标普500"])]
            if not idx.empty:
                res.append("  - **隔夜美股**：")
                for _, r in idx.iterrows():
                    res.append(f"    - {r['名称']}：{r['最新价']}（{r['涨跌幅']}%）")
        else:
            res.append("  - 美股暂无数据")

        # 离岸人民币（真实接口 currency_boc_safe，返回列含“美元”）
        cnh = SafeFetcher.fetch_multi("离岸人民币", [(ak.currency_boc_safe, (), {})])
        if isinstance(cnh, pd.DataFrame):
            usd_cols = [c for c in cnh.columns if "美元" in c]
            if usd_cols and pd.notna(cnh.iloc[-1][usd_cols[0]]):
                res.append(f"  - **离岸人民币**：1美元兑{cnh.iloc[-1][usd_cols[0]]}CNH")
            else:
                res.append("  - 离岸人民币暂无数据")
        else:
            res.append("  - 离岸人民币暂无数据")
        return "\n".join(res)

    @classmethod
    def get_macro_data(cls) -> str:
        res = ["\n🇨🇳 **【宏观脉搏】**"]
        # 制造业PMI
        pmi = SafeFetcher.fetch_multi("制造业PMI", [(ak.macro_china_pmi_yearly, (), {})])
        if isinstance(pmi, pd.DataFrame):
            mcol = [c for c in pmi.columns if "制造业" in c]
            if mcol:
                res.append(f"  - **制造业PMI**：{pmi.iloc[0][mcol[0]]}（前值：{pmi.iloc[1][mcol[0]]}）")
            else: res.append("  - 制造业PMI暂无数据")
        else: res.append("  - 制造业PMI暂无数据")

        # CPI
        cpi = SafeFetcher.fetch_multi("CPI", [(ak.macro_china_cpi_yearly, (), {})])
        if isinstance(cpi, pd.DataFrame):
            ccol = [c for c in cpi.columns if any(k in c for k in ["CPI", "同比"])]
            if ccol:
                res.append(f"  - **CPI同比**：{cpi.iloc[0][ccol[0]]}%（前值：{cpi.iloc[1][ccol[0]]}）")
            else: res.append("  - CPI暂无数据")
        else: res.append("  - CPI暂无数据")

        # 🔧 央行逆回购：用官方真实接口 macro_china_gksccz，多候选兜底
        repo = SafeFetcher.fetch_multi("央行逆回购", [
            (ak.macro_china_gksccz, (), {}),          # 官方真实接口
            (ak.macro_china_gksccz_df, (), {}),       # 别名兜底
        ])
        if isinstance(repo, pd.DataFrame) and not repo.empty:
            latest = repo.iloc[-1]
            date = latest.get("操作日期", latest.get("日期", "最新"))
            amt = latest.get("交易量", "N/A")
            rate = latest.get("中标利率", "N/A")
            direction = latest.get("正/逆回购", "逆回购")
            res.append(f"  - **央行操作**：{date} {direction} {amt}亿，中标利率{rate}%")
        else:
            res.append("  - 央行逆回购暂无数据")
        return "\n".join(res)

    @classmethod
    def get_cls_news(cls) -> List[str]:
        res = ["\n📰 **【盘前快讯】**"]
        try:
            resp = SafeFetcher.fetch_multi("财联社", [
                (lambda: requests.get("https://www.cls.cn/nodeapi/updateTelegraphList?app=1&last_time=0",
                                      headers=cfg.HEADERS, timeout=cfg.TIMEOUT), (), {})
            ])
            if isinstance(resp, requests.Response):
                d = resp.json()
                ns = [i["content"] for i in d["data"]["list"][:5] if any(k in i["content"] for k in ["盘前", "早间", "隔夜"])]
                if ns:
                    for n in ns: res.append(f"  - {n}")
                else: res.append("  - 今日暂无盘前快讯")
            else: res.append("  - 财联社快讯暂无数据")
        except Exception:
            res.append("  - 财联社快讯抓取异常")
        return res

class PushService:
    @staticmethod
    def push(content: str) -> bool:
        if not cfg.PUSHPLUS_TOKEN:
            print("❌ 未配置PUSHPLUS_TOKEN")
            return False
        mask = cfg.PUSHPLUS_TOKEN[:4] + "****" + cfg.PUSHPLUS_TOKEN[-4:] if len(cfg.PUSHPLUS_TOKEN) > 8 else "****"
        print(f"🔍 使用PushPlus Token：{mask}")
        try:
            r = requests.post("https://www.pushplus.plus/send", json={
                "token": cfg.PUSHPLUS_TOKEN,
                "title": f"买方Alpha早参 · {datetime.now().strftime('%Y-%m-%d')}",
                "content": content, "template": "markdown", "channel": "wechat"
            }, headers=cfg.HEADERS, timeout=cfg.TIMEOUT)
            j = r.json()
            if j.get("code") == 200:
                print("✅ 微信推送成功！去公众号「pushplus 推送加」查收（没收到看订阅号消息文件夹）")
                return True
            else:
                print(f"❌ 推送失败：{j.get('msg')}（code={j.get('code')}）")
                return False
        except Exception as e:
            print(f"❌ 推送异常：{str(e)[:50]}")
            return False

def main():
    print("=" * 50)
    print(f"🚀 启动：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | akshare={ak.__version__}")
    print("=" * 50)
    global_data = DataFetcher.get_global_overnight()
    macro_data = DataFetcher.get_macro_data()
    news_data = DataFetcher.get_cls_news()
    content = f"# 📈 买方Alpha早参 · {datetime.now().strftime('%Y年%m月%d日')}\n\n{global_data}\n{macro_data}\n\n" + "\n".join(news_data) + "\n\n---\n*数据来源：交易所/央行/财联社 | 不构成投资建议*"
    PushService.push(content)
    with open("raw_news.txt", "w", encoding="utf-8") as f:
        f.write(content)
    print("=" * 50)

if __name__ == "__main__":
    main()
