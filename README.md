# KARAdi Info — 방사선 산업 정보 플랫폼

한국방사선진흥협회(KARA) 방사선 산업 정보를 자동 수집하여 제공하는 PWA 앱.

🔗 **[https://karadiation-app.onrender.com](https://karadiation-app.onrender.com)**

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| 자동 수집 | 매일 오전 05:00 방사선 관련 뉴스 자동 수집 |
| 5개 카테고리 | 산업 뉴스 / KARA 주요이벤트 / 국내외 공고 / 업계 행사 / 국제 동향 |
| 검색 | 제목·출처·요약 전문 검색 |
| 읽음/즐겨찾기 | 기사별 읽음 표시, 즐겨찾기 저장 |
| AI 요약 | Claude API 기반 기사 요약 |
| 주요 이슈 | 사회적 영향력 점수 기반 Top 3 자동 선정 |
| PWA | iOS/Android 홈 화면 설치 지원 |

---

## 수집 규칙 (카테고리별)

| 카테고리 | 1회 수집 상한 | DB 누적 상한 | 우선순위 정렬 |
|----------|--------------|--------------|---------------|
| KARA 주요이벤트 | 10건 | 15건 자동 trim | 협회공식→RATIS→Campus→최신순 |
| 산업 뉴스 | 10건 | — | 최신순 |
| 국제 동향 | 10건 | — | 최신순 |
| 업계 행사 | 10건 | — | 최신순 |
| 국내외 공고 | 10건 | — | 최신순 |

---

## 수집 소스

- **Google News RSS** — 방사선, 원자력, 방사성의약품, 동위원소 등 키워드
- **에너지데일리 / 에너지안전신문 RSS** — 방사선 전문 매체
- **World Nuclear News RSS** — 국제 원자력 뉴스
- **한국방사선진흥협회** — KARA 공식 소식 (kara.or.kr)
- **KARA Campus** — 교육 강좌 (kara-campus.or.kr)
- **RATIS** — 방사선 기술 정보
- **KEIT / bizinfo** — 국내외 공고
- **KARP / ANS / EANM** — 업계 행사

---

## 배포 구조

```
GitHub (raion-nasun/KARAdiation-App, main)
    ↓ push → 자동 배포
Render.com
    ├── Flask 서버 (APScheduler 내장 — 매일 05:00 수집)
    ├── SQLite DB (data/news.db)
    └── PWA (manifest.json + sw.js)
```

### 코드 수정 → 배포

```bash
git add .
git commit -m "변경 내용"
git push origin main
# Render 2~3분 내 자동 배포
```

### 수동 수집 트리거

```bash
curl -X POST https://karadiation-app.onrender.com/api/collect \
     -H "Content-Type: application/json" -d "{}"
```

---

## 환경 변수 (Render 대시보드 설정)

| 변수 | 설명 |
|------|------|
| `ANTHROPIC_API_KEY` | AI 요약 기능용 Claude API 키 |
| `COLLECT_SECRET` | 수동 수집 엔드포인트 보호 키 (선택) |
| `DB_PATH` | DB 경로 (기본: `data/news.db`) |

---

## 파일 구조

```
방사선 소식 어플/
├── app.py              # Flask 서버 + APScheduler
├── collector.py        # 뉴스 수집 엔진
├── database.py         # SQLite DB 관리
├── seed_events.py      # 초기 시드 데이터 (업계 행사)
├── seed_intl.py        # 초기 시드 데이터 (국제 동향)
├── requirements.txt
├── static/
│   ├── style.css
│   ├── app.js
│   ├── sw.js           # Service Worker (PWA)
│   ├── manifest.json   # PWA 매니페스트
│   └── images/         # 아이콘 (icon-192, icon-512, apple-touch-icon)
├── templates/
│   └── index.html
├── data/
│   └── news.db         # SQLite DB (자동 생성)
└── daily-notes/        # 일별 수집 노트 (Obsidian)
```
