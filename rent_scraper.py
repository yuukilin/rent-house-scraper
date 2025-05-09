#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
爬 https://rent.thurc.org.taipei/RentHouse/List/5?page=N
自動翻頁，所有房源一次收；以「名稱」去重推 Telegram。
"""

import json, os, re, sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict

import requests, urllib3
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# ---------- ❶ 環境變數 ----------
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
assert BOT_TOKEN and CHAT_ID, "沒設定 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID！"

# ---------- ❷ 常數 ----------
BASE_URL    = "https://rent.thurc.org.taipei"
LIST_PREFIX = f"{BASE_URL}/RentHouse/List/5?page={{}}"           # page=1,2,…
HEADERS     = {"User-Agent": "Mozilla/5.0 (RentScraper/1.4)"}
STATE_FILE  = Path("seen_listings.json")

# ---------- ❸ 工具 ----------
def load_seen() -> set[str]:
    try:
        return set(json.loads(STATE_FILE.read_text()))
    except Exception:
        return set()

def save_seen(seen: set[str]) -> None:
    STATE_FILE.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2))

def fetch_html(url: str) -> str:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    r = requests.get(url, headers=HEADERS, timeout=20, verify=False)
    r.raise_for_status()
    return r.text

def get_last_page(soup: BeautifulSoup) -> int:
    last = 1
    for a in soup.select("ul.pagination a.page-link"):
        m = re.search(r"page=(\d+)", a.get("href", ""))
        if m:
            last = max(last, int(m.group(1)))
    return last

def parse_cards(soup: BeautifulSoup) -> List[Dict]:
    listings = []
    for card in soup.select("div.property-item"):
        title_a = card.select_one("h3.title a, h5.title a")
        if not title_a:
            continue

        name = title_a.get_text(strip=True)
        if not name:           # 🚫 空名稱直接跳過
            continue

        href = title_a["href"]

        price = (card.select_one("span.price")
                 .get_text(strip=True).replace("\u00a0", " ")
                 if card.select_one("span.price") else "未知")

        loc = (card.select_one("span.location")
               .get_text(strip=True).replace("\u00a0", " ")
               if card.select_one("span.location") else "未知")

        listings.append({
            "name": name,
            "location": loc,
            "price": price,
            "url": BASE_URL + href,
        })
    return listings

def send_telegram(text: str) -> None:
    api = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = requests.post(api, data={
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": True
    }, timeout=20)
    if r.status_code != 200:
        print("Telegram 失敗：", r.text, file=sys.stderr)

# ---------- ❹ 主流程 ----------
def main() -> None:
    # (1) 抓第 1 頁決定總頁數
    soup1 = BeautifulSoup(fetch_html(LIST_PREFIX.format(1)), "html.parser")
    last_page = get_last_page(soup1)

    # (2) 逐頁收集
    all_listings = parse_cards(soup1)
    for p in range(2, last_page + 1):
        soup = BeautifulSoup(fetch_html(LIST_PREFIX.format(p)), "html.parser")
        all_listings.extend(parse_cards(soup))

    # (3) 印前 5 筆
    print("\n=== 前 5 筆房源 ===")
    for it in all_listings[:5]:
        print(f"{it['name']} | {it['location']} | {it['price']}")
    print("===================\n")

    # (4) 新增比對
    seen = load_seen()
    newbies = [it for it in all_listings if it["name"] not in seen]

    if newbies:
        send_telegram("\n\n".join(
            f"🏠 {it['name']}\n📍 {it['location']}\n💰 {it['price']}\n🔗 {it['url']}"
            for it in newbies
        ))
        seen.update(it["name"] for it in newbies)
        save_seen(seen)
        print(f"✅ 已推送 {len(newbies)} 筆新房源")
    else:
        print(datetime.now().strftime("%F %T"), "沒有新房源")

if __name__ == "__main__":
    main()
