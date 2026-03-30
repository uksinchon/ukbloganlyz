"""
이메일 발송 모듈
- SMTP를 통한 리포트 이메일 발송
- Gmail API를 통한 발송도 지원
- PDF 리포트 첨부
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from pathlib import Path
from datetime import datetime

from config.settings import (
    REPORT_EMAIL_TO, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
)

logger = logging.getLogger(__name__)


class EmailSender:
    """이메일 발송"""

    def __init__(self):
        self.smtp_host = SMTP_HOST
        self.smtp_port = SMTP_PORT
        self.smtp_user = SMTP_USER
        self.smtp_password = SMTP_PASSWORD
        self.default_to = REPORT_EMAIL_TO

    def send_report_email(
        self,
        subject: str,
        html_body: str,
        pdf_path: Path | None = None,
        to_email: str | None = None,
    ) -> bool:
        """리포트 이메일 발송"""
        to_email = to_email or self.default_to

        if not self.smtp_user or not self.smtp_password:
            logger.error("SMTP 설정이 없습니다. .env 파일을 확인해주세요.")
            return False

        try:
            msg = MIMEMultipart("mixed")
            msg["From"] = self.smtp_user
            msg["To"] = to_email
            msg["Subject"] = subject

            # HTML 본문
            msg.attach(MIMEText(html_body, "html", "utf-8"))

            # PDF 첨부
            if pdf_path and pdf_path.exists():
                with open(pdf_path, "rb") as f:
                    attachment = MIMEApplication(f.read(), _subtype="pdf")
                    attachment.add_header(
                        "Content-Disposition", "attachment",
                        filename=pdf_path.name,
                    )
                    msg.attach(attachment)

            # 발송
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.smtp_user, [to_email], msg.as_string())

            logger.info(f"이메일 발송 완료: {to_email}")
            return True

        except Exception as e:
            logger.error(f"이메일 발송 실패: {e}")
            return False

    def build_daily_report_email(self, analysis: dict) -> tuple[str, str]:
        """일일 리포트 이메일 생성"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        subject = f"[UK Centre] 일일 블로그 분석 리포트 - {date_str}"

        comparison = analysis.get("own_vs_competitor", {})
        missed = comparison.get("missed_topics", {})

        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: 'Malgun Gothic', Arial, sans-serif; color: #333; }}
                .header {{ background: #1a237e; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; }}
                .stat-box {{ display: inline-block; background: #E3F2FD; padding: 15px; margin: 5px;
                            border-radius: 8px; text-align: center; min-width: 120px; }}
                .stat-number {{ font-size: 24px; font-weight: bold; color: #1976D2; }}
                .alert {{ background: #FFEBEE; border-left: 4px solid #D32F2F; padding: 15px; margin: 10px 0; }}
                table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
                th {{ background: #1a237e; color: white; padding: 8px; text-align: left; }}
                td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
                tr:nth-child(even) {{ background: #f5f5f5; }}
                .footer {{ background: #f5f5f5; padding: 15px; text-align: center; font-size: 12px; color: #999; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>UK Centre Blog Analysis</h1>
                <p>일일 블로그 분석 리포트 - {date_str}</p>
            </div>

            <div class="content">
                <h2>📊 오늘의 요약</h2>
                <div>
                    <div class="stat-box">
                        <div class="stat-number">{analysis.get('total_posts', 0)}</div>
                        <div>전체 포스트</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{comparison.get('own_total', 0)}</div>
                        <div>본사 포스트</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{comparison.get('competitor_total', 0)}</div>
                        <div>경쟁사 포스트</div>
                    </div>
                </div>
        """

        # 놓치는 트렌드 경고
        if missed:
            html += """
                <div class="alert">
                    <h3>⚠️ 놓치고 있는 트렌드</h3>
                    <p>아래 주제는 경쟁사가 다루고 있지만 본사가 놓치고 있습니다:</p>
                    <table>
                        <tr><th>주제</th><th>경쟁사 포스트 수</th></tr>
            """
            for topic, count in missed.items():
                html += f"<tr><td>{topic}</td><td>{count}</td></tr>"
            html += "</table></div>"

        # 주제별 현황
        cats = analysis.get("posting_by_category", {})
        if cats:
            html += """
                <h2>🏷️ 주제별 포스팅 현황</h2>
                <table>
                    <tr><th>주제</th><th>포스트 수</th></tr>
            """
            for cat, count in list(cats.items())[:10]:
                html += f"<tr><td>{cat}</td><td>{count}</td></tr>"
            html += "</table>"

        # AI 인사이트
        ai = analysis.get("ai_analysis", "")
        if ai:
            ai_html = ai.replace("\n", "<br>")
            html += f"""
                <h2>🤖 AI 분석 인사이트</h2>
                <div style="background: #F3E5F5; padding: 15px; border-radius: 8px;">
                    {ai_html}
                </div>
            """

        html += """
            </div>
            <div class="footer">
                <p>UK Centre Blog Analysis System | 자동 생성 리포트</p>
                <p>대시보드 접속: http://localhost:8501</p>
            </div>
        </body>
        </html>
        """

        return subject, html

    def build_weekly_report_email(self, analysis: dict) -> tuple[str, str]:
        """주간 리포트 이메일 생성"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        subject = f"[UK Centre] 주간 블로그 분석 리포트 - {date_str}"
        # 일일 리포트와 동일 포맷에 기간만 다름
        _, html = self.build_daily_report_email(analysis)
        html = html.replace("일일 블로그 분석 리포트", "주간 블로그 분석 리포트")
        return subject, html

    def build_monthly_report_email(self, analysis: dict) -> tuple[str, str]:
        """월간 리포트 이메일 생성"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        subject = f"[UK Centre] 월간 블로그 분석 리포트 - {date_str}"
        _, html = self.build_daily_report_email(analysis)
        html = html.replace("일일 블로그 분석 리포트", "월간 블로그 분석 리포트")
        return subject, html
