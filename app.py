"""
방사선 소식 대시보드 - Flask 웹 서버
"""
from flask import Flask, render_template, jsonify, request, Response
from apscheduler.schedulers.background import BackgroundScheduler
import database
import collector
import anthropic
import requests
import os
from bs4 import BeautifulSoup

# .env 파일에서 API 키 로드 (있는 경우)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
database.init_db()
database.migrate_regions()

# DB가 비어있으면 시드 데이터 자동 삽입 (Render 등 영구 디스크 없는 환경 대비)
def _auto_seed():
    conn = database.get_conn()
    total = conn.execute("SELECT COUNT(*) FROM news").fetchone()[0]
    conn.close()
    if total == 0:
        print("  [시드] DB가 비어있음 — 업계 행사·국제 동향 자동 시드 시작")
        try:
            import seed_events
        except Exception as e:
            print(f"  [시드] seed_events 오류: {e}")
        try:
            import seed_intl
        except Exception as e:
            print(f"  [시드] seed_intl 오류: {e}")
        print("  [시드] 완료")

_auto_seed()

# ──────────────────────────────────────────
# 스케줄러 (매일 오전 5시 자동 수집)
# ──────────────────────────────────────────
scheduler = BackgroundScheduler(timezone="Asia/Seoul")
scheduler.add_job(
    collector.run_collection,
    trigger="cron",
    hour=5,
    minute=0,
    id="daily_collect",
)
scheduler.start()

CATEGORIES = ["전체", "산업 뉴스", "KARA 주요이벤트", "국내외 공고", "업계 행사", "국제 동향"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ──────────────────────────────────────────
# 페이지 라우트
# ──────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", categories=CATEGORIES)


@app.route("/sw.js")
def service_worker():
    """sw.js를 동적으로 서빙 — 배포마다 캐시 버전 자동 갱신"""
    sw_path = os.path.join(os.path.dirname(__file__), "static", "sw.js")
    try:
        # app.js·style.css 중 최신 수정 시각을 버전으로 사용
        version = max(
            int(os.path.getmtime(os.path.join(os.path.dirname(__file__), "static", "app.js"))),
            int(os.path.getmtime(os.path.join(os.path.dirname(__file__), "static", "style.css"))),
        )
    except Exception:
        import time
        version = int(time.time())

    with open(sw_path, encoding="utf-8") as f:
        content = f.read().replace("{{CACHE_VERSION}}", f"kara-news-{version}")

    return Response(content, mimetype="application/javascript", headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Service-Worker-Allowed": "/",
    })


# ──────────────────────────────────────────
# API 라우트
# ──────────────────────────────────────────

@app.route("/api/news")
def api_news():
    category = request.args.get("category", "전체")
    search = request.args.get("search", "")
    starred = request.args.get("starred") == "1"
    unread = request.args.get("unread") == "1"
    offset = int(request.args.get("offset", 0))
    news = database.get_news(
        category=category,
        search=search,
        starred=starred,
        unread=unread,
        limit=50,
        offset=offset,
    )
    return jsonify(news)


@app.route("/api/stats")
def api_stats():
    return jsonify(database.get_stats())


@app.route("/api/read/<int:news_id>", methods=["POST"])
def api_read(news_id):
    database.mark_read(news_id)
    return jsonify({"ok": True})


@app.route("/api/star/<int:news_id>", methods=["POST"])
def api_star(news_id):
    database.toggle_star(news_id)
    return jsonify({"ok": True})


@app.route("/api/read_all", methods=["POST"])
def api_read_all():
    category = request.json.get("category", "전체")
    database.mark_all_read(category)
    return jsonify({"ok": True})


@app.route("/api/top-issues")
def api_top_issues():
    """당일 수집 기사에서 사회적 영향력 점수를 매겨 Top 3 반환.
    오늘 수집된 기사가 없으면 최근 7일 이내로 확장."""
    import datetime, re

    today = datetime.date.today().isoformat()  # "YYYY-MM-DD"

    conn = database.get_conn()
    # 오늘 collected_at 기준 수집분
    rows = conn.execute(
        "SELECT id, title, source, url, published, category, summary "
        "FROM news WHERE DATE(collected_at) = ? "
        "ORDER BY collected_at DESC",
        (today,)
    ).fetchall()

    # 오늘 수집분이 없으면 최근 7일로 확장 (서비스 초기 또는 당일 미수집 대비)
    if not rows:
        rows = conn.execute(
            "SELECT id, title, source, url, published, category, summary "
            "FROM news WHERE collected_at >= datetime('now', '-7 days') "
            "ORDER BY collected_at DESC LIMIT 100"
        ).fetchall()
    conn.close()

    # 영향력 키워드 가중치
    HIGH   = 3.0  # 사회적 파급력 큰 이슈
    MED    = 2.0
    LOW    = 1.4

    KEYWORDS = {
        # 위험/사고/규제
        "사고": HIGH, "피해": HIGH, "위험": HIGH, "긴급": HIGH, "경고": HIGH,
        "규제": HIGH, "금지": HIGH, "제재": HIGH, "처벌": HIGH, "재난": HIGH,
        "법안": HIGH, "개정": HIGH, "정책": HIGH, "기준": HIGH, "안전": MED,
        # 산업/기술 이슈
        "smr": HIGH, "소형모듈": HIGH, "원전": HIGH, "원자력": MED,
        "방사선": LOW, "방사능": MED, "방사성": MED,
        "의약품": MED, "치료": LOW, "임상": MED, "허가": MED, "승인": MED,
        # 국제/협력
        "국제": MED, "협력": LOW, "협약": MED, "iaea": HIGH, "국가": LOW,
        "수출": MED, "수입": MED, "글로벌": LOW,
        # 경제/산업
        "투자": LOW, "예산": MED, "예산삭감": HIGH, "지원": LOW,
        "연구": LOW, "개발": LOW, "산업": LOW,
    }

    # 카테고리 가중치
    CAT_W = {
        "국제 동향":      1.3,
        "산업 뉴스":      1.2,
        "KARA 주요이벤트": 1.1,
        "국내외 공고":    1.0,
        "업계 행사":      0.9,
    }

    def score(row):
        text = ((row["title"] or "") + " " + (row["summary"] or "")).lower()
        kw_score = sum(w for kw, w in KEYWORDS.items() if kw in text) or 1.0
        cat_w = CAT_W.get(row["category"] or "", 1.0)
        return kw_score * cat_w

    scored = sorted(rows, key=score, reverse=True)[:3]
    result = [dict(r) for r in scored]
    return jsonify(result)


@app.route("/api/reset-db", methods=["POST"])
def api_reset_db():
    """DB 전체 초기화 — COLLECT_SECRET 필수"""
    secret = os.environ.get("COLLECT_SECRET", "")
    if not secret or request.json.get("key") != secret:
        return jsonify({"error": "unauthorized"}), 403
    try:
        conn = database.get_conn()
        conn.execute("DELETE FROM news")
        conn.execute("DELETE FROM collect_log")
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "message": "DB 초기화 완료"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/collect", methods=["POST"])
def api_collect():
    """수동 수집 트리거 — 관리자용 (SECRET_KEY 환경변수로 보호)"""
    secret = os.environ.get("COLLECT_SECRET", "")
    if secret and request.json.get("key") != secret:
        return jsonify({"error": "unauthorized"}), 403
    try:
        collector.run_collection()
        return jsonify({"ok": True, "message": "수집 완료"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/summarize/<int:news_id>")
def api_summarize(news_id):
    """AI 요약 — 캐시 우선, 없으면 Claude API 호출"""
    cached = database.get_ai_summary(news_id)
    if cached:
        return jsonify({"summary": cached})

    row = database.get_news_url(news_id)
    if not row:
        return jsonify({"error": "기사를 찾을 수 없습니다."}), 404

    url = row["url"]
    title = row["title"]

    # 원문 텍스트 추출
    article_text = ""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()
        article_text = soup.get_text(separator="\n", strip=True)[:4000]
    except Exception as e:
        article_text = ""

    if not article_text.strip():
        article_text = f"제목: {title}"

    # Claude API 호출
    try:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return jsonify({"error": "ANTHROPIC_API_KEY가 설정되지 않았습니다. .env 파일에 키를 추가해주세요."}), 500
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=600,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "다음 방사선·원자력 관련 뉴스 기사를 한국어로 3~5문장으로 핵심만 간결하게 요약해주세요.\n\n"
                        f"제목: {title}\n\n"
                        f"본문:\n{article_text}"
                    ),
                }
            ],
        )
        ai_summary = message.content[0].text.strip()
    except Exception as e:
        return jsonify({"error": f"AI 요약 생성 실패: {str(e)}"}), 500

    database.save_ai_summary(news_id, ai_summary)
    return jsonify({"summary": ai_summary})


if __name__ == "__main__":
    print("=" * 50)
    print("  방사선 소식 대시보드 시작")
    print("  http://localhost:5000 에서 접속하세요")
    print("  매일 오전 5시 자동 수집 예약됨")
    print("=" * 50)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
