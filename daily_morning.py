#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘前早报完整版（整改后）：
1. 全周7:45推送，适配GitHub Actions海外服务器
2. 所有数据源加异常捕获，失败不崩溃，只返回提示
3. 优先使用稳定的akshare接口，降级处理易失败源
4. 最终必须print完整内容，供PushPlus捕获
"""

import os
import time
import random
import requests
import akshare as ak
import tushare as ts
from datetime import datetime

# ====================== 基础配置 ======================
# 从GitHub Secrets读取密钥（不要硬编码）
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN")
PUSHPLUS_TOKEN = os.getenv("PUSHPLUS_TOKEN")

# 请求头（模拟浏览器，降低反爬概率）
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# 超时设置（海外服务器访问国内站容易超时，设为10秒）
TIMEOUT = 10

# ====================== 通用防崩溃抓取函数 ======================
def safe_fetch(label: str, fetch_func, *args, **kwargs) -> str:
    """
    所有数据源的统一抓取入口：
    - 成功则返回抓取内容
    - 失败则返回友好提示，不中断程序
    """
    try:
        # 随机延时1-3秒，降低被反爬的概率
        time.sleep(random.uniform(1, 3))
        result = fetch_func(*args, **kwargs)
        # 如果结果为空，返回提示
        if not result or (isinstance(result, str) and len(result.strip()) == 0):
            return f"【{label}】暂无数据"
        return str(result)
    except Exception as e:
        # 捕获所有异常，返回精简错误信息（避免满屏报错）
        return f"【{label}】获取失败：{str(e)[:50]}"

# ====================== 1. 隔夜全球市场（稳定源：akshare） ======================
def get_global_overnight() -> str:
    """美股、A50、离岸人民币、油金（akshare接口稳定，优先保留）"""
    res = []
    # 美股三大指数
    us_data = safe_fetch("隔夜美股", ak.stock_us_spot_em)
    if "获取失败" not in us_data:
        us_df = ak.stock_us_spot_em()
        us_key = us_df[us_df["名称"].isin(["道琼斯", "纳斯达克", "标普500"])]
        res.append("【隔夜美股】")
        res.append(us_key[["名称", "最新价", "涨跌幅"]].to_string(index=False))
    
    # A50期货（盘前核心指标）
    a50_data = safe_fetch("A50期货", ak.futures_foreign_contract_em, symbol="A50")
    if "获取失败" not in a50_data:
        a50_df = ak.futures_foreign_contract_em(symbol="A50")
        res.append(f"\n【A50期货】最新价: {a50_df['最新价'].iloc[-1]}, 涨跌幅: {a50_df['涨跌幅'].iloc[-1]}%")
    
    # 离岸人民币
    cnh_data = safe_fetch("离岸人民币", ak.currency_boc_safe_infer)
    if "获取失败" not in cnh_data:
        cnh_df = ak.currency_boc_safe_infer()
        cnh_val = cnh_df[cnh_df["货币名称"] == "美元"]["现汇买入价"].values[0]
        res.append(f"\n【离岸人民币】1美元兑CNH: {cnh_val}")
    
    return "\n".join(res) if res else "【隔夜全球】暂无数据"

# ====================== 2. 宏观数据（稳定源：akshare） ======================
def get_macro_data() -> str:
    """PMI、CPI、央行逆回购（官方数据，接口稳定）"""
    res = []
    # 制造业PMI
    pmi_data = safe_fetch("制造业PMI", ak.macro_china_pmi_yearly)
    if "获取失败" not in pmi_data:
        pmi_df = ak.macro_china_pmi_yearly()
        res.append(f"【宏观PMI】最新值: {pmi_df['value'].iloc[-1]}%，前值: {pmi_df['value'].iloc[-2]}%")
    
    # CPI
    cpi_data = safe_fetch("CPI通胀", ak.macro_china_cpi_yearly)
    if "获取失败" not in cpi_data:
        cpi_df = ak.macro_china_cpi_yearly()
        res.append(f"【CPI通胀】最新值: {cpi_df['value'].iloc[-1]}%，前值: {cpi_df['value'].iloc[-2]}%")
    
    # 央行逆回购
    repo_data = safe_fetch("央行逆回购", ak.pboc_open_market_operation_em)
    if "获取失败" not in repo_data:
        repo_df = ak.pboc_open_market_operation_em()
        latest = repo_df.iloc[0]
        res.append(f"\n【央行逆回购】{latest['日期']}操作{latest['交易量']}亿元，中标利率{latest['中标利率']}%")
    
    return "\n".join(res) if res else "【宏观数据】暂无数据"

# ====================== 3. A股核心行情（稳定源：akshare） ======================
def get_a_share_core() -> str:
    """涨停池、龙虎榜（交易所官方数据，稳定）"""
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    res = []
    
    # 昨日涨停池
    zt_data = safe_fetch("昨日涨停池", ak.stock_zt_pool_em, date=yesterday)
    if "获取失败" not in zt_data:
        zt_df = ak.stock_zt_pool_em(date=yesterday)
        res.append(f"【昨日涨停】共{len(zt_df)}只，连板高度: {zt_df['连板数'].max()}板")
        res.append(zt_df.head(10)[["代码", "名称", "连板数", "涨跌幅"]].to_string(index=False))
    
    # 龙虎榜
    lhb_data = safe_fetch("昨日龙虎榜", ak.stock_lhb_detail_em, start_date=yesterday, end_date=yesterday)
    if "获取失败" not in lhb_data:
        lhb_df = ak.stock_lhb_detail_em(start_date=yesterday, end_date=yesterday)
        buy_df = lhb_df[lhb_df["机构净买入额"] > 0].head(3)
        if not buy_df.empty:
            res.append(f"\n【昨日龙虎榜】机构净买入前3:")
            res.append(buy_df[["代码", "名称", "机构净买入额"]].to_string(index=False))
    
    return "\n".join(res) if res else "【A股行情】暂无数据"

# ====================== 4. 快讯/政策（易失败源：降级处理） ======================
def get_light_news() -> str:
    """财联社快讯、CME美联储预期（海外服务器易失败，降级处理）"""
    res = []
    # 财联社快讯（海外服务器容易被封，失败则返回提示）
    def fetch_cls():
        url = "https://www.cls.cn/nodeapi/updateTelegraphList?app=1&last_time=0"
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        data = resp.json()
        return "\n".join([f"- {i['content']}" for i in data["data"]["list"][:3] if "盘前" in i["content"]])
    
    cls_data = safe_fetch("财联社快讯", fetch_cls)
    res.append("【财联社盘前快讯】")
    res.append(cls_data)
    
    # CME美联储预期（海外源，稳定）
    def fetch_cme():
        url = "https://cdn.cmegroup.com/www/files/fedwatch/fedfundsprobabilities.json"
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        data = resp.json()
        latest = data["probabilities"][0]
        return f"加息概率: {latest['prob']}%，降息概率: {latest['cutProb']}%"
    
    cme_data = safe_fetch("美联储利率预期", fetch_cme)
    res.append(f"\n【美联储利率预期】{cme_data}")
    
    return "\n".join(res)

# ====================== 5. 个股公告（可选源：Tushare） ======================
def get_stock_announcements() -> str:
    """个股公告（依赖Tushare Token，没有则提示）"""
    if not TUSHARE_TOKEN:
        return "【个股公告】未配置TUSHARE_TOKEN，请在GitHub Secrets中添加"
    
    def fetch_tushare():
        ts.set_token(TUSHARE_TOKEN)
        pro = ts.pro_api()
        today = datetime.now().strftime("%Y%m%d")
        anns = pro.anns(ann_date=today, fields="ts_code,title")
        key_anns = anns[anns["title"].str.contains("业绩|重组|增持|减持|停牌|复牌")]
        return "\n".join([f"- {row['ts_code']} {row['title']}" for _, row in key_anns.head(5).iterrows()])
    
    return safe_fetch("个股公告", fetch_tushare)

# ====================== 组装完整早报 ======================
def build_full_morning_report() -> str:
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
        get_light_news(),
        "\n---\n",
        get_stock_announcements(),
        "\n---\n",
        "⚠️ 本报告仅供参考，不构成投资建议。数据来源：交易所/央行/统计局/akshare。"
    ]
    # 过滤空内容，避免推送空白
    valid_parts = [p for p in report_parts if p and len(p.strip()) > 0]
    return "\n".join(valid_parts)

# ====================== 主函数：必须print完整内容 ======================
if __name__ == "__main__":
    try:
        full_report = build_full_morning_report()
        # 关键：必须print完整内容，GitHub Actions才能捕获并推送给微信
        print(full_report)
    except Exception as e:
        # 即使顶层报错，也输出错误信息，避免PushPlus收到空白
        print(f"# ❌ 早报生成失败\n错误信息：{str(e)[:200]}")
