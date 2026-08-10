import os
import sys
import requests
import yfinance as yf
from lxml import etree
from datetime import datetime
import pytz

# ========== 配置区（自行修改环境变量） ==========
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_API_URL = "https://api.hunyuan.cloud.tencent.com/v1/chat/completions"
ENABLE_AI_ANALYSIS = True
TZ_CN = pytz.timezone("Asia/Shanghai")

# 大模型System Prompt 【基金经理视角，固定约束】
SYSTEM_PROMPT = """
你是资深公募股票基金经理，拥有多年宏观权益投研经验，请严格遵守规则输出盘前投研分析：
1. 仅使用本次提供的行情、新闻、政策素材分析，禁止编造数据，禁止直接预测涨跌，不输出任何买卖个股建议。
2. 输出必须包含4个模块：
①宏观传导：隔夜海外资产、政策如何传导至A股对应板块与产业链；
②市场一致预期：当前市场主流的观点；
③反向思考【强制】：找出逻辑漏洞、已经被市场定价的预期、容易被忽略潜在风险；
④跟踪线索：客观列出值得后续跟踪的方向，只讲逻辑，不推标的。
3. 结尾必须加上：本内容仅作为投研思考素材，不构成投资建议。
4. 使用Markdown格式，语言专业冷峻，总字数控制600‑900。素材不足时如实说明，不要强行推演。
"""

# ========== 工具函数 ==========
def safe_http_get(url, timeout=15):
    """http请求封装，异常返回None"""
    try:
        resp = requests.get(url, timeout=timeout, headers={
            "User‑Agent":"Mozilla/5.0 (Windows NT10; Win64; x64) AppleWebKit/537.36"
        })
        resp.raise_for_status()
        return resp
    except Exception as e:
        print(f"请求失败 {url} ｜ {str(e)}")
        return None

def fetch_oversea_market():
    """yfinance获取隔夜全球资产收盘"""
    result = []
    ticker_map = {
        "^DJI":"道琼斯工业",
        "^IXIC":"纳斯达克",
        "^GSPC":"标普500",
        "GC=F":"COMEX黄金(美元/盎司)",
        "BZ=F":"布伦特原油(美元)",
        "DX‑Y":"美元指数"
    }
    for symbol,name in ticker_map.items():
        try:
            tk = yf.Ticker(symbol)
            hist = tk.history(period="2d")
            if len(hist)>=2:
                last_close = hist["Close"].iloc[-1]
                prev_close = hist["Close"].iloc[-2]
                pct = ((last_close - prev_close)/prev_close)*100
                result.append(f"- **{name}**: {round(last_close,2)} ｜ {round(pct,2)}%")
            else:
                result.append(f"- **{name}**: 获取失败，请前往Yahoo Finance查看")
        except Exception:
            result.append(f"- **{name}**: 获取失败，请前往Yahoo Finance查看")
    # 美债10Y‑2Y
    try:
        t10 = yf.Ticker("^TNX")
        t2 = yf.Ticker("^TWOY")
        h10 = t10.history(period="2d")
        h2 = t2.history(period="2d")
        if len(h10)>=1 and len(h2)>=1:
            y10 = h10["Close"].iloc[-1]
            y2 = h2["Close"].iloc[-1]
            spread_bp = (y10 - y2)*100
            result.append(f"- **美债10Y‑2Y利差**: {round(spread_bp,2)} bp")
    except Exception:
        result.append("- **美债10Y‑2Y利差**: 获取失败，请前往Yahoo Finance查看")
    return "\n".join(result)

def fetch_cls_news():
    """轻量抓取财联社快讯，失败返回网页链接"""
    url = "https://www.cls.cn/telegraph"
    resp = safe_http_get(url)
    if resp is None:
        return "- 财联社快讯抓取失败，请访问：https://www.cls.cn/telegraph"
    html = etree.HTML(resp.text)
    items = html.xpath('//div[contains(@class,"telegraph‑list‑item")]//p/text()')
    out = []
    for idx,item in enumerate(items[:8]):
        txt = str(item).strip()
        if txt:
            out.append(f"{idx+1}. {txt}")
    if len(out)==0:
        return "- 财联社页面结构变更，请访问：https://www.cls.cn/telegraph"
    return "\n".join(out)

def fetch_gov_policy():
    """获取央行、证监会公告入口，不做深度解析"""
    text = """
### 🌐中央金融政策查阅入口
- 中国人民银行公告：https://www.pbc.gov.cn
- 证监会政策发布：http://www.csrc.gov.cn

> ⚠️地方财政金融政策不再自动抓取，请手动访问各省市财政厅官网查看最新文件。
"""
    return text.strip()

def call_ai_analysis(all_input_text):
    """调用混元lite免费接口做投研分析"""
    if not ENABLE_AI_ANALYSIS or not LLM_API_KEY:
        return "### 🎯基金经理视角研判\nAI分析模块已关闭，请基于上面行情新闻素材自行做投研思考。"
    payload = {
        "model":"hunyuan‑lite",
        "messages":[
            {"role":"system","content":SYSTEM_PROMPT},
            {"role":"user","content":f"盘前原始素材:\n{all_input_text}"}
        ],
        "temperature":0.7,
        "max_tokens":900
    }
    try:
        r = requests.post(LLM_API_URL, headers={"Authorization":f"Bearer {LLM_API_KEY}","Content‑Type":"application/json"},
                          json=payload, timeout=45)
        j = r.json()
        choices = j.get("choices",[])
        if not choices:
            return "### 🎯基金经理视角研判\n⚠️免费大模型额度耗尽，无法生成分析，请次日再试。"
        return "### 🎯基金经理视角研判\n" + choices[0]["message"]["content"]
    except Exception as e:
        return f"### 🎯基金经理视角研判\n⚠️AI调用异常：{str(e)[:60]}，请核查密钥或额度。"

def pushplus_send(title,md_content):
    if not PUSHPLUS_TOKEN:
        print("未配置PUSHPLUS_TOKEN，跳过推送")
        return
    requests.post("https://www.pushplus.plus/send",json={
        "token":PUSHPLUS_TOKEN,
        "title":title,
        "content":md_content,
        "template":"markdown"
    },timeout=25)

def main():
    now = datetime.now(TZ_CN)
    date_str = now.strftime("%Y‑%m‑%d")
    print(f"开始执行盘前晨报 {date_str}")

    market_block = "## 🌍隔夜全球资产收盘快照\n" + fetch_oversea_market()
    news_block = "\n## 📰隔夜财经时政快讯\n" + fetch_cls_news()
    policy_block = "\n## 🏛财政金融政策查阅\n" + fetch_gov_policy()

    raw_all_material = f"{market_block}\n{news_block}\n{policy_block}"
    ai_block = call_ai_analysis(raw_all_material)

    full_report = f"""# 📈盘前晨报｜{date_str}【权威公开数据源】
> ⚠️全部数据存在网络延迟，仅作为投研参考，**不构成投资建议**

{market_block}

{news_block}

{policy_block}

{ai_block}

---
数据源：Yahoo‑Finance、财联社、央行官网、证监会官网
> 抓取失败项，请点击链接跳转官方网页核验原始信息。
"""
    #本地保存文件
    with open(f"report_{now.strftime('%Y%m%d')}.md","w",encoding="utf‑8") as f:
        f.write(full_report)
    pushplus_send(f"盘前晨报｜{date_str}",full_report)
    print("任务执行完成")

if __name__ == "__main__":
    main()
