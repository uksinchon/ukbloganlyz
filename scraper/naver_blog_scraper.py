"""
네이버 블로그 스크래퍼
- RSS 피드 및 웹 스크래핑으로 블로그 포스트 수집
- 모바일 페이지 스크래핑 (데스크탑보다 안정적)
- 제목, 본문, 날짜, URL, 카테고리 추출
"""
import re
import time
import json
import hashlib
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable

import requests
import feedparser
from bs4 import BeautifulSoup

from config.settings import (
    ALL_BLOGS, OWN_BLOGS, DATA_DIR, NAVER_BLOG_RSS_URL,
    NAVER_BLOG_BASE_URL, NAVER_CLIENT_ID, NAVER_CLIENT_SECRET,
    CUSTOM_COMPETITORS_FILE,
)

logger = logging.getLogger(__name__)

# 데이터 저장 경로
POSTS_DB_FILE = DATA_DIR / "posts.json"


def _load_custom_competitors() -> dict:
    if CUSTOM_COMPETITORS_FILE.exists():
        with open(CUSTOM_COMPETITORS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


class NaverBlogScraper:
    """네이버 블로그 포스트 수집기"""

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.0 Mobile/15E148 Safari/604.1"
        )
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self.posts_db = self._load_posts_db()
        # 진행상황 콜백 (대시보드에서 사용)
        self.on_progress: Optional[Callable[[str], None]] = None

    def _log(self, msg: str):
        logger.info(msg)
        if self.on_progress:
            self.on_progress(msg)

    # ----------------------------------------------------------
    # Persistence
    # ----------------------------------------------------------
    def _load_posts_db(self) -> dict:
        if POSTS_DB_FILE.exists():
            with open(POSTS_DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"posts": [], "last_updated": None}

    def _save_posts_db(self):
        self.posts_db["last_updated"] = datetime.now().isoformat()
        with open(POSTS_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(self.posts_db, f, ensure_ascii=False, indent=2)

    def _post_id(self, blog_id: str, title: str, date: str) -> str:
        raw = f"{blog_id}:{title}:{date}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _get_all_target_blogs(self) -> dict:
        """고정 블로그 + 사용자 추가 경쟁사"""
        custom = _load_custom_competitors()
        return {**ALL_BLOGS, **custom}

    def _is_own_blog(self, blog_id: str) -> bool:
        return blog_id in OWN_BLOGS.values()

    # ----------------------------------------------------------
    # RSS 수집
    # ----------------------------------------------------------
    def fetch_rss(self, blog_id: str, max_items: int = 50) -> list[dict]:
        """RSS 피드에서 최근 포스트 수집"""
        url = NAVER_BLOG_RSS_URL.format(blog_id=blog_id)
        posts = []

        try:
            resp = self.session.get(url, timeout=15)
            feed = feedparser.parse(resp.content)

            for entry in feed.entries[:max_items]:
                pub_date = ""
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_date = time.strftime("%Y-%m-%d", entry.published_parsed)
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    pub_date = time.strftime("%Y-%m-%d", entry.updated_parsed)

                # HTML 태그 제거한 본문 요약
                summary = BeautifulSoup(
                    entry.get("summary", entry.get("description", "")), "html.parser"
                ).get_text(strip=True)[:500]

                title = entry.get("title", "").strip()
                if not title:
                    continue

                post = {
                    "blog_id": blog_id,
                    "title": title,
                    "url": entry.get("link", ""),
                    "date": pub_date,
                    "summary": summary,
                    "source": "rss",
                }
                post["id"] = self._post_id(blog_id, post["title"], post["date"])
                posts.append(post)

            self._log(f"[RSS] {blog_id}: {len(posts)}개 수집")
        except Exception as e:
            self._log(f"[RSS] {blog_id}: 실패 ({e})")

        return posts

    # ----------------------------------------------------------
    # 모바일 웹 스크래핑 (더 안정적)
    # ----------------------------------------------------------
    @staticmethod
    def _parse_naver_date(raw: str) -> str:
        """네이버 API 날짜를 YYYY-MM-DD로 변환
        지원 형식: '2026. 3. 31. 14:30', '2026-03-31', '20260331',
                   Unix ms timestamp (숫자 문자열)
        """
        if not raw:
            return ""
        raw = str(raw).strip()

        # Unix timestamp (밀리초)
        if raw.isdigit() and len(raw) >= 10:
            try:
                ts = int(raw) / 1000 if len(raw) >= 13 else int(raw)
                return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            except (ValueError, OSError):
                pass

        # "2026. 3. 31." 또는 "2026. 3. 31. 14:30" (한국식 점 구분)
        m = re.match(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})", raw)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

        # "2026-03-31" 또는 "2026-03-31T..."  (ISO 형식)
        m = re.match(r"(\d{4}-\d{2}-\d{2})", raw)
        if m:
            return m.group(1)

        # "20260331" (숫자 8자리)
        m = re.match(r"(\d{4})(\d{2})(\d{2})", raw)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

        return ""

    def fetch_mobile(self, blog_id: str, count: int = 30) -> list[dict]:
        """모바일 블로그 페이지에서 포스트 목록 수집"""
        posts = []
        url = f"https://m.blog.naver.com/api/blogs/{blog_id}/post-list?categoryNo=0&itemCount={count}&page=1"

        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("result", {}).get("items", [])

                for item in items:
                    title = item.get("titleWithInspectMessage", item.get("title", "")).strip()
                    if not title:
                        continue

                    log_no = item.get("logNo", "")
                    add_date = item.get("addDate", "")
                    pub_date = self._parse_naver_date(add_date)

                    post = {
                        "blog_id": blog_id,
                        "title": BeautifulSoup(title, "html.parser").get_text(strip=True),
                        "url": f"https://blog.naver.com/{blog_id}/{log_no}",
                        "date": pub_date,
                        "summary": item.get("briefContents", "")[:500],
                        "source": "mobile_api",
                    }
                    post["id"] = self._post_id(blog_id, post["title"], post["date"])
                    posts.append(post)

                self._log(f"[MOBILE] {blog_id}: {len(posts)}개 수집")
            else:
                self._log(f"[MOBILE] {blog_id}: HTTP {resp.status_code}")
        except Exception as e:
            self._log(f"[MOBILE] {blog_id}: 실패 ({e})")

        return posts

    # ----------------------------------------------------------
    # 웹 스크래핑 (백업)
    # ----------------------------------------------------------
    def fetch_web(self, blog_id: str, pages: int = 3) -> list[dict]:
        """웹 스크래핑으로 포스트 목록 수집"""
        posts = []

        for page in range(1, pages + 1):
            url = (
                f"https://blog.naver.com/PostList.naver"
                f"?blogId={blog_id}&from=postList&categoryNo=0&currentPage={page}"
            )
            try:
                resp = self.session.get(url, timeout=15)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                for item in soup.select(".post-item, .item, .title a, table.post-list td a"):
                    title = item.get_text(strip=True)
                    link = item.get("href", "")
                    if title and len(title) > 3:
                        if not link.startswith("http"):
                            link = f"https://blog.naver.com{link}"
                        post = {
                            "blog_id": blog_id,
                            "title": title,
                            "url": link,
                            "date": datetime.now().strftime("%Y-%m-%d"),
                            "summary": "",
                            "source": "web",
                        }
                        post["id"] = self._post_id(blog_id, title, post["date"])
                        posts.append(post)

                time.sleep(1)
            except Exception as e:
                self._log(f"[WEB] {blog_id} page {page}: 실패 ({e})")

        if posts:
            self._log(f"[WEB] {blog_id}: {len(posts)}개 수집")
        return posts

    # ----------------------------------------------------------
    # Naver Search API (추가 수집)
    # ----------------------------------------------------------
    def fetch_naver_search(self, blog_id: str, query: str = "", max_items: int = 100) -> list[dict]:
        """네이버 검색 API로 블로그 포스트 검색"""
        if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
            return []

        search_query = f"site:blog.naver.com/{blog_id} {query}".strip()
        url = "https://openapi.naver.com/v1/search/blog.json"
        headers = {
            "X-Naver-Client-Id": NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
        }

        posts = []
        for start in range(1, max_items, 10):
            params = {
                "query": search_query,
                "display": 10,
                "start": start,
                "sort": "date",
            }
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()

                for item in data.get("items", []):
                    clean_title = BeautifulSoup(item["title"], "html.parser").get_text()
                    clean_desc = BeautifulSoup(item["description"], "html.parser").get_text()

                    post = {
                        "blog_id": blog_id,
                        "title": clean_title,
                        "url": item["link"],
                        "date": item.get("postdate", ""),
                        "summary": clean_desc[:500],
                        "source": "search_api",
                    }
                    post["id"] = self._post_id(blog_id, clean_title, post["date"])
                    posts.append(post)

                time.sleep(0.5)
            except Exception as e:
                self._log(f"[SEARCH] {blog_id}: 실패 ({e})")
                break

        if posts:
            self._log(f"[SEARCH] {blog_id}: {len(posts)}개 수집")
        return posts

    # ----------------------------------------------------------
    # 전체 수집 실행
    # ----------------------------------------------------------
    def scrape_all_blogs(self, fetch_content: bool = False) -> list[dict]:
        """모든 블로그에서 포스트 수집"""
        all_posts = []
        existing_ids = {p["id"] for p in self.posts_db["posts"]}
        target_blogs = self._get_all_target_blogs()

        self._log(f"스크래핑 시작: {len(target_blogs)}개 블로그")

        for name, blog_id in target_blogs.items():
            self._log(f"수집 중: {name} ({blog_id})")

            # 1차: 모바일 API (가장 안정적)
            posts = self.fetch_mobile(blog_id)

            # 2차: RSS
            if not posts:
                posts = self.fetch_rss(blog_id)

            # 3차: 웹 스크래핑
            if not posts:
                posts = self.fetch_web(blog_id)

            # 4차: 네이버 검색 API (키 있을 때만)
            search_posts = self.fetch_naver_search(blog_id)
            posts.extend(search_posts)

            # 중복 제거 및 저장
            new_posts = []
            for p in posts:
                if p["id"] not in existing_ids:
                    p["blog_name"] = name
                    p["is_own"] = self._is_own_blog(blog_id)
                    p["collected_at"] = datetime.now().isoformat()
                    new_posts.append(p)
                    existing_ids.add(p["id"])

            all_posts.extend(new_posts)
            self._log(f"  → {name}: 신규 {len(new_posts)}개")
            time.sleep(1)  # 블로그 간 간격

        # DB에 저장
        self.posts_db["posts"].extend(all_posts)
        self._save_posts_db()

        self._log(f"스크래핑 완료: 총 {len(all_posts)}개 신규 포스트")
        return all_posts

    def get_posts_by_period(
        self,
        start_date: str,
        end_date: str,
        blog_id: Optional[str] = None,
    ) -> list[dict]:
        """특정 기간의 포스트 조회"""
        results = []
        for post in self.posts_db["posts"]:
            if not post.get("date"):
                continue
            if start_date <= post["date"] <= end_date:
                if blog_id is None or post["blog_id"] == blog_id:
                    results.append(post)
        return results

    def get_recent_posts(self, days: int = 1) -> list[dict]:
        """최근 N일간의 포스트 조회"""
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        return self.get_posts_by_period(start, end)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scraper = NaverBlogScraper()
    posts = scraper.scrape_all_blogs()
    print(f"\n총 {len(posts)}개 포스트 수집 완료")
    for p in posts[:5]:
        print(f"  [{p['blog_name']}] {p['title']} ({p['date']})")
