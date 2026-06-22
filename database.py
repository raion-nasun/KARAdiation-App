import sqlite3
import os

# 배포 환경(Fly.io)에서는 DB_PATH 환경변수로 /data/news.db 사용
# 로컬에서는 프로젝트 폴더 내 data/news.db 사용
DB_PATH = os.environ.get(
    "DB_PATH",
    os.path.join(os.path.dirname(__file__), "data", "news.db")
)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            source TEXT,
            url TEXT UNIQUE,
            published TEXT,
            category TEXT,
            summary TEXT,
            collected_at TEXT DEFAULT (datetime('now', 'localtime')),
            is_read INTEGER DEFAULT 0,
            is_starred INTEGER DEFAULT 0,
            ai_summary TEXT,
            region TEXT,
            end_date TEXT,
            location TEXT
        )
    """)
    # 기존 DB 컬럼 마이그레이션
    for col_def in ["ai_summary TEXT", "region TEXT", "end_date TEXT", "location TEXT"]:
        try:
            c.execute(f"ALTER TABLE news ADD COLUMN {col_def}")
        except Exception:
            pass
    c.execute("""
        CREATE TABLE IF NOT EXISTS collect_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at TEXT DEFAULT (datetime('now', 'localtime')),
            count_added INTEGER DEFAULT 0,
            status TEXT,
            message TEXT
        )
    """)
    conn.commit()
    conn.close()


def migrate_regions():
    """기존 공고/행사 레코드에 국내/해외 region 자동 설정"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, url, source FROM news WHERE region IS NULL AND category IN ('국내외 공고', '업계 행사')"
    ).fetchall()
    kr_url = ['.go.kr', '.or.kr', '.re.kr', '.ac.kr', '.co.kr', '.kr/']
    kr_src_domestic = ['한국', 'kins', 'kara', 'nrf', 'iitp', 'ketep', 'korad',
                        '비즈인포', '나라장터', 'kaif', 'kns', 'karp',
                        '방사선', '원자력', '에너지데일리', '에너지안전']
    overseas_src = ['iaea', 'world nuclear', 'ans ', 'nea', 'hps', 'irpa', 'oecd', 'wna', 'icrp', 'nrc']
    for row in rows:
        url = (row['url'] or '').lower()
        src = (row['source'] or '').lower()
        if any(p in url for p in kr_url):
            region = '국내'
        elif any(k in src for k in kr_src_domestic):
            region = '국내'
        elif any(k in src for k in overseas_src):
            region = '해외'
        elif any('가' <= ch <= '힣' for ch in (row['source'] or '')):
            region = '국내'
        else:
            region = '해외'
        conn.execute("UPDATE news SET region=? WHERE id=?", (region, row['id']))
    conn.commit()
    conn.close()


def insert_news(items):
    conn = get_conn()
    c = conn.cursor()
    added = 0
    for item in items:
        try:
            c.execute("""
                INSERT OR IGNORE INTO news
                  (title, source, url, published, category, summary, region, end_date, location)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item["title"], item["source"], item["url"],
                item["published"], item["category"], item.get("summary", ""),
                item.get("region", ""), item.get("end_date", ""), item.get("location", ""),
            ))
            if c.rowcount > 0:
                added += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return added


def log_collection(count_added, status, message=""):
    conn = get_conn()
    conn.execute(
        "INSERT INTO collect_log (count_added, status, message) VALUES (?, ?, ?)",
        (count_added, status, message)
    )
    conn.commit()
    conn.close()


def get_news(category=None, starred=None, unread=None, search=None, limit=200, offset=0):
    conn = get_conn()
    where = []
    params = []
    if category and category != "전체":
        where.append("category = ?")
        params.append(category)
    if starred:
        where.append("is_starred = 1")
    if unread:
        where.append("is_read = 0")
    if search:
        where.append("(title LIKE ? OR source LIKE ? OR summary LIKE ?)")
        params += [f"%{search}%", f"%{search}%", f"%{search}%"]
    sql = "SELECT * FROM news"
    if where:
        sql += " WHERE " + " AND ".join(where)
    # KARA 주요이벤트는 협회공식→RATIS→교육(Campus) 순, 그 외는 최신순
    if category == "KARA 주요이벤트":
        sql += (
            " ORDER BY CASE source"
            " WHEN '한국방사선진흥협회' THEN 0"
            " WHEN 'RATIS' THEN 1"
            " WHEN 'KARA Campus' THEN 2"
            " ELSE 3 END,"
            " published DESC, collected_at DESC LIMIT ? OFFSET ?"
        )
    else:
        sql += " ORDER BY published DESC, collected_at DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats():
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM news").fetchone()[0]
    # 모든 ID 반환 — 프론트엔드 로컬스토리지 기반 unread 계산에 사용
    all_ids = [r[0] for r in conn.execute("SELECT id FROM news").fetchall()]
    by_cat = conn.execute(
        "SELECT category, COUNT(*) as cnt FROM news GROUP BY category ORDER BY cnt DESC"
    ).fetchall()
    last_collect = conn.execute(
        "SELECT run_at, count_added, status FROM collect_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    recent_7d = conn.execute(
        "SELECT COUNT(*) FROM news WHERE published >= date('now','-7 days')"
    ).fetchone()[0]
    conn.close()
    return {
        "total": total,
        "all_ids": all_ids,
        "by_category": [dict(r) for r in by_cat],
        "last_collect": dict(last_collect) if last_collect else None,
        "recent_7d": recent_7d,
    }


def mark_read(news_id):
    conn = get_conn()
    conn.execute("UPDATE news SET is_read=1 WHERE id=?", (news_id,))
    conn.commit()
    conn.close()


def toggle_star(news_id):
    conn = get_conn()
    conn.execute("UPDATE news SET is_starred = 1 - is_starred WHERE id=?", (news_id,))
    conn.commit()
    conn.close()


def get_ai_summary(news_id):
    conn = get_conn()
    row = conn.execute("SELECT ai_summary FROM news WHERE id=?", (news_id,)).fetchone()
    conn.close()
    return row["ai_summary"] if row else None


def save_ai_summary(news_id, ai_summary):
    conn = get_conn()
    conn.execute("UPDATE news SET ai_summary=? WHERE id=?", (ai_summary, news_id))
    conn.commit()
    conn.close()


def get_news_url(news_id):
    conn = get_conn()
    row = conn.execute("SELECT url, title FROM news WHERE id=?", (news_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def trim_kara_events(max_count: int = 15):
    """KARA 주요이벤트를 최신순 max_count건만 유지, 초과분 자동 삭제"""
    conn = get_conn()
    conn.execute(f"""
        DELETE FROM news
        WHERE category = 'KARA 주요이벤트'
          AND id NOT IN (
            SELECT id FROM news
            WHERE category = 'KARA 주요이벤트'
            ORDER BY
              CASE source
                WHEN '한국방사선진흥협회' THEN 0
                WHEN 'RATIS' THEN 1
                WHEN 'KARA Campus' THEN 2
                ELSE 3 END,
              published DESC,
              collected_at DESC
            LIMIT {max_count}
          )
    """)
    deleted = conn.total_changes
    conn.commit()
    conn.close()
    if deleted:
        print(f"    KARA 이벤트 초과 {deleted}건 삭제 (최대 {max_count}건 유지)")


def trim_category(category: str, max_count: int):
    """일반 카테고리를 최신순 max_count건만 유지, 초과분 자동 삭제"""
    conn = get_conn()
    conn.execute(f"""
        DELETE FROM news
        WHERE category = ?
          AND id NOT IN (
            SELECT id FROM news
            WHERE category = ?
            ORDER BY published DESC, collected_at DESC
            LIMIT {max_count}
          )
    """, (category, category))
    deleted = conn.total_changes
    conn.commit()
    conn.close()
    if deleted:
        print(f"    [{category}] 초과 {deleted}건 삭제 (최대 {max_count}건 유지)")


def trim_expired_events():
    """업계 행사·국내외 공고 중 오늘 이전 날짜 항목 자동 삭제"""
    import datetime
    today = datetime.date.today().isoformat()
    conn = get_conn()
    conn.execute("""
        DELETE FROM news
        WHERE category IN ('업계 행사', '국내외 공고')
          AND published IS NOT NULL
          AND published != ''
          AND DATE(published) < ?
    """, (today,))
    deleted = conn.total_changes
    conn.commit()
    conn.close()
    if deleted:
        print(f"    만료 행사/공고 {deleted}건 삭제 (오늘 이전 날짜)")


def mark_all_read(category=None):
    conn = get_conn()
    if category and category != "전체":
        conn.execute("UPDATE news SET is_read=1 WHERE category=?", (category,))
    else:
        conn.execute("UPDATE news SET is_read=1")
    conn.commit()
    conn.close()
