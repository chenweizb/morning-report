# -*- coding: utf-8 -*-
import requests, time, os
import akshare as ak

PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "")
WECHAT_WEBHOOK = os.environ.get("WECHAT_WEBHOOK", "")

def cls_news(n=6):
    try:
        r = requests.get("https://www.cls.cn/nodeapi/telegraphList",
                         params={"app":"CailianpressWeb","rn":str(n)}, timeout=5).json()
        return [f"【{time.strftime('%H:%M',time.localtime(i['ctime']))}】{i['title']}"
                for i in r["data"]["roll_data"][:n]]
    except Exception as e:
        return [f"财联社失败:{e}"]

def jin10_news(n=6):
    try:
        hdr = {"x-app-id":"rU6QIu7JHe2gOUeR","user-agent":"Mozilla/5.0"}
        r = requests.get("https://datacenter-api.jin10.com/sentiment/list", headers=hdr, timeout=5).json()
        return [f"【{i.get('time','')}】{i.get('content','')}" for i in r["data"][:n]]
    except Exception as e:
        return [f"金十失败:{e}"]

def futures():
    out = {}
    for c in ["IF","IC","IH","IM"]:
        try:
            df = ak.futures_zh_spot(symbol=f"{c}0", market="CFFEX")
            out[c] = float(df.iloc[0]["current_price"])
        except: out[c] = None
    return out

def emotion():
    try:
        df = ak.stock_zh_a_spot_em()
        return df[df["涨跌幅"]>=9.5].shape[0], df[df["涨跌幅"]<=-9.5].shape[0]
    except Exception as e:
        return f"N/A({e})", "N/A"

def push(title, content):
    if PUSHPLUS_TOKEN:
        requests.post("http://www.pushplus.plus/send",
            json={"token":PUSHPLUS_TOKEN,"title":title,"content":content,"channel":"wechat"})
    if WECHAT_WEBHOOK:
        requests.post(WECHAT_WEBHOOK, json={"msgtype":"markdown",
            "markdown":{"content":f"## {title}\n{content}"}})

if __name__ == "__main__":
    cls = cls_news(6)
    jin = jin10_news(6)
    futs = futures()
    up, dn = emotion()
    content = f"""
📡 **盘前跨市场早报 {time.strftime('%Y-%m-%d %H:%M')}**

**期指**：IF={futs['IF']} IC={futs['IC']} IH={futs['IH']} IM={futs['IM']}  
**A股情绪**：涨停 {up} / 跌停 {dn}  

⚡ **财联社电报**  
{'<br>'.join(cls)}

🔥 **金十快讯**  
{'<br>'.join(jin)}

> 复制以上给元宝 → 输出《今日作战地图》（情绪周期+仓位+主攻/回避板块）
"""
    push("📈 盘前早报", content)
    print("✅ 已推送")