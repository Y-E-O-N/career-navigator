#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Wanted 채용공고 크롤러 (Playwright 버전)

Playwright를 사용하여 동적 페이지를 크롤링합니다.
검색 결과 목록과 상세 페이지 모두 수집합니다.
"""

import re
import json
import asyncio
from typing import List, Dict, Optional
from urllib.parse import quote, urljoin
from datetime import datetime

try:
    from playwright.async_api import async_playwright, Page, Browser
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

from config.settings import settings
from utils.helpers import setup_logger, clean_text, extract_skills_from_text


class WantedPlaywrightCrawler:
    """Playwright 기반 Wanted 크롤러"""

    def __init__(self):
        self.site_name = 'wanted'
        self.base_url = 'https://www.wanted.co.kr'
        self.search_url = 'https://www.wanted.co.kr/search'
        self.logger = setup_logger(f"crawler.{self.site_name}")
        self.browser: Optional[Browser] = None
        self.request_delay = settings.crawler.request_delay

    async def init_browser(self, headless: bool = True):
        """브라우저 초기화"""
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError("playwright가 설치되어 있지 않습니다. 'pip install playwright && playwright install chromium' 실행하세요.")

        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=headless)
        self.logger.info("브라우저 초기화 완료")

    async def close_browser(self):
        """브라우저 종료"""
        if self.browser:
            await self.browser.close()
            self.logger.info("브라우저 종료")

    async def search_jobs(self, keyword: str, max_pages: int = 5) -> List[Dict]:
        """
        Wanted 채용공고 검색

        Args:
            keyword: 검색 키워드
            max_pages: 최대 스크롤 횟수

        Returns:
            채용공고 목록 (기본 정보만)
        """
        if not self.browser:
            await self.init_browser()

        page = await self.browser.new_page()
        jobs = []

        try:
            # 검색 페이지로 이동
            search_url = f"{self.search_url}?query={quote(keyword)}&tab=position"
            self.logger.info(f"검색 URL: {search_url}")

            await page.goto(search_url, wait_until='networkidle')
            await asyncio.sleep(2)  # 초기 로딩 대기

            # 스크롤하며 더 많은 결과 로드
            for scroll_count in range(max_pages):
                # 현재 페이지의 채용공고 카드 수집
                job_cards = await page.query_selector_all('[class*="JobCard_content"]')

                self.logger.info(f"스크롤 {scroll_count + 1}: {len(job_cards)}개 카드 발견")

                # 스크롤 다운
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await asyncio.sleep(self.request_delay)

                # 새로운 카드가 로드되었는지 확인
                new_cards = await page.query_selector_all('[class*="JobCard_content"]')
                if len(new_cards) == len(job_cards):
                    self.logger.info("더 이상 새로운 결과 없음")
                    break

            # 모든 채용공고 링크에서 정보 추출 (a 태그 기준)
            job_links = await page.query_selector_all('a[href*="/wd/"]')

            for link in job_links:
                try:
                    job = await self._parse_job_link(link)
                    if job and job.get('job_id'):
                        # 중복 제거
                        if not any(j['job_id'] == job['job_id'] for j in jobs):
                            jobs.append(job)
                except Exception as e:
                    self.logger.debug(f"링크 파싱 실패: {e}")

            self.logger.info(f"검색 완료: {len(jobs)}개 채용공고 발견")

        except Exception as e:
            self.logger.error(f"검색 실패: {e}")

        finally:
            await page.close()

        return jobs

    async def _parse_job_link(self, link) -> Optional[Dict]:
        """채용공고 링크에서 정보 추출"""
        try:
            # href에서 job_id 추출
            href = await link.get_attribute('href')
            if not href:
                return None

            match = re.search(r'/wd/(\d+)', href)
            if not match:
                return None

            job_id = match.group(1)
            url = f"{self.base_url}/wd/{job_id}"

            # 링크 내부의 카드 컨텐츠에서 정보 추출
            # 제목
            title_elem = await link.query_selector('[class*="JobCard_title"], strong')
            title = await title_elem.inner_text() if title_elem else ''

            if not title:
                return None

            # 회사명
            company_elem = await link.query_selector('[class*="CompanyNameWithLocationPeriod__company"], [class*="company"]')
            company_name = await company_elem.inner_text() if company_elem else ''

            # 경력/위치 정보
            location_elem = await link.query_selector('[class*="CompanyNameWithLocationPeriod__location"], [class*="location"]')
            experience_level = await location_elem.inner_text() if location_elem else ''

            # 보상금
            reward_elem = await link.query_selector('[class*="JobCard_reward"], [class*="reward"]')
            reward_info = await reward_elem.inner_text() if reward_elem else ''

            return {
                'source_site': self.site_name,
                'job_id': job_id,
                'title': clean_text(title),
                'company_name': clean_text(company_name),
                'experience_level': clean_text(experience_level),
                'reward_info': clean_text(reward_info),
                'url': url
            }

        except Exception as e:
            self.logger.debug(f"링크 파싱 오류: {e}")
            return None

    async def get_job_detail(self, job_id: str) -> Optional[Dict]:
        """
        채용공고 상세 정보 조회

        Args:
            job_id: 채용공고 ID

        Returns:
            상세 정보 딕셔너리
        """
        if not self.browser:
            await self.init_browser()

        page = await self.browser.new_page()
        url = f"{self.base_url}/wd/{job_id}"

        try:
            self.logger.debug(f"상세 페이지 조회: {url}")
            await page.goto(url, wait_until='networkidle')
            await asyncio.sleep(1)

            detail = {
                'job_id': job_id,
                'url': url,
                'source_site': self.site_name
            }

            # 제목
            title_elem = await page.query_selector('h1.wds-58fmok, h1[class*="JobHeader"]')
            if title_elem:
                detail['title'] = clean_text(await title_elem.inner_text())

            # 회사 정보 (헤더에서)
            company_link = await page.query_selector('[class*="JobHeader__Tools__Company__Link"]')
            if company_link:
                detail['company_name'] = clean_text(await company_link.inner_text())
                # data 속성에서 추가 정보 추출
                company_id = await company_link.get_attribute('data-company-id')
                if company_id:
                    detail['company_id_external'] = company_id

            # 위치 및 경력 정보 (헤더의 span들)
            info_spans = await page.query_selector_all('[class*="JobHeader__Tools__Company__Info"]')
            if len(info_spans) >= 1:
                detail['location'] = clean_text(await info_spans[0].inner_text())
            if len(info_spans) >= 2:
                detail['experience_level'] = clean_text(await info_spans[1].inner_text())

            # 보상금 정보
            reward_elem = await page.query_selector('[class*="JobHighlight"] .wds-455m6j')
            if reward_elem:
                detail['reward_info'] = clean_text(await reward_elem.inner_text())

            # 포지션 상세 설명 전체
            desc_wrapper = await page.query_selector('[class*="JobDescription_JobDescription__paragraph__wrapper"]')
            if desc_wrapper:
                detail['description'] = clean_text(await desc_wrapper.inner_text())

            # 주요업무, 자격요건, 우대사항 개별 추출
            paragraphs = await page.query_selector_all('[class*="JobDescription_JobDescription__paragraph__"]')
            for para in paragraphs:
                header = await para.query_selector('h3')
                content = await para.query_selector('span[class*="wds-h4ga6o"]')

                if header and content:
                    header_text = clean_text(await header.inner_text())
                    content_text = clean_text(await content.inner_text())

                    if '주요업무' in header_text:
                        detail['main_tasks'] = content_text
                    elif '자격요건' in header_text:
                        detail['requirements'] = content_text
                    elif '우대' in header_text:
                        detail['preferred'] = content_text

            # 회사 태그들 (복지, 규모 등)
            tags = []
            tag_buttons = await page.query_selector_all('[class*="CompanyTags_CompanyTagItem"] button')
            for btn in tag_buttons:
                tag_name = await btn.get_attribute('data-tag-name')
                if tag_name:
                    tags.append(tag_name)
            detail['company_tags'] = tags

            # 마감일
            deadline_elem = await page.query_selector('[class*="JobDueTime"] span[class*="wds-"]')
            if deadline_elem:
                detail['deadline'] = clean_text(await deadline_elem.inner_text())

            # 근무지역 상세 주소
            address_elem = await page.query_selector('[class*="JobWorkPlace"] span[class*="wds-"]')
            if address_elem:
                detail['work_address'] = clean_text(await address_elem.inner_text())

            # 회사 정보 (하단)
            company_info = await page.query_selector('[class*="CompanyInfo_CompanyInfo"]')
            if company_info:
                industry_elem = await company_info.query_selector('[class*="CompanyInfo__industy"]')
                if industry_elem:
                    detail['company_industry'] = clean_text(await industry_elem.inner_text())

            # data 속성에서 상세 정보 추출 (북마크 버튼에서)
            bookmark_btn = await page.query_selector('[class*="BookmarkBtn"] button, button[data-attribute-id="position__bookmark__click"]')
            if bookmark_btn:
                # 회사 정보
                company_id = await bookmark_btn.get_attribute('data-company-id')
                if company_id:
                    detail['wanted_company_id'] = company_id

                company_name = await bookmark_btn.get_attribute('data-company-name')
                if company_name and not detail.get('company_name'):
                    detail['company_name'] = company_name

                # 포지션 정보
                position_id = await bookmark_btn.get_attribute('data-position-id')
                if position_id:
                    detail['wanted_position_id'] = position_id

                position_name = await bookmark_btn.get_attribute('data-position-name')
                if position_name and not detail.get('title'):
                    detail['title'] = position_name

                # 고용 형태 (regular, contract 등)
                employment_type = await bookmark_btn.get_attribute('data-position-employment-type')
                if employment_type:
                    # 영문을 한글로 변환
                    employment_map = {
                        'regular': '정규직',
                        'contract': '계약직',
                        'intern': '인턴',
                        'freelance': '프리랜서',
                        'part-time': '파트타임'
                    }
                    detail['employment_type'] = employment_map.get(employment_type, employment_type)

                # 직무 카테고리
                job_category = await bookmark_btn.get_attribute('data-job-category')
                if job_category:
                    detail['job_category'] = job_category

                job_category_id = await bookmark_btn.get_attribute('data-job-category-id')
                if job_category_id:
                    detail['wanted_job_category_id'] = job_category_id

            # 스킬 추출 (설명에서)
            if detail.get('requirements') or detail.get('description'):
                full_text = f"{detail.get('description', '')} {detail.get('requirements', '')} {detail.get('preferred', '')}"
                skills = extract_skills_from_text(full_text)
                detail['required_skills'] = skills.get('hard_skills', [])
                detail['preferred_skills'] = skills.get('soft_skills', [])

            return detail

        except Exception as e:
            self.logger.error(f"상세 조회 실패 ({job_id}): {e}")
            return None

        finally:
            await page.close()

    async def crawl_keyword(self, keyword: str, max_pages: int = None) -> List[Dict]:
        """
        키워드로 전체 크롤링 실행

        Args:
            keyword: 검색 키워드
            max_pages: 최대 스크롤 횟수

        Returns:
            상세 정보가 포함된 채용공고 목록
        """
        if max_pages is None:
            max_pages = settings.crawler.max_pages_per_keyword

        self.logger.info(f"Wanted 크롤링 시작: {keyword}")

        try:
            await self.init_browser()

            # 1. 검색 결과 수집
            jobs = await self.search_jobs(keyword, max_pages)

            # 2. 각 채용공고의 상세 정보 수집
            detailed_jobs = []
            for i, job in enumerate(jobs):
                if not job.get('job_id'):
                    continue

                self.logger.info(f"상세 조회 중: {i + 1}/{len(jobs)} - {job.get('title', '')[:30]}...")

                detail = await self.get_job_detail(job['job_id'])
                if detail:
                    # 기본 정보와 상세 정보 병합
                    merged = {**job, **detail}
                    detailed_jobs.append(merged)
                else:
                    detailed_jobs.append(job)

                # 요청 간 딜레이
                await asyncio.sleep(self.request_delay)

            self.logger.info(f"Wanted 크롤링 완료: {len(detailed_jobs)}개 수집")
            return detailed_jobs

        finally:
            await self.close_browser()

    def crawl_keyword_sync(self, keyword: str, max_pages: int = None) -> List[Dict]:
        """동기 방식 크롤링 (기존 인터페이스 호환)"""
        return asyncio.get_event_loop().run_until_complete(
            self.crawl_keyword(keyword, max_pages)
        )


# 기존 크롤러 인터페이스와 호환되는 래퍼 클래스
class WantedCrawler:
    """기존 인터페이스와 호환되는 Wanted 크롤러"""

    def __init__(self):
        self.playwright_crawler = WantedPlaywrightCrawler()
        self.site_name = 'wanted'
        self.logger = setup_logger(f"crawler.{self.site_name}")

    def crawl_keyword(self, keyword: str, max_pages: int = None) -> List[Dict]:
        """키워드로 크롤링 실행"""
        try:
            # 새 이벤트 루프 생성 (이미 실행 중인 루프가 없는 경우)
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 이미 실행 중인 루프가 있으면 새 루프 생성
                    import nest_asyncio
                    nest_asyncio.apply()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            return loop.run_until_complete(
                self.playwright_crawler.crawl_keyword(keyword, max_pages)
            )
        except Exception as e:
            self.logger.error(f"크롤링 실패: {e}")
            return []

    def search_jobs(self, keyword: str, max_pages: int = 5) -> List[Dict]:
        """검색만 실행 (상세 조회 없음)"""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        async def _search():
            try:
                await self.playwright_crawler.init_browser()
                return await self.playwright_crawler.search_jobs(keyword, max_pages)
            finally:
                await self.playwright_crawler.close_browser()

        return loop.run_until_complete(_search())

    def get_job_detail(self, job_id: str) -> Optional[Dict]:
        """상세 정보 조회"""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        async def _get_detail():
            try:
                await self.playwright_crawler.init_browser()
                return await self.playwright_crawler.get_job_detail(job_id)
            finally:
                await self.playwright_crawler.close_browser()

        return loop.run_until_complete(_get_detail())


# 테스트 코드
if __name__ == '__main__':
    async def test():
        crawler = WantedPlaywrightCrawler()
        try:
            await crawler.init_browser(headless=False)  # 디버깅용 헤드리스 비활성화

            # 검색 테스트
            print("=== 검색 테스트 ===")
            jobs = await crawler.search_jobs("백엔드", max_pages=2)
            print(f"검색 결과: {len(jobs)}개")

            if jobs:
                print(f"\n첫 번째 결과: {jobs[0]}")

                # 상세 조회 테스트
                print("\n=== 상세 조회 테스트 ===")
                detail = await crawler.get_job_detail(jobs[0]['job_id'])
                print(f"상세 정보: {json.dumps(detail, ensure_ascii=False, indent=2)}")

        finally:
            await crawler.close_browser()

    asyncio.run(test())
