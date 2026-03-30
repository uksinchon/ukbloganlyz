"""
네이버 블로그 & 쓰레드 자동 포스팅
- 네이버 블로그 API / Selenium 기반 포스팅
- Meta Threads API 연동
"""
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

from config.settings import (
    NAVER_BLOG_ACCESS_TOKEN,
    THREADS_ACCESS_TOKEN, THREADS_USER_ID,
    DATA_DIR,
)

logger = logging.getLogger(__name__)

PUBLISH_LOG_FILE = DATA_DIR / "publish_log.json"


class NaverBlogPublisher:
    """네이버 블로그 포스팅"""

    WRITE_API_URL = "https://openapi.naver.com/blog/writePost.json"

    def __init__(self):
        self.access_token = NAVER_BLOG_ACCESS_TOKEN

    def publish(self, title: str, body_html: str, tags: list[str] = None) -> Optional[str]:
        """네이버 블로그에 포스트 게시

        Returns:
            게시된 포스트 URL 또는 None
        """
        if not self.access_token:
            logger.error("NAVER_BLOG_ACCESS_TOKEN이 설정되지 않았습니다.")
            logger.info("네이버 개발자센터에서 블로그 API 접근 토큰을 발급받으세요.")
            logger.info("대안: Selenium 기반 자동 포스팅을 사용할 수 있습니다.")
            return None

        try:
            headers = {
                "Authorization": f"Bearer {self.access_token}",
            }
            data = {
                "title": title,
                "contents": body_html,
            }
            if tags:
                data["tag"] = ",".join(tags[:10])

            resp = requests.post(self.WRITE_API_URL, headers=headers, data=data, timeout=30)
            resp.raise_for_status()
            result = resp.json()

            post_url = result.get("item", {}).get("url", "")
            logger.info(f"네이버 블로그 포스팅 성공: {post_url}")
            return post_url

        except Exception as e:
            logger.error(f"네이버 블로그 포스팅 실패: {e}")
            return None

    def publish_via_selenium(self, title: str, body_html: str, tags: list[str] = None) -> Optional[str]:
        """Selenium으로 네이버 블로그 포스팅 (API 대안)

        NOTE: 이 방법을 사용하려면:
        1. playwright install chromium 실행
        2. 네이버 로그인 쿠키를 data/naver_cookies.json에 저장
        """
        try:
            from playwright.sync_api import sync_playwright

            cookies_file = DATA_DIR / "naver_cookies.json"
            if not cookies_file.exists():
                logger.error("네이버 쿠키 파일이 없습니다. 먼저 로그인 쿠키를 저장해주세요.")
                return None

            with open(cookies_file, "r") as f:
                cookies = json.load(f)

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context()
                context.add_cookies(cookies)
                page = context.new_page()

                # 블로그 글쓰기 페이지
                page.goto("https://blog.naver.com/ukcentre/postwrite")
                page.wait_for_load_state("networkidle")

                time.sleep(3)

                # SmartEditor 프레임 접근
                # Note: 네이버 에디터 구조가 변경될 수 있어 유지보수 필요
                frame = page.frame_locator("iframe.se2_input_wysiwyg")
                if frame:
                    frame.locator("body").fill(body_html)

                # 제목 입력
                title_input = page.locator("input.se2_inputarea, textarea.se2_inputarea")
                if title_input.count() > 0:
                    title_input.fill(title)

                # 발행
                publish_btn = page.locator("button:has-text('발행')")
                if publish_btn.count() > 0:
                    publish_btn.click()
                    time.sleep(3)

                current_url = page.url
                browser.close()

                logger.info(f"Selenium 포스팅 완료: {current_url}")
                return current_url

        except ImportError:
            logger.error("playwright가 설치되지 않았습니다: pip install playwright && playwright install")
            return None
        except Exception as e:
            logger.error(f"Selenium 포스팅 실패: {e}")
            return None


class ThreadsPublisher:
    """Meta Threads API 포스팅"""

    API_BASE = "https://graph.threads.net/v1.0"

    def __init__(self):
        self.access_token = THREADS_ACCESS_TOKEN
        self.user_id = THREADS_USER_ID

    def publish(self, text: str, image_url: str = None) -> Optional[str]:
        """쓰레드에 포스트 게시

        Threads API는 2단계:
        1. 미디어 컨테이너 생성
        2. 발행

        Returns:
            게시된 포스트 ID 또는 None
        """
        if not self.access_token or not self.user_id:
            logger.error("THREADS_ACCESS_TOKEN / THREADS_USER_ID가 설정되지 않았습니다.")
            return None

        try:
            # Step 1: 미디어 컨테이너 생성
            create_url = f"{self.API_BASE}/{self.user_id}/threads"
            params = {
                "media_type": "TEXT",
                "text": text[:500],  # Threads 글자 제한
                "access_token": self.access_token,
            }

            if image_url:
                params["media_type"] = "IMAGE"
                params["image_url"] = image_url

            resp = requests.post(create_url, params=params, timeout=30)
            resp.raise_for_status()
            container_id = resp.json().get("id")

            if not container_id:
                logger.error("Threads 컨테이너 생성 실패")
                return None

            # 처리 대기
            time.sleep(5)

            # Step 2: 발행
            publish_url = f"{self.API_BASE}/{self.user_id}/threads_publish"
            publish_params = {
                "creation_id": container_id,
                "access_token": self.access_token,
            }

            resp = requests.post(publish_url, params=publish_params, timeout=30)
            resp.raise_for_status()
            post_id = resp.json().get("id")

            logger.info(f"Threads 포스팅 성공: {post_id}")
            return post_id

        except Exception as e:
            logger.error(f"Threads 포스팅 실패: {e}")
            return None


class PublishManager:
    """포스팅 관리 (생성 → 승인 → 발행 워크플로우)"""

    def __init__(self):
        self.naver = NaverBlogPublisher()
        self.threads = ThreadsPublisher()
        self.publish_log = self._load_log()

    def _load_log(self) -> list:
        if PUBLISH_LOG_FILE.exists():
            with open(PUBLISH_LOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_log(self):
        with open(PUBLISH_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.publish_log, f, ensure_ascii=False, indent=2)

    def publish_to_all(self, post: dict, auto_publish: bool = False) -> dict:
        """네이버 블로그 + 쓰레드 동시 발행"""
        result = {
            "title": post["title"],
            "timestamp": datetime.now().isoformat(),
            "naver_url": None,
            "threads_id": None,
            "status": "pending",
        }

        if not auto_publish:
            result["status"] = "draft_saved"
            self.publish_log.append(result)
            self._save_log()
            logger.info(f"초안 저장: {post['title']} (수동 승인 필요)")
            return result

        # 1. 네이버 블로그 포스팅
        naver_url = self.naver.publish(
            title=post["title"],
            body_html=post.get("body_html", ""),
            tags=post.get("tags", []),
        )
        result["naver_url"] = naver_url

        # 2. 쓰레드 포스팅
        threads_text = post.get("threads_text", "")
        if not threads_text:
            threads_text = f"📢 {post['title']}\n\n자세한 내용은 블로그에서 확인하세요!"
        if naver_url:
            threads_text += f"\n\n👉 {naver_url}"

        threads_id = self.threads.publish(text=threads_text)
        result["threads_id"] = threads_id

        # 상태 업데이트
        if naver_url or threads_id:
            result["status"] = "published"
        else:
            result["status"] = "failed"

        self.publish_log.append(result)
        self._save_log()

        logger.info(f"발행 완료: {post['title']} (네이버: {naver_url}, 쓰레드: {threads_id})")
        return result

    def get_pending_drafts(self) -> list[dict]:
        """승인 대기중인 초안 목록"""
        return [log for log in self.publish_log if log.get("status") == "draft_saved"]

    def get_publish_history(self) -> list[dict]:
        """발행 이력"""
        return self.publish_log
