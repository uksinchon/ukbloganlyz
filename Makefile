.PHONY: setup scrape analyze report email dashboard gmail scheduler full clean

# ============================================================
# UK Centre 블로그 분석 자동화 시스템
# ============================================================

# Python 실행 경로
PYTHON := python3

# 초기 설정
setup:
	$(PYTHON) -m pip install -r requirements.txt
	mkdir -p data logs reports/output
	@echo "✅ 설치 완료. .env.example을 .env로 복사하고 API 키를 설정해주세요."
	@echo "   cp .env.example .env"

# 블로그 스크래핑
scrape:
	$(PYTHON) main.py scrape

# 분석 실행
analyze:
	$(PYTHON) main.py analyze

# PDF 리포트 생성
report:
	$(PYTHON) main.py report

# 이메일 발송
email:
	$(PYTHON) main.py email

# 대시보드 실행 (http://localhost:8501)
dashboard:
	$(PYTHON) main.py dashboard

# Gmail 뉴스 체크 (1회)
gmail:
	$(PYTHON) main.py gmail

# 전체 자동화 스케줄러 시작
scheduler:
	$(PYTHON) main.py scheduler

# 전체 파이프라인 1회 실행 (스크래핑 → 분석 → 리포트 → 이메일)
full:
	$(PYTHON) main.py full

# 로그/데이터 정리
clean:
	rm -rf logs/*.log reports/output/*.pdf
	@echo "✅ 로그 및 리포트 정리 완료"
