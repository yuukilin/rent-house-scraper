#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
爬 https://rent.thurc.org.taipei/RentHouse/List/5?page=N
自動翻頁 → 抓「地址＋狀態」→ 只推『招租中』→ 每次都更新 seen_addresses.json
"""

import json, os, re, sys, subprocess
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
LIST_PREFIX = f"{BASE_URL}/RentHouse/List/5?page={{}}"
HEADERS     = {"User-Agent": "Mozilla/5.0 (RentScraper/1.6)"}
STATE_FILE  = Path("seen_addresses.json")

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
        addr_tag   = card.select_one("span.location")
        # 只抓綠色 badge (class=badge-success) 才算「招租中」
        status_tag = card.select_one("span.badge-success")
        if not addr_tag or not status_tag:
            continue

        address = addr_tag.get_text(strip=True)
        status  = status_tag.get_text(strip=True)

        if "招租" not in status:        # 仍再保險一次
            continue

        title_a = card.select_one("h3.title a, h5.title a")
        url     = BASE_URL + title_a["href"] if title_a and title_a.has_attr("href") else BASE_URL

        listings.append({"address": address, "status": status, "url": url})
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
    soup1 = BeautifulSoup(fetch_html(LIST_PREFIX.format(1)), "html.parser")
    last_page = get_last_page(soup1)

    all_listings = parse_cards(soup1)
    for p in range(2, last_page + 1):
        soup = BeautifulSoup(fetch_html(LIST_PREFIX.format(p)), "html.parser")
        all_listings.extend(parse_cards(soup))

    # 現場所有「招租中」地址
    snapshot = {it["address"]: it for it in all_listings}

    seen   = load_seen()
    newbies = [snapshot[addr] for addr in snapshot if addr not in seen]

    # === 推播 ===
    if newbies:
        send_telegram("\n\n".join(
            f"🏠 {it['address']}\n🟢 {it['status']}\n🔗 {it['url']}"
            for it in newbies
        ))
        print(f"✅ 已推送 {len(newbies)} 筆新房源")
    else:
        print(datetime.now().strftime("%F %T"), "沒有新房源")

    # === 無論有沒有新人，都把最新 snapshot 寫回檔 ===
    save_seen(set(snapshot.keys()))

if __name__ == "__main__":
    main()
