"""
스케줄러 - 모든 자동화 작업의 정기 실행 관리
- APScheduler 기반
- 일간/주간/월간 분석 및 리포트
- Gmail 모니터링
"""
import logging
import signal
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config.settings import (
    SCHEDULE_DAILY_HOUR, SCHEDULE_WEEKLY_DAY, SCHEDULE_WEEKLY_HOUR,
    SCHEDULE_MONTHLY_DAY, SCHEDULE_MONTHLY_HOUR, GMAIL_POLL_INTERVAL_MINUTES,
    LOG_LEVEL, LOG_FORMAT,
)

logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


# ============================================================
# 작업 함수들
# ============================================================

def job_scrape_blogs():
    """블로그 스크래핑"""
    logger.info("="*50)
    logger.info("[JOB] 블로그 스크래핑 시작")
    try:
        from scraper.naver_blog_scraper import NaverBlogScraper
        scraper = NaverBlogScraper()
        posts = scraper.scrape_all_blogs()
        logger.info(f"[JOB] 스크래핑 완료: {len(posts)}개 신규 포스트")
    except Exception as e:
        logger.error(f"[JOB] 스크래핑 실패: {e}")


def job_daily_analysis():
    """일일 분석 + 리포트 + 이메일"""
    logger.info("="*50)
    logger.info("[JOB] 일일 분석 시작")
    try:
        from scraper.naver_blog_scraper import NaverBlogScraper
        from analyzer.trend_analyzer import TrendAnalyzer
        from reports.pdf_generator import PDFReportGenerator
        from notifier.email_sender import EmailSender

        # 1. 스크래핑
        scraper = NaverBlogScraper()
        scraper.scrape_all_blogs()

        # 2. 분석 (최근 1일)
        posts = scraper.get_recent_posts(days=1)
        if not posts:
            logger.info("[JOB] 오늘 신규 포스트 없음 - 건너뜀")
            return

        analyzer = TrendAnalyzer(posts)
        analysis = analyzer.generate_full_analysis(
            period_label=f"일일 ({datetime.now().strftime('%Y-%m-%d')})"
        )

        # 3. PDF 리포트
        pdf_gen = PDFReportGenerator(analysis)
        pdf_path = pdf_gen.generate()

        # 4. 이메일 발송
        sender = EmailSender()
        subject, html = sender.build_daily_report_email(analysis)
        sender.send_report_email(subject, html, pdf_path)

        logger.info("[JOB] 일일 분석 완료")
    except Exception as e:
        logger.error(f"[JOB] 일일 분석 실패: {e}")


def job_weekly_analysis():
    """주간 분석 + 리포트 + 이메일"""
    logger.info("="*50)
    logger.info("[JOB] 주간 분석 시작")
    try:
        from scraper.naver_blog_scraper import NaverBlogScraper
        from analyzer.trend_analyzer import TrendAnalyzer
        from reports.pdf_generator import PDFReportGenerator
        from notifier.email_sender import EmailSender

        scraper = NaverBlogScraper()
        scraper.scrape_all_blogs()

        posts = scraper.get_recent_posts(days=7)
        if not posts:
            logger.info("[JOB] 이번 주 신규 포스트 없음")
            return

        analyzer = TrendAnalyzer(posts)
        analysis = analyzer.generate_full_analysis(
            period_label=f"주간 ({datetime.now().strftime('%Y-%m-%d')})"
        )

        pdf_gen = PDFReportGenerator(analysis)
        pdf_path = pdf_gen.generate()

        sender = EmailSender()
        subject, html = sender.build_weekly_report_email(analysis)
        sender.send_report_email(subject, html, pdf_path)

        logger.info("[JOB] 주간 분석 완료")
    except Exception as e:
        logger.error(f"[JOB] 주간 분석 실패: {e}")


def job_monthly_analysis():
    """월간 분석 + 리포트 + 이메일"""
    logger.info("="*50)
    logger.info("[JOB] 월간 분석 시작")
    try:
        from scraper.naver_blog_scraper import NaverBlogScraper
        from analyzer.trend_analyzer import TrendAnalyzer
        from reports.pdf_generator import PDFReportGenerator
        from notifier.email_sender import EmailSender

        scraper = NaverBlogScraper()
        scraper.scrape_all_blogs()

        posts = scraper.get_recent_posts(days=30)
        if not posts:
            logger.info("[JOB] 이번 달 신규 포스트 없음")
            return

        analyzer = TrendAnalyzer(posts)
        analysis = analyzer.generate_full_analysis(
            period_label=f"월간 ({datetime.now().strftime('%Y년 %m월')})"
        )

        pdf_gen = PDFReportGenerator(analysis)
        pdf_path = pdf_gen.generate()

        sender = EmailSender()
        subject, html = sender.build_monthly_report_email(analysis)
        sender.send_report_email(subject, html, pdf_path)

        logger.info("[JOB] 월간 분석 완료")
    except Exception as e:
        logger.error(f"[JOB] 월간 분석 실패: {e}")


def job_check_gmail():
    """Gmail 뉴스 모니터링 → 블로그 글 생성"""
    logger.info("[JOB] Gmail 뉴스 체크")
    try:
        from gmail_pipeline.gmail_monitor import GmailNewsMonitor, BlogPostGenerator
        from gmail_pipeline.publisher import PublishManager

        monitor = GmailNewsMonitor()
        emails = monitor.fetch_news_emails()

        if not emails:
            logger.info("[JOB] 새 뉴스 이메일 없음")
            return

        relevant = monitor.filter_relevant_emails(emails, threshold=4.0)
        logger.info(f"[JOB] 관련 뉴스 {len(relevant)}건 발견")

        generator = BlogPostGenerator()
        publisher = PublishManager()

        for email in relevant:
            post = generator.generate_blog_post(email)
            if post:
                # 초안으로 저장 (수동 승인 후 발행)
                publisher.publish_to_all(post, auto_publish=False)
                logger.info(f"[JOB] 블로그 초안 생성: {post['title']}")

            monitor.mark_processed(email["gmail_id"])

    except Exception as e:
        logger.error(f"[JOB] Gmail 체크 실패: {e}")


# ============================================================
# 스케줄러
# ============================================================

def create_scheduler() -> BlockingScheduler:
    """스케줄러 생성 및 작업 등록"""
    scheduler = BlockingScheduler(timezone="Asia/Seoul")

    # 블로그 스크래핑: 6시간마다
    scheduler.add_job(
        job_scrape_blogs,
        IntervalTrigger(hours=6),
        id="scrape_blogs",
        name="블로그 스크래핑",
        replace_existing=True,
    )

    # 일일 분석: 매일 오전 8시
    scheduler.add_job(
        job_daily_analysis,
        CronTrigger(hour=SCHEDULE_DAILY_HOUR, minute=0),
        id="daily_analysis",
        name="일일 분석 리포트",
        replace_existing=True,
    )

    # 주간 분석: 매주 월요일 오전 9시
    scheduler.add_job(
        job_weekly_analysis,
        CronTrigger(day_of_week=SCHEDULE_WEEKLY_DAY, hour=SCHEDULE_WEEKLY_HOUR, minute=0),
        id="weekly_analysis",
        name="주간 분석 리포트",
        replace_existing=True,
    )

    # 월간 분석: 매월 1일 오전 10시
    scheduler.add_job(
        job_monthly_analysis,
        CronTrigger(day=SCHEDULE_MONTHLY_DAY, hour=SCHEDULE_MONTHLY_HOUR, minute=0),
        id="monthly_analysis",
        name="월간 분석 리포트",
        replace_existing=True,
    )

    # Gmail 체크: 5분마다
    scheduler.add_job(
        job_check_gmail,
        IntervalTrigger(minutes=GMAIL_POLL_INTERVAL_MINUTES),
        id="check_gmail",
        name="Gmail 뉴스 모니터링",
        replace_existing=True,
    )

    return scheduler


def main():
    """스케줄러 실행"""
    logger.info("=" * 60)
    logger.info("UK Centre 블로그 분석 자동화 시스템 시작")
    logger.info("=" * 60)

    scheduler = create_scheduler()

    # 등록된 작업 출력
    jobs = scheduler.get_jobs()
    logger.info(f"등록된 작업 {len(jobs)}개:")
    for job in jobs:
        logger.info(f"  - {job.name}: {job.trigger}")

    # 종료 시그널 처리
    def shutdown(signum, frame):
        logger.info("종료 시그널 수신 - 스케줄러 중지")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        logger.info("스케줄러 시작 (Ctrl+C로 종료)")
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("스케줄러 종료")


if __name__ == "__main__":
    main()
