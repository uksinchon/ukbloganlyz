"""
Gmail 뉴스 모니터링 모듈
- Gmail API로 수신 뉴스 이메일 감지
- 영국 유학 관련 뉴스 필터링 및 가치 판단
- Claude AI로 블로그 글 자동 생성
"""
import logging
import base64
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from email.mime.text import MIMEText

from config.settings import (
    GMAIL_CREDENTIALS_FILE, GMAIL_TOKEN_FILE,
    ANTHROPIC_API_KEY, DATA_DIR,
)

logger = logging.getLogger(__name__)

PROCESSED_EMAILS_FILE = DATA_DIR / "processed_emails.json"


class GmailNewsMonitor:
    """Gmail 뉴스 이메일 모니터링"""

    # 관련 뉴스 판별 키워드
    RELEVANCE_KEYWORDS = [
        "UK", "영국", "university", "대학", "유학", "비자", "visa",
        "IELTS", "UCAS", "scholarship", "장학금", "ranking", "순위",
        "British Council", "Russell Group", "foundation", "파운데이션",
        "masters", "석사", "PhD", "박사", "MBA", "admission", "입학",
        "tuition", "학비", "accommodation", "기숙사", "student",
        "education", "교육", "graduate", "졸업", "offer", "오퍼",
    ]

    # 뉴스 발신자 키워드 (높은 관련성)
    TRUSTED_SENDERS = [
        "british council", "ucas", "qs ranking", "times higher",
        "the guardian university", "bbc education", "studyuk",
        "uk education", "university", "college",
    ]

    def __init__(self):
        self.service = None
        self.processed_ids = self._load_processed_ids()

    def _load_processed_ids(self) -> set:
        if PROCESSED_EMAILS_FILE.exists():
            with open(PROCESSED_EMAILS_FILE, "r") as f:
                data = json.load(f)
                return set(data.get("processed_ids", []))
        return set()

    def _save_processed_ids(self):
        with open(PROCESSED_EMAILS_FILE, "w") as f:
            json.dump({"processed_ids": list(self.processed_ids)}, f)

    def authenticate(self) -> bool:
        """Gmail API 인증"""
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build

            SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
            creds = None

            token_path = Path(GMAIL_TOKEN_FILE)
            if token_path.exists():
                creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    cred_path = Path(GMAIL_CREDENTIALS_FILE)
                    if not cred_path.exists():
                        logger.error(f"Gmail credentials 파일이 없습니다: {cred_path}")
                        logger.error("Google Cloud Console에서 OAuth 2.0 credentials를 다운로드하세요.")
                        return False
                    flow = InstalledAppFlow.from_client_secrets_file(str(cred_path), SCOPES)
                    creds = flow.run_local_server(port=0)

                with open(str(token_path), "w") as token:
                    token.write(creds.to_json())

            self.service = build("gmail", "v1", credentials=creds)
            logger.info("Gmail API 인증 성공")
            return True

        except Exception as e:
            logger.error(f"Gmail API 인증 실패: {e}")
            return False

    def fetch_news_emails(self, max_results: int = 20) -> list[dict]:
        """뉴스 이메일 가져오기"""
        if not self.service:
            if not self.authenticate():
                return []

        try:
            # 최근 읽지 않은 이메일 검색
            query = "is:unread newer_than:1d"
            results = self.service.users().messages().list(
                userId="me", q=query, maxResults=max_results
            ).execute()

            messages = results.get("messages", [])
            emails = []

            for msg_info in messages:
                msg_id = msg_info["id"]
                if msg_id in self.processed_ids:
                    continue

                msg = self.service.users().messages().get(
                    userId="me", id=msg_id, format="full"
                ).execute()

                email_data = self._parse_email(msg)
                if email_data:
                    email_data["gmail_id"] = msg_id
                    emails.append(email_data)

            logger.info(f"신규 이메일 {len(emails)}건 수집")
            return emails

        except Exception as e:
            logger.error(f"이메일 수집 실패: {e}")
            return []

    def _parse_email(self, msg: dict) -> Optional[dict]:
        """이메일 파싱"""
        headers = msg.get("payload", {}).get("headers", [])
        header_map = {h["name"].lower(): h["value"] for h in headers}

        subject = header_map.get("subject", "")
        sender = header_map.get("from", "")
        date = header_map.get("date", "")

        # 본문 추출
        body = self._extract_body(msg.get("payload", {}))

        return {
            "subject": subject,
            "sender": sender,
            "date": date,
            "body": body[:3000],  # 길이 제한
            "snippet": msg.get("snippet", ""),
        }

    def _extract_body(self, payload: dict) -> str:
        """이메일 본문 추출"""
        body_text = ""

        if payload.get("body", {}).get("data"):
            body_text = base64.urlsafe_b64decode(
                payload["body"]["data"]
            ).decode("utf-8", errors="ignore")

        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    body_text = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                    break
            elif part.get("mimeType") == "text/html":
                data = part.get("body", {}).get("data", "")
                if data:
                    html = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                    from bs4 import BeautifulSoup
                    body_text = BeautifulSoup(html, "html.parser").get_text(strip=True)

            # 중첩 multipart 처리
            if part.get("parts"):
                body_text = self._extract_body(part) or body_text

        return body_text

    def score_relevance(self, email: dict) -> float:
        """이메일 관련성 점수 (0-10)"""
        score = 0.0
        text = f"{email['subject']} {email['body']}".lower()
        sender = email["sender"].lower()

        # 발신자 신뢰도
        for trusted in self.TRUSTED_SENDERS:
            if trusted in sender:
                score += 3.0
                break

        # 키워드 매칭
        keyword_hits = 0
        for keyword in self.RELEVANCE_KEYWORDS:
            if keyword.lower() in text:
                keyword_hits += 1

        score += min(keyword_hits * 0.5, 5.0)

        # 제목에 키워드가 있으면 가산
        subject_lower = email["subject"].lower()
        for keyword in self.RELEVANCE_KEYWORDS:
            if keyword.lower() in subject_lower:
                score += 1.0
                break

        # 본문 길이 (너무 짧으면 광고일 수 있음)
        if len(email["body"]) > 200:
            score += 1.0

        return min(score, 10.0)

    def filter_relevant_emails(self, emails: list[dict], threshold: float = 4.0) -> list[dict]:
        """관련성 높은 이메일만 필터링"""
        relevant = []
        for email in emails:
            score = self.score_relevance(email)
            email["relevance_score"] = score
            if score >= threshold:
                relevant.append(email)
                logger.info(f"관련 뉴스 감지 (점수 {score:.1f}): {email['subject']}")

        return sorted(relevant, key=lambda x: -x["relevance_score"])

    def mark_processed(self, gmail_id: str):
        """처리 완료 표시"""
        self.processed_ids.add(gmail_id)
        self._save_processed_ids()


class BlogPostGenerator:
    """뉴스 이메일로부터 블로그 포스트 생성"""

    def __init__(self):
        self.style_guide = self._load_style_guide()

    def _load_style_guide(self) -> str:
        """UK Centre 블로그 스타일 가이드"""
        return """
## UK유학센터 블로그 스타일 가이드

### 톤 & 보이스
- 전문적이면서도 친근한 톤 (존댓말 ~입니다/~합니다 체)
- 영국 유학 전문 상담사의 관점에서 작성
- 학생과 학부모에게 도움이 되는 실질적 정보 중심
- 과도한 광고성 문구 자제, 정보 제공 위주

### 구조
- 눈에 띄는 제목 (키워드 포함, 호기심 유발)
- 서론: 뉴스/소식의 핵심을 1-2문장으로 요약
- 본론: 상세 내용, 학생들에게 미치는 영향
- 결론: UK유학센터의 관점/조언, 상담 유도 (자연스럽게)

### 포맷
- 적절한 소제목 사용
- 중요 정보는 굵은 글씨
- 필요시 리스트 형태로 정리
- 관련 키워드 자연스럽게 삽입 (SEO)

### 브랜드 언급
- "UK유학센터"로 통일
- 마무리에 자연스럽게 상담 안내 (강압적이지 않게)
- 전화번호: 별도 추가
"""

    def generate_blog_post(self, email: dict) -> Optional[dict]:
        """이메일 내용으로 블로그 포스트 생성"""
        if not ANTHROPIC_API_KEY:
            logger.error("ANTHROPIC_API_KEY 미설정")
            return None

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

            prompt = f"""{self.style_guide}

---

아래 뉴스 이메일을 바탕으로 네이버 블로그 포스트를 작성해주세요.

## 뉴스 이메일
제목: {email['subject']}
발신자: {email['sender']}
내용:
{email['body'][:2000]}

---

다음 형식으로 작성해주세요:

## 블로그 제목
(SEO 최적화된 매력적인 제목)

## 블로그 본문
(위 스타일 가이드에 맞춰 작성. HTML 형식. 최소 800자 이상)

## 태그
(쉼표로 구분된 관련 태그 5-10개)

## 쓰레드 포스트
(같은 내용을 쓰레드용으로 280자 이내로 요약. 핵심 정보 + 블로그 링크 유도)
"""

            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=3000,
                messages=[{"role": "user", "content": prompt}],
            )

            result_text = response.content[0].text
            return self._parse_generated_content(result_text, email)

        except Exception as e:
            logger.error(f"블로그 포스트 생성 실패: {e}")
            return None

    def _parse_generated_content(self, text: str, email: dict) -> dict:
        """생성된 텍스트에서 구조화된 데이터 추출"""
        sections = {}
        current_section = None
        current_content = []

        for line in text.split("\n"):
            if line.startswith("## 블로그 제목"):
                current_section = "title"
                current_content = []
            elif line.startswith("## 블로그 본문"):
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = "body"
                current_content = []
            elif line.startswith("## 태그"):
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = "tags"
                current_content = []
            elif line.startswith("## 쓰레드"):
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = "threads"
                current_content = []
            elif current_section:
                current_content.append(line)

        if current_section:
            sections[current_section] = "\n".join(current_content).strip()

        return {
            "title": sections.get("title", email["subject"]),
            "body_html": sections.get("body", ""),
            "tags": [t.strip() for t in sections.get("tags", "").split(",") if t.strip()],
            "threads_text": sections.get("threads", ""),
            "source_email": email["subject"],
            "source_sender": email["sender"],
            "relevance_score": email.get("relevance_score", 0),
            "generated_at": datetime.now().isoformat(),
            "status": "draft",
        }

    def generate_threads_post(self, blog_title: str, blog_url: str = "") -> str:
        """쓰레드용 숏폼 포스트 생성"""
        if not ANTHROPIC_API_KEY:
            return f"📢 새 블로그 포스트: {blog_title}\n\n자세한 내용은 블로그에서 확인하세요!\n{blog_url}"

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
                messages=[{
                    "role": "user",
                    "content": f"""다음 블로그 제목을 쓰레드(Threads) 포스트로 변환해주세요.
280자 이내, 한국어, 영국 유학 전문가 톤, 이모지 1-2개만 사용, 블로그 링크 유도.

제목: {blog_title}
블로그 URL: {blog_url}"""
                }],
            )
            return response.content[0].text

        except Exception as e:
            logger.error(f"쓰레드 포스트 생성 실패: {e}")
            return f"📢 {blog_title}\n{blog_url}"
