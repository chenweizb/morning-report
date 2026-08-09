# -*- coding: utf-8 -*-
# B2.1 买方Alpha早参 · 容错增强版（无旧股票信息/无调试代码/优先推送）
import os
import re
import time
import random
import requests
from bs4 import BeautifulSoup  # 补全BeautifulSoup导入，解决之前的NameError
import akshare as ak
import pandas as pd
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict, Any

# ==================== 基础配置（提交前务必确认Token为环境变量读取！） ====================
@dataclass
class Config:
    # 【提交前必须保留】从GitHub Secrets读取Token，禁止明文写Token！
    PUSHPLUS_TOKEN: str = os.getenv("PUSHPLUS_TOKEN", "")
    TUSHARE_TOKEN: str = os.getenv("TUSHARE_TOKEN", "")
    
    HEADERS: dict = None
    TIMEOUT: int = 25  # 延长超时时间，适配国内访问海外数据源的延迟
    DELAY_RANGE: tuple = (2, 5)  # 增加随机延时，降低反爬拦截概率
    RETRY_TIMES: int = 2  # 接口失败重试次数

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

# ==================== 数据爬取（全接口容错+重试，单接口失败不影响全局） ====================
class DataFetcher:
    @staticmethod
    def safe_fetch(label: str, func, *args, **kwargs) -> Any:
        """通用容错+重试装饰器，失败返回友好提示，不崩程序"""
        for i in range(cfg.RETRY_TIMES + 1):
            try:
                time.sleep(random.uniform(*cfg.DELAY_RANGE))
                result = func(*args, **kwargs)
                if result is not None:
                    return result
            except Exception as e:
                if i == cfg.RETRY_TIMES:
                    return f"【获取失败】{label}: {str(e)[:50]}"
        return f"【获取失败】{label}: 重试{cfg.RETRY_TIMES}次后仍失败"

    @classmethod
    def get_global_overnight(cls) -> str:
        res = []
        # 美股行情（稳定接口，类型判断避免报错）
        us_df = cls.safe_fetch("美股行情", ak.stock_us_spot_em)
        if isinstance(us_df, pd.DataFrame) and not us_df.empty:
            us_key = us_df[us_df["名称"].isin(["道琼斯", "纳斯达克", "标普500"])]
            if not us_key.empty:
                res.append("【隔夜美股】\n" + us_key[["名称", "最新价", "涨跌幅"]].to_string(index=False))
        
        # A50期货（适配最新akshare，无废弃接口）
        global_df = cls.safe_fetch("外盘期货", ak.futures_global_em)
        if isinstance(global_df, pd.DataFrame) and not global_df.empty:
            a50_df = global_df[global_df["合约名称"].str.contains("A50|富时中国A50", na=False)]
            if not a50_df.empty:
                res.append(f"\n【A50期货】最新价: {a50_df.iloc[0]['最新价']}, 涨跌幅: {a50_df.iloc[0]['涨跌幅']}%")
        
        # 离岸人民币（稳定接口）
        cnh_df = cls.safe_fetch("离岸人民币", ak.currency_boc_safe_infer)
        if isinstance(cnh_df, pd.DataFrame) and not cnh_df.empty:
            cnh_row = cnh_df[cnh_df["货币名称"] == "美元"]
            if not cnh_row.empty:
                res.append(f"\n【离岸人民币】1美元兑CNH: {cnh_row['现汇买入价'].values[0]}")
        
        # 原油+黄金
        if isinstance(global_df, pd.DataFrame) and not global_df.empty:
            oil_df = global_df[global_df["合约名称"].str.contains("原油|WTI", na=False)]
            gold_df = global_df[global_df["合约名称"].str.contains("黄金|COMEX", na=False)]
            if not oil_df.empty:
                res.append(f"\n【大宗商品】美油: {oil_df.iloc[0]['最新价']}美元/桶")
            if not gold_df.empty:
                res.append(f"黄金: {gold_df.iloc[0]['最新价']}美元/盎司")
        return "\n".join(res) if res else "【外围行情】暂无数据（网络超时）"

    @classmethod
    def get_macro_data(cls) -> str:
        res = []
        # 制造业PMI
        pmi_df = cls.safe_fetch("制造业PMI", ak.macro_china_pmi_yearly)
        if isinstance(pmi_df, pd.DataFrame) and not pmi_df.empty and len(pmi_df) >= 2:
            res.append(f"【制造业PMI】最新值: {pmi_df['value'].iloc[-1]}%, 前值: {pmi_df['value'].iloc[-2]}%")
        
        # CPI通胀
        cpi_df = cls.safe_fetch("CPI通胀", ak.macro_china_cpi_yearly)
        if isinstance(cpi_df, pd.DataFrame) and not cpi_df.empty and len(cpi_df) >= 2:
            res.append(f"【CPI通胀】最新值: {cpi_df['value'].iloc[-1]}%, 前值: {cpi_df['value'].iloc[-2]}%")
        
        # 央行逆回购
        repo_df = cls.safe_fetch("央行逆回购", ak.pboc_open_market_operation_em)
        if isinstance(repo_df, pd.DataFrame) and not repo_df.empty:
            res.append(f"\n【央行逆回购】{repo_df.iloc[0]['日期']}操作{repo_df.iloc[0]['交易量']}亿元，中标利率{repo_df.iloc[0]['中标利率']}%")
        return "\n".join(res) if res else "【宏观数据】暂无数据（网络超时）"

    @classmethod
    def get_cls_news(cls) -> List[str]:
        try:
            resp = cls.safe_fetch(
                "财联社快讯",
                lambda: requests.get(
                    "https://www.cls.cn/nodeapi/updateTelegraphList?app=1&last_time=0",
                    headers=cfg.HEADERS,
                    timeout=cfg.TIMEOUT
                )
            )
            if isinstance(resp, str):  # 如果是错误提示字符串，直接返回
                return [resp]
            data = resp.json()
            news_list = [i["content"] for i in data["data"]["list"][:5] if "盘前" in i["content"] or "早间" in i["content"]]
            return news_list if news_list else ["【财联社快讯】今日暂无盘前快讯"]
        except Exception as e:
            return [f"【获取失败】财联社快讯: {str(e)[:50]}"]

    @classmethod
    def get_stock_announcements(cls) -> List[str]:
        if not cfg.TUSHARE_TOKEN:
            return ["【个股公告】未配置TUSHARE_TOKEN（可选，不影响运行）"]
        try:
            import tushare as ts
            ts.set_token(cfg.TUSHARE_TOKEN)
            pro = ts.pro_api()
            today = datetime.now().strftime("%Y%m%d")
            anns = pro.anns(ann_date=today, fields="ts_code,title")
            key_anns = anns[anns["title"].str.contains("业绩|重组|增持|减持|停牌|复牌")]
            return [f"- {row['ts_code']} {row['title']}" for _, row in key_anns.head(5).iterrows()] if not key_anns.empty else ["【个股公告】今日暂无重要公告"]
        except Exception as e:
            return [f"【获取失败】个股公告: {str(e)[:50]}"]

# ==================== 事件解析（无旧规则残留，空数据不报错） ====================
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

# ==================== 双轨选股引擎（无旧股票信息，空池不报错） ====================
class AlphaEngine:
    @staticmethod
    def get_base_scores(is_aggressive: bool) -> Dict[str, float]:
        # 【必须自己填】关注的股票池，格式：{"股票代码.交易所": {"name": "简称", "roe": ROE, "vol": 波动率, "ret_20d": 20日涨幅}}
        stock_pool = {}  # 【必须自己填，否则选股结果为空，不影响程序运行】
        
        if not stock_pool:
            return {}
        
        scores = {}
        for ts_code, metrics in stock_pool.items():
            if not all(key in metrics for key in ["roe", "vol", "ret_20d"]):
                continue
            if is_aggressive:
                # 激进派：侧重动量（20日涨幅）+ 波动率
                scores[ts_code] = round(0.6 * metrics["ret_20d"] + 0.4 * metrics["vol"], 2)
            else:
                # 稳健派：侧重ROE + 低波动
                scores[ts_code] = round(0.7 * metrics["roe"] + 0.3 * (1 - metrics["vol"]), 2)
        return scores

    @staticmethod
    def fuse_event_scores(base_scores: Dict[str, float], events: List[EventSignal], is_aggressive: bool) -> Dict[str, float]:
        if not base_scores:
            return {}
        fused = base_scores.copy()
        cap = 0.45 if is_aggressive else 0.15  # 事件权重上限，避免过度拟合
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

# ==================== 推送渲染（优先执行推送，落盘失败不影响推送） ====================
class PushRenderer:
    @staticmethod
    def render(alpha_book: Dict, raw: Dict) -> str:
        date = datetime.now().strftime("%Y年%m月%d日")
        md = f"# 📈 买方Alpha早参 · {date}\n\n## 【外围全景】\n{raw.get('global', '暂无数据')}\n\n## 【宏观脉搏】\n{raw.get('macro', '暂无数据')}\n\n"
        
        # 稳健派
        md += "## 【稳健派 · 核心底仓】（60-80%仓位）\n"
        if alpha_book.get("stable"):
            for s in alpha_book["stable"]:
                md += f"- **{s['ts_code']}** | 评分: `{s['score']}` | {s['reason']}\n"
        else:
            md += "- 【提示】未配置股票池，暂无选股结果（请在AlphaEngine中填写关注的股票）\n"
        
        # 激进派
        md += "\n## 【激进派 · 冲锋号角】（20-40%仓位）\n"
        if alpha_book.get("aggressive"):
            for s in alpha_book["aggressive"]:
                md += f"- **{s['ts_code']}** | 评分: `{s['score']}` | {s['reason']}\n"
        else:
            md += "- 【提示】未配置股票池，暂无选股结果（请在AlphaEngine中填写关注的股票）\n"
        
        # 盘前快讯
        md += "\n---\n### 【盘前快讯】\n"
        for news in raw.get("news", []):
            md += f"- {news}\n"
        
        md += "\n---\n*数据来源：交易所/央行/财联社 | 不构成投资建议*"
        return md

    @staticmethod
    def push(content: str) -> bool:
        if not cfg.PUSHPLUS_TOKEN:
            print("【提示】未配置PUSHPLUS_TOKEN，跳过推送（本地测试可临时填Token，提交前务必改回环境变量读取）")
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

# ==================== 主流程（优先推送，落盘交给Actions，避免阻断推送） ====================
def main():
    print("=" * 50)
    print("B2.1 买方Alpha早参 · 启动中...")
    print("=" * 50)
    
    # 1. 爬取原始数据（容错，单模块失败不影响整体）
    print("\n[Step 1/4] 爬取原始数据...")
    raw = {
        "global": DataFetcher.get_global_overnight(),
        "macro": DataFetcher.get_macro_data(),
        "news": DataFetcher.get_cls_news(),
        "anns": DataFetcher.get_stock_announcements()
    }
    print("原始数据爬取完成（部分失败会显示提示，不影响后续流程）")
    
    # 2. 解析事件信号（空数据不报错）
    print("\n[Step 2/4] 解析事件信号...")
    events = EventParser.parse_news(raw["news"]) + EventParser.parse_announcements(raw["anns"])
    print(f"共解析到 {len(events)} 个有效事件信号")
    
    # 3. 双轨选股（空池不报错）
    print("\n[Step 3/4] 双轨选股中...")
    alpha_book = AlphaEngine.select_stocks(events)
    print(f"稳健派选中 {len(alpha_book['stable'])} 只，激进派选中 {len(alpha_book['aggressive'])} 只")
    
    # 4. 【优先执行】渲染并推送至微信（即使后续落盘失败，也能收到推送）
    print("\n[Step 4/4] 渲染并推送至微信...")
    content = PushRenderer.render(alpha_book, raw)
    PushRenderer.push(content)
    
    # 5. 生成本地文件（交给GitHub Actions落盘，代码内不执行Git提交，避免冲突）
    with open("raw_news.txt", "w", encoding="utf-8") as f:
        f.write(content)
    print("\n[完成] 原始数据已生成本地文件，等待Actions落盘")
    print("=" * 50)

if __name__ == "__main__":
    main()
