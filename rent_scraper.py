#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
爬 https://rent.thurc.org.taipei/RentHouse/List/5?page=N
1. 自動偵測最後一頁，全部抓完
2. 不限「招租中」，所有房源都收
3. 新房源以「名稱」去重比對，沒看過就推 Telegram
4. 每跑一次先列印前 5 筆供人工確認
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict

import requests
import urllib3
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# ---------- ❶ 讀環境變數 ----------
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
assert BOT_TOKEN and CHAT_ID, "沒設定 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID！"

# ---------- ❷ 常數 ----------
BASE_URL    = "https://rent.thurc.org.taipei"
LIST_PREFIX = f"{BASE_URL}/RentHouse/List/5?page={{}}"  # page=1,2,…
HEADERS     = {"User-Agent": "Mozilla/5.0 (RentScraper/1.3)"}
STATE_FILE  = Path("seen_listings.json")

# ---------- ❸ 工具函式 ----------
def load_seen() -> set[str]:
    if not STATE_FILE.exists() or STATE_FILE.stat().st_size == 0:
        return set()
    try:
        return set(json.loads(STATE_FILE.read_text()))
    except json.JSONDecodeError:
        print("⚠️  seen_listings.json 壞掉，重建", file=sys.stderr)
        return set()

def save_seen(seen: set[str]) -> None:
    STATE_FILE.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2))

def fetch_html(url: str) -> str:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    r = requests.get(url, headers=HEADERS, timeout=20, verify=False)
    r.raise_for_status()
    return r.text

def get_last_page(soup: BeautifulSoup) -> int:
    """從分頁元件抓最後一頁數字，預設 1"""
    last = 1
    for a in soup.select("ul.pagination a.page-link"):
        m = re.search(r"page=(\d+)", a.get("href", ""))
        if m:
            last = max(last, int(m.group(1)))
    return last

def parse_cards(soup: BeautifulSoup) -> List[Dict]:
    """從單頁 soup 解析所有房卡"""
    cards = soup.select("div.property-item")  # list 版
    listings = []

    for card in cards:
        a = card.find("a", href=re.compile(r"/rentHouse/detail/\d+"))
        if not a:
            continue

        href = a["href"]
        name = a.get_text(strip=True)

        price = card.select_one("span.price")
        price = price.get_text(strip=True).replace("\u00a0", " ") if price else "未知"

        loc = card.select_one("span.location")
        loc = loc.get_text(strip=True).replace("\u00a0", " ") if loc else "未知"

        listings.append({
            "name": name,
            "location": loc,
            "price": price,
            "url": BASE_URL + href,
        })
    return listings

# ---------- ❹ 主流程 ----------
def main() -> None:
    # 1) 先抓第 1 頁，決定總頁數
    html_page1 = fetch_html(LIST_PREFIX.format(1))
    soup_page1 = BeautifulSoup(html_page1, "html.parser")
    last_page  = get_last_page(soup_page1)

    print(f"👉 共 {last_page} 頁，開始抓取…")

    # 2) 逐頁抓
    all_listings = parse_cards(soup_page1)

    for p in range(2, last_page + 1):
        html = fetch_html(LIST_PREFIX.format(p))
        soup = BeautifulSoup(html, "html.parser")
        all_listings.extend(parse_cards(soup))

    # 3) 印前 5 筆供人工確認
    print("\n=== 前 5 筆房源 ===")
    for it in all_listings[:5]:
        print(f"{it['name']} | {it['location']} | {it['price']}")
    print("===================\n")

    # 4) 新增比對
    seen_names = load_seen()
    newbies = [it for it in all_listings if it["name"] not in seen_names]

    if newbies:
        msg = "\n\n".join(
            f"🏠 {it['name']}\n📍 {it['location']}\n💰 {it['price']}\n🔗 {it['url']}"
            for it in newbies
        )
        send_telegram(msg)
        seen_names.update(it["name"] for it in newbies)
        save_seen(seen_names)
        print(f"✅ 已推送 {len(newbies)} 筆新房源")
    else:
        print(datetime.now().strftime("%F %T"), "沒有新房源")

def send_telegram(text: str) -> None:
    api = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = requests.post(api, data={
        "chat_id": CHAT_ID,
        "text":    text,
        "disable_web_page_preview": True
    }, timeout=20)
    if r.status_code != 200:
        print("Telegram 失敗：", r.text, file=sys.stderr)

if __name__ == "__main__":
    main()
