import os
import requests
import yfinance as yf
from lxml import etree
from datetime import datetime
import pytz

# ========== 配置区（全部读取环境变量，不要写死密钥） ==========
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_API_URL = "https://api.hunyuan.cloud.tencent.com/v1/chat/completions"
ENABLE_AI = True
TZ_CN = pytz.timezone("Asia/Shanghai")

SYSTEM_PROMPT = """
你是资深公募基金经理，擅长宏观A股投研，请严格遵守规则输出盘前分析：
1. 只使用本次传入的行情、新闻、政策素材，禁止编造数据；禁止预测涨跌，不输出买卖建议。
2. 输出固定4个模块：
①宏观传导：海外资产、政策会如何传导到A股各个产业链；
②市场一致预期：当前市场主流的交易逻辑；
③反向思考【强制】：风险点、逻辑漏洞、容易被忽略的利空；
④跟踪线索：后续需要重点观察的指标与事件，只讲逻辑，不推个股。
3. 末尾固定带上一句话：本内容仅作为投研参考，不构成投资建议。
4. 使用markdown格式，文字专业克制，总字数控制600-900字。素材不足时如实说明，不要强行编造。
"""

def safe_http_get(url, timeout=15):
    try:
        resp = requests.get(url, timeout=timeout, headers={
            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        resp.raise_for_status()
        return resp
    except Exception as e:
        print(f"请求异常 {url} ：{str(e)}")
        return None

def fetch_global_market():
    result = []
    tick_list = [
        ("^DJI","道琼斯工业"),
        ("^IXIC","纳斯达克"),
        ("^GSPC","标普500"),
        ("GC=F","COMEX黄金(美元/盎司)"),
        ("CL=F","WTI原油(美元/桶)"),
        ("DX-Y.NYB","美元指数")
    ]
    for symbol,name in tick_list:
        try:
            tk = yf.Ticker(symbol)
            hist = tk.history(period="2d")
            if len(hist)>=2:
                last = hist.iloc[-1]
                prev = hist.iloc[-2]
                close = round(last["Close"],2)
                pct = round(((last["close"] - prev["close"]) / prev["close"]) * 100, 2)
                result.append(f"- **{name}**: {close} ｜ {pct}%")
            else:
                result.append(f"- **{name}**: 获取失败，请访问Yahoo Finance查看")
        except Exception:
            result.append(f"- **{name}**: 获取失败，请访问Yahoo Finance查看")
    return "\n".join(result)

def fetch_cls_news():
    url = "https://www.cls.cn/telegraph"
    resp = safe_http_get(url)
    if resp is None:
        return "- 财联社快讯抓取失败，请手动访问 https://www.cls.cn/telegraph"
    html = etree.HTML(resp.text)
    items = html.xpath('//div[contains(@class,"telegraph-list-item")]//p/text()')
    out = []
    for idx,item in enumerate(items[:8]):
        txt = str(item).strip()
        if txt:
            out.append(f"{idx+1}. {txt}")
    if len(out)==0:
        return "- 财联社页面结构变更，请访问 https://www.cls.cn/telegraph"
    return "\n".join(out)

def get_policy_note():
    return """
### 🌐中央金融政策查阅入口
- 中国人民银行：https://www.pbc.gov.cn
- 证监会官网：http://www.csrc.gov.cn

> ⚠️地方财政政策不再自动抓取，请自行访问各省市财政厅官网。
""".strip()

def ai_analyse(raw_text:str):
    if not ENABLE_AI or not LLM_API_KEY:
        return "### 🎯基金经理视角研判\nAI模块未启用，请结合上面素材自行完成投研分析。"
    payload = {
        "model":"hunyuan-lite",
        "messages":[
            {"role":"system","content":SYSTEM_PROMPT},
            {"role":"user","content":f"原始素材：\n{raw_text}"}
        ],
        "temperature":0.7,
        "max_tokens":1200
    }
    headers = {"Authorization":f"Bearer {LLM_API_KEY}","Content-Type":"application/json"}
    try:
        r = requests.post(LLM_API_URL,json=payload,headers=headers,timeout=45)
        r.raise_for_status()
        j = r.json()
        content = j["choices"][0]["message"]["content"]
        return f"### 🎯基金经理视角研判\n{content}"
    except Exception as e:
        return f"### 🎯基金经理视角研判\nAI调用出错：{str(e)[:80]}，请检查API密钥、额度。"

def pushplus_send(title,content):
    if not PUSHPLUS_TOKEN:
        print("未配置PUSHPLUS_TOKEN，跳过推送")
        return
    api = "http://www.pushplus.plus/send"
    body = {
        "token":PUSHPLUS_TOKEN,
        "title":title,
        "content":content,
        "template":"markdown"
    }
    try:
        requests.post(api,json=body,timeout=20)
    except Exception as e:
        print(f"推送失败 {str(e)}")

def main():
    now = datetime.now(TZ_CN)
    date_str = now.strftime("%Y-%m-%d")
    print(f"====开始生成盘前晨报 {date_str}====")

    market_block = "## 🌍隔夜全球资产收盘\n" + fetch_global_market()
    news_block = "\n## 📰财联社快讯\n" + fetch_cls_news()
    policy_block = "\n## 🏛政策查询入口\n" + get_policy_note()

    full_source = f"{market_block}\n{news_block}\n{policy_block}"
    ai_block = "\n" + ai_analyse(full_source)

    full_report = f"""# 📈盘前晨报｜{date_str}
> ⚠️全部数据仅供投研复盘，**不构成任何投资建议**

{market_block}

{news_block}

{policy_block}

{ai_block}

---
数据源：Yahoo Finance、财联社公开网页
"""
    #本地保存文件
    with open(f"report_{date_str}.md","w",encoding="utf-8") as f:
        f.write(full_report)
    pushplus_send(f"盘前晨报 {date_str}",full_report)
    print("执行完成，报告已本地保存并尝试推送")

if __name__ == "__main__":
    main()
