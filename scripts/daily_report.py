#!/usr/bin/env python3
"""
일일 자동 리포트: 스크래핑 → AI 분석 → 이메일 발송
GitHub Actions 또는 로컬에서 독립 실행 가능

사용법:
    python scripts/daily_report.py
"""
import json
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path

# 프로젝트 루트 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    DATA_DIR, OWN_BLOGS, COMPETITOR_BLOGS, ALL_BLOGS,
    ANTHROPIC_API_KEY, TOPIC_CATEGORIES,
    SMTP_USER, SMTP_PASSWORD, REPORT_EMAIL_TO,
    CUSTOM_COMPETITORS_FILE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def load_custom_competitors() -> dict:
    if CUSTOM_COMPETITORS_FILE.exists():
        with open(CUSTOM_COMPETITORS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def categorize_post(title: str, summary: str) -> list[str]:
    """제목+요약에서 주제 카테고리 자동 분류"""
    text = f"{title} {summary}".lower()
    categories = []
    for category, keywords in TOPIC_CATEGORIES.items():
        for keyword in keywords:
            if keyword.lower() in text:
                categories.append(category)
                break
    return categories if categories else ["기타"]


def step1_scrape() -> list[dict]:
    """1단계: 전체 블로그 스크래핑"""
    logger.info("=" * 50)
    logger.info("1단계: 블로그 스크래핑 시작")
    logger.info("=" * 50)

    from scraper.naver_blog_scraper import NaverBlogScraper
    scraper = NaverBlogScraper()
    scraper.on_progress = lambda msg: logger.info(msg)
    posts = scraper.scrape_all_blogs()
    logger.info(f"스크래핑 완료: {len(posts)}개 신규 포스트 수집")
    return posts


def step2_filter_today(posts_db_path: Path) -> list[dict]:
    """2단계: 당일 포스트만 필터링"""
    logger.info("=" * 50)
    logger.info("2단계: 당일 포스트 필터링")
    logger.info("=" * 50)

    with open(posts_db_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    all_posts = data.get("posts", [])
    today = datetime.now().strftime("%Y-%m-%d")

    today_posts = [p for p in all_posts if p.get("date", "") == today]
    logger.info(f"전체 {len(all_posts)}건 중 당일({today}) 포스트: {len(today_posts)}건")

    # 카테고리 자동 분류
    for p in today_posts:
        if "categories" not in p:
            p["categories"] = categorize_post(p.get("title", ""), p.get("summary", ""))

    return today_posts


def step3_ai_analysis(posts: list[dict]) -> dict:
    """3단계: AI 분석 리포트 생성"""
    logger.info("=" * 50)
    logger.info("3단계: AI 분석 실행")
    logger.info("=" * 50)

    if not ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY 미설정 - AI 분석 건너뜀")
        return _build_basic_analysis(posts)

    own_ids = set(OWN_BLOGS.values())
    own_posts = [p for p in posts if p.get("blog_id") in own_ids]
    comp_posts = [p for p in posts if p.get("blog_id") not in own_ids]

    own_cats = {}
    comp_cats = {}
    for p in own_posts:
        for cat in p.get("categories", ["기타"]):
            own_cats[cat] = own_cats.get(cat, 0) + 1
    for p in comp_posts:
        for cat in p.get("categories", ["기타"]):
            comp_cats[cat] = comp_cats.get(cat, 0) + 1

    missed_topics = {}
    for cat in set(list(own_cats.keys()) + list(comp_cats.keys())):
        oc = own_cats.get(cat, 0)
        cc = comp_cats.get(cat, 0)
        if (cc > 0 and oc == 0) or (cc > oc * 2 and cc > 2):
            missed_topics[cat] = cc

    titles_by_blog = {}
    for p in posts:
        b = p.get("blog_name", "")
        if b not in titles_by_blog:
            titles_by_blog[b] = []
        titles_by_blog[b].append(p.get("title", ""))

    custom = load_custom_competitors()
    today = datetime.now().strftime("%Y-%m-%d")

    prompt = f"""당신은 영국 유학 시장 전문 분석가입니다.

## 분석 대상
- 영국유학센터 신촌지사 + 본사 2개 vs 경쟁사 {len(COMPETITOR_BLOGS) + len(custom)}개
- 기간: {today} 당일 ({len(posts)}건 분석)

## 신촌지사 + 본사 포스팅 ({len(own_posts)}건)
주제 분포: {json.dumps(own_cats, ensure_ascii=False)}

## 경쟁사 포스팅 ({len(comp_posts)}건)
주제 분포: {json.dumps(comp_cats, ensure_ascii=False)}

## 본사가 놓치는 주제
{json.dumps(missed_topics, ensure_ascii=False)}

## 블로그별 당일 포스트 제목
{json.dumps(titles_by_blog, ensure_ascii=False, indent=1)}

다음을 분석해주세요:

### 1. 오늘의 핵심 요약
- 가장 활발한 경쟁사와 주요 포스팅 주제
- 오늘의 포스팅 키워드 트렌드

### 2. 주요 트렌드 (TOP 5)
- 업계에서 오늘 가장 많이 다루는 주제

### 3. 놓치고 있는 기회
- 경쟁사가 다루지만 우리가 놓치고 있는 주제
- 구체적 대응 방안

### 4. 즉시 작성 추천 콘텐츠 (3개)
- 구체적인 블로그 제목과 키워드

### 5. SEO 키워드 기회
- 선점 가능한 검색 키워드 3개

한국어로, 간결하고 실행 가능한 인사이트를 제공하세요."""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        ai_text = response.content[0].text
        logger.info("AI 분석 완료")
    except Exception as e:
        logger.error(f"AI 분석 실패: {e}")
        ai_text = ""

    analysis = {
        "period": "당일",
        "generated_at": datetime.now().isoformat(),
        "total_posts": len(posts),
        "ai_analysis": ai_text,
        "posting_by_category": {**own_cats, **comp_cats},
        "own_vs_competitor": {
            "own_total": len(own_posts),
            "competitor_total": len(comp_posts),
            "own_categories": own_cats,
            "competitor_categories": comp_cats,
            "missed_topics": missed_topics,
        },
    }

    # 분석 결과 저장
    analysis_file = DATA_DIR / f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(analysis_file, "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)
    logger.info(f"분석 결과 저장: {analysis_file}")

    return analysis


def _build_basic_analysis(posts: list[dict]) -> dict:
    """AI 없이 기본 통계만 생성"""
    own_ids = set(OWN_BLOGS.values())
    own_posts = [p for p in posts if p.get("blog_id") in own_ids]
    comp_posts = [p for p in posts if p.get("blog_id") not in own_ids]

    return {
        "period": "당일",
        "generated_at": datetime.now().isoformat(),
        "total_posts": len(posts),
        "ai_analysis": "",
        "posting_by_category": {},
        "own_vs_competitor": {
            "own_total": len(own_posts),
            "competitor_total": len(comp_posts),
            "own_categories": {},
            "competitor_categories": {},
            "missed_topics": {},
        },
    }


def step4_send_email(analysis: dict):
    """4단계: 이메일 발송"""
    logger.info("=" * 50)
    logger.info("4단계: 이메일 발송")
    logger.info("=" * 50)

    if not SMTP_USER or not SMTP_PASSWORD:
        logger.error("SMTP_USER / SMTP_PASSWORD 미설정 - 이메일 발송 건너뜀")
        return False

    from notifier.email_sender import EmailSender
    sender = EmailSender()
    subject, html = sender.build_daily_report_email(analysis)

    # 대시보드 링크 업데이트
    html = html.replace(
        "http://localhost:8501",
        "https://uksinchon-ukbloganlyz-dashboardapp.streamlit.app",
    )

    success = sender.send_report_email(
        subject=subject,
        html_body=html,
        to_email=REPORT_EMAIL_TO,
    )

    if success:
        logger.info(f"이메일 발송 완료: {REPORT_EMAIL_TO}")
    else:
        logger.error("이메일 발송 실패")

    return success


def main():
    logger.info("=" * 60)
    logger.info("UK Centre 일일 블로그 분석 리포트 시작")
    logger.info(f"실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # 1. 스크래핑
    new_posts = step1_scrape()

    # 2. 당일 포스트 필터링
    posts_db_path = DATA_DIR / "posts.json"
    today_posts = step2_filter_today(posts_db_path)

    if not today_posts:
        logger.warning("당일 포스트가 없습니다. 최근 수집된 전체 데이터로 리포트 생성합니다.")
        # 당일 포스트가 없으면 신규 수집 포스트라도 사용
        today_posts = new_posts if new_posts else []

    if not today_posts:
        logger.warning("수집된 포스트가 없어 리포트를 생성할 수 없습니다.")
        return

    # 3. AI 분석
    analysis = step3_ai_analysis(today_posts)

    # 4. 이메일 발송
    step4_send_email(analysis)

    logger.info("=" * 60)
    logger.info("일일 리포트 완료!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
