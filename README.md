# UK Centre 경쟁사 블로그 분석 & 자동 포스팅 시스템

영국 유학 업계 경쟁사 블로그를 자동으로 모니터링·분석하고, Gmail 뉴스를 네이버 블로그 + 쓰레드로 자동 포스팅하는 시스템입니다.

## 주요 기능

### 시스템 1: 경쟁사 블로그 분석
- 본사 2개 + 경쟁사 11개 네이버 블로그 자동 스크래핑
- 주제별 트렌드 분석 (12개 카테고리)
- 본사 vs 경쟁사 비교 분석 및 놓치는 주제 감지
- Claude AI 심층 분석 인사이트
- PDF 상세 리포트 자동 생성
- 웹 대시보드 (Streamlit)
- 일간/주간/월간 이메일 리포트 (j.lee@ukcentre.co.kr)

### 시스템 2: Gmail 뉴스 → 블로그/쓰레드 자동 포스팅
- Gmail 뉴스 이메일 자동 감지 (5분 간격)
- AI 기반 관련성 점수화 및 필터링
- UK유학센터 톤앤보이스에 맞는 블로그 글 자동 생성
- 네이버 블로그 + Threads 동시 포스팅
- 승인 워크플로우 (초안 → 승인 → 발행)

## PDF 리포트 vs 대시보드 차이

| 구분 | PDF 리포트 | 웹 대시보드 |
|------|-----------|------------|
| 형태 | 정적 문서 (이메일 첨부) | 인터랙티브 웹 페이지 |
| 용도 | 정기 보고, 경영진 공유 | 실시간 현황 파악, 데이터 탐색 |
| 업데이트 | 일/주/월 단위 스냅샷 | 실시간 (5분 캐시) |
| 필터링 | 고정된 분석 결과 | 날짜, 블로그, 주제별 필터 가능 |
| 공유 | 이메일, 인쇄 가능 | URL 공유, 브라우저에서 접속 |
| 내용 | 종합 분석 + AI 인사이트 | 차트, 히트맵, 드릴다운 기능 |

## 빠른 시작

```bash
# 1. 설치
make setup

# 2. 환경변수 설정
cp .env.example .env
# .env 파일을 열어 API 키 입력

# 3. 1회 전체 실행 (스크래핑 → 분석 → 리포트 → 이메일)
make full

# 4. 대시보드 실행
make dashboard

# 5. 전체 자동화 시작
make scheduler
```

## 개별 명령어

```bash
python main.py scrape      # 블로그 스크래핑
python main.py analyze     # 분석 실행
python main.py report      # PDF 리포트 생성
python main.py email       # 이메일 발송
python main.py dashboard   # 대시보드 실행 (http://localhost:8501)
python main.py gmail       # Gmail 뉴스 체크 (1회)
python main.py scheduler   # 자동화 스케줄러 시작
python main.py full        # 전체 1회 실행
```

## 필수 API 키 설정

### 기본 (블로그 분석만 사용 시)
- 없음 (RSS 스크래핑은 API 키 불필요)

### 고급 기능
| API | 용도 | 발급처 |
|-----|------|--------|
| `ANTHROPIC_API_KEY` | AI 분석, 글 생성 | https://console.anthropic.com |
| `NAVER_CLIENT_ID/SECRET` | 네이버 검색 API | https://developers.naver.com |
| `SMTP_USER/PASSWORD` | 이메일 발송 | Gmail 앱 비밀번호 |
| `GMAIL_CREDENTIALS_FILE` | Gmail 수신 모니터링 | Google Cloud Console |
| `THREADS_ACCESS_TOKEN` | Threads 포스팅 | Meta Developer Console |
| `NAVER_BLOG_ACCESS_TOKEN` | 네이버 블로그 포스팅 | 네이버 개발자센터 |

## 모니터링 대상 블로그

### 본사
- UK유학센터 메인: https://blog.naver.com/ukcentre
- UK유학센터 서브: https://blog.naver.com/ukcentre1

### 경쟁사
- 유켄유학원: ukentkorea, ukenkorea1
- EDM유학: edmedu
- IDP유학: idp_uk
- 더유학: uhakbooking
- SAUK: theukcom, saukbusan
- 유학시그널: uhaksignal
- 디지털조선일보: ukchosun
- 종로유학: chongroblog
- 세이인터내셔널: sassistsyou

## 자동 스케줄

| 작업 | 주기 | 시간 (KST) |
|------|------|-----------|
| 블로그 스크래핑 | 6시간마다 | - |
| 일일 분석 리포트 | 매일 | 08:00 |
| 주간 분석 리포트 | 매주 월요일 | 09:00 |
| 월간 분석 리포트 | 매월 1일 | 10:00 |
| Gmail 뉴스 체크 | 5분마다 | - |

## 프로젝트 구조

```
ukbloganlyz/
├── main.py                     # CLI 메인 진입점
├── config/
│   └── settings.py             # 전체 설정
├── scraper/
│   └── naver_blog_scraper.py   # 네이버 블로그 스크래퍼
├── analyzer/
│   └── trend_analyzer.py       # 트렌드 분석 엔진
├── reports/
│   └── pdf_generator.py        # PDF 리포트 생성기
├── dashboard/
│   └── app.py                  # Streamlit 대시보드
├── notifier/
│   └── email_sender.py         # 이메일 발송
├── gmail_pipeline/
│   ├── gmail_monitor.py        # Gmail 모니터링 & 글 생성
│   └── publisher.py            # 네이버/Threads 포스팅
├── scheduler/
│   └── main_scheduler.py       # APScheduler 기반 스케줄러
├── data/                       # 수집 데이터 (git 제외)
├── logs/                       # 로그 (git 제외)
└── reports/output/             # 생성된 PDF (git 제외)
```
