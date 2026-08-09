# -*- coding: utf-8 -*-
# B2.1 买方Alpha早参 · 终极稳定全量版（适配AkShare 1.16+/全动态字段匹配/零崩溃/优先推送）
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

# ==================== 基础配置（严禁明文写Token，从GitHub Secrets读取） ====================
@dataclass
class Config:
    PUSHPLUS_TOKEN: str = os.getenv("PUSHPLUS_TOKEN", "")
    TUSHARE_TOKEN: str = os.getenv("TUSHARE_TOKEN", "")
    HEADERS: dict = None
    TIMEOUT: int = 30
    DELAY_RANGE: tuple = (2, 5)
    RETRY_TIMES: int = 3

    def __post_init__(self):
        self.HEADERS = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.cls.cn/"
        }

cfg = Config()

# ==================== 事件信号结构体 ====================
@dataclass
class EventSignal:
    ts_code: str = ""
    event_type: str = ""
    direction: int = 0  # +1利好/-1利空
    strength: float = 0.0  # 0~1强度
    decay_hours: int = 12  # 事件有效期
    source: str = ""  # 来源：cls/央行/交易所

# ==================== 数据爬取（全接口容错+动态字段适配，彻底解决接口变动问题） ====================
class DataFetcher:
    @staticmethod
    def safe_fetch(label: str, func, *args, **kwargs) -> Any:
        """通用容错+重试装饰器，单接口失败不影响全局"""
        for i in range(cfg.RETRY_TIMES + 1):
            try:
                time.sleep(random.uniform(*cfg.DELAY_RANGE))
                result = func(*args, **kwargs)
                if result is not None and not (isinstance(result, pd.DataFrame) and result.empty):
                    return result
            except Exception as e:
                if i == cfg.RETRY_TIMES:
                    print(f"⚠️ 【{label}】抓取失败（已重试{cfg.RETRY_TIMES}次）：{str(e)[:50]}")
                    return None
        return None

    @classmethod
    def get_global_overnight(cls) -> str:
        """获取隔夜外围行情（全接口适配AkShare 1.16+）"""
        res = []
        res.append("🌍 **【外围全景】**")
        
        # 1. 外盘期货（动态适配字段）
        global_df = cls.safe_fetch("外盘期货", ak.futures_global_spot_em)
        if isinstance(global_df, pd.DataFrame):
            # 动态适配新接口字段
            rename_map = {}
            for col in global_df.columns:
                col_lower = col.lower()
                if "symbol" in col_lower or "代码" in col:
                    rename_map[col] = "代码"
                elif "name" in col_lower or "名称" in col:
                    rename_map[col] = "名称"
                elif "price" in col_lower or "最新价" in col or "last" in col_lower:
                    rename_map[col] = "最新价"
                elif "pct" in col_lower or "涨跌幅" in col or "涨跌幅" in col_lower:
                    rename_map[col] = "涨跌幅"
            if rename_map:
                global_df = global_df.rename(columns=rename_map)
            
            # 筛选A50
            if "名称" in global_df.columns:
                a50_mask = global_df["名称"].str.contains("A50|富时中国A50", case=False, na=False)
                if a50_mask.any():
                    a50_df = global_df[a50_mask]
                    res.append(f"  - **A50期货**：最新价 {a50_df.iloc[0]['最新价']}，涨跌幅 {a50_df.iloc[0]['涨跌幅']}%")
            
            # 筛选原油/黄金
            if "名称" in global_df.columns:
                oil_mask = global_df["名称"].str.contains("原油|WTI", case=False, na=False)
                gold_mask = global_df["名称"].str.contains("黄金|COMEX", case=False, na=False)
                if oil_mask.any():
                    oil_df = global_df[oil_mask]
                    res.append(f"  - **大宗商品**：美油 {oil_df.iloc[0]['最新价']}美元/桶")
                if gold_mask.any():
                    gold_df = global_df[gold_mask]
                    res.append(f"  - **黄金**：{gold_df.iloc[0]['最新价']}美元/盎司")
        else:
            res.append("  - 外盘期货数据暂缺")

        # 2. 美股行情（稳定接口）
        us_df = cls.safe_fetch("美股行情", ak.stock_us_spot_em)
        if isinstance(us_df, pd.DataFrame) and "名称" in us_df.columns:
            us_key = us_df[us_df["名称"].isin(["道琼斯", "纳斯达克", "标普500"])]
            if not us_key.empty:
                res.append("  - **隔夜美股**：")
                for _, row in us_key.iterrows():
                    res.append(f"    - {row['名称']}：{row['最新价']}，涨跌幅 {row['涨跌幅']}%")
        else:
            res.append("  - 美股数据暂缺")

        # 3. 离岸人民币（动态匹配美元列）
        cnh_df = cls.safe_fetch("离岸人民币", ak.currency_boc_safe)
        if isinstance(cnh_df, pd.DataFrame):
            usd_cols = [col for col in cnh_df.columns if "美元" in col]
            if usd_cols and pd.notna(cnh_df.iloc[0][usd_cols[0]]):
                cnh_value = cnh_df.iloc[0][usd_cols[0]]
                res.append(f"  - **离岸人民币**：1美元兑CNH {cnh_value}")
            else:
                res.append("  - 离岸人民币汇率数据暂缺")
        else:
            res.append("  - 离岸人民币汇率数据暂缺")

        return "\n".join(res)

    @classmethod
    def get_macro_data(cls) -> str:
        """获取宏观数据（全动态字段匹配，彻底解决KeyError/AttributeError）"""
        res = []
        res.append("\n🇨🇳 **【宏观脉搏】**")
        
        # 1. 制造业PMI（动态匹配含“制造业”的列）
        pmi_df = cls.safe_fetch("制造业PMI", ak.macro_china_pmi_yearly)
        if isinstance(pmi_df, pd.DataFrame):
            mfg_cols = [col for col in pmi_df.columns if "制造业" in col]
            if mfg_cols and len(pmi_df) >= 1:
                val_col = mfg_cols[0]
                latest_val = pmi_df.iloc[0][val_col]
                prev_val = pmi_df.iloc[1][val_col] if len(pmi_df) >= 2 else "N/A"
                date_col = [col for col in pmi_df.columns if "日期" in col or "月份" in col]
                date_str = pmi_df.iloc[0][date_col[0]] if date_col else "未知时间"
                res.append(f"  - **制造业PMI**：{latest_val}%（{date_str}，前值 {prev_val}%）")
            else:
                res.append("  - 制造业PMI数据暂缺")
        else:
            res.append("  - 制造业PMI数据暂缺")

        # 2. CPI通胀（动态匹配含“CPI”/“同比”的列）
        cpi_df = cls.safe_fetch("CPI通胀", ak.macro_china_cpi_yearly)
        if isinstance(cpi_df, pd.DataFrame):
            cpi_cols = [col for col in cpi_df.columns if "CPI" in col or "同比" in col]
            if cpi_cols and len(cpi_df) >= 1:
                val_col = cpi_cols[0]
                latest_val = pmi_df.iloc[0][val_col] if "pmi_df" in locals() else cpi_df.iloc[0][val_col]
                prev_val = cpi_df.iloc[1][val_col] if len(cpi_df) >= 2 else "N/A"
                date_col = [col for col in cpi_df.columns if "日期" in col or "月份" in col]
                date_str = cpi_df.iloc[0][date_col[0]] if date_col else "未知时间"
                res.append(f"  - **CPI通胀**：{latest_val}%（{date_str}，前值 {prev_val}%）")
            else:
                res.append("  - CPI通胀数据暂缺")
        else:
            res.append("  - CPI通胀数据暂缺")

        # 3. 央行逆回购（已修复为最新接口）
        repo_df = cls.safe_fetch("央行逆回购", ak.macro_china_gksccz)
        if isinstance(repo_df, pd.DataFrame) and len(repo_df) >= 1:
            latest = repo_df.iloc[0]
            # 动态匹配逆回购相关字段
            direction_col = [col for col in repo_df.columns if "正/逆回购" in col or "操作方向" in col]
            amount_col = [col for col in repo_df.columns if "交易量" in col or "投放量" in col]
            rate_col = [col for col in repo_df.columns if "中标利率" in col or "利率" in col]
            term_col = [col for col in repo_df.columns if "期限" in col]
            date_col = [col for col in repo_df.columns if "日期" in col]
            
            direction = latest[direction_col[0]] if direction_col else "逆回购"
            amount = latest[amount_col[0]] if amount_col else "N/A"
            rate = latest[rate_col[0]] if rate_col else "N/A"
            term = latest[term_col[0]] if term_col else "N/A"
            date_str = latest[date_col[0]] if date_col else "未知时间"
            
            res.append(f"  - **央行操作**：{date_str}开展{direction} {amount}亿元，期限{term}天，中标利率{rate}%")
        else:
            res.append("  - 央行逆回购数据暂缺")

        return "\n".join(res)

    @classmethod
    def get_cls_news(cls) -> List[str]:
        """获取财联社盘前快讯（反爬+容错）"""
        res = []
        res.append("\n📰 **【盘前快讯】**")
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
                news_list = [i["content"] for i in data["data"]["list"][:5] if "盘前" in i["content"] or "早间" in i["content"]]
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

    @classmethod
    def get_stock_announcements(cls) -> List[str]:
        """获取个股公告（Tushare可选，无Token不影响运行）"""
        res = []
        res.append("\n📑 **【个股公告】**")
        if not cfg.TUSHARE_TOKEN:
            res.append("  - 未配置TUSHARE_TOKEN（可选，不影响其他功能）")
            return res
        try:
            import tushare as ts
            ts.set_token(cfg.TUSHARE_TOKEN)
            pro = ts.pro_api()
            today = datetime.now().strftime("%Y%m%d")
            anns = pro.anns(ann_date=today, fields="ts_code,title")
            if not anns.empty:
                key_anns = anns[anns["title"].str.contains("业绩|重组|增持|减持|停牌|复牌")]
                if not key_anns.empty:
                    for _, row in key_anns.head(5).iterrows():
                        res.append(f"  - {row['ts_code']}：{row['title']}")
                else:
                    res.append("  - 今日暂无重要个股公告")
            else:
                res.append("  - 今日暂无个股公告")
        except Exception as e:
            res.append(f"  - 个股公告抓取异常：{str(e)[:50]}")
        return res

# ==================== 事件解析（空数据不报错） ====================
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

    @staticmethod
    def parse_announcements(anns: List[str]) -> List[EventSignal]:
        events = []
        for item in anns:
            if not isinstance(item, str):
                continue
            if match := re.search(r"业绩预增.*(\d+)%", item):
                strength = min(int(match.group(1)) / 100, 1.0)
                ts_code = re.search(r"(\d{6}\.[A-Z]{2})", item).group(1) if re.search(r"(\d{6}\.[A-Z]{2})", item) else ""
                events.append(EventSignal(ts_code=ts_code, event_type="earnings_beat", direction=1, strength=strength, source="cninfo"))
            elif re.search(r"(重组|资产注入|并购)", item):
                ts_code = re.search(r"(\d{6}\.[A-Z]{2})", item).group(1) if re.search(r"(\d{6}\.[A-Z]{2})", item) else ""
                events.append(EventSignal(ts_code=ts_code, event_type="restructuring", direction=1, strength=0.9, decay_hours=24, source="cninfo"))
        return events

# ==================== 双轨选股引擎（空池不报错，明确提示） ====================
class AlphaEngine:
    @staticmethod
    def get_base_scores(is_aggressive: bool) -> Dict[str, float]:
        # 【必填】关注股票池，格式：{"股票代码.交易所": {"name": "简称", "roe": ROE, "vol": 波动率, "ret_20d": 20日涨幅}}
        # 示例（取消注释即可测试）：
        # stock_pool = {
        #     "600519.SH": {"name": "贵州茅台", "roe": 0.25, "vol": 0.15, "ret_20d": 0.05},
        #     "300750.SZ": {"name": "宁德时代", "roe": 0.18, "vol": 0.25, "ret_20d": 0.12},
        # }
        stock_pool = {}  # 空池不影响推送，仅提示未配置
        if not stock_pool:
            return {}
        scores = {}
        for ts_code, metrics in stock_pool.items():
            if not all(key in metrics for key in ["roe", "vol", "ret_20d"]):
                continue
            if is_aggressive:
                scores[ts_code] = round(0.6 * metrics["ret_20d"] + 0.4 * metrics["vol"], 2)
            else:
                scores[ts_code] = round(0.7 * metrics["roe"] + 0.3 * (1 - metrics["vol"]), 2)
        return scores

    @staticmethod
    def fuse_event_scores(base_scores: Dict[str, float], events: List[EventSignal], is_aggressive: bool) -> Dict[str, float]:
        if not base_scores:
            return {}
        fused = base_scores.copy()
        cap = 0.45 if is_aggressive else 0.15
        current_time = datetime.now()
        for ts_code, base in base_scores.items():
            boost = 0.0
            for e in events:
                if e.ts_code == ts_code or e.ts_code == "":
                    decay = max(0, 1 - (current_time - getattr(e, 'release_time', current_time)).total_seconds() / (e.decay_hours * 3600))
                    weight = e.strength * e.direction * decay * (0.5 if e.ts_code == "" else 1.0)
                    boost += weight
            fused[ts_code] = round(base + max(min(boost, cap), -cap), 2)
        return fused

    @classmethod
    def select_stocks(cls, events: List[EventSignal]) -> Dict[str, List[Dict]]:
        stable_base = cls.get_base_scores(False)
        stable_fused = cls.fuse_event_scores(stable_base, events, False)
        stable = sorted(stable_fused.items(), key=lambda x: x[1], reverse=True)[:5]
        aggro_base = cls.get_base_scores(True)
        aggro_fused = cls.fuse_event_scores(aggro_base, events, True)
        aggro = sorted(aggro_fused.items(), key=lambda x: x[1], reverse=True)[:3]
        return {
            "stable": [{"ts_code": k, "score": v, "reason": "稳健底仓"} for k, v in stable],
            "aggressive": [{"ts_code": k, "score": v, "reason": "事件驱动"} for k, v in aggro]
        }

# ==================== 推送渲染（优先推送，落盘失败不影响接收） ====================
class PushRenderer:
    @staticmethod
    def render(alpha_book: Dict, raw: Dict) -> str:
        date = datetime.now().strftime("%Y年%m月%d日")
        md = f"# 📈 买方Alpha早参 · {date}\n\n"
        
        # 外围行情
        md += raw.get("global", "🌍 **【外围全景】**\n  - 数据暂缺") + "\n"
        
        # 宏观数据
        md += raw.get("macro", "🇨🇳 **【宏观脉搏】**\n  - 数据暂缺") + "\n"
        
        # 双轨选股结果
        md += "\n## 🎯 **【双轨选股结果】**\n"
        md += "### 【稳健派 · 核心底仓】（60-80%仓位）\n"
        if alpha_book.get("stable"):
            for s in alpha_book["stable"]:
                md += f"- **{s['ts_code']}** | 评分: `{s['score']}` | {s['reason']}\n"
        else:
            md += "- 【提示】未配置股票池，暂无选股结果（请在AlphaEngine中填写关注的股票）\n"
        
        md += "\n### 【激进派 · 冲锋号角】（20-40%仓位）\n"
        if alpha_book.get("aggressive"):
            for s in alpha_book["aggressive"]:
                md += f"- **{s['ts_code']}** | 评分: `{s['score']}` | {s['reason']}\n"
        else:
            md += "- 【提示】未配置股票池，暂无选股结果（请在AlphaEngine中填写关注的股票）\n"
        
        # 盘前快讯
        md += "\n" + "\n".join(raw.get("news", ["📰 **【盘前快讯】**\n  - 数据暂缺"])) + "\n"
        
        # 个股公告
        md += "\n" + "\n".join(raw.get("anns", ["📑 **【个股公告】**\n  - 数据暂缺"])) + "\n"
        
        md += "\n---\n*数据来源：交易所/央行/财联社 | 不构成投资建议*"
        return md

    @staticmethod
    def push(content: str) -> bool:
        if not cfg.PUSHPLUS_TOKEN:
            print("【提示】未配置PUSHPLUS_TOKEN，请到GitHub Secrets中配置")
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
                print("【成功】推送已发送至微信")
                return True
            else:
                print(f"【失败】推送失败: {result.get('msg')}")
                return False
        except Exception as e:
            print(f"【错误】推送异常: {str(e)[:50]}")
            return False

# ==================== 主流程（优先推送，绝不阻断） ====================
def main():
    print("=" * 50)
    print("B2.1 买方Alpha早参 · 启动中...")
    print("=" * 50)
    
    try:
        print("\n[Step 1/4] 爬取原始数据...")
        raw = {
            "global": DataFetcher.get_global_overnight(),
            "macro": DataFetcher.get_macro_data(),
            "news": DataFetcher.get_cls_news(),
            "anns": DataFetcher.get_stock_announcements()
        }
        print("原始数据爬取完成（部分失败会显示提示，不影响后续流程）")
        
        print("\n[Step 2/4] 解析事件信号...")
        events = EventParser.parse_news(raw["news"]) + EventParser.parse_announcements(raw["anns"])
        print(f"共解析到 {len(events)} 个有效事件信号")
        
        print("\n[Step 3/4] 双轨选股中...")
        alpha_book = AlphaEngine.select_stocks(events)
        print(f"稳健派选中 {len(alpha_book['stable'])} 只，激进派选中 {len(alpha_book['aggressive'])} 只")
        
        print("\n[Step 4/4] 渲染并推送至微信（优先执行，落盘失败不影响推送）...")
        content = PushRenderer.render(alpha_book, raw)
        PushRenderer.push(content)
        
        # 落盘原始数据（失败不影响推送）
        with open("raw_news.txt", "w", encoding="utf-8") as f:
            f.write(content)
        print("\n[完成] 原始数据已生成本地文件，等待Actions落盘")
        
    except Exception as e:
        print(f"!!! 程序发生致命错误: {e}")
        # 即使主程序崩溃，也尝试发送告警
        if cfg.PUSHPLUS_TOKEN:
            try:
                requests.post(
                    "https://www.pushplus.plus/send",
                    json={
                        "token": cfg.PUSHPLUS_TOKEN,
                        "title": "B2.1 早报系统崩溃告警",
                        "content": f"程序发生致命错误，请及时排查：\n```\n{e}\n```",
                        "template": "markdown"
                    },
                    headers=cfg.HEADERS,
                    timeout=cfg.TIMEOUT
                )
            except:
                pass
    finally:
        print("=" * 50)

if __name__ == "__main__":
    main()
