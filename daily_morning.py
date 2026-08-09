#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘前早报完整版：覆盖权威信源+全周7:45推送
适配GitHub Actions + PushPlus + akshare + tushare
"""

import os
import re
import time
import random
import requests
import akshare as ak
import tushare as ts
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# ====================== 基础配置（从GitHub Secrets读取，不要硬编码） ======================
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN")  # 需在GitHub Secrets中添加
PUSHPLUS_TOKEN = os.getenv("PUSHPLUS_TOKEN")  # 已配置可忽略

# 请求头（模拟浏览器，规避反爬）
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.cls.cn/"
}

# 重试装饰器（海外服务器爬国内站点易超时，最多重试3次）
def retry_request(func):
    def wrapper(*args, **kwargs):
        for i in range(3):
            try:
                time.sleep(random.uniform(1, 3))  # 随机延迟，避免被封
                return func(*args, **kwargs)
            except Exception as e:
                if i == 2:
                    return f"【获取失败】{func.__name__}: {str(e)[:100]}"
                continue
    return wrapper


# ====================== 1. 隔夜全球市场（权威：交易所/akshare） ======================
@retry_request
def get_global_overnight():
    """美股、A50、离岸人民币、油金（来源：akshare官方接口）"""
    res = []
    # 美股三大指数
    us_spot = ak.stock_us_spot_em()
    us_key = us_spot[us_spot["名称"].isin(["道琼斯", "纳斯达克", "标普500"])]
    res.append("【隔夜美股】")
    res.append(us_key[["名称", "最新价", "涨跌幅"]].to_string(index=False))
    
    # A50期货（富时中国A50，盘前核心指标）
    a50 = ak.futures_foreign_contract_em(symbol="A50")
    res.append(f"\n【A50期货】最新价: {a50['最新价'].iloc[-1]}, 涨跌幅: {a50['涨跌幅'].iloc[-1]}%")
    
    # 离岸人民币（CNH，影响外资流向）
    cnh = ak.currency_boc_safe_infer()
    res.append(f"\n【离岸人民币】1美元兑CNH: {cnh['现汇买入价'].iloc[cnh['货币名称']=='美元'].values[0]}")
    
    # 原油/黄金（大宗商品风向标）
    oil = ak.futures_main_sina(symbol="NYMEX_CRUDE")
    gold = ak.futures_main_sina(symbol="COMEX_GOLD")
    res.append(f"\n【大宗商品】美油: {oil['最新价'].iloc[-1]}美元/桶 | 黄金: {gold['最新价'].iloc[-1]}美元/盎司")
    
    return "\n".join(res)


# ====================== 2. 宏观与央行操作（权威：央行/统计局） ======================
@retry_request
def get_macro_data():
    """PMI、CPI、央行逆回购（来源：akshare官方接口）"""
    res = []
    # 制造业PMI（统计局官方数据）
    pmi = ak.macro_china_pmi_yearly()
    res.append(f"【宏观PMI】最新值: {pmi['value'].iloc[-1]}%，前值: {pmi['value'].iloc[-2]}%")
    
    # CPI（通胀数据）
    cpi = ak.macro_china_cpi_yearly()
    res.append(f"【CPI通胀】最新值: {cpi['value'].iloc[-1]}%，前值: {cpi['value'].iloc[-2]}%")
    
    # 央行逆回购（流动性指标）
    reverse_repo = ak.pboc_open_market_operation_em()
    latest_repo = reverse_repo.iloc[0]
    res.append(f"\n【央行逆回购】{latest_repo['日期']}操作{latest_repo['交易量']}亿元，中标利率{latest_repo['中标利率']}%")
    
    return "\n".join(res)


# ====================== 3. 财经日历与快讯（权威：财联社/金十/CME） ======================
@retry_request
def get_finance_calendar():
    """财联社快讯、金十日历、CME美联储利率预期（免费权威源）"""
    res = []
    # 财联社盘前快讯（7×24权威快讯）
    cls_url = "https://www.cls.cn/nodeapi/updateTelegraphList?app=1&last_time=0"
    cls_data = requests.get(cls_url, headers=HEADERS).json()
    cls_news = [i["content"] for i in cls_data["data"]["list"][:5] if "盘前" in i["content"] or "早间" in i["content"]]
    res.append("【财联社盘前快讯】")
    res.extend([f"- {news}" for news in cls_news])
    
    # CME FedWatch（美联储利率预期，全球资产定价锚）
    fed_url = "https://cdn.cmegroup.com/www/files/fedwatch/fedfundsprobabilities.json"
    fed_data = requests.get(fed_url, headers=HEADERS).json()
    latest_prob = fed_data["probabilities"][0]
    res.append(f"\n【美联储利率预期】{latest_prob['label']}加息概率: {latest_prob['prob']}%，降息概率: {latest_prob['cutProb']}%")
    
    return "\n".join(res)


# ====================== 4. 政策与监管（权威：新华社/证监会） ======================
@retry_request
def get_policy_regulation():
    """新华社权威新闻、证监会处罚公告（防雷必备）"""
    res = []
    # 新华社时政要闻RSS（官方权威，无广告）
    xinhua_rss = "http://www.xinhuanet.com/politics/rss.xml"
    rss_data = requests.get(xinhua_rss, headers=HEADERS).content
    soup = BeautifulSoup(rss_data, "xml")
    items = soup.find_all("item")[:3]
    res.append("【新华社权威要闻】")
    for item in items:
        title = item.title.text.strip()
        res.append(f"- {title}")
    
    # 证监会行政处罚公告（防雷核心，官方披露）
    csrc_url = "http://www.csrc.gov.cn/csrc/c101902/index.htm"
    csrc_html = requests.get(csrc_url, headers=HEADERS).text
    csrc_soup = BeautifulSoup(csrc_html, "html.parser")
    punish_list = csrc_soup.find_all("div", class_="zcfg_list")[:3]
    res.append("\n【证监会最新处罚】")
    for punish in punish_list:
        title = punish.find("a").text.strip()
        res.append(f"- {title}")
    
    return "\n".join(res)


# ====================== 5. A股核心行情（原有逻辑+akshare权威接口） ======================
@retry_request
def get_a_share_core():
    """涨停池、龙虎榜、竞价数据（来源：akshare官方接口）"""
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    res = []
    
    # 昨日涨停池
    zt_pool = ak.stock_zt_pool_em(date=yesterday)
    res.append(f"【昨日涨停】共{len(zt_pool)}只，连板高度: {zt_pool['连板数'].max()}板")
    res.append(zt_pool.head(10)[["代码", "名称", "连板数", "涨跌幅"]].to_string(index=False))
    
    # 龙虎榜（机构动向）
    lhb = ak.stock_lhb_detail_em(start_date=yesterday, end_date=yesterday)
    res.append(f"\n【昨日龙虎榜】机构净买入前3:")
    res.append(lhb[lhb["机构净买入额"] > 0].head(3)[["代码", "名称", "机构净买入额"]].to_string(index=False))
    
    return "\n".join(res)


# ====================== 6. 个股公告（权威：巨潮/tushare） ======================
@retry_request
def get_stock_announcements():
    """个股公告、业绩预告（来源：tushare官方接口）"""
    if not TUSHARE_TOKEN:
        return "【个股公告】未配置TUSHARE_TOKEN，请在GitHub Secrets中添加"
    
    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()
    today = datetime.now().strftime("%Y%m%d")
    
    # 最新个股公告（巨潮权威披露）
    anns = pro.anns(
        ann_date=today,
        src="cninfo",
        fields="ts_code,ann_date,title"
    )
    # 筛选重要公告（业绩、重组、增减持）
    key_anns = anns[anns["title"].str.contains("业绩|重组|增持|减持|停牌|复牌")]
    
    res = ["【重要个股公告】"]
    if len(key_anns) > 0:
        for _, row in key_anns.head(5).iterrows():
            res.append(f"- {row['ts_code']} {row['title']}")
    else:
        res.append("- 今日暂无重要个股公告")
    
    return "\n".join(res)


# ====================== 7. 组装完整早报 ======================
def build_full_morning_report():
    """将所有模块拼接成完整早报，格式适配PushPlus Markdown渲染"""
    today_str = datetime.now().strftime("%Y年%m月%d日")
    report_parts = [
        f"# 📈 盘前早报（{today_str} 北京时间7:45）",
        "---\n",
        get_global_overnight(),
        "\n---\n",
        get_macro_data(),
        "\n---\n",
        get_finance_calendar(),
        "\n---\n",
        get_policy_regulation(),
        "\n---\n",
        get_a_share_core(),
        "\n---\n",
        get_stock_announcements(),
        "\n---\n",
        "⚠️ 本报告仅供参考，不构成投资建议。数据来源：交易所/央行/统计局/财联社/CME。"
    ]
    
    # 过滤空内容，避免推送空白
    valid_parts = [part for part in report_parts if part and len(part.strip()) > 0]
    return "\n".join(valid_parts)


# ====================== 主函数：必须print输出，供GitHub Actions捕获 ======================
if __name__ == "__main__":
    try:
        full_report = build_full_morning_report()
        # 关键：必须print，GitHub Actions才能捕获内容推送到微信
        print(full_report)
    except Exception as e:
        # 即使报错也要输出，避免PushPlus收到空消息
        print(f"# ❌ 早报生成失败\n错误信息：{str(e)[:200]}")
