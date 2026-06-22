"""
로컬 수집 → Render 푸시 스크립트
- 로컬 PC에서 실행: 한국 기관 사이트(kara.or.kr, campus, ratis) 포함 전체 수집
- 수집 결과를 Render 서버 DB로 전송
- Windows 작업 스케줄러로 매일 오전 5시 자동 실행 권장

실행 방법:
    python local_push.py
    또는 push.bat 더블클릭
"""
import os
import sys
import requests
import database
import collector
from datetime import date

# ── 설정 ────────────────────────────────────────────
RENDER_URL  = "https://karadiation-app.onrender.com"
SECRET      = os.environ.get("COLLECT_SECRET", "")   # 환경변수 or 아래 직접 입력
# SECRET    = "여기에_시크릿_값_입력"                  # 환경변수 없을 때 직접 지정
# ────────────────────────────────────────────────────


def collect_and_push():
    print("=" * 50)
    print("  KARAdi Info — 로컬 수집 & Render 푸시")
    print("=" * 50)

    if not SECRET:
        print("\n[오류] COLLECT_SECRET 환경변수가 설정되지 않았습니다.")
        print("  Render 대시보드 → Environment에서 COLLECT_SECRET 값을 확인 후")
        print("  이 스크립트 상단의 SECRET 변수에 직접 입력하거나")
        print("  환경변수로 설정해주세요.")
        sys.exit(1)

    # 1. 로컬 수집 (한국 기관 사이트 포함)
    print("\n[1단계] 로컬 수집 시작...")
    collector.run_collection()

    # 2. 오늘 수집된 항목 로컬 DB에서 조회
    today = date.today().isoformat()
    conn = database.get_conn()
    rows = conn.execute(
        "SELECT title, source, url, published, category, summary, "
        "region, end_date, location, collected_at "
        "FROM news WHERE DATE(collected_at) = ?",
        (today,)
    ).fetchall()
    conn.close()

    items = [dict(r) for r in rows]
    if not items:
        print("\n[경고] 오늘 수집된 항목이 없습니다. 푸시를 건너뜁니다.")
        return

    print(f"\n[2단계] Render 서버로 {len(items)}건 푸시 중...")

    # 3. Render 서버로 전송
    try:
        resp = requests.post(
            f"{RENDER_URL}/api/push-news",
            json={"key": SECRET, "items": items},
            timeout=60
        )
        resp.raise_for_status()
        data = resp.json()
        print(f"  ✓ 푸시 완료 — 전송 {data.get('received')}건 / 신규 반영 {data.get('added')}건")
    except requests.exceptions.ConnectionError:
        print("  [오류] Render 서버에 연결할 수 없습니다. 인터넷 연결을 확인해주세요.")
        sys.exit(1)
    except requests.exceptions.Timeout:
        print("  [오류] Render 서버 응답 타임아웃 (60초 초과)")
        sys.exit(1)
    except Exception as e:
        print(f"  [오류] 푸시 실패: {e}")
        sys.exit(1)

    print("\n완료!")
    print("=" * 50)


if __name__ == "__main__":
    collect_and_push()
