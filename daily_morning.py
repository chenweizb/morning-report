#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘前早报完整整改版：
1. 替换废弃的akshare接口，适配最新版本
2. 所有数据源加防崩溃机制，单源失败不影响整体推送
3. 海外服务器反爬优化，随机延时+超时控制
4. 全周7:45北京时间推送，自动降级处理不稳定源
5. 必须print完整内容，供PushPlus捕获
"""

import os
import time
import random
import requests
import akshare as ak
import tushare as ts
from datetime import datetime, timedelta

# ====================== 基础配置（从GitHub Secrets读取，禁止硬编码） ======================
PUSHPLUS_TOKEN = os.getenv("PUSHPLUS_TOKEN")
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN")

# 请求头（模拟浏览器，降低反爬概率）
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.cls.cn/"
}
# 超时设置（海外服务器访问国内源容易超时）
TIMEOUT = 15
# 随机延时范围（降低被反爬的概率）
DELAY_RANGE = (1, 3)

# ====================== 通用防崩溃抓取装饰器 ======================
def safe_fetch(label: str):
    """装饰器：包裹所有数据源抓取逻辑，失败返回友好提示，不中断程序"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                # 随机延时，避免短时间高频请求被封
                time.sleep(random.uniform(*DELAY_RANGE))
                result = func(*args, **kwargs)
                # 过滤空结果
                if result is None or (isinstance(result, str) and len(result.strip()) == 0):
                    return f"【{label}】暂无数据"
                if isinstance(result, pd.DataFrame) and result.empty:
                    return f"【{label}】暂无数据"
                return result
            except Exception as e:
                # 捕获所有异常，返回精简错误信息（避免满屏报错）
                return f"【{label}】获取失败：{str(e)[:50]}"
        return wrapper
    return decorator

# 导入pandas（akshare返回的多是DataFrame，需提前导入）
import pandas as pd

# ====================== 1. 隔夜全球市场（替换废弃接口，适配最新akshare） ======================
@safe_fetch("隔夜全球市场")
def get_global_overnight():
    """美股、A50、离岸人民币、油金（替换废弃的futures_foreign_contract_em接口）"""
    res = []
    
    # 1. 美股三大指数（akshare稳定接口）
    us_df = ak.stock_us_spot_em()
    us_key = us_df[us_df["名称"].isin(["道琼斯", "纳斯达克", "标普500"])]
    res.append("【隔夜美股】")
    res.append(us_key[["名称", "最新价", "涨跌幅"]].to_string(index=False))
    
    # 2. A50期货（替换废弃接口：用futures_global_em筛选A50合约）
    global_df = ak.futures_global_em()  # 最新外盘期货接口
    a50_df = global_df[global_df["合约名称"].str.contains("A50|富时中国A50", na=False)]
    if not a50_df.empty:
        latest_a50 = a50_df.iloc[0]
        res.append(f"\n【A50期货】最新价: {latest_a50['最新价']}, 涨跌幅: {latest_a50['涨跌幅']}%")
    
    # 3. 离岸人民币（akshare稳定接口）
    cnh_df = ak.currency_boc_safe_infer()
    cnh_val = cnh_df[cnh_df["货币名称"] == "美元"]["现汇买入价"].values[0]
    res.append(f"\n【离岸人民币】1美元兑CNH: {cnh_val}")
    
    # 4. 原油+黄金（从外盘期货接口筛选）
    oil_df = global_df[global_df["合约名称"].str.contains("原油|WTI", na=False)]
    gold_df = global_df[global_df["合约名称"].str.contains("黄金|COMEX", na=False)]
    if not oil_df.empty:
        latest_oil = oil_df.iloc[0]
        res.append(f"\n【大宗商品】美油: {latest_oil['最新价']}美元/桶")
    if not gold_df.empty:
        latest_gold = gold_df.iloc[0]
        res.append(f"黄金: {latest_gold['最新价']}美元/盎司")
    
    return "\n".join(res)

# ====================== 2. 宏观数据（akshare稳定接口，无变动） ======================
@safe_fetch("宏观数据")
def get_macro_data():
    """PMI、CPI、央行逆回购（官方数据，接口稳定）"""
    res = []
    
    # 制造业PMI
    pmi_df = ak.macro_china_pmi_yearly()
    res.append(f"【制造业PMI】最新值: {pmi_df['value'].iloc[-1]}%，前值: {pmi_df['value'].iloc[-2]}%")
    
    # CPI通胀
    cpi_df = ak.macro_china_cpi_yearly()
    res.append(f"【CPI通胀】最新值: {cpi_df['value'].iloc[-1]}%，前值: {cpi_df['value'].iloc[-2]}%")
    
    # 央行逆回购
    repo_df = ak.pboc_open_market_operation_em()
    latest_repo = repo_df.iloc[0]
    res.append(f"\n【央行逆回购】{latest_repo['日期']}操作{latest_repo['交易量']}亿元，中标利率{latest_repo['中标利率']}%")
    
    return "\n".join(res)

# ====================== 3. A股核心行情（akshare稳定接口，无变动） ======================
@safe_fetch("A股核心行情")
def get_a_share_core():
    """涨停池、龙虎榜（交易所官方数据，稳定）"""
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    res = []
    
    # 昨日涨停池
    zt_df = ak.stock_zt_pool_em(date=yesterday)
    res.append(f"【昨日涨停】共{len(zt_df)}只，连板高度: {zt_df['连板数'].max()}板")
    res.append(zt_df.head(10)[["代码", "名称", "连板数", "涨跌幅"]].to_string(index=False))
    
    # 龙虎榜（机构净买入前3）
    lhb_df = ak.stock_lhb_detail_em(start_date=yesterday, end_date=yesterday)
    buy_df = lhb_df[lhb_df["机构净买入额"] > 0].head(3)
    if not buy_df.empty:
        res.append(f"\n【昨日龙虎榜】机构净买入前3:")
        res.append(buy_df[["代码", "名称", "机构净买入额"]].to_string(index=False))
    
    return "\n".join(res)

# ====================== 4. 快讯/政策（易失败源，降级处理） ======================
@safe_fetch("财联社快讯")
def get_cls_news():
    """财联社盘前快讯（海外服务器易失败，降级处理）"""
    url = "https://www.cls.cn/nodeapi/updateTelegraphList?app=1&last_time=0"
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    data = resp.json()
    # 筛选盘前/早间相关快讯
    news_list = [i["content"] for i in data["data"]["list"][:5] if "盘前" in i["content"] or "早间" in i["content"]]
    return "【财联社盘前快讯】\n" + "\n".join([f"- {news}" for news in news_list])

@safe_fetch("美联储利率预期")
def get_cme_probability():
    """CME FedWatch（海外源，稳定）"""
    url = "https://cdn.cmegroup.com/www/files/fedwatch/fedfundsprobabilities.json"
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    data = resp.json()
    latest = data["probabilities"][0]
    return f"【美联储利率预期】{latest['label']}加息概率: {latest['prob']}%，降息概率: {latest['cutProb']}%"

# ====================== 5. 政策监管（可选源，失败则跳过） ======================
@safe_fetch("新华社要闻")
def get_xinhua_news():
    """新华社权威要闻（RSS源，海外服务器可能不稳定）"""
    url = "http://www.xinhuanet.com/politics/rss.xml"
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    soup = BeautifulSoup(resp.content, "xml")
    items = soup.find_all("item")[:3]
    news_list = [item.title.text.strip() for item in items]
    return "【新华社权威要闻】\n" + "\n".join([f"- {news}" for news in news_list])

# ====================== 6. 个股公告（依赖Tushare，无Token则提示） ======================
@safe_fetch("个股公告")
def get_stock_announcements():
    """个股公告（依赖Tushare Token，未配置则降级提示）"""
    if not TUSHARE_TOKEN:
        return "【个股公告】未配置TUSHARE_TOKEN，请在GitHub Secrets中添加"
    
    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()
    today = datetime.now().strftime("%Y%m%d")
    # 筛选业绩、重组、增减持等重要公告
    anns = pro.anns(ann_date=today, fields="ts_code,title")
    key_anns = anns[anns["title"].str.contains("业绩|重组|增持|减持|停牌|复牌")]
    if len(key_anns) == 0:
        return "【个股公告】今日暂无重要公告"
    
    news_list = [f"- {row['ts_code']} {row['title']}" for _, row in key_anns.head(5).iterrows()]
    return "【重要个股公告】\n" + "\n".join(news_list)

# ====================== 组装完整早报 ======================
def build_full_morning_report():
    today_str = datetime.now().strftime("%Y年%m月%d日")
    report_parts = [
        f"# 📈 盘前早报（{today_str} 北京时间7:45）",
        "---\n",
        get_global_overnight(),
        "\n---\n",
        get_macro_data(),
        "\n---\n",
        get_a_share_core(),
        "\n---\n",
        get_cls_news(),
        "\n",
        get_cme_probability(),
        "\n---\n",
        get_xinhua_news(),
        "\n---\n",
        get_stock_announcements(),
        "\n---\n",
        "⚠️ 本报告仅供参考，不构成投资建议。数据来源：交易所/央行/统计局/akshare。"
    ]
    
    # 过滤空内容和失败提示，避免推送冗余信息
    valid_parts = []
    for part in report_parts:
        if part and len(part.strip()) > 0:
            # 保留【获取失败】的提示，方便排查问题，但不保留空行
            valid_parts.append(part)
    
    return "\n".join(valid_parts)

# ====================== 主函数：必须print完整内容，供GitHub Actions捕获 ======================
if __name__ == "__main__":
    try:
        full_report = build_full_morning_report()
        # 关键：必须print完整内容，否则PushPlus会收到空白消息
        print(full_report)
    except Exception as e:
        # 顶层异常捕获，确保即使程序崩溃也能输出错误信息，避免空白推送
        print(f"# ❌ 早报生成失败\n错误信息：{str(e)[:200]}")
