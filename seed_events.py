"""업계 행사 초기 데이터 삽입 스크립트 — 기존 14건 삭제 후 검증된 10건 삽입"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import database

database.init_db()

conn = database.get_conn()
deleted = conn.execute("DELETE FROM news WHERE category='업계 행사'").rowcount
conn.commit()
conn.close()
print(f"기존 업계 행사 {deleted}건 삭제")

EVENTS = [
    # ─── 국내 7건 ───
    {
        "title": "ICRS15-ANS RPSD2026 (제15회 국제 방사선 차폐 학술대회)",
        "source": "대한방사선방어학회(KARP)",
        "url": "https://karp.or.kr/index.php?page=view&pg=1&idx=10909&hCode=BOARD&bo_idx=8",
        "published": "2026-10-25",
        "end_date": "2026-10-29",
        "category": "업계 행사",
        "region": "국내",
        "location": "대한민국",
        "summary": "대한방사선방어학회·한국원자력학회·미국원자력학회 공동 주최 국제 방사선 차폐 학술대회",
    },
    {
        "title": "2026년 KARP 추계학술대회",
        "source": "대한방사선방어학회(KARP)",
        "url": "https://karp.or.kr/index.php?page=view&pg=1&idx=10902&hCode=BOARD&bo_idx=8",
        "published": "2026-10-29",
        "end_date": "2026-10-31",
        "category": "업계 행사",
        "region": "국내",
        "location": "롯데호텔 제주",
        "summary": "대한방사선방어학회 2026년 추계학술대회. ICRS15 참가자 등록비 면제 혜택 제공",
    },
    {
        "title": "AOCMP 2026 (제17회 아시아-오세아니아 의료물리학 학술대회)",
        "source": "AOCMP 2026",
        "url": "https://www.aocmp2026.org/",
        "published": "2026-09-09",
        "end_date": "2026-09-11",
        "category": "업계 행사",
        "region": "국내",
        "location": "부산항국제전시장(BPEX), 부산",
        "summary": "아시아-오세아니아 의료물리학 국제 학술대회. 방사선 치료 물리학, 진단 영상 물리학 등 다루는 국제 학술행사",
    },
    {
        "title": "KCR 2026 — KARP 공동 심포지엄 (제82차 대한영상의학회 학술대회)",
        "source": "대한영상의학회(KSR)",
        "url": "https://www.kcr4u.org/",
        "published": "2026-09-09",
        "end_date": "2026-09-12",
        "category": "업계 행사",
        "region": "국내",
        "location": "Kintex 2, 고양",
        "summary": "대한영상의학회 연례 학술대회. 대한방사선방어학회(KARP)와 공동 심포지엄 포함. 방사선 영상 진단 및 방사선 안전 주제 다룸",
    },
    {
        "title": "KSMO 2026 (19차 대한종양내과학회 학술대회 & FACO 국제학술대회)",
        "source": "대한종양내과학회(KSMO)",
        "url": "https://www.ksmoconference.org/",
        "published": "2026-09-02",
        "end_date": "2026-09-04",
        "category": "업계 행사",
        "region": "국내",
        "location": "그랜드 인터컨티넨탈 서울 파르나스호텔, 서울",
        "summary": "대한종양내과학회 연례 학술대회 및 아시아임상종양연맹 국제학술대회. 방사선 항암 치료·방사성의약품 관련 세션 포함",
    },
    {
        "title": "APCMBE 2026 (제13차 아시아·태평양 의용생체공학 학술대회)",
        "source": "대한의용생체공학회",
        "url": "https://apcmbe2026.org/",
        "published": "2026-11-04",
        "end_date": "2026-11-07",
        "category": "업계 행사",
        "region": "국내",
        "location": "EXCO, 대구",
        "summary": "아시아·태평양 의용생체공학 국제 학술대회. 의료방사선 계측, 방사선 치료 기기 등 의공학 세션 포함",
    },
    {
        "title": "2026 원자력협의회 심포지엄",
        "source": "대한방사선방어학회(KARP)",
        "url": "https://karp.or.kr/index.php?page=view&pg=1&idx=10894&hCode=BOARD&bo_idx=9",
        "published": "2026-07-09",
        "end_date": "2026-07-10",
        "category": "업계 행사",
        "region": "국내",
        "location": "대한민국",
        "summary": "원자력 관련 학회 공동 심포지엄. 방사선 안전관리·방사성폐기물 처리 등 발표 포함",
    },
    # ─── 국외 3건 ───
    {
        "title": "EANM'26 (유럽핵의학학회 연례 학술대회)",
        "source": "EANM",
        "url": "https://www.eanm.org/congresses/eanm26/",
        "published": "2026-10-17",
        "end_date": "2026-10-21",
        "category": "업계 행사",
        "region": "해외",
        "location": "Austria Center Vienna, Vienna, Austria",
        "summary": "유럽핵의학학회 연례 학술대회. 방사성의약품, PET/SPECT 영상, 방사선 내부 치료, 핵의학 최신 연구 발표",
    },
    {
        "title": "2026 Nuclear Energy Conference & Expo (ANS NECX)",
        "source": "ANS",
        "url": "https://nuclearenergyconference.org/",
        "published": "2026-08-24",
        "end_date": "2026-08-27",
        "category": "업계 행사",
        "region": "해외",
        "location": "Hilton Anatole, Dallas, TX",
        "summary": "미국원자력학회 주관 핵에너지 학술대회 및 엑스포. 방사선 안전, SMR, 핵연료 주기 등 다양한 세션 포함",
    },
    {
        "title": "ANS Global 2026 (Deploying Sustainable Nuclear Fuel Cycles)",
        "source": "ANS",
        "url": "https://www.ans.org/meetings/global2026/",
        "published": "2026-08-16",
        "end_date": "2026-08-20",
        "category": "업계 행사",
        "region": "해외",
        "location": "Westin Chicago River North, Chicago, IL",
        "summary": "미국원자력학회 Global 2026 학술대회. 핵연료 주기, 방사성폐기물 관리, 방사선 방호 분야 발표",
    },
]

added = database.insert_news(EVENTS)
print(f"신규 업계 행사 {added}건 삽입 완료")

conn2 = database.get_conn()
rows = conn2.execute(
    "SELECT title, published, end_date, region, location "
    "FROM news WHERE category='업계 행사' ORDER BY published"
).fetchall()
conn2.close()

print(f"\n현재 업계 행사 총 {len(rows)}건:")
for r in rows:
    print(f"  [{r['region']}] {r['published']}~{r['end_date']} | {r['title'][:58]}")
    print(f"         장소: {r['location'][:65]}")
