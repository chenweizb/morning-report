python
内容由AI生成，仅供参考
反馈
去元宝做同款
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27
28
29
30
31
32
33
34
35
36
# -*- coding: utf-8 -*-
# B2.1 买方Alpha早参 · 终极稳定版（全接口适配/优先推送/零崩溃）
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

# ==================== 基础配置（提交前确认Token从Secrets读取，严禁明文！） ====================
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
