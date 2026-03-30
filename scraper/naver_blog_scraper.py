"""
네이버 블로그 스크래퍼
- RSS 피드 및 웹 스크래핑으로 블로그 포스트 수집
- 제목, 본문, 날짜, URL, 카테고리 추출
"""
import re
import time
import json
import hashlib
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
import feedparser
from bs4 import BeautifulSoup

from config.settings import (
    ALL_BLOGS, DATA_DIR, NAVER_BLOG_RSS_URL,
    NAVER_BLOG_BASE_URL, NAVER_CLIENT_ID, NAVER_CLIENT_SECRET,
)

logger = logging.getLogger(__name__)

# 데이터 저장 경로
POSTS_DB_FILE = DATA_DIR / "posts.json"


class NaverBlogScraper:
    """네이버 블로그 포스트 수집기"""

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self.posts_db = self._load_posts_db()

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

    # ----------------------------------------------------------
    # RSS 수집
    # ----------------------------------------------------------
    def fetch_rss(self, blog_id: str, max_items: int = 50) -> list[dict]:
        """RSS 피드에서 최근 포스트 수집"""
        url = NAVER_BLOG_RSS_URL.format(blog_id=blog_id)
        posts = []

        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_items]:
                pub_date = ""
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_date = time.strftime("%Y-%m-%d", entry.published_parsed)

                # HTML 태그 제거한 본문 요약
                summary = BeautifulSoup(
                    entry.get("summary", ""), "html.parser"
                ).get_text(strip=True)[:500]

                post = {
                    "blog_id": blog_id,
                    "title": entry.get("title", ""),
                    "url": entry.get("link", ""),
                    "date": pub_date,
                    "summary": summary,
                    "source": "rss",
                }
                post["id"] = self._post_id(blog_id, post["title"], post["date"])
                posts.append(post)

            logger.info(f"[RSS] {blog_id}: {len(posts)}개 포스트 수집")
        except Exception as e:
            logger.error(f"[RSS] {blog_id} 수집 실패: {e}")

        return posts

    # ----------------------------------------------------------
    # 웹 스크래핑 (RSS 실패 시 백업)
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

                # 포스트 제목과 링크 추출
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

                time.sleep(1)  # 요청 간격
            except Exception as e:
                logger.error(f"[WEB] {blog_id} page {page} 수집 실패: {e}")

        logger.info(f"[WEB] {blog_id}: {len(posts)}개 포스트 수집")
        return posts

    # ----------------------------------------------------------
    # Naver Search API (추가 수집)
    # ----------------------------------------------------------
    def fetch_naver_search(self, blog_id: str, query: str = "", max_items: int = 100) -> list[dict]:
        """네이버 검색 API로 블로그 포스트 검색"""
        if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
            logger.warning("네이버 API 키가 설정되지 않음 - 검색 API 건너뜀")
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
                logger.error(f"[SEARCH] {blog_id} 검색 실패: {e}")
                break

        logger.info(f"[SEARCH] {blog_id}: {len(posts)}개 포스트 수집")
        return posts

    # ----------------------------------------------------------
    # 포스트 본문 상세 수집
    # ----------------------------------------------------------
    def fetch_post_content(self, post_url: str) -> Optional[str]:
        """개별 포스트의 본문 내용 수집"""
        try:
            # 네이버 블로그는 iframe 내부에 본문이 있음
            resp = self.session.get(post_url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # iframe src 추출
            iframe = soup.select_one("iframe#mainFrame")
            if iframe and iframe.get("src"):
                iframe_url = "https://blog.naver.com" + iframe["src"]
                resp2 = self.session.get(iframe_url, timeout=15)
                resp2.raise_for_status()
                soup2 = BeautifulSoup(resp2.text, "html.parser")

                # 본문 영역 추출
                content_area = soup2.select_one(
                    ".se-main-container, .post-view, #postViewArea, .se_component_wrap"
                )
                if content_area:
                    return content_area.get_text(strip=True)[:2000]

            return None
        except Exception as e:
            logger.error(f"본문 수집 실패 {post_url}: {e}")
            return None

    # ----------------------------------------------------------
    # 전체 수집 실행
    # ----------------------------------------------------------
    def scrape_all_blogs(self, fetch_content: bool = False) -> list[dict]:
        """모든 블로그에서 포스트 수집"""
        all_posts = []
        existing_ids = {p["id"] for p in self.posts_db["posts"]}

        for name, blog_id in ALL_BLOGS.items():
            logger.info(f"수집 시작: {name} ({blog_id})")

            # 1차: RSS 수집
            posts = self.fetch_rss(blog_id)

            # RSS가 비어있으면 웹 스크래핑
            if not posts:
                posts = self.fetch_web(blog_id)

            # 네이버 검색 API 추가
            search_posts = self.fetch_naver_search(blog_id)
            posts.extend(search_posts)

            # 중복 제거
            new_posts = []
            for p in posts:
                if p["id"] not in existing_ids:
                    p["blog_name"] = name
                    p["is_own"] = blog_id in ("ukcentre", "ukcentre1")
                    p["collected_at"] = datetime.now().isoformat()

                    # 본문 수집 (선택적)
                    if fetch_content and not p.get("summary"):
                        content = self.fetch_post_content(p["url"])
                        if content:
                            p["summary"] = content[:500]

                    new_posts.append(p)
                    existing_ids.add(p["id"])

            all_posts.extend(new_posts)
            logger.info(f"{name}: 신규 {len(new_posts)}개 수집")
            time.sleep(2)  # 블로그 간 간격

        # DB에 저장
        self.posts_db["posts"].extend(all_posts)
        self._save_posts_db()

        logger.info(f"전체 신규 포스트: {len(all_posts)}개 수집 완료")
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
