"""국제 동향 재수집 스크립트 — 기존 전체 삭제 후 방사선 관련 10건 신규 수집"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import database
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime
from collections import defaultdict
import urllib.parse

database.init_db()

conn = database.get_conn()
deleted = conn.execute("DELETE FROM news WHERE category='국제 동향'").rowcount
conn.commit()
conn.close()
print(f"기존 국제 동향 {deleted}건 삭제\n")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# 방사선 관련성 필터
RADIATION_KWS = [
    "radiation", "radioactive", "radioactivity", "radiological",
    "radiopharmaceutical", "radionuclide", "radioisotope",
    "dosimetry", "dose", "contamination", "decontamination",
    "nuclear medicine", "radiology", "radioprotection",
    "radioactive waste", "spent fuel", "nuclear waste",
    "radiation safety", "radiation protection",
    "gamma", "tritium", "radon", "fallout", "isotope",
    "brachytherapy", "radiosurgery", "radioiodine",
    "pet scan", "spect", "scintigraphy",
    "radiation emergency", "nuclear accident", "nuclear safety",
    "radiation therapy", "radiotherapy",
    "radiation monitoring", "radiation measurement",
    "radioactive contamination",
    "방사선", "방사성", "방사능", "방사성의약품", "방사성동위원소",
    "핵의학", "방사선 치료", "방사선 안전", "방사성폐기물",
]

def is_rad_relevant(title: str, summary: str = "") -> bool:
    text = (title + " " + summary).lower()
    return any(kw.lower() in text for kw in RADIATION_KWS)


def normalize_date_entry(entry) -> str:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6]).strftime("%Y-%m-%d")
            except Exception:
                pass
    return datetime.now().strftime("%Y-%m-%d")


# 다양한 분야의 국제 방사선 뉴스 쿼리 (Google News EN)
INTL_QUERIES = [
    "IAEA radiation safety nuclear medicine 2026",
    "radiopharmaceutical therapy treatment international",
    "radiation protection guidelines WHO UNSCEAR",
    "radioactive contamination environmental monitoring",
    "nuclear medicine imaging PET SPECT international",
    "radiation emergency response international",
    "radioactive waste disposal management 2026",
    "radiation dosimetry measurement international",
]

all_candidates = []

for query in INTL_QUERIES:
    rss_url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en&gl=US&ceid=US:en"
    try:
        resp = requests.get(rss_url, headers=HEADERS, timeout=15)
        feed = feedparser.parse(resp.content)
        collected = 0
        for entry in feed.entries[:10]:
            raw_title = entry.get("title", "").strip()
            link = entry.get("link", "")
            if not raw_title or not link:
                continue
            # 소스 분리
            if " - " in raw_title:
                title, source = raw_title.rsplit(" - ", 1)
                title = title.strip()
                source = source.strip()
            else:
                title = raw_title
                source = "International"
            summary = BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:300]
            if not is_rad_relevant(title, summary):
                continue
            pub = normalize_date_entry(entry)
            all_candidates.append({
                "title":    title,
                "source":   source,
                "url":      link,
                "published": pub,
                "category": "국제 동향",
                "summary":  summary,
                "region":   "해외",
                "end_date": "",
                "location": "",
            })
            collected += 1
        print(f"  [{query[:55]:<55}] {collected}건")
    except Exception as e:
        print(f"  [{query[:55]:<55}] 오류: {e}")

# World Nuclear News RSS도 추가 (방사선 관련 기사만)
try:
    resp = requests.get("https://www.world-nuclear-news.org/rss", headers=HEADERS, timeout=15)
    feed = feedparser.parse(resp.content)
    wnn_count = 0
    for entry in feed.entries[:30]:
        title = entry.get("title", "").strip()
        link = entry.get("link", "")
        if not title or not link:
            continue
        summary = BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:300]
        if not is_rad_relevant(title, summary):
            continue
        pub = normalize_date_entry(entry)
        all_candidates.append({
            "title": title, "source": "World Nuclear News",
            "url": link, "published": pub,
            "category": "국제 동향", "summary": summary,
            "region": "해외", "end_date": "", "location": "",
        })
        wnn_count += 1
    print(f"  [World Nuclear News RSS{'':<34}] {wnn_count}건")
except Exception as e:
    print(f"  [World Nuclear News RSS] 오류: {e}")

print()

# 최신순 정렬
all_candidates.sort(key=lambda x: x["published"], reverse=True)

# URL 중복 제거
seen_urls: set = set()
unique: list = []
for item in all_candidates:
    if item["url"] not in seen_urls:
        seen_urls.add(item["url"])
        unique.append(item)

# 소스 다양성 보장: 소스당 최대 2건
src_cnt: dict = defaultdict(int)
diverse: list = []
for item in unique:
    src = item["source"]
    if src_cnt[src] < 2:
        diverse.append(item)
        src_cnt[src] += 1
    if len(diverse) >= 10:
        break

print(f"전체 후보 {len(unique)}건 → 다양성 적용 후 {len(diverse)}건 선정\n")

added = database.insert_news(diverse)
print(f"국제 동향 {added}건 삽입 완료\n")

print("── 삽입된 항목 ──")
for item in diverse:
    print(f"  [{item['source']}] {item['published']} | {item['title'][:65]}")
    print(f"    {item['url'][:80]}")
