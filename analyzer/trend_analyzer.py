"""
트렌드 분석 엔진
- 주제별 분류 및 빈도 분석
- 경쟁사 vs 본사 비교 분석
- 키워드 트렌드 추출
- Claude AI를 활용한 심층 분석
"""
import json
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Optional

from config.settings import (
    ANTHROPIC_API_KEY, DATA_DIR, OWN_BLOGS, COMPETITOR_BLOGS,
    TOPIC_CATEGORIES, ALL_BLOGS,
)

logger = logging.getLogger(__name__)


class TrendAnalyzer:
    """블로그 포스트 트렌드 분석"""

    def __init__(self, posts: list[dict]):
        self.posts = posts
        self.own_blog_ids = set(OWN_BLOGS.values())
        self.competitor_blog_ids = set(COMPETITOR_BLOGS.values())

    # ----------------------------------------------------------
    # 주제 분류
    # ----------------------------------------------------------
    def categorize_post(self, post: dict) -> list[str]:
        """포스트를 주제 카테고리로 분류"""
        text = f"{post.get('title', '')} {post.get('summary', '')}".lower()
        categories = []

        for category, keywords in TOPIC_CATEGORIES.items():
            for keyword in keywords:
                if keyword.lower() in text:
                    categories.append(category)
                    break

        return categories if categories else ["기타"]

    def categorize_all_posts(self) -> list[dict]:
        """모든 포스트에 카테고리 부여"""
        for post in self.posts:
            post["categories"] = self.categorize_post(post)
        return self.posts

    # ----------------------------------------------------------
    # 포스팅 통계
    # ----------------------------------------------------------
    def posting_count_by_blog(self) -> dict:
        """블로그별 포스팅 수"""
        counts = Counter()
        for post in self.posts:
            blog_name = post.get("blog_name", post.get("blog_id", "unknown"))
            counts[blog_name] += 1
        return dict(counts.most_common())

    def posting_count_by_date(self) -> dict:
        """날짜별 포스팅 수"""
        counts = defaultdict(int)
        for post in self.posts:
            date = post.get("date", "")
            if date:
                counts[date] += 1
        return dict(sorted(counts.items()))

    def posting_count_by_category(self) -> dict:
        """카테고리별 포스팅 수"""
        counts = Counter()
        for post in self.posts:
            for cat in post.get("categories", ["미분류"]):
                counts[cat] += 1
        return dict(counts.most_common())

    # ----------------------------------------------------------
    # 경쟁사 vs 본사 비교
    # ----------------------------------------------------------
    def compare_own_vs_competitors(self) -> dict:
        """본사 vs 경쟁사 포스팅 비교"""
        own_posts = [p for p in self.posts if p.get("blog_id") in self.own_blog_ids]
        comp_posts = [p for p in self.posts if p.get("blog_id") in self.competitor_blog_ids]

        own_categories = Counter()
        comp_categories = Counter()

        for p in own_posts:
            for cat in p.get("categories", []):
                own_categories[cat] += 1

        for p in comp_posts:
            for cat in p.get("categories", []):
                comp_categories[cat] += 1

        # 경쟁사는 다루지만 본사가 놓치는 주제
        all_categories = set(own_categories.keys()) | set(comp_categories.keys())
        missed_topics = {}
        for cat in all_categories:
            own_count = own_categories.get(cat, 0)
            comp_count = comp_categories.get(cat, 0)
            if comp_count > 0 and own_count == 0:
                missed_topics[cat] = comp_count
            elif comp_count > own_count * 2:
                missed_topics[cat] = comp_count

        return {
            "own_total": len(own_posts),
            "competitor_total": len(comp_posts),
            "own_categories": dict(own_categories),
            "competitor_categories": dict(comp_categories),
            "missed_topics": dict(sorted(missed_topics.items(), key=lambda x: -x[1])),
        }

    # ----------------------------------------------------------
    # 키워드 분석
    # ----------------------------------------------------------
    def extract_top_keywords(self, n: int = 30) -> list[tuple[str, int]]:
        """전체 포스트에서 상위 키워드 추출"""
        # 불용어
        stopwords = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "그", "이", "저", "것", "수", "등", "및", "또", "더",
            "하다", "있다", "되다", "않다", "없다", "같다",
            "합니다", "입니다", "습니다", "에서", "으로", "에게",
            "블로그", "포스트", "글", "작성", "공유",
        }

        word_counts = Counter()
        for post in self.posts:
            text = f"{post.get('title', '')} {post.get('summary', '')}"
            # 한글 + 영어 단어 추출 (2글자 이상)
            words = re.findall(r"[가-힣]{2,}|[a-zA-Z]{3,}", text)
            for word in words:
                word_lower = word.lower()
                if word_lower not in stopwords and len(word) >= 2:
                    word_counts[word_lower] += 1

        return word_counts.most_common(n)

    # ----------------------------------------------------------
    # 트렌드 감지 (기간 비교)
    # ----------------------------------------------------------
    def detect_trending_topics(
        self,
        current_start: str,
        current_end: str,
        previous_start: str,
        previous_end: str,
    ) -> dict:
        """이전 기간 대비 증가한 주제 감지"""
        current_posts = [
            p for p in self.posts
            if p.get("date", "") >= current_start and p.get("date", "") <= current_end
        ]
        previous_posts = [
            p for p in self.posts
            if p.get("date", "") >= previous_start and p.get("date", "") <= previous_end
        ]

        current_cats = Counter()
        previous_cats = Counter()

        for p in current_posts:
            for cat in p.get("categories", []):
                current_cats[cat] += 1

        for p in previous_posts:
            for cat in p.get("categories", []):
                previous_cats[cat] += 1

        trending = {}
        for cat in set(current_cats.keys()) | set(previous_cats.keys()):
            curr = current_cats.get(cat, 0)
            prev = previous_cats.get(cat, 0)
            if prev == 0 and curr > 0:
                trending[cat] = {"current": curr, "previous": prev, "change": "NEW"}
            elif prev > 0:
                change_pct = ((curr - prev) / prev) * 100
                if change_pct > 20:
                    trending[cat] = {
                        "current": curr,
                        "previous": prev,
                        "change": f"+{change_pct:.0f}%",
                    }

        return dict(sorted(trending.items(), key=lambda x: -x[1]["current"]))

    # ----------------------------------------------------------
    # 경쟁사별 상세 분석
    # ----------------------------------------------------------
    def competitor_detail_analysis(self) -> list[dict]:
        """각 경쟁사별 상세 분석"""
        blog_name_map = {v: k for k, v in ALL_BLOGS.items()}
        blog_groups = defaultdict(list)

        for post in self.posts:
            blog_groups[post.get("blog_id", "")].append(post)

        results = []
        for blog_id, posts in blog_groups.items():
            cats = Counter()
            for p in posts:
                for cat in p.get("categories", []):
                    cats[cat] += 1

            results.append({
                "blog_id": blog_id,
                "blog_name": blog_name_map.get(blog_id, blog_id),
                "total_posts": len(posts),
                "top_categories": dict(cats.most_common(5)),
                "recent_titles": [p["title"] for p in sorted(
                    posts, key=lambda x: x.get("date", ""), reverse=True
                )[:5]],
                "is_own": blog_id in self.own_blog_ids,
            })

        return sorted(results, key=lambda x: -x["total_posts"])

    # ----------------------------------------------------------
    # Claude AI 심층 분석
    # ----------------------------------------------------------
    def ai_deep_analysis(self, period_label: str = "이번 주") -> Optional[str]:
        """Claude API를 사용한 심층 트렌드 분석"""
        if not ANTHROPIC_API_KEY:
            logger.warning("ANTHROPIC_API_KEY 미설정 - AI 분석 건너뜀")
            return None

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

            # 분석 데이터 요약
            comparison = self.compare_own_vs_competitors()
            top_keywords = self.extract_top_keywords(20)
            blog_analysis = self.competitor_detail_analysis()

            prompt = f"""당신은 영국 유학 시장 전문 분석가입니다.
아래는 {period_label} 영국 유학 관련 블로그 포스팅 분석 데이터입니다.

## 본사 vs 경쟁사 비교
- 본사 포스팅 수: {comparison['own_total']}
- 경쟁사 포스팅 수: {comparison['competitor_total']}
- 본사 주제 분포: {json.dumps(comparison['own_categories'], ensure_ascii=False)}
- 경쟁사 주제 분포: {json.dumps(comparison['competitor_categories'], ensure_ascii=False)}
- 본사가 놓치는 주제: {json.dumps(comparison['missed_topics'], ensure_ascii=False)}

## 상위 키워드
{json.dumps(top_keywords, ensure_ascii=False)}

## 경쟁사별 분석
{json.dumps(blog_analysis[:5], ensure_ascii=False, indent=2)}

## 최근 포스트 제목 (최신 20개)
{json.dumps([p['title'] for p in sorted(self.posts, key=lambda x: x.get('date',''), reverse=True)[:20]], ensure_ascii=False)}

위 데이터를 바탕으로 다음을 분석해주세요:

1. **주요 트렌드**: 현재 업계에서 가장 많이 다루는 주제 3-5개
2. **놓치는 기회**: 경쟁사가 다루지만 본사(UK유학센터)가 놓치고 있는 주제
3. **경쟁사 동향**: 주요 경쟁사들의 콘텐츠 전략 패턴
4. **추천 콘텐츠**: 본사가 즉시 작성해야 할 블로그 주제 5개 (제목 포함)
5. **키워드 기회**: SEO 관점에서 선점할 수 있는 키워드

한국어로 작성하고, 실행 가능한 구체적 인사이트를 제공하세요."""

            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )

            return response.content[0].text

        except Exception as e:
            logger.error(f"AI 분석 실패: {e}")
            return None

    # ----------------------------------------------------------
    # 전체 분석 리포트 생성
    # ----------------------------------------------------------
    def generate_full_analysis(self, period_label: str = "분석 기간") -> dict:
        """종합 분석 리포트 데이터 생성"""
        self.categorize_all_posts()

        report = {
            "period": period_label,
            "generated_at": datetime.now().isoformat(),
            "total_posts": len(self.posts),
            "posting_by_blog": self.posting_count_by_blog(),
            "posting_by_date": self.posting_count_by_date(),
            "posting_by_category": self.posting_count_by_category(),
            "own_vs_competitor": self.compare_own_vs_competitors(),
            "top_keywords": self.extract_top_keywords(),
            "competitor_details": self.competitor_detail_analysis(),
            "ai_analysis": self.ai_deep_analysis(period_label),
        }

        # 저장
        report_file = DATA_DIR / f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(f"분석 리포트 생성: {report_file}")
        return report
