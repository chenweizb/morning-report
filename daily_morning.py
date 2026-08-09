# -*- coding: utf-8 -*-
# B2.1 买方Alpha早参 · 生产级稳定版（2024.10更新/无乱告警/推送必达）
import os
import re
import time
import random
import requests
from datetime import datetime, timedelta
import akshare as ak
import pandas as pd
from typing import List, Dict, Any

# ==================== 基础配置（自动读取GitHub Secrets，无需改代码） ====================
class Config:
    # 微信推送配置（必填，从GitHub Secrets读取）
    PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "")
    # 可选：Tushare配置（无Token不影响核心推送）
    TUSHARE_TOKEN = os.environ.get("TUSHARE_TOKEN", "")
    
    # 请求头（反爬必备）
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Referer": "https://www.cls.cn/"
    }
    
    # 超时/重试配置
    TIMEOUT = 30
    RETRY_TIMES = 3  # 单接口最多重试3次
    DELAY_RANGE = (1, 3)  # 反爬随机延迟（秒）

cfg = Config()

# ==================== 工具类：安全数据抓取（单接口失败不影响全局） ====================
class SafeFetcher:
    """所有第三方接口调用都包一层容错，单个接口失败仅返回「暂无数据」，不触发程序崩溃"""
    @staticmethod
    def fetch(label: str, func, *args, default_return="暂无数据", **kwargs) -> Any:
        for attempt in range(cfg.RETRY_TIMES + 1):
            try:
                time.sleep(random.uniform(*cfg.DELAY_RANGE))  # 随机延迟防封
                result = func(*args, **kwargs)
                # 校验返回结果是否有效
                if result is None:
                    raise ValueError("返回结果为空")
                if isinstance(result, pd.DataFrame) and result.empty:
                    raise ValueError("返回DataFrame为空")
                print(f"✅ [{label}] 抓取成功")
                return result
            except Exception as e:
                if attempt == cfg.RETRY_TIMES:
                    print(f"⚠️ [{label}] 抓取失败（已重试{cfg.RETRY_TIMES}次）：{str(e)[:50]}")
                    return default_return
                time.sleep(1)  # 重试前等待1秒

# ==================== 数据抓取层（全接口适配2024.10最新AkShare版本） ====================
class DataFetcher:
    """所有数据抓取逻辑，单个接口失败不影响其他模块"""
    
    @classmethod
    def get_global_overnight(cls) -> str:
        """获取外围行情（A50/原油/黄金/美股/汇率）"""
        res = ["🌍 **【外围全景】**"]
        
        # 1. 外盘期货（最新稳定接口：futures_global_spot_em）
        global_df = SafeFetcher.fetch("外盘期货", ak.futures_global_spot_em)
        if isinstance(global_df, pd.DataFrame):
            # 动态适配列名（不同AkShare版本列名可能有差异）
            col_map = {}
            for col in global_df.columns:
                col_lower = col.lower()
                if any(k in col_lower for k in ["symbol", "代码"]):
                    col_map[col] = "代码"
                elif any(k in col_lower for k in ["name", "名称"]):
                    col_map[col] = "名称"
                elif any(k in col_lower for k in ["price", "最新价", "last"]):
                    col_map[col] = "最新价"
                elif any(k in col_lower for k in ["pct", "涨跌幅", "chg"]):
                    col_map[col] = "涨跌幅"
            if col_map:
                global_df = global_df.rename(columns=col_map)
            
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

        # 2. 美股行情（最新稳定接口：stock_us_spot_em）
        us_df = SafeFetcher.fetch("美股行情", ak.stock_us_spot_em)
        if isinstance(us_df, pd.DataFrame) and "名称" in us_df.columns:
            us_idx = us_df[us_df["名称"].isin(["道琼斯", "纳斯达克", "标普500"])]
            if not us_idx.empty:
                res.append("  - **隔夜美股**：")
                for _, row in us_idx.iterrows():
                    res.append(f"    - {row['名称']}：{row['最新价']}（涨跌幅：{row['涨跌幅']}%）")
        else:
            res.append("  - 美股数据暂缺")

        # 3. 离岸人民币（最新稳定接口：currency_boc_safe）
        cnh_df = SafeFetcher.fetch("离岸人民币", ak.currency_boc_safe)
        if isinstance(cnh_df, pd.DataFrame):
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
        """获取宏观数据（修复逆回购接口失效问题）"""
        res = ["\n🇨🇳 **【宏观脉搏】**"]
        
        # 1. 制造业PMI
        pmi_df = SafeFetcher.fetch("制造业PMI", ak.macro_china_pmi_yearly)
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
        cpi_df = SafeFetcher.fetch("CPI通胀", ak.macro_china_cpi_yearly)
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

        # 3. 央行逆回购（🔧 核心修复：旧接口macro_china_gksccz已失效，替换为官方维护的macro_china_hb）
        repo_df = SafeFetcher.fetch("央行逆回购", ak.macro_china_hb, symbol="weekly")  # weekly=周度数据，可改为daily取日度
        if isinstance(repo_df, pd.DataFrame) and not repo_df.empty:
            latest = repo_df.iloc[-1]  # 取最新一条数据
            # 动态匹配列名（不同版本列名可能有差异）
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
            resp = SafeFetcher.fetch(
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

# ==================== 推送层（明确日志，方便排查） ====================
class PushService:
    @staticmethod
    def push(content: str) -> bool:
        """发送微信推送，返回是否成功"""
        # 1. 校验Token是否存在
        if not cfg.PUSHPLUS_TOKEN:
            print("❌ 推送失败：未配置PUSHPLUS_TOKEN，请检查GitHub Secrets")
            return False
        
        # 2. 打印Token状态（掩码，不泄露隐私）
        mask = cfg.PUSHPLUS_TOKEN[:4] + "****" + cfg.PUSHPLUS_TOKEN[-4:] if len(cfg.PUSHPLUS_TOKEN) > 8 else "****"
        print(f"🔍 正在使用PushPlus Token：{mask}")
        
        # 3. 发送请求
        try:
            resp = requests.post(
                "https://www.pushplus.plus/send",
                json={
                    "token": cfg.PUSHPLUS_TOKEN,
                    "title": f"买方Alpha早参 · {datetime.now().strftime('%Y-%m-%d')}",
                    "content": content,
                    "template": "markdown",
                    "channel": "wechat"  # 强制推送到微信公众号
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

# ==================== 主流程（优先推送，仅致命错误发告警） ====================
def main():
    print("=" * 50)
    print(f"🚀 B2.1 买方Alpha早参启动：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    # 1. 抓取所有数据（单接口失败不影响其他部分）
    print("\n[Step 1/3] 抓取市场数据...")
    global_data = DataFetcher.get_global_overnight()
    macro_data = DataFetcher.get_macro_data()
    news_data = DataFetcher.get_cls_news()
    
    # 2. 组装推送内容
    print("\n[Step 2/3] 组装推送内容...")
    content = f"# 📈 买方Alpha早参 · {datetime.now().strftime('%Y年%m月%d日')}\n\n"
    content += global_data + "\n"
    content += macro_data + "\n"
    content += "\n".join(news_data) + "\n"
    content += "\n---\n*数据来源：交易所/央行/财联社 | 不构成投资建议*"
    
    # 3. 发送推送
    print("\n[Step 3/3] 发送微信推送...")
    push_success = PushService.push(content)
    
    # 4. 落盘原始数据（失败不影响推送）
    try:
        with open("raw_news.txt", "w", encoding="utf-8") as f:
            f.write(content)
        print("\n✅ 原始数据已落盘：raw_news.txt")
    except Exception as e:
        print(f"\n⚠️ 落盘失败（不影响推送）：{str(e)[:50]}")
    
    # 5. 仅当推送失败时发告警（不再乱发崩溃告警）
    if not push_success and cfg.PUSHPLUS_TOKEN:
        PushService.push(
            f"# ⚠️ B2.1 早报推送失败告警\n\n"
            f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"原因：微信推送接口调用失败，请检查Token配置或PushPlus服务状态\n"
            f"原始内容预览：\n```\n{content[:500]}...\n```"
        )
    
    print("\n" + "=" * 50)
    print("✨ 本次运行结束")
    print("=" * 50)

if __name__ == "__main__":
    main()
