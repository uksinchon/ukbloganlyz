#!/usr/bin/env python3
"""
UK Centre 블로그 분석 시스템 - 메인 CLI
사용법:
    python main.py scrape          # 블로그 스크래핑
    python main.py analyze          # 분석 실행
    python main.py report           # PDF 리포트 생성
    python main.py email            # 이메일 리포트 발송
    python main.py dashboard        # 대시보드 실행
    python main.py gmail            # Gmail 뉴스 체크 (1회)
    python main.py scheduler        # 전체 자동화 스케줄러 시작
    python main.py full             # 스크래핑 → 분석 → 리포트 → 이메일 (1회 전체 실행)
"""
import sys
import logging
from datetime import datetime
from pathlib import Path

# 프로젝트 루트
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import LOG_LEVEL, LOG_FORMAT

logging.basicConfig(
    level=LOG_LEVEL,
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            Path(__file__).parent / "logs" / f"main_{datetime.now().strftime('%Y%m%d')}.log",
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger(__name__)


def cmd_scrape():
    """블로그 스크래핑"""
    from scraper.naver_blog_scraper import NaverBlogScraper
    print("🔍 블로그 스크래핑 시작...")
    scraper = NaverBlogScraper()
    posts = scraper.scrape_all_blogs()
    print(f"✅ 완료: {len(posts)}개 신규 포스트 수집")
    return posts


def cmd_analyze(days: int = 7):
    """분석 실행"""
    from scraper.naver_blog_scraper import NaverBlogScraper
    from analyzer.trend_analyzer import TrendAnalyzer

    print(f"📊 최근 {days}일 분석 시작...")
    scraper = NaverBlogScraper()
    posts = scraper.get_recent_posts(days=days)
    print(f"  분석 대상: {len(posts)}개 포스트")

    analyzer = TrendAnalyzer(posts)
    analysis = analyzer.generate_full_analysis(
        period_label=f"최근 {days}일 ({datetime.now().strftime('%Y-%m-%d')})"
    )

    # 요약 출력
    print("\n" + "=" * 50)
    print("📋 분석 요약")
    print("=" * 50)
    print(f"전체 포스트: {analysis['total_posts']}건")

    comparison = analysis.get("own_vs_competitor", {})
    print(f"본사 포스트: {comparison.get('own_total', 0)}건")
    print(f"경쟁사 포스트: {comparison.get('competitor_total', 0)}건")

    print("\n🏷️ 주제별 현황:")
    for cat, count in list(analysis.get("posting_by_category", {}).items())[:10]:
        print(f"  {cat}: {count}건")

    missed = comparison.get("missed_topics", {})
    if missed:
        print("\n⚠️ 놓치고 있는 주제:")
        for topic, count in missed.items():
            print(f"  ❗ {topic} (경쟁사 {count}건)")

    if analysis.get("ai_analysis"):
        print("\n🤖 AI 분석 인사이트:")
        print(analysis["ai_analysis"][:500])

    return analysis


def cmd_report(analysis: dict = None):
    """PDF 리포트 생성"""
    from reports.pdf_generator import PDFReportGenerator

    if not analysis:
        analysis = cmd_analyze()

    print("\n📄 PDF 리포트 생성 중...")
    gen = PDFReportGenerator(analysis)
    pdf_path = gen.generate()
    print(f"✅ PDF 리포트 생성 완료: {pdf_path}")
    return pdf_path


def cmd_email(analysis: dict = None, pdf_path: Path = None):
    """이메일 리포트 발송"""
    from notifier.email_sender import EmailSender

    if not analysis:
        analysis = cmd_analyze()
    if not pdf_path:
        pdf_path = cmd_report(analysis)

    print("\n📧 이메일 발송 중...")
    sender = EmailSender()
    subject, html = sender.build_daily_report_email(analysis)
    success = sender.send_report_email(subject, html, pdf_path)
    if success:
        print("✅ 이메일 발송 완료")
    else:
        print("❌ 이메일 발송 실패 - .env 설정을 확인해주세요")


def cmd_dashboard():
    """대시보드 실행"""
    import subprocess
    print("🌐 대시보드 시작 (http://localhost:8501)")
    subprocess.run([
        sys.executable, "-m", "streamlit", "run",
        str(Path(__file__).parent / "dashboard" / "app.py"),
        "--server.port", "8501",
        "--server.headless", "true",
    ])


def cmd_gmail():
    """Gmail 뉴스 체크 (1회)"""
    from gmail_pipeline.gmail_monitor import GmailNewsMonitor, BlogPostGenerator
    from gmail_pipeline.publisher import PublishManager

    print("📬 Gmail 뉴스 체크 중...")
    monitor = GmailNewsMonitor()
    emails = monitor.fetch_news_emails()
    print(f"  수신 이메일: {len(emails)}건")

    relevant = monitor.filter_relevant_emails(emails)
    print(f"  관련 뉴스: {len(relevant)}건")

    if relevant:
        generator = BlogPostGenerator()
        publisher = PublishManager()

        for email in relevant:
            print(f"\n  📰 {email['subject']} (점수: {email['relevance_score']:.1f})")
            post = generator.generate_blog_post(email)
            if post:
                result = publisher.publish_to_all(post, auto_publish=False)
                print(f"    → 초안 저장됨: {post['title']}")
                print(f"    → 상태: {result['status']}")
            monitor.mark_processed(email["gmail_id"])


def cmd_scheduler():
    """스케줄러 시작"""
    from scheduler.main_scheduler import main
    main()


def cmd_full():
    """전체 실행 (스크래핑 → 분석 → 리포트 → 이메일)"""
    print("🚀 전체 파이프라인 실행")
    print("=" * 60)

    cmd_scrape()
    analysis = cmd_analyze()
    pdf_path = cmd_report(analysis)
    cmd_email(analysis, pdf_path)

    print("\n" + "=" * 60)
    print("🎉 전체 파이프라인 완료!")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    command = sys.argv[1].lower()

    commands = {
        "scrape": cmd_scrape,
        "analyze": cmd_analyze,
        "report": cmd_report,
        "email": cmd_email,
        "dashboard": cmd_dashboard,
        "gmail": cmd_gmail,
        "scheduler": cmd_scheduler,
        "full": cmd_full,
    }

    if command in commands:
        commands[command]()
    else:
        print(f"❌ 알 수 없는 명령: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
