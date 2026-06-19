"""
방사선 소식 뉴스 수집기
Google News RSS + 전용 사이트 RSS를 활용하여 API 비용 없이 수집
"""
import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import time
import re
import os
import database

# Obsidian 마크다운 저장 경로 (프로젝트 폴더 내 daily-notes 디렉토리)
OBSIDIAN_DIR = os.path.join(os.path.dirname(__file__), "daily-notes")

# ──────────────────────────────────────────
# 카테고리별 키워드 정의 (엑셀 소스 기반)
# ──────────────────────────────────────────
CATEGORY_KEYWORDS = {
    "산업 뉴스": [
        "방사선", "방사성", "방사능", "원자력", "원전", "핵",
        "동위원소", "방사성의약품", "방사성동위원소",
        "가속기", "선형가속기", "중이온가속기",
        "X선", "엑스선", "X-ray",
        "비파괴검사", "방폐물", "방폐장", "SMR", "소형모듈원자로",
        "중성자", "베타선", "알파선", "감마선",
        "의료방사선", "방사선치료", "핵의학", "PET", "SPECT",
        "방사성폐기물", "사용후핵연료", "핵연료",
    ],
    "KARA 주요이벤트": [
        "한국방사선진흥협회", "KARA", "방사선진흥협회",
        "카라캠퍼스", "RATIS", "방사선기술통합정보",
    ],
    "국내외 공고": [
        "방사선 공고", "원자력 공모", "방사선 R&D", "방사선 지원사업",
        "원자력 연구개발", "방사성 사업화", "비파괴검사 공고",
        "한국원자력안전기술원", "KINS", "한국원자력환경공단", "KORAD",
    ],
    "업계 행사": [
        "방사선 학회", "원자력 학술", "방사선 컨퍼런스", "원자력 심포지엄",
        "방사선 전시회", "핵의학 학회", "방사선 세미나",
        "KAIF", "KNS", "WCI", "ICRP", "IRPA",
    ],
    "국제 동향": [
        "IAEA", "NRC", "NEA", "World Nuclear",
        "nuclear radiation", "radioactive", "radiopharmaceutical",
        "방사선 국제", "원자력 국제", "핵 국제동향",
    ],
}

# ──────────────────────────────────────────
# 뉴스 소스 정의
# ──────────────────────────────────────────

# Google News RSS — 산업 뉴스·KARA·국제 동향 전용 (공고/행사는 전용 스크래퍼 사용)
GOOGLE_NEWS_QUERIES = [
    ("방사선", "산업 뉴스"),
    ("방사성의약품", "산업 뉴스"),
    ("원자력 원전", "산업 뉴스"),
    ("방사성동위원소 동위원소", "산업 뉴스"),
    ("한국방사선진흥협회 KARA", "KARA 주요이벤트"),
    ("IAEA nuclear radiation international", "국제 동향"),
    ("비파괴검사 방사선안전", "산업 뉴스"),
    ("SMR 소형모듈원자로", "산업 뉴스"),
]

# 언론사 파급력 순위 — KARA 보도자료 중복 시 우선 채택 기준 (높을수록 우선)
MEDIA_RANK = {
    "연합뉴스": 10,
    "ytn": 9, "kbs": 9,
    "mbc": 8, "sbs": 8, "조선일보": 8, "중앙일보": 8, "동아일보": 8,
    "매일경제": 8, "한국경제": 8,
    "한겨레": 7, "경향신문": 7, "한국일보": 7,
    "전자신문": 6, "디지털타임스": 6,
    "뉴시스": 5, "뉴스1": 5,
    "에너지데일리": 4, "에너지안전신문": 3,
}

# KARA 공식 소스 (항상 우선, 보도자료 dedup 에서 제외)
KARA_OFFICIAL_SOURCES = {"한국방사선진흥협회", "KARA Campus", "RATIS"}

# 전용 뉴스 RSS 피드 (산업 뉴스·국제 동향)
RSS_FEEDS = [
    ("https://www.energydaily.co.kr/rss/allArticle.xml", "에너지데일리", None),
    ("https://www.esnews.kr/rss/allArticle.xml", "에너지안전신문", None),
    ("https://www.world-nuclear-news.org/rss", "World Nuclear News", "국제 동향"),
    ("https://www.iaea.org/feeds/pressreleases.xml", "IAEA", "국제 동향"),
]

# 국내외 공고 전용 RSS (실제 공고 수집)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ──────────────────────────────────────────
# 유틸리티
# ──────────────────────────────────────────

def normalize_date(entry) -> str:
    """feedparser entry에서 날짜 문자열을 ISO 형식으로 변환"""
    for attr in ("published_parsed", "updated_parsed", "start_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6]).strftime("%Y-%m-%d")
            except Exception:
                pass
    return datetime.now().strftime("%Y-%m-%d")


def normalize_end_date(entry) -> str:
    """종료일/마감일 추출"""
    for attr in ("end_parsed", "expires_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6]).strftime("%Y-%m-%d")
            except Exception:
                pass
    return ""


def auto_category(title: str, source: str, hint: str = None) -> str:
    """제목과 출처 기반 카테고리 자동 분류"""
    text = (title + " " + source).lower()
    if hint:
        return hint

    for kw in CATEGORY_KEYWORDS["KARA 주요이벤트"]:
        if kw.lower() in text:
            return "KARA 주요이벤트"

    for kw in CATEGORY_KEYWORDS["국제 동향"]:
        if kw.lower() in text:
            return "국제 동향"

    event_hints = ["학회", "컨퍼런스", "심포지엄", "전시회", "세미나", "학술대회", "annual conference", "symposium"]
    for kw in event_hints:
        if kw in text:
            return "업계 행사"

    announce_hints = ["공고", "모집", "지원사업", "공모", "입찰", "r&d"]
    for kw in announce_hints:
        if kw in text:
            return "국내외 공고"

    for kw in CATEGORY_KEYWORDS["산업 뉴스"]:
        if kw.lower() in text:
            return "산업 뉴스"

    return "산업 뉴스"


def is_radiation_related(title: str) -> bool:
    """방사선 관련 기사인지 필터링"""
    all_keywords = []
    for kws in CATEGORY_KEYWORDS.values():
        all_keywords.extend(kws)
    text = title.lower()
    if re.search(r"[a-zA-Z]{4,}", title):
        return True
    return any(kw.lower() in text for kw in all_keywords)


def detect_region(url: str, source: str = "") -> str:
    """URL/출처 기반 국내/해외 자동 판별"""
    url_l = (url or "").lower()
    src_l = (source or "").lower()
    kr_url = [".go.kr", ".or.kr", ".re.kr", ".ac.kr", ".co.kr", ".kr/", ".kr?", ".kr#"]
    kr_src = ["한국", "국내", "kins", "kara", "nrf", "iitp", "ketep", "korad",
               "비즈인포", "나라장터", "kaif", "kns", "kria", "산업부", "과기부"]
    if any(p in url_l for p in kr_url):
        return "국내"
    if any(k in src_l for k in kr_src):
        return "국내"
    return "해외"


def extract_deadline(text: str) -> str:
    """텍스트에서 마감일 추출 시도"""
    patterns = [
        r'마감[일\s]*[:\s]*(\d{4}[-./]\d{1,2}[-./]\d{1,2})',
        r'접수마감[:\s]*(\d{4}[-./]\d{1,2}[-./]\d{1,2})',
        r'(\d{4}[-./]\d{1,2}[-./]\d{1,2})\s*까지',
        r'기한[:\s]*(\d{4}[-./]\d{1,2}[-./]\d{1,2})',
        r'~\s*(\d{4}[-./]\d{1,2}[-./]\d{1,2})',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            raw = m.group(1).replace(".", "-").replace("/", "-")
            return raw
    return ""


def extract_location(text: str, entry=None) -> str:
    """행사 장소 추출 시도"""
    if entry:
        for attr in ("location", "geo_lat"):
            val = getattr(entry, attr, None)
            if val and isinstance(val, str) and len(val) > 2:
                return val[:100]
    patterns = [
        r'(?:장소|개최지|venue|location)[:\s]+([^\n,<]{3,60})',
        r'(?:at|in)\s+([A-Z][^,\n<]{3,50})',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()[:100]
    return ""


# ──────────────────────────────────────────
# 뉴스 수집 함수
# ──────────────────────────────────────────

def fetch_google_news_rss(query: str, category_hint: str) -> list:
    """Google News RSS로 뉴스 수집"""
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
    items = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        feed = feedparser.parse(resp.content)
        for entry in feed.entries[:15]:
            title = entry.get("title", "").strip()
            if " - " in title:
                parts = title.rsplit(" - ", 1)
                title = parts[0].strip()
                source = parts[1].strip()
            else:
                source = "Google News"

            link = entry.get("link", "")
            if not title or not link:
                continue

            raw_summary = entry.get("summary", "") or ""
            summary = BeautifulSoup(raw_summary, "html.parser").get_text()[:300]
            items.append({
                "title": title,
                "source": source,
                "url": link,
                "published": normalize_date(entry),
                "category": auto_category(title, source, category_hint),
                "summary": summary,
                "region": "",
                "end_date": "",
                "location": "",
            })
    except Exception as e:
        print(f"  [오류] Google News RSS ({query}): {e}")
    return items


def fetch_rss_feed(feed_url: str, source_name: str, category_hint: str = None) -> list:
    """일반 RSS 피드 수집"""
    items = []
    try:
        resp = requests.get(feed_url, headers=HEADERS, timeout=15)
        feed = feedparser.parse(resp.content)
        for entry in feed.entries[:20]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "")
            if not title or not link:
                continue

            if source_name not in ("World Nuclear News", "IAEA"):
                if not is_radiation_related(title):
                    continue

            summary = BeautifulSoup(
                entry.get("summary", ""), "html.parser"
            ).get_text()[:300]

            items.append({
                "title": title,
                "source": source_name,
                "url": link,
                "published": normalize_date(entry),
                "category": auto_category(title, source_name, category_hint),
                "summary": summary,
                "region": "",
                "end_date": "",
                "location": "",
            })
    except Exception as e:
        print(f"  [오류] RSS ({source_name}): {e}")
    return items


# ──────────────────────────────────────────
# 소스 귀인 헬퍼 — KNS/KAIF 재게시 시 실제 주최기관 추출
# ──────────────────────────────────────────

def _extract_real_source(title: str, default_source: str) -> tuple:
    """
    제목에서 [기관명] 접두어를 추출해 실제 source를 반환.
    반환: (정제된 제목, 실제 source)
    예) "[한국원자력안전기술원] 2026 심포지엄" → ("2026 심포지엄", "한국원자력안전기술원")
        "[한국원자력환경공단 2026년도 채용]..." → ("...", "한국원자력환경공단")
    """
    m = re.match(r'^\[([^\]]{2,40})\]\s*', title)
    if not m:
        return title, default_source
    bracket_content = m.group(1).strip()
    clean_title = title[m.end():].strip()
    if not clean_title:
        return title, default_source
    # 연도(4자리) 앞까지만 기관명으로 추출
    org = re.split(r'\s*\d{4}', bracket_content)[0].strip()
    # 숫자로 시작하거나 한글 2자 미만이면 제외
    korean_chars = sum(1 for c in org if '가' <= c <= '힣')
    if korean_chars >= 2 and not re.match(r'^\d', org) and len(org) >= 3:
        return clean_title, org
    return title, default_source


# ──────────────────────────────────────────
# KAIF 공통 파싱 헬퍼
# ──────────────────────────────────────────

def _parse_kaif_main() -> list:
    """KAIF(한국원자력산업협회) 메인 페이지에서 공지/행사 링크 파싱"""
    raw = []
    try:
        resp = requests.get("https://www.kaif.or.kr", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        event_kws = ["행사", "세미나", "포럼", "심포", "컨퍼", "워크숍", "학술",
                     "공고", "모집", "입찰", "지원", "시행공고", "채용"]
        seen = set()
        for a in soup.find_all("a", href=True):
            txt = a.get_text(strip=True)
            href = a.get("href", "")
            if not any(k in txt for k in event_kws):
                continue
            if len(txt) < 8:
                continue
            if not href.startswith("http"):
                href = "https://www.kaif.or.kr" + href
            if href in seen:
                continue
            seen.add(href)
            # type_tag 추출 (대괄호 유무 모두 처리)
            # 형식: "[공지사항제목]" 또는 "공지사항제목"
            type_prefixes = ["공지사항", "입찰정보", "보도자료", "행사안내", "교육안내"]
            type_tag = ""
            for tp in type_prefixes:
                if txt.startswith("[" + tp) or txt.startswith(tp):
                    type_tag = tp
                    break
            # 타입 태그 제거
            clean = re.sub(r'^\[?(공지사항|입찰정보|보도자료|행사안내|교육안내)\]?', '', txt).strip()
            # 마감일 추출: (~숫자. 숫자) 또는 (~ 숫자. 숫자) 패턴 (공백, 시간 허용)
            deadline = ""
            dm = re.search(r'\(~\s*(\d{1,2})\.\s*(\d{1,2})', clean)
            if dm:
                month, day = dm.group(1), dm.group(2)
                deadline = f"2026-{month.zfill(2)}-{day.zfill(2)}"
                clean = re.sub(r'\s*\(~\s*[\d\s.:]+\)', '', clean).strip()
            # 날짜 포함 형식 (YYYY.MM.DD) 제거
            clean = re.sub(r'\d{4}\.\d{2}\.\d{2}\.?\s*$', '', clean).strip()
            # 마감 문자열 패턴 제거 (_마감 등)
            clean = re.sub(r'_?마감\s*$', '', clean).strip()
            if clean and len(clean) > 5:
                raw.append({
                    "title": clean,
                    "href": href,
                    "deadline": deadline,
                    "type_tag": type_tag,
                })
    except Exception as e:
        print(f"  [오류] KAIF 메인 파싱: {e}")
    return raw


# ──────────────────────────────────────────
# 공고 전용 수집
# ──────────────────────────────────────────

# 방사선 + 과학계통 공고 관련 키워드 (넓게 설정)
ANNOUNCE_SCIENCE_KWS = [
    # 방사선 직접
    "방사선", "방사성", "방사능", "방사성동위원소", "동위원소",
    "원자력", "원자로", "핵의학", "방사선치료", "방사선사",
    "방호", "방재", "방폐", "비파괴", "중성자", "가속기",
    # 의료/바이오 계통
    "의료기기", "바이오헬스", "바이오헬스케어", "항암", "진단영상", "의료영상",
    "방사성의약품", "의약품", "임상", "체외진단",
    # 과학기술 계통 (방사선 응용 포함)
    "나노소재", "나노융합", "첨단소재", "소재공정", "신소재",
    "측정기술", "계측", "정밀측정",
    "레이저", "광학", "전자빔", "플라즈마",
    "생명과학", "방사선과학", "핵융합",
    # 제품안전·표준 (방사선 기기 인증 포함)
    "제품안전", "국가표준", "안전인증",
]

# 채용·인사 공고 제외 키워드
ANNOUNCE_RECRUIT_EXCLUDE = [
    "채용", "구인", "직원 모집", "임직원", "이사장 모집", "비상임감사",
    "박사후연구원", "포닥", "인사혁신", "공무원 모집", "고공단",
    "ITER 기구 채용", "연구원 채용",
]


def _is_recruit_announcement(title: str) -> bool:
    """채용·인사 공고이면 True (제외 대상)"""
    return any(k in title for k in ANNOUNCE_RECRUIT_EXCLUDE)


def fetch_announcements() -> list:
    """국내외 공고 — KEIT SROME + bizinfo 중심으로 수집
    (채용·인사 공고 제외, 방사선+과학계통 R&D/지원사업만)
    """
    items = []

    # 1. KEIT SROME — 방사선·과학계통 R&D 과제 공고
    items.extend(fetch_srome_announcements())

    # 2. 비즈인포 — 방사선 업계 관련 지원사업·공모 공고 (원본 기관 URL 추적)
    items.extend(fetch_bizinfo_announcements())

    # 채용·인사 공고 최종 제거
    before = len(items)
    items = [i for i in items if not _is_recruit_announcement(i.get("title", ""))]
    if len(items) < before:
        print(f"    채용/인사 공고 {before - len(items)}건 제외")

    print(f"    공고 합계: {len(items)}건")
    return items


# ──────────────────────────────────────────
# 행사 전용 수집
# ──────────────────────────────────────────

def fetch_events() -> list:
    """국내외 업계 행사 전문 사이트에서 실제 행사 수집"""
    items = []

    # 1. KNS(한국원자력학회) 메인에서 학술대회/행사 추출 (실제 주최기관 귀인 포함)
    items.extend(fetch_kns_events())

    # 2. KAIF(한국원자력산업협회) 메인에서 행사 추출
    items.extend(fetch_kaif_events())

    # 3. KARP(대한방사선방어학회) 공식 행사 페이지
    items.extend(fetch_karp_events())

    print(f"    행사 합계: {len(items)}건")
    return items


def fetch_kns_events() -> list:
    """KNS(한국원자력학회) 메인에서 학술대회·행사 수집"""
    items = []
    try:
        resp = requests.get("https://www.kns.org", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        event_kws = ["학술대회", "심포지엄", "워크숍", "세미나", "포럼", "컨퍼런스",
                     "학술발표", "정기총회"]
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            # 첫 번째 직계 텍스트 노드만 제목으로 사용 (미리보기 내용 제외)
            direct_texts = [t.strip() for t in a.strings if t.strip()]
            txt = direct_texts[0] if direct_texts else a.get_text(strip=True)
            full_txt = a.get_text(strip=True)
            if "/boards/view/" not in href:
                continue
            if not any(k in full_txt for k in event_kws):
                continue
            if href in seen or len(txt) < 5:
                continue
            seen.add(href)
            if not href.startswith("http"):
                href = "https://www.kns.org" + href
            # 날짜 추출 (전체 텍스트에서)
            dates = re.findall(r'\d{4}[-./년]\s*\d{1,2}[-./월]\s*\d{1,2}', full_txt)
            pub_dt = datetime.now().strftime("%Y-%m-%d")
            end_dt = ""
            if len(dates) >= 2:
                pub_dt = dates[0].replace(".", "-").replace("/", "-").replace("년", "-").replace("월", "-")
                end_dt = dates[1].replace(".", "-").replace("/", "-").replace("년", "-").replace("월", "-")
                pub_dt = re.sub(r'-+', '-', pub_dt).strip('-')
                end_dt = re.sub(r'-+', '-', end_dt).strip('-')
            elif len(dates) == 1:
                pub_dt = dates[0].replace(".", "-").replace("/", "-")
            # 첫 직계 텍스트를 제목으로 사용, 너무 짧으면 두 번째까지 합침
            title = txt
            if len(title) < 8 and len(direct_texts) > 1:
                title = " ".join(direct_texts[:2])
            title = title[:100]
            # 실제 주최기관 추출 (KNS가 타 기관 행사 재게시하는 경우)
            real_title, real_source = _extract_real_source(title, "한국원자력학회(KNS)")
            items.append({
                "title": real_title,
                "source": real_source,
                "url": href,
                "published": pub_dt,
                "category": "업계 행사",
                "summary": "",
                "region": "국내",
                "end_date": end_dt,
                "location": "",
            })
    except Exception as e:
        print(f"  [오류] KNS 행사: {e}")
    if items:
        print(f"    KNS 행사: {len(items)}건")
    return items


def fetch_kaif_events() -> list:
    """KAIF(한국원자력산업협회) 메인에서 행사 수집"""
    items = []
    EVENT_KWS = ["포럼", "심포지엄", "워크숍", "세미나", "컨퍼런스", "학술", "대회", "총회"]
    for parsed in _parse_kaif_main():
        # 반드시 행사 키워드가 제목에 있어야 함 (보도자료도 키워드 없으면 제외)
        if not any(k in parsed["title"] for k in EVENT_KWS):
            continue
        items.append({
            "title": parsed["title"],
            "source": "한국원자력산업협회(KAIF)",
            "url": parsed["href"],
            "published": datetime.now().strftime("%Y-%m-%d"),
            "category": "업계 행사",
            "summary": "",
            "region": "국내",
            "end_date": parsed["deadline"],
            "location": "",
        })
    if items:
        print(f"    KAIF 행사: {len(items)}건")
    return items


def fetch_karp_events() -> list:
    """대한방사선방어학회(KARP) 공식 행사 수집 — cl_Idx 스캔 방식"""
    items = []
    try:
        # 현재 연도 기준으로 cl_Idx 탐색 범위 설정 (최근 70부터 상향 스캔)
        # cl_Idx 패턴: 연간 3~4개 행사 (동계/춘계/하계/추계)
        from datetime import timedelta
        today = datetime.now()
        cutoff_past = (today - timedelta(days=180)).strftime("%Y-%m-%d")
        cutoff_future = (today + timedelta(days=365)).strftime("%Y-%m-%d")

        # 유효 cl_Idx 탐색 (연속으로 내용 없으면 중단)
        empty_count = 0
        for cl_idx in range(70, 100):
            if empty_count >= 5:
                break
            try:
                r = requests.get(
                    f"https://karp.or.kr/index.php?hCode=CONFERENCE_INFO&cl_Idx={cl_idx}",
                    headers=HEADERS, timeout=10, verify=False
                )
                soup = BeautifulSoup(r.text, "html.parser")
                page_text = soup.get_text("\n", strip=True)

                # 날짜 패턴 탐지
                dates_found = re.findall(r'20(?:25|26|27)\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}', page_text)
                event_names = re.findall(
                    r'(20\d{2}년\s*(?:동계|춘계|하계|추계)\s*(?:학술대회|워크숍))',
                    page_text
                )

                if not dates_found and not event_names:
                    empty_count += 1
                    continue
                empty_count = 0

                # 날짜 정제
                def parse_karp_date(raw):
                    cleaned = re.sub(r'\s+', '', raw)  # "2026. 8.27" → "2026.8.27"
                    m = re.match(r'(\d{4})\.(\d{1,2})\.(\d{1,2})', cleaned)
                    if m:
                        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
                    return ""

                parsed_dates = [parse_karp_date(d) for d in dates_found]
                parsed_dates = [d for d in parsed_dates if d]  # 빈 값 제거
                if not parsed_dates:
                    continue

                start_dt = parsed_dates[0]
                # end_dt은 start_dt 이후인 날짜 중 가장 가까운 것
                end_dt = ""
                for pd in parsed_dates[1:]:
                    if pd >= start_dt:
                        end_dt = pd
                        break

                # 날짜 범위 필터 (과거 6개월 ~ 미래 1년)
                if start_dt < cutoff_past and (not end_dt or end_dt < cutoff_past):
                    continue
                if start_dt > cutoff_future:
                    continue

                # 행사명
                if event_names:
                    event_title = event_names[0].strip()
                else:
                    # 텍스트에서 행사명 추출 시도
                    lines = [l.strip() for l in page_text.split("\n") if l.strip() and len(l.strip()) > 5]
                    event_lines = [l for l in lines if "대한방사선방어학회" in l or "KARP" in l
                                   or any(k in l for k in ["학술대회", "워크숍", "심포"])]
                    event_title = event_lines[0][:80] if event_lines else f"대한방사선방어학회 행사 (cl_Idx={cl_idx})"

                items.append({
                    "title": event_title,
                    "source": "대한방사선방어학회(KARP)",
                    "url": f"https://karp.or.kr/index.php?hCode=CONFERENCE_INFO&cl_Idx={cl_idx}",
                    "published": datetime.now().strftime("%Y-%m-%d"),
                    "category": "업계 행사",
                    "summary": "",
                    "region": "국내",
                    "end_date": end_dt,
                    "location": "",
                })
            except Exception:
                empty_count += 1
    except Exception as e:
        print(f"  [오류] KARP 행사: {e}")
    if items:
        print(f"    KARP 행사: {len(items)}건")
    return items


def fetch_bizinfo_announcements() -> list:
    """비즈인포(bizinfo.go.kr) 방사선·과학계통 지원사업 공고 수집.
    - pblancId 파싱으로 상세 URL 직접 구성
    - 상세 페이지의 '출처 바로가기' 링크를 원본 기관 URL로 저장
    """
    items = []
    sess = requests.Session()
    sess.headers.update(HEADERS)
    try:
        sess.get("https://www.bizinfo.go.kr/sii/siia/selectSIIA200View.do",
                 timeout=15, verify=False)
        seen_ids = set()
        for page in range(1, 16):  # 최대 15페이지 순회
            r = sess.get(
                "https://www.bizinfo.go.kr/sii/siia/selectSIIA200View.do",
                params={"rows": "30", "cpage": str(page)},  # 마감 제한 없이 최근 공고 전체
                timeout=15, verify=False
            )
            soup = BeautifulSoup(r.text, "html.parser")
            page_hits = 0
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                txt = a.get_text(strip=True)
                if "Detail" not in href or not txt or len(txt) < 5:
                    continue
                if not any(k in txt for k in ANNOUNCE_SCIENCE_KWS):
                    continue
                # pblancId 추출
                m = re.search(r'pblancId=(PBLN_\w+)', href)
                if not m:
                    continue
                pblanc_id = m.group(1)
                if pblanc_id in seen_ids:
                    continue
                seen_ids.add(pblanc_id)
                page_hits += 1

                # 신청기간(마감일) — 같은 tr에서 파싱
                parent_tr = a.find_parent("tr")
                start_dt, end_dt = "", ""
                if parent_tr:
                    dates = re.findall(
                        r'(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})',
                        parent_tr.get_text()
                    )
                    if dates:
                        start_dt, end_dt = dates[0]

                # 상세 페이지에서 원본 기관 URL 추적
                detail_url = (f"https://www.bizinfo.go.kr/sii/siia/"
                              f"selectSIIA200Detail.do?pblancId={pblanc_id}")
                original_url = detail_url
                try:
                    dr = sess.get(detail_url, timeout=12, verify=False)
                    dsoup = BeautifulSoup(dr.text, "html.parser")
                    # '출처 바로가기' or '온라인신청 바로가기' 링크가 원본
                    for anchor in dsoup.find_all("a", href=True):
                        atxt = anchor.get_text(strip=True)
                        ahref = anchor.get("href", "")
                        if ("출처" in atxt or "원문" in atxt) and ahref.startswith("http") and "bizinfo" not in ahref:
                            original_url = ahref
                            break
                    time.sleep(0.2)
                except Exception:
                    pass

                # 소관부처/주관기관 추출
                # 컬럼 순서: [번호, 지원분야, 사업명, 신청기간, 소관부처, 주관기관, 등록일, 조회수]
                source_name = "비즈인포"
                if parent_tr:
                    tds = parent_tr.find_all("td")
                    org = tds[5].get_text(strip=True) if len(tds) > 5 else ""
                    dept = tds[4].get_text(strip=True) if len(tds) > 4 else ""
                    # 주관기관 우선, 없으면 소관부처
                    candidate = org if (org and len(org) <= 30 and not org.isdigit()) else dept
                    if candidate and len(candidate) <= 30 and not candidate.isdigit():
                        source_name = candidate

                items.append({
                    "title": txt[:120],
                    "source": source_name,
                    "url": original_url,
                    "published": start_dt or datetime.now().strftime("%Y-%m-%d"),
                    "category": "국내외 공고",
                    "summary": "",
                    "region": "국내",
                    "end_date": end_dt,
                    "location": "",
                })
            if page_hits == 0 and page > 5:
                break
            time.sleep(0.4)
    except Exception as e:
        print(f"  [오류] bizinfo: {e}")
    if items:
        print(f"    bizinfo 공고: {len(items)}건")
    return items


def fetch_srome_announcements() -> list:
    """KEIT SROME(srome.keit.re.kr) 방사선·과학계통 R&D 과제 공고 수집.
    prgmId=XPG201040000a, 방사선+과학계통 키워드 필터링.
    """
    PRGM_ID = "XPG201040000a"
    items = []
    sess = requests.Session()
    sess.headers.update(HEADERS)
    try:
        sess.get(
            f"https://srome.keit.re.kr/srome/biz/perform/opnnPrpsl/retrieveTaskAnncmListView.do?prgmId={PRGM_ID}",
            timeout=15, verify=False
        )
        seen = set()
        for page in range(1, 11):
            r = sess.get(
                "https://srome.keit.re.kr/srome/biz/perform/opnnPrpsl/retrieveTaskAnncmListView.do",
                params={"prgmId": PRGM_ID, "pageIndex": str(page), "rcveStatus": "all"},
                timeout=15, verify=False
            )
            soup = BeautifulSoup(r.text, "html.parser")
            page_items = 0
            for a in soup.find_all("a"):
                onclick = a.get("onclick", "")
                txt = a.get_text(strip=True)
                if "f_detail" not in onclick or not txt or len(txt) < 5:
                    continue
                if not any(k.lower() in txt.lower() for k in ANNOUNCE_SCIENCE_KWS):
                    continue
                m = re.search(r"f_detail\('([^']+)',\s*'([^']+)'\)", onclick)
                if not m:
                    continue
                ancm_id, bsns_yy = m.group(1), m.group(2)
                if ancm_id in seen:
                    continue
                seen.add(ancm_id)
                page_items += 1

                # 상세 페이지에서 접수기간 파싱
                start_dt, end_dt = "", ""
                try:
                    dr = sess.post(
                        "https://srome.keit.re.kr/srome/biz/perform/opnnPrpsl/retrieveTaskAnncmInfoView.do",
                        data={"prgmId": PRGM_ID, "ancmId": ancm_id, "bsnsYy": bsns_yy,
                              "srchKwd": "", "pageIndex": str(page), "rcveStatus": "all"},
                        timeout=15, verify=False
                    )
                    detail_soup = BeautifulSoup(dr.text, "html.parser")
                    detail_text = detail_soup.get_text()
                    # "접수기간|2026-06-08 09:00 ~ 2026-06-29 18:00|등록일|" 패턴
                    dm = re.search(
                        r'접수기간\D*(\d{4}-\d{2}-\d{2}).*?~.*?(\d{4}-\d{2}-\d{2})',
                        detail_text, re.DOTALL
                    )
                    if dm:
                        start_dt, end_dt = dm.group(1), dm.group(2)
                    time.sleep(0.3)
                except Exception:
                    pass

                detail_url = (
                    f"https://srome.keit.re.kr/srome/biz/perform/opnnPrpsl/"
                    f"retrieveTaskAnncmInfoView.do?ancmId={ancm_id}&bsnsYy={bsns_yy}&prgmId={PRGM_ID}"
                )
                items.append({
                    "title": txt[:120],
                    "source": "KEIT(한국산업기술기획평가원)",
                    "url": detail_url,
                    "published": start_dt or datetime.now().strftime("%Y-%m-%d"),
                    "category": "국내외 공고",
                    "summary": "",
                    "region": "국내",
                    "end_date": end_dt,
                    "location": "",
                })
            if page_items == 0 and page > 3:
                break
            time.sleep(0.5)
    except Exception as e:
        print(f"  [오류] KEIT SROME: {e}")
    if items:
        print(f"    KEIT SROME 공고: {len(items)}건")
    return items


def _get_media_rank(source: str) -> int:
    """언론사 파급력 점수 반환"""
    src = source.lower()
    for key, rank in MEDIA_RANK.items():
        if key in src:
            return rank
    return 1


def _normalize_event_key(title: str) -> str:
    """행사 제목 정규화 — 연도·숫자·특수문자 제거 후 중복 감지용 키 생성"""
    t = re.sub(r'\d+', '', title)
    t = re.sub(r'[^\w가-힣a-zA-Z]', '', t)
    return t.lower().strip()


def _deduplicate_kara_events(items: list) -> list:
    """
    KARA 이벤트 중복 제거.
    1) URL 기반 완전 중복 제거
    2) 공식 소스(kara.or.kr / KARA Campus / RATIS) 항목은 그대로 유지
    3) 보도자료는 같은 행사끼리 묶어 파급력 높은 언론사 버전만 유지
    """
    # URL 중복 제거
    url_seen = {}
    for item in items:
        url = item.get("url", "")
        if url not in url_seen:
            url_seen[url] = item
    items = list(url_seen.values())

    official = [i for i in items if i.get("source") in KARA_OFFICIAL_SOURCES]
    press    = [i for i in items if i.get("source") not in KARA_OFFICIAL_SOURCES]

    # 공식 소스 키 집합 (보도자료와 동일 이벤트면 보도자료 제외)
    official_keys = {_normalize_event_key(i.get("title", "")) for i in official}

    # 보도자료 그룹화 → 파급력 순 채택
    groups = {}
    for item in press:
        key = _normalize_event_key(item.get("title", ""))
        if not key or key in official_keys:
            continue
        if key not in groups:
            groups[key] = item
        else:
            if _get_media_rank(item.get("source", "")) > _get_media_rank(groups[key].get("source", "")):
                groups[key] = item

    return official + list(groups.values())


def _title_keywords(title: str) -> set:
    """제목에서 의미있는 키워드 집합 추출.
    - 한글 2자 이상 / 영문 3자 이상, 불용어 제외
    - 4자 이상 복합어는 2자 단위 앞/뒤 분해도 추가 (띄어쓰기 차이 극복)
    - 기관명 축약어 정규화: '원안위원장' → '원안위' 등 접미사 제거
    """
    STOPWORDS = {
        "위한", "대한", "관련", "통해", "따른", "의한", "등의", "있는", "하는", "에서",
        "으로", "에게", "이후", "이전", "까지", "부터", "대해", "관해", "하여", "되어",
        "있어", "하고", "이며", "으며", "이고", "이다", "한다", "했다", "된다", "됩니다",
        "뉴스", "기자", "특파원", "보도", "단독", "속보", "긴급", "확인",
        "방사선", "원자력", "원전", "방사성", "방사능", "안전", "관리", "기술",
        "개발", "연구", "사업", "추진", "시행", "발표", "진행", "현황", "강화",
        "지원", "대책", "방안", "계획", "목표", "결과", "제공", "운영", "구축",
        "안전관리", "현장점검", "안전점검",  # 복합 stopword 추가
    }
    # 기관명 접미사: 짧은 것부터 시도해 최대한 stem을 보존
    ORG_SUFFIXES = ['원장', '위원장', '장관', '대표', '사장', '총장', '회장']
    ORG_SUFFIXES_SORTED = sorted(ORG_SUFFIXES, key=len)  # 짧은 것 먼저

    def _strip_org_suffix(w: str) -> str:
        for suf in ORG_SUFFIXES_SORTED:
            if w.endswith(suf) and len(w) - len(suf) >= 2:
                return w[:-len(suf)]
        return w

    raw_words = re.findall(r'[가-힣]{2,}|[A-Za-z]{3,}', title)
    expanded = set()
    for w in raw_words:
        if w in STOPWORDS:
            continue
        # 기관명 접미사 제거 버전도 추가 (예: 원안위원장 → 원안위)
        normalized = _strip_org_suffix(w)
        if len(normalized) >= 2 and normalized not in STOPWORDS:
            expanded.add(normalized)
        if w not in STOPWORDS:
            expanded.add(w)
        # 4자 이상 복합어 앞/뒤 2자씩 분해 추가 (현장점검 → 현장, 점검)
        if len(w) == 4:
            front, back = w[:2], w[2:]
            for part in (front, back):
                if part not in STOPWORDS and len(part) >= 2:
                    expanded.add(part)
    return expanded


def _is_radiation_relevant(item: dict) -> bool:
    """산업 뉴스 항목이 방사선과 직접 관련 있는지 확인.
    원전·원자력 내용이라도 방사선 연관 키워드가 없으면 제외.
    """
    RADIATION_KWS = {
        "방사선", "방사성", "방사능",
        "방사성의약품", "방사성동위원소", "동위원소", "방사성폐기물",
        "X선", "엑스선", "X-ray", "xray",
        "중성자", "베타선", "알파선", "감마선",
        "의료방사선", "방사선치료", "핵의학", "PET", "SPECT",
        "방폐물", "방폐장", "사용후핵연료",
        "비파괴검사", "비파괴",
        "방사선사", "방사선사",
        "방사선량", "피폭", "선량", "제염",
        "원자력안전", "방사선안전", "원자력안전위원회", "원안위",
        "RASIS", "RATIS",
    }
    # 원전·원자력만 있고 방사선 연관 없는 경우 제외 대상 마커
    # (RADIATION_KWS 체크를 먼저 하므로 핵의학·핵연료방사성 등은 이미 통과됨)
    NUCLEAR_ONLY_MARKERS = {
        "원전", "원자력", "SMR", "소형모듈원자로", "핵연료", "핵발전",
        "두코바니", "체르노빌", "후쿠시마",
        "핵 동맹", "핵무장", "핵무기", "핵잠수함", "핵전쟁", "핵 협력",
    }

    text = (item.get("title", "") + " " + item.get("summary", "") + " " + item.get("source", "")).lower()
    title = item.get("title", "")

    # 방사선 키워드가 하나라도 있으면 통과
    for kw in RADIATION_KWS:
        if kw.lower() in text:
            return True

    # 방사선 키워드 없는데 원전·원자력 마커만 있으면 제외
    has_nuclear = any(m in title for m in NUCLEAR_ONLY_MARKERS)
    if has_nuclear:
        return False

    # 둘 다 없으면 일단 포함 (비파괴검사, 핵의학 등 다른 도메인)
    return True


def _deduplicate_industry_news(items: list) -> list:
    """산업 뉴스 중복 제거.
    동일 사건을 여러 언론사가 보도한 경우 파급력 높은 언론사 버전 1건만 유지.
    1단계: URL 완전 중복 제거
    2단계: 제목 키워드 3개 이상 공유 시 같은 사건으로 판단 → 파급력 높은 언론사 채택
    """
    # 1단계: URL 중복 제거
    url_seen = {}
    for item in items:
        url = item.get("url", "")
        if url not in url_seen:
            url_seen[url] = item
    items = list(url_seen.values())

    # 2단계: 키워드 유사도 기반 그룹핑
    # 대표 아이템 리스트와 키워드 셋을 함께 유지
    groups: list[tuple] = []  # [(item, keywords_set)]

    for item in items:
        kws = _title_keywords(item.get("title", ""))
        if not kws:
            groups.append((item, kws))
            continue

        merged = False
        for idx, (rep, rep_kws) in enumerate(groups):
            # 교집합 2개 이상이면 같은 사건 (도메인 공통어 제거 후 2개면 충분히 구체적)
            if len(kws & rep_kws) >= 2:
                # 파급력 비교 후 더 높은 언론사로 교체
                if _get_media_rank(item.get("source", "")) > _get_media_rank(rep.get("source", "")):
                    groups[idx] = (item, rep_kws | kws)
                else:
                    groups[idx] = (rep, rep_kws | kws)
                merged = True
                break

        if not merged:
            groups.append((item, kws))

    result = [g[0] for g in groups]
    result.sort(key=lambda x: x.get("published", ""), reverse=True)
    return result


def fetch_kara_official() -> list:
    """kara.or.kr 메인 페이지에서 협회 공식 소식·행사 수집.
    Ty=4(협회동정), Ty=5(사업현황), Ty=6(보도자료)는 전부 포함.
    Ty=1(공지사항)은 KARA 주최 이벤트/대회만 포함.
    채용(Ty=2), 입찰(Ty=3), 회원사채용(Ty=7) 제외.
    """
    items = []
    BASE = "https://www.koara.or.kr/new"
    # 메인 페이지에서 최신 항목 파싱
    SOURCES = [
        f"{BASE}/main/main.php",
        f"{BASE}/notice/notice.php?Ty=1",   # 공지사항 전체 목록
        f"{BASE}/notice/movement.php?Ty=4", # 협회동정
        f"{BASE}/notice/report.php?Ty=6",   # 보도자료
    ]
    # KARA 이벤트로 분류할 공지 키워드
    KARA_NOTICE_KWS = [
        "KARA", "방사선진흥협회", "아이디어", "경진대회", "공모전",
        "이용실태", "창의", "융합", "방사선기술", "협회 주최", "협회 주관",
        "WCI", "IRPA", "IAEA", "국제협력", "MOU",
    ]
    # 제외할 타입
    EXCLUDE_TY = {"2", "3", "7", "9"}

    seen = set()
    for page_url in SOURCES:
        try:
            resp = requests.get(page_url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                title = a.get_text(strip=True)
                if len(title) < 8:
                    continue
                # 실제 기사 링크만 (notice_view, movement_view, report_view)
                if "_view" not in href:
                    continue
                # URL 절대 경로 변환
                if not href.startswith("http"):
                    # ../notice/xxx → /new/notice/xxx
                    href_clean = re.sub(r'^\.\./', '', href)
                    full_url = f"https://www.koara.or.kr/new/{href_clean.lstrip('/')}"
                else:
                    full_url = href
                if full_url in seen:
                    continue

                # Ty 추출
                ty_m = re.search(r'Ty=(\d+)', href)
                ty = ty_m.group(1) if ty_m else "1"

                # 제외 타입 스킵
                if ty in EXCLUDE_TY:
                    continue

                # Ty=1 공지사항은 KARA 이벤트 키워드 있을 때만
                if ty == "1" and not any(kw in title for kw in KARA_NOTICE_KWS):
                    continue

                seen.add(full_url)

                # 날짜 추출 (부모 요소 텍스트)
                parent = a.find_parent(["li", "tr", "div", "td"])
                parent_txt = parent.get_text() if parent else title
                dm = re.search(r'(\d{4})[.\-](\d{1,2})[.\-](\d{1,2})', parent_txt)
                pub = (f"{dm.group(1)}-{dm.group(2).zfill(2)}-{dm.group(3).zfill(2)}"
                       if dm else datetime.now().strftime("%Y-%m-%d"))

                items.append({
                    "title": title,
                    "source": "한국방사선진흥협회",
                    "url": full_url,
                    "published": pub,
                    "category": "KARA 주요이벤트",
                    "summary": "",
                    "region": "국내",
                    "end_date": "",
                    "location": "",
                })
        except Exception as e:
            print(f"  [오류] KARA 공식({page_url}): {e}")
    if items:
        print(f"    KARA 공식: {len(items)}건")
    return items


def fetch_kara_campus_events() -> list:
    """KARA Campus(kara-campus.or.kr) 교육 과정 수집.
    실제 강좌/교육 목록만 수집, 네비게이션 항목 제외.
    """
    items = []
    BASE = "https://kara-campus.or.kr"
    PAGES = [
        f"{BASE}/main/main.do",
    ]
    # 실제 교육 과정 필수 키워드 (하나 이상 포함해야 함)
    COURSE_KWS = [
        "과정", "강좌", "교육(정기)", "교육(수시)", "마스터클래스",
        "R-class", "RT-ON", "Geant4", "SRI", "RI면허", "방사성의약품",
        "방사선작업종사자", "원전 해체", "방사성폐기물", "사이클로트론",
        "집중교육", "직장교육",
    ]
    # 제외할 네비게이션 텍스트
    NAV_EXACT = {"오프라인교육", "온라인교육", "혼합교육", "교육 과정 안내",
                 "교육과정안내", "수강신청", "교육일정", "강사소개"}
    seen = set()
    for page_url in PAGES:
        try:
            resp = requests.get(page_url, headers=HEADERS, timeout=12)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                if not href.startswith("http"):
                    href = BASE + "/" + href.lstrip("/")
                if href in seen or href == page_url:
                    continue

                raw_txt = a.get_text(strip=True)
                # "대체텍스트오프라인[...]" 접두어 제거
                txt = re.sub(r'^대체텍스트(오프라인|온라인|혼합교육|집합교육|집체)?', '', raw_txt).strip()
                # 공지 접두어 정리: "공지제목날짜" 형식 → 날짜 제거
                txt = re.sub(r'^공지', '', txt).strip()
                txt = re.sub(r'\d{4}-\d{2}-\d{2}$', '', txt).strip()

                if len(txt) < 12:
                    continue
                if txt in NAV_EXACT:
                    continue
                if not any(k.lower() in txt.lower() for k in COURSE_KWS):
                    continue

                seen.add(href)
                parent = a.find_parent(["tr", "li", "div"])
                parent_txt = parent.get_text() if parent else ""
                dm = re.search(r'(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})', parent_txt)
                pub = (f"{dm.group(1)}-{dm.group(2).zfill(2)}-{dm.group(3).zfill(2)}"
                       if dm else datetime.now().strftime("%Y-%m-%d"))
                items.append({
                    "title": txt[:100],
                    "source": "KARA Campus",
                    "url": href,
                    "published": pub,
                    "category": "KARA 주요이벤트",
                    "summary": "",
                    "region": "국내",
                    "end_date": "",
                    "location": "",
                })
        except Exception as e:
            print(f"  [오류] KARA Campus({page_url}): {e}")
    if items:
        print(f"    KARA Campus: {len(items)}건")
    return items


def fetch_ratis_news() -> list:
    """RATIS(방사선기술통합정보시스템) 전문분석 보고서 수집.
    RATIS는 JS 렌더링이 필요해 메인 페이지 직접 스크래핑 불가.
    정적으로 접근 가능한 보고서 목록 페이지만 수집한다.
    """
    items = []
    BASE = "https://www.ratis.or.kr"
    PAGES = [
        (f"{BASE}/ratis/cnterPblct/analsAcademyReport/retrieveUsrAnalsAcademyReportList.do", "학회리뷰"),
        (f"{BASE}/ratis/cnterPblct/analsForumReport/retrieveUsrAnalsForumReportList.do", "포럼보고서"),
        (f"{BASE}/ratis/rtTrend/retrieveUsrRtTrendList.do", "전문분석"),
    ]
    # 실제 보고서/기사 URL 패턴 (상세 조회 URL 포함)
    DETAIL_PATTERNS = ["Detail", "detail", "view", "View", "Info", "info"]
    rad_kws = ["방사선", "방사성", "원자력", "핵의학", "동위원소", "방호", "방재", "KARA"]
    seen = set()
    for page_url, label in PAGES:
        try:
            resp = requests.get(page_url, headers=HEADERS, timeout=12)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                txt = a.get_text(strip=True)
                href = a.get("href", "")
                if len(txt) < 10:
                    continue
                # 실제 상세 링크만
                if not any(p in href for p in DETAIL_PATTERNS):
                    continue
                if not any(k in txt for k in rad_kws):
                    continue
                if not href.startswith("http"):
                    href = BASE + href if href.startswith("/") else BASE + "/" + href
                if href in seen:
                    continue
                seen.add(href)
                parent = a.find_parent(["tr", "li", "div"])
                parent_txt = parent.get_text() if parent else ""
                dm = re.search(r'(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})', parent_txt)
                pub = (f"{dm.group(1)}-{dm.group(2).zfill(2)}-{dm.group(3).zfill(2)}"
                       if dm else datetime.now().strftime("%Y-%m-%d"))
                items.append({
                    "title": txt[:100],
                    "source": "RATIS",
                    "url": href,
                    "published": pub,
                    "category": "KARA 주요이벤트",
                    "summary": "",
                    "region": "국내",
                    "end_date": "",
                    "location": "",
                })
        except Exception as e:
            print(f"  [오류] RATIS {label}: {e}")
    if items:
        print(f"    RATIS: {len(items)}건")
    return items


def fetch_kara_news() -> list:
    """KARA 주요이벤트 통합 수집 — 공식 소스 우선, 보도자료 중복 제거"""
    all_items = []

    # 1. 공식 소스 (kara.or.kr, KARA Campus, RATIS)
    all_items.extend(fetch_kara_official())
    all_items.extend(fetch_kara_campus_events())
    all_items.extend(fetch_ratis_news())

    # 2. Google News 보도자료 (이미 run_collection 에서 수집됨 — 여기서는 별도 수집 안 함)
    #    → run_collection 에서 Google News 결과 중 KARA 카테고리 항목을 전달받아 함께 dedup 처리

    # 3. 중복 제거
    deduped = _deduplicate_kara_events(all_items)
    print(f"    KARA 이벤트 합계 (dedup 후): {len(deduped)}건")
    return deduped


# ──────────────────────────────────────────
# 메인 수집 실행
# ──────────────────────────────────────────

def run_collection() -> dict:
    """전체 수집 실행 - 매일 오전 5시 호출"""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 방사선 소식 수집 시작")
    database.init_db()

    all_items = []

    # 1. Google News RSS — 산업 뉴스 / KARA / 국제 동향
    print("  Google News RSS 수집 중...")
    for query, category in GOOGLE_NEWS_QUERIES:
        items = fetch_google_news_rss(query, category)
        all_items.extend(items)
        print(f"    '{query}': {len(items)}건")
        time.sleep(1)

    # 2. 전용 뉴스 RSS
    print("  전용 뉴스 RSS 수집 중...")
    for feed_url, source, category in RSS_FEEDS:
        items = fetch_rss_feed(feed_url, source, category)
        all_items.extend(items)
        print(f"    {source}: {len(items)}건")
        time.sleep(0.5)

    # 3. KARA 공식 소식 (kara.or.kr + KARA Campus + RATIS)
    print("  KARA 공식 소식 수집 중...")
    # Google News에서 수집된 KARA 보도자료와 합쳐서 중복 제거
    google_kara = [i for i in all_items if i.get("category") == "KARA 주요이벤트"]
    # 기존 all_items에서 KARA 카테고리 제거 후 dedup된 버전으로 교체
    all_items = [i for i in all_items if i.get("category") != "KARA 주요이벤트"]
    kara_official = fetch_kara_official()
    kara_campus   = fetch_kara_campus_events()
    kara_ratis    = fetch_ratis_news()
    kara_combined = _deduplicate_kara_events(kara_official + kara_campus + kara_ratis + google_kara)
    all_items.extend(kara_combined)
    print(f"    KARA 최종: {len(kara_combined)}건 (dedup 완료)")
    database.trim_kara_events(max_count=20)

    # 4. 국내외 공고 (실제 공고 전용)
    print("  국내외 공고 수집 중...")
    announce_items = fetch_announcements()
    all_items.extend(announce_items)

    # 5. 업계 행사 (실제 행사 전용)
    print("  업계 행사 수집 중...")
    event_items = fetch_events()
    all_items.extend(event_items)

    # 180일 이내 뉴스만 보존
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
    all_items = [i for i in all_items if not (i.get("published") and i["published"] < cutoff)]

    # 산업 뉴스: 원전·원자력 전용(방사선 무관) 기사 제외 후 dedup
    industry = [i for i in all_items if i.get("category") == "산업 뉴스"]
    others   = [i for i in all_items if i.get("category") != "산업 뉴스"]
    industry_filtered = [i for i in industry if _is_radiation_relevant(i)]
    excluded = len(industry) - len(industry_filtered)
    if excluded:
        print(f"  산업 뉴스 방사선 무관 제외: {len(industry)}건 → {len(industry_filtered)}건 ({excluded}건 제외)")
    industry_deduped = _deduplicate_industry_news(industry_filtered)
    print(f"  산업 뉴스 dedup: {len(industry_filtered)}건 → {len(industry_deduped)}건")
    all_items = industry_deduped + others

    # 전체 URL 중복 제거
    seen_urls = set()
    unique_items = []
    for item in all_items:
        if item["url"] in seen_urls:
            continue
        seen_urls.add(item["url"])
        unique_items.append(item)

    # 하루 최대 50건
    unique_items = unique_items[:50]

    # DB 저장
    added = database.insert_news(unique_items)
    database.log_collection(added, "success", f"총 {len(unique_items)}건 처리, {added}건 신규 저장")

    result = {
        "total_fetched": len(unique_items),
        "added": added,
        "status": "success",
    }
    print(f"  완료: {len(unique_items)}건 수집, {added}건 신규 저장\n")

    # Obsidian 마크다운 저장
    save_obsidian_note(unique_items, added)

    return result


def save_obsidian_note(items: list, added: int):
    """수집한 뉴스를 Obsidian용 마크다운 파일로 저장"""
    try:
        os.makedirs(OBSIDIAN_DIR, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        filepath = os.path.join(OBSIDIAN_DIR, f"{today}.md")

        cats = {
            "KARA 주요이벤트": [],
            "산업 뉴스": [],
            "국내외 공고": [],
            "업계 행사": [],
            "국제 동향": [],
        }
        for item in items:
            cat = item.get("category", "산업 뉴스")
            if cat in cats:
                cats[cat].append(item)

        lines = [
            f"# 방사선 소식 — {today}",
            f"",
            f"> 수집 시각: {datetime.now().strftime('%H:%M')}  |  신규 {added}건",
            f"",
        ]

        cat_emoji = {
            "KARA 주요이벤트": "🏢",
            "산업 뉴스": "📰",
            "국내외 공고": "📋",
            "업계 행사": "🎤",
            "국제 동향": "🌐",
        }

        for cat, emoji in cat_emoji.items():
            cat_items = cats.get(cat, [])
            if not cat_items:
                continue
            lines.append(f"## {emoji} {cat} ({len(cat_items)}건)")
            lines.append("")
            for item in cat_items:
                title = item.get("title", "")
                url = item.get("url", "")
                source = item.get("source", "")
                pub = item.get("published", "")
                region = item.get("region", "")
                end_date = item.get("end_date", "")
                location = item.get("location", "")
                summary = item.get("summary", "")

                region_tag = f" [{region}]" if region else ""
                lines.append(f"### [{title}]({url}){region_tag}")
                meta = f"- **출처:** {source}  |  **날짜:** {pub}"
                if end_date:
                    meta += f"  |  **마감/종료:** {end_date}"
                if location:
                    meta += f"  |  **장소:** {location}"
                lines.append(meta)
                if summary:
                    lines.append(f"- {summary[:200]}")
                lines.append("")

        lines.append("---")
        lines.append(f"*Generated by 방사선 소식 앱 (KARA)*")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        print(f"  Obsidian 노트 저장: {filepath}")
    except Exception as e:
        print(f"  [오류] Obsidian 노트 저장 실패: {e}")


if __name__ == "__main__":
    run_collection()
