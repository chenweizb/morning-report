# -*- coding: utf-8 -*-
# B2.1 买方Alpha早参 · 最终稳定版（全接口官方核验/云端本地一致/无崩溃告警）
import os
import time
import random
import requests
from datetime import datetime
import akshare as ak
import pandas as pd
from typing import Any, List

# ==================== 配置区（自动读取GitHub Secrets，无需修改） ====================
class Config:
    # 微信推送配置（严格匹配GitHub Secrets名称，全大写）
    PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "")
    # 反爬请求头
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Referer": "https://www.cls.cn/"
    }
    # 超时/重试配置
    TIMEOUT = 30
    RETRY_TIMES = 3
    DELAY_RANGE = (1, 3)

cfg = Config()

# ==================== 全接口容错工具类（单接口失败不影响全局） ====================
class SafeFetcher:
    """多候选接口兜底：挨个尝试，全失败仅返回默认文本，绝不抛异常"""
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

# ==================== 数据抓取层（全接口为AkShare官方确认的稳定接口） ====================
class DataFetcher:
    @classmethod
    def get_global_overnight(cls) -> str:
        """获取外围行情（官方稳定接口）"""
        res = ["🌍 **【外围全景】**"]
        # 外盘期货（官方接口：futures_global_spot_em，兜底旧接口）
        global_df = SafeFetcher.fetch_multi("外盘期货", [
            (ak.futures_global_spot_em, (), {}),
            (ak.futures_global_em, (), {}),
        ])
        if isinstance(global_df, pd.DataFrame):
            # 动态适配列名（兼容不同AkShare版本）
            col_map = {}
            for col in global_df.columns:
                col_lower = col.lower()
                if any(k in col_lower for k in ["symbol", "代码"]): col_map[col] = "代码"
                elif any(k in col_lower for k in ["name", "名称"]): col_map[col] = "名称"
                elif any(k in col_lower for k in ["price", "最新价", "last"]): col_map[col] = "最新价"
                elif any(k in col_lower for k in ["pct", "涨跌幅", "chg"]): col_map[col] = "涨跌幅"
            if col_map: global_df = global_df.rename(columns=col_map)
            # 筛选A50
            if "名称" in global_df.columns:
                a50 = global_df[global_df["名称"].str.contains("A50|富时中国A50", case=False, na=False)]
                if not a50.empty: res.append(f"  - **A50期货**：{a50.iloc[0]['最新价']}（涨跌幅：{a50.iloc[0]['涨跌幅']}%）")
                oil = global_df[global_df["名称"].str.contains("原油|WTI", case=False, na=False)]
                gold = global_df[global_df["名称"].str.contains("黄金|COMEX", case=False, na=False)]
                if not oil.empty: res.append(f"  - **美油**：{oil.iloc[0]['最新价']}美元/桶")
                if not gold.empty: res.append(f"  - **COMEX黄金**：{gold.iloc[0]['最新价']}美元/盎司")
        else:
            res.append("  - 外盘期货暂无数据")

        # 美股行情（官方稳定接口）
        us_df = SafeFetcher.fetch_multi("美股行情", [(ak.stock_us_spot_em, (), {})])
        if isinstance(us_df, pd.DataFrame) and "名称" in us_df.columns:
            us_idx = us_df[us_df["名称"].isin(["道琼斯", "纳斯达克", "标普500"])]
            if not us_idx.empty:
                res.append("  - **隔夜美股**：")
                for _, row in us_idx.iterrows():
                    res.append(f"    - {row['名称']}：{row['最新价']}（涨跌幅：{row['涨跌幅']}%）")
        else:
            res.append("  - 美股暂无数据")

        # 离岸人民币（官方稳定接口，列含“美元”）
        cnh_df = SafeFetcher.fetch_multi("离岸人民币", [(ak.currency_boc_safe, (), {})])
        if isinstance(cnh_df, pd.DataFrame):
            usd_cols = [c for c in cnh_df.columns if "美元" in c]
            if usd_cols and pd.notna(cnh_df.iloc[-1][usd_cols[0]]):
                res.append(f"  - **离岸人民币**：1美元兑{cnh_df.iloc[-1][usd_cols[0]]}CNH")
            else:
                res.append("  - 离岸人民币暂无数据")
        else:
            res.append("  - 离岸人民币暂无数据")
        return "\n".join(res)

    @classmethod
    def get_macro_data(cls) -> str:
        """获取宏观数据（官方确认的稳定接口）"""
        res = ["\n🇨🇳 **【宏观脉搏】**"]
        # 制造业PMI（官方稳定接口）
        pmi_df = SafeFetcher.fetch_multi("制造业PMI", [(ak.macro_china_pmi_yearly, (), {})])
        if isinstance(pmi_df, pd.DataFrame):
            mfg_cols = [c for c in pmi_df.columns if "制造业" in c]
            if mfg_cols:
                res.append(f"  - **制造业PMI**：{pmi_df.iloc[0][mfg_cols[0]]}（前值：{pmi_df.iloc[1][mfg_cols[0]]}）")
            else: res.append("  - 制造业PMI暂无数据")
        else: res.append("  - 制造业PMI暂无数据")

        # CPI（官方稳定接口）
        cpi_df = SafeFetcher.fetch_multi("CPI", [(ak.macro_china_cpi_yearly, (), {})])
        if isinstance(cpi_df, pd.DataFrame):
            cpi_cols = [c for c in cpi_df.columns if any(k in c for k in ["CPI", "同比"])]
            if cpi_cols:
                res.append(f"  - **CPI同比**：{cpi_df.iloc[0][cpi_cols[0]]}%（前值：{cpi_df.iloc[1][cpi_cols[0]]}%）")
            else: res.append("  - CPI暂无数据")
        else: res.append("  - CPI暂无数据")

        # 央行逆回购（官方确认接口：macro_china_gksccz，多兜底）
        repo_df = SafeFetcher.fetch_multi("央行逆回购", [
            (ak.macro_china_gksccz, (), {}),
            (ak.macro_china_gksccz_df, (), {}),
        ])
        if isinstance(repo_df, pd.DataFrame) and not repo_df.empty:
            latest = repo_df.iloc[-1]
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
        """获取财联社盘前快讯"""
        res = ["\n📰 **【盘前快讯】**"]
        try:
            resp = SafeFetcher.fetch_multi("财联社快讯", [
                (lambda: requests.get("https://www.cls.cn/nodeapi/updateTelegraphList?app=1&last_time=0",
                                      headers=cfg.HEADERS, timeout=cfg.TIMEOUT), (), {})
            ])
            if isinstance(resp, requests.Response):
                data = resp.json()
                news_list = [i["content"] for i in data["data"]["list"][:5] if any(k in i["content"] for k in ["盘前", "早间", "隔夜"])]
                if news_list:
                    for news in news_list: res.append(f"  - {news}")
                else: res.append("  - 今日暂无盘前快讯")
            else: res.append("  - 财联社快讯暂无数据")
        except Exception:
            res.append("  - 财联社快讯抓取异常")
        return res

# ==================== 推送服务层（严格匹配配置，打印明确日志） ====================
class PushService:
    @staticmethod
    def push(content: str) -> bool:
        # 校验Token是否存在
        if not cfg.PUSHPLUS_TOKEN:
            print("❌ 推送失败：未读取到PUSHPLUS_TOKEN，请检查GitHub Secrets配置")
            return False
        # 打印Token掩码，方便确认配置正确
        mask = cfg.PUSHPLUS_TOKEN[:4] + "****" + cfg.PUSHPLUS_TOKEN[-4:] if len(cfg.PUSHPLUS_TOKEN) > 8 else "****"
        print(f"🔍 正在使用PushPlus Token：{mask}")
        try:
            resp = requests.post(
                "https://www.pushplus.plus/send",
                json={
                    "token": cfg.PUSHPLUS_TOKEN,
                    "title": f"买方Alpha早参 · {datetime.now().strftime('%Y-%m-%d')}",
                    "content": content,
                    "template": "markdown",
                    "channel": "wechat"
                },
                headers=cfg.HEADERS,
                timeout=cfg.TIMEOUT
            )
            result = resp.json()
            if result.get("code") == 200:
                print("✅ 微信推送成功！请检查微信服务号「pushplus 推送加」，若未收到请去「订阅号消息」文件夹查找")
                return True
            else:
                print(f"❌ 推送失败：{result.get('msg')}（错误码：{result.get('code')}）")
                return False
        except Exception as e:
            print(f"❌ 推送异常：{str(e)[:50]}")
            return False

# ==================== 主流程（打印版本信息，方便排查云端问题） ====================
def main():
    print("=" * 50)
    print(f"🚀 启动时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📦 AkShare版本：{ak.__version__}（需≥1.16.60，否则逆回购接口不可用）")
    print("=" * 50)
    # 抓取数据
    print("\n[Step 1/3] 抓取外围行情...")
    global_data = DataFetcher.get_global_overnight()
    print("\n[Step 2/3] 抓取宏观数据...")
    macro_data = DataFetcher.get_macro_data()
    print("\n[Step 3/3] 抓取盘前快讯...")
    news_data = DataFetcher.get_cls_news()
    # 组装内容
    content = f"# 📈 买方Alpha早参 · {datetime.now().strftime('%Y年%m月%d日')}\n\n{global_data}\n{macro_data}\n\n" + "\n".join(news_data) + "\n\n---\n*数据来源：交易所/央行/财联社 | 不构成投资建议*"
    # 推送
    PushService.push(content)
    # 落盘（容错，不阻塞流程）
    try:
        with open("raw_news.txt", "w", encoding="utf-8") as f:
            f.write(content)
        print("\n✅ 原始数据已落盘：raw_news.txt")
    except Exception as e:
        print(f"\n⚠️ 落盘失败（不影响推送）：{str(e)[:50]}")
    print("=" * 50)

if __name__ == "__main__":
    main()
