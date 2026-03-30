"""
UK Centre 경쟁사 블로그 분석 & 자동 포스팅 시스템 설정
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# 프로젝트 경로
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
REPORT_DIR = BASE_DIR / "reports" / "output"
TEMPLATE_DIR = BASE_DIR / "templates"

for d in [DATA_DIR, LOG_DIR, REPORT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ============================================================
# 블로그 설정 - 3그룹: 신촌지사 / 본사 / 경쟁사
# ============================================================
SINCHON_BLOGS = {
    "영국유학센터 신촌지사": "pedu2",
}

HQ_BLOGS = {
    "영국유학센터 본사①": "ukcentre",
    "영국유학센터 본사②": "ukcentre1",
}

# 본사 전체 (신촌지사 + 본사)
OWN_BLOGS = {**SINCHON_BLOGS, **HQ_BLOGS}

COMPETITOR_BLOGS = {
    "유켄유학원①": "ukenkorea",
    "유켄유학원②": "ukenkorea1",
    "SAUK 서울": "theukcom",
    "SAUK 부산": "saukbusan",
    "EDM유학": "edmedu",
    "IDP유학": "idp_uk",
    "더유학": "uhakbooking",
    "유학시그널": "uhaksignal",
    "디지털조선일보": "ukchosun",
    "종로유학": "chongroblog",
    "세이인터내셔널": "sassistsyou",
}

ALL_BLOGS = {**OWN_BLOGS, **COMPETITOR_BLOGS}

# 사용자 추가 경쟁사 저장 파일
CUSTOM_COMPETITORS_FILE = DATA_DIR / "custom_competitors.json"

NAVER_BLOG_BASE_URL = "https://blog.naver.com/{blog_id}"
NAVER_BLOG_RSS_URL = "https://rss.blog.naver.com/{blog_id}.xml"
NAVER_BLOG_POST_LIST_URL = "https://blog.naver.com/PostList.naver?blogId={blog_id}&from=postList&categoryNo=0&currentPage={page}"

# ============================================================
# API 키 설정
# ============================================================
# API 키 설정 (환경변수 또는 Streamlit secrets 지원)
# ============================================================
def _get_secret(key: str, default: str = "") -> str:
    """환경변수 → Streamlit secrets 순서로 API 키 조회"""
    val = os.getenv(key, "")
    if val:
        return val
    try:
        import streamlit as st
        return st.secrets.get(key, default)
    except Exception:
        return default

ANTHROPIC_API_KEY = _get_secret("ANTHROPIC_API_KEY")
NAVER_CLIENT_ID = _get_secret("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = _get_secret("NAVER_CLIENT_SECRET")

# Gmail API
GMAIL_CREDENTIALS_FILE = os.getenv("GMAIL_CREDENTIALS_FILE", str(BASE_DIR / "credentials.json"))
GMAIL_TOKEN_FILE = os.getenv("GMAIL_TOKEN_FILE", str(BASE_DIR / "token.json"))

# Threads API
THREADS_ACCESS_TOKEN = os.getenv("THREADS_ACCESS_TOKEN", "")
THREADS_USER_ID = os.getenv("THREADS_USER_ID", "")

# Naver Blog API (for posting)
NAVER_BLOG_API_CLIENT_ID = os.getenv("NAVER_BLOG_API_CLIENT_ID", "")
NAVER_BLOG_API_CLIENT_SECRET = os.getenv("NAVER_BLOG_API_CLIENT_SECRET", "")
NAVER_BLOG_ACCESS_TOKEN = os.getenv("NAVER_BLOG_ACCESS_TOKEN", "")

# ============================================================
# 이메일 설정
# ============================================================
REPORT_EMAIL_TO = "j.lee@ukcentre.co.kr"
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

# ============================================================
# 스케줄링 설정
# ============================================================
SCHEDULE_DAILY_HOUR = 8       # 매일 오전 8시
SCHEDULE_WEEKLY_DAY = "mon"   # 매주 월요일
SCHEDULE_WEEKLY_HOUR = 9      # 오전 9시
SCHEDULE_MONTHLY_DAY = 1      # 매월 1일
SCHEDULE_MONTHLY_HOUR = 10    # 오전 10시

# Gmail 폴링 간격 (분)
GMAIL_POLL_INTERVAL_MINUTES = 5

# ============================================================
# 분석 설정
# ============================================================
# 트렌드 분석용 키워드 카테고리
TOPIC_CATEGORIES = {
    "영국대학": ["영국대학", "영국유학", "UK university", "university ranking", "대학순위", "대학원", "학사", "석사", "박사", "MBA"],
    "비자/이민": ["비자", "visa", "이민", "영주권", "취업비자", "학생비자", "Graduate visa", "Skilled Worker"],
    "어학연수": ["어학연수", "영어", "IELTS", "아이엘츠", "영어시험", "어학원", "language school"],
    "장학금": ["장학금", "scholarship", "펀딩", "funding", "재정지원", "학비"],
    "생활정보": ["숙소", "생활비", "accommodation", "기숙사", "홈스테이", "생활", "문화"],
    "입학/지원": ["입학", "지원", "UCAS", "application", "원서", "합격", "오퍼", "offer", "conditional"],
    "파운데이션": ["파운데이션", "foundation", "프리마스터", "pre-master", "패스웨이", "pathway"],
    "취업/커리어": ["취업", "career", "인턴", "internship", "취업률", "졸업후"],
    "학교별정보": ["옥스포드", "캠브리지", "UCL", "임페리얼", "LSE", "킹스칼리지", "에딘버러", "맨체스터", "워릭", "브리스톨", "러프버러"],
    "시험/자격": ["IELTS", "TOEFL", "GRE", "GMAT", "시험", "점수", "자격"],
    "이벤트/설명회": ["설명회", "상담", "박람회", "세미나", "웨비나", "이벤트", "오픈데이"],
    "뉴스/정책": ["뉴스", "정책", "변경", "업데이트", "발표", "규정"],
}

# ============================================================
# 대시보드 설정
# ============================================================
DASHBOARD_HOST = "0.0.0.0"
DASHBOARD_PORT = 8501

# ============================================================
# 로깅 설정
# ============================================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
