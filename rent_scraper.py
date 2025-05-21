#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
爬 https://rent.thurc.org.taipei/RentHouse/List/5?page=N
自動翻頁，抓「地址＋狀態」，只推送『招租中』且之前沒看過的新地址到 Telegram。
— 勇成專用／無外部依賴 —
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
HEADERS     = {"User-Agent": "Mozilla/5.0 (RentScraper/1.5)"}    # 💡 版號 +0.1
STATE_FILE  = Path("seen_addresses.json")                        # 💡 重新命名，存地址

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
    """
    解析每張物件卡，回傳：address / status / url
    只要卡片裡有地址與狀態就留下。
    """
    listings = []
    for card in soup.select("div.property-item"):
        addr_tag   = card.select_one("span.location")
        status_tag = card.select_one("span.badge")        # 💡 .badge-… 直接抓第一個徽章

        if not addr_tag or not status_tag:
            continue

        address = addr_tag.get_text(strip=True)
        status  = status_tag.get_text(strip=True)

        # 物件連結可有可無，抓得到就給，抓不到也不會死
        title_a = card.select_one("h3.title a, h5.title a")
        url     = BASE_URL + title_a["href"] if title_a and title_a.has_attr("href") else BASE_URL

        listings.append({
            "address": address,
            "status":  status,
            "url":     url,
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

    # (3) 只留「招租中」
    available = [it for it in all_listings if it["status"] == "招租中"]

    # (4) 印前 5 筆偵錯用
    print("\n=== 前 5 筆招租中 ===")
    for it in available[:5]:
        print(f"{it['address']} | {it['status']}")
    print("====================\n")

    # (5) 與既有地址比對，只推新貨
    seen = load_seen()
    newbies = [it for it in available if it["address"] not in seen]

    if newbies:
        send_telegram("\n\n".join(
            f"🏠 {it['address']}\n🟢 {it['status']}\n🔗 {it['url']}"
            for it in newbies
        ))
        seen.update(it["address"] for it in newbies)
        save_seen(seen)
        print(f"✅ 已推送 {len(newbies)} 筆新房源")
    else:
        print(datetime.now().strftime("%F %T"), "沒有新房源")

if __name__ == "__main__":
    main()
