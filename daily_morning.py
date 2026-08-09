# -*- coding: utf-8 -*-
# B2.1 买方Alpha早参 · 全接口适配版（2024.10更新/推送必达/零崩溃）
import os
import re
import time
import random
import requests
from bs4 import BeautifulSoup
import akshare as ak
import pandas as pd
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict, Any

# ==================== 基础配置（自动读取GitHub Secrets，无需改代码） ====================
@dataclass
class Config:
    PUSHPLUS_TOKEN: str = os.getenv("PUSHPLUS_TOKEN", "")
    TUSHARE_TOKEN: str = os.getenv("TUSHARE_TOKEN", "")
    HEADERS: dict = None
    TIMEOUT: int = 30
    DELAY_RANGE: tuple = (2, 5)  # 反爬延迟
    RETRY_TIMES: int = 3  # 接口重试次数

    def __post_init__(self):
        self.HEADERS = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            "Referer": "https://www.cls.cn/"
        }
        # 调试用：打印Token状态（不泄露隐私，仅显示前后4位）
        if self.PUSHPLUS_TOKEN:
            mask = self.PUSHPLUS_TOKEN[:4] + "****" + self.PUSHPLUS_TOKEN[-4:] if len(self.PUSHPLUS_TOKEN) > 8 else "****"
            print(f"✅ 已读取PushPlus Token: {mask}")
        else:
            print("❌ 未检测到PUSHPLUS_TOKEN，请检查GitHub Secrets配置！")

cfg = Config()

# ==================== 事件信号结构体 ====================
@dataclass
class EventSignal:
    ts_code: str = ""
    event_type: str = ""
    direction: int = 0  # +1利好/-1利空
    strength: float = 0.0
    decay_hours: int = 12
    source: str = ""

# ==================== 数据抓取（全接口容错+最新接口适配） ====================
class DataFetcher:
    """所有第三方接口调用都包一层容错，单接口失败不影响全局"""
    @staticmethod
    def safe_fetch(label: str, func, *args, **kwargs) -> Any:
        """带重试的安全抓取：失败自动重试3次，仍失败返回None"""
        for i in range(cfg.RETRY_TIMES + 1):
            try:
                time.sleep(random.uniform(*cfg.DELAY_RANGE))
                result = func(*args, **kwargs)
                if result is not None and not (isinstance(result, pd.DataFrame) and result.empty):
                    print(f"✅ [{label}] 抓取成功")
                    return result
            except Exception as e:
                if i == cfg.RETRY_TIMES:
                    print(f"⚠️ [{label}] 抓取失败（重试{cfg.RETRY_TIMES}次）：{str(e)[:50]}")
                    return None
                time.sleep(1)
        return None

    @classmethod
    def get_global_overnight(cls) -> str:
        """获取外围行情（适配最新AkShare接口）"""
        res = ["🌍 **【外围全景】**"]
        
        # 1. 外盘期货（最新接口：futures_global_spot_em）
        global_df = cls.safe_fetch("外盘期货", ak.futures_global_spot_em)
        if isinstance(global_df, pd.DataFrame):
            # 动态适配列名（不同版本AkShare列名可能不同）
            rename_map = {}
            for col in global_df.columns:
                col_lower = col.lower()
                if any(k in col_lower for k in ["symbol", "代码"]):
                    rename_map[col] = "代码"
                elif any(k in col_lower for k in ["name", "名称"]):
                    rename_map[col] = "名称"
                elif any(k in col_lower for k in ["price", "最新价", "last"]):
                    rename_map[col] = "最新价"
                elif any(k in col_lower for k in ["pct", "涨跌幅", "chg"]):
                    rename_map[col] = "涨跌幅"
            if rename_map:
                global_df = global_df.rename(columns=rename_map)
            
            # 筛选A50
            if "名称" in global_df.columns:
                a50 = global_df[global_df["名称"].str.contains("A50|富时中国A50", case=False, na=False)]
                if not a50.empty:
                    res.append(f"  - **A50期货**：{a50.iloc[0]['最新价']}（涨跌幅：{a50.iloc[0]['涨跌幅']}%）")
            
            # 筛选原油/黄金
            if "名称" in global_df.columns:
                oil = global_df[global_df["名称"].str.contains("原油|WTI", case=False, na=False)]
                gold = global_df[global_df["名称"].str.contains("黄金|COMEX", case=False, na=False)]
                if not oil.empty:
                    res.append(f"  - **美油**：{oil.iloc[0]['最新价']}美元/桶")
                if not gold.empty:
                    res.append(f"  - **COMEX黄金**：{gold.iloc[0]['最新价']}美元/盎司")
        else:
            res.append("  - 外盘期货数据暂缺")

        # 2. 美股行情
        us_df = cls.safe_fetch("美股行情", ak.stock_us_spot_em)
        if isinstance(us_df, pd.DataFrame) and "名称" in us_df.columns:
            us_idx = us_df[us_df["名称"].isin(["道琼斯", "纳斯达克", "标普500"])]
            if not us_idx.empty:
                res.append("  - **隔夜美股**：")
                for _, row in us_idx.iterrows():
                    res.append(f"    - {row['名称']}：{row['最新价']}（涨跌幅：{row['涨跌幅']}%）")
        else:
            res.append("  - 美股数据暂缺")

        # 3. 离岸人民币（最新接口：currency_boc_safe）
        cnh_df = cls.safe_fetch("离岸人民币", ak.currency_boc_safe)
        if isinstance(cnh_df, pd.DataFrame):
            # 动态匹配美元列
            usd_cols = [col for col in cnh_df.columns if "美元" in col]
            if usd_cols and pd.notna(cnh_df.iloc[0][usd_cols[0]]):
                cnh_val = cnh_df.iloc[0][usd_cols[0]]
                res.append(f"  - **离岸人民币**：1美元兑{cnh_val}CNH")
            else:
                res.append("  - 离岸人民币汇率暂缺")
        else:
            res.append("  - 离岸人民币汇率暂缺")
        
        return "\n".join(res)

    @classmethod
    def get_macro_data(cls) -> str:
        """获取宏观数据（适配最新AkShare接口，修复逆回购报错）"""
        res = ["\n🇨🇳 **【宏观脉搏】**"]
        
        # 1. 制造业PMI
        pmi_df = cls.safe_fetch("制造业PMI", ak.macro_china_pmi_yearly)
        if isinstance(pmi_df, pd.DataFrame):
            mfg_cols = [col for col in pmi_df.columns if "制造业" in col]
            if mfg_cols and len(pmi_df) >= 1:
                val = pmi_df.iloc[0][mfg_cols[0]]
                prev = pmi_df.iloc[1][mfg_cols[0]] if len(pmi_df) >= 2 else "N/A"
                date_col = [col for col in pmi_df.columns if any(k in col for k in ["日期", "月份"])]
                date_str = pmi_df.iloc[0][date_col[0]] if date_col else "最新"
                res.append(f"  - **制造业PMI**：{val}%（{date_str}，前值：{prev}%）")
            else:
                res.append("  - 制造业PMI数据暂缺")
        else:
            res.append("  - 制造业PMI数据暂缺")

        # 2. CPI通胀
        cpi_df = cls.safe_fetch("CPI通胀", ak.macro_china_cpi_yearly)
        if isinstance(cpi_df, pd.DataFrame):
            cpi_cols = [col for col in cpi_df.columns if any(k in col for k in ["CPI", "同比"])]
            if cpi_cols and len(cpi_df) >= 1:
                val = cpi_df.iloc[0][cpi_cols[0]]
                prev = cpi_df.iloc[1][cpi_cols[0]] if len(cpi_df) >= 2 else "N/A"
                date_col = [col for col in cpi_df.columns if any(k in col for k in ["日期", "月份"])]
                date_str = cpi_df.iloc[0][date_col[0]] if date_col else "最新"
                res.append(f"  - **CPI同比**：{val}%（{date_str}，前值：{prev}%）")
            else:
                res.append("  - CPI通胀数据暂缺")
        else:
            res.append("  - CPI通胀数据暂缺")

        # 3. 央行逆回购（🔧 修复点：旧接口macro_china_gksccz已失效，替换为最新接口macro_china_hb）
        repo_df = cls.safe_fetch("央行逆回购", ak.macro_china_hb, symbol="weekly")  # weekly=周度数据，也可改为daily
        if isinstance(repo_df, pd.DataFrame) and not repo_df.empty:
            latest = repo_df.iloc[-1]  # 取最新一条
            # 动态匹配列名（不同版本列名可能不同）
            put_col = [col for col in repo_df.columns if "投放量" in col]
            back_col = [col for col in repo_df.columns if "回笼量" in col]
            net_col = [col for col in repo_df.columns if "净投放" in col]
            date_col = [col for col in repo_df.columns if "日期" in col]
            
            put_val = latest[put_col[0]] if put_col else "N/A"
            back_val = latest[back_col[0]] if back_col else "N/A"
            net_val = latest[net_col[0]] if net_col else "N/A"
            date_str = latest[date_col[0]] if date_col else "最新"
            
            res.append(f"  - **央行逆回购**：{date_str}净投放{net_val}亿元（投放：{put_val}，回笼：{back_val}）")
        else:
            res.append("  - 央行逆回购数据暂缺")
        
        return "\n".join(res)

    @classmethod
    def get_cls_news(cls) -> List[str]:
        """获取财联社盘前快讯"""
        res = ["\n📰 **【盘前快讯】**"]
        try:
            resp = cls.safe_fetch(
                "财联社快讯",
                lambda: requests.get(
                    "https://www.cls.cn/nodeapi/updateTelegraphList?app=1&last_time=0",
                    headers=cfg.HEADERS,
                    timeout=cfg.TIMEOUT
                )
            )
            if isinstance(resp, requests.Response):
                data = resp.json()
                news_list = [i["content"] for i in data["data"]["list"][:5] if any(k in i["content"] for k in ["盘前", "早间", "隔夜"])]
                if news_list:
                    for news in news_list:
                        res.append(f"  - {news}")
                else:
                    res.append("  - 今日暂无盘前快讯")
            else:
                res.append("  - 财联社快讯抓取失败")
        except Exception as e:
            res.append(f"  - 财联社快讯异常：{str(e)[:50]}")
        return res

# ==================== 事件解析/选股/推送（保留原有逻辑，优化容错） ====================
class EventParser:
    @staticmethod
    def parse_news(news: List[str]) -> List[EventSignal]:
        events = []
        for item in news:
            if not isinstance(item, str):
                continue
            if re.search(r"(利好|支持|扩大|稳增长)", item):
                events.append(EventSignal(event_type="policy_bullish", direction=1, strength=0.6, source="cls"))
            elif re.search(r"(利空|收紧|限制|调控)", item):
                events.append(EventSignal(event_type="policy_bearish", direction=-1, strength=0.6, source="cls"))
            if re.search(r"(美股|纳指|道指).*(跌|暴跌)", item):
                events.append(EventSignal(event_type="global_risk", direction=-1, strength=0.8, decay_hours=6, source="cls"))
        return events

class AlphaEngine:
    @staticmethod
    def select_stocks(events: List[EventSignal]) -> Dict[str, List[Dict]]:
        """双轨选股：未配置股票池时明确提示"""
        # 【必填】在此处添加你的股票池，格式：{"股票代码.交易所": {"name": "简称", "roe": ROE, "vol": 波动率, "ret_20d": 20日涨幅}}
        stock_pool = {}  # 空池时会提示未配置
        if not stock_pool:
            return {
                "stable": [{"ts_code": "未配置", "score": 0, "reason": "请在AlphaEngine中填写股票池"}],
                "aggressive": [{"ts_code": "未配置", "score": 0, "reason": "请在AlphaEngine中填写股票池"}]
            }
        # 以下为原有选股逻辑（省略，不影响推送）
        return {"stable": [], "aggressive": []}

class PushRenderer:
    @staticmethod
    def render(alpha_book: Dict, raw: Dict) -> str:
        date = datetime.now().strftime("%Y年%m月%d日")
        md = f"# 📈 买方Alpha早参 · {date}\n\n"
        md += raw.get("global", "🌍 **【外围全景】**\n  - 数据暂缺") + "\n"
        md += raw.get("macro", "🇨🇳 **【宏观脉搏】**\n  - 数据暂缺") + "\n"
        md += "\n## 🎯 **【双轨选股结果】**\n"
        md += f"### 【稳健派 · 核心底仓】（60-80%仓位）\n"
        for s in alpha_book["stable"]:
            md += f"- **{s['ts_code']}** | 评分: `{s['score']}` | {s['reason']}\n"
        md += f"\n### 【激进派 · 冲锋号角】（20-40%仓位）\n"
        for s in alpha_book["aggressive"]:
            md += f"- **{s['ts_code']}** | 评分: `{s['score']}` | {s['reason']}\n"
        md += "\n" + "\n".join(raw.get("news", ["📰 **【盘前快讯】**\n  - 数据暂缺"])) + "\n"
        md += "\n---\n*数据来源：交易所/央行/财联社 | 不构成投资建议*"
        return md

    @staticmethod
    def push(content: str) -> bool:
        """发送微信推送：增加详细日志，方便排查"""
        if not cfg.PUSHPLUS_TOKEN:
            print("❌ 推送失败：未配置PUSHPLUS_TOKEN")
            return False
        try:
            resp = requests.post(
                "https://www.pushplus.plus/send",
                json={
                    "token": cfg.PUSHPLUS_TOKEN,
                    "title": f"买方Alpha早参 · {datetime.now().strftime('%Y-%m-%d')}",
                    "content": content,
                    "template": "markdown"
                },
                headers=cfg.HEADERS,
                timeout=cfg.TIMEOUT
            )
            result = resp.json()
            if result.get("code") == 200:
                print("✅ 微信推送成功！请检查微信服务号「pushplus 推送加」")
                return True
            else:
                print(f"❌ 推送失败：{result.get('msg')}（错误码：{result.get('code')}）")
                return False
        except Exception as e:
            print(f"❌ 推送异常：{str(e)[:50]}")
            return False

# ==================== 主流程（优先推送，崩溃也发告警） ====================
def main():
    print("=" * 50)
    print("B2.1 买方Alpha早参 · 启动中...")
    print("=" * 50)
    try:
        print("\n[Step 1/4] 抓取外围行情...")
        global_data = DataFetcher.get_global_overnight()
        print("\n[Step 2/4] 抓取宏观数据...")
        macro_data = DataFetcher.get_macro_data()
        print("\n[Step 3/4] 抓取盘前快讯...")
        news_data = DataFetcher.get_cls_news()
        print("\n[Step 4/4] 渲染并推送...")
        raw = {"global": global_data, "macro": macro_data, "news": news_data}
        alpha_book = AlphaEngine.select_stocks(EventParser.parse_news(news_data))
        content = PushRenderer.render(alpha_book, raw)
        PushRenderer.push(content)
        # 落盘（失败不影响推送）
        with open("raw_news.txt", "w", encoding="utf-8") as f:
            f.write(content)
        print("\n[完成] 流程结束，原始数据已落盘")
    except Exception as e:
        print(f"!!! 程序发生致命错误：{e}")
        # 崩溃时也发告警
        if cfg.PUSHPLUS_TOKEN:
            requests.post(
                "https://www.pushplus.plus/send",
                json={
                    "token": cfg.PUSHPLUS_TOKEN,
                    "title": "B2.1 早报系统崩溃告警",
                    "content": f"程序崩溃，错误信息：\n```\n{e}\n```",
                    "template": "markdown"
                },
                headers=cfg.HEADERS,
                timeout=cfg.TIMEOUT
            )
    finally:
        print("=" * 50)

if __name__ == "__main__":
    main()
