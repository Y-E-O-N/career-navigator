#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Wanted 채용공고 크롤러 (Playwright 버전)

Playwright를 사용하여 동적 페이지를 크롤링합니다.
검색 결과 목록과 상세 페이지 모두 수집합니다.

HTML 구조 (2024년 기준):
- 검색 결과: a[data-position-id] 태그에 모든 정보 포함
- 상세 페이지: section.JobContent_JobContent 내부
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
from utils.database import db, JobPosting


class WantedPlaywrightCrawler:
    """Playwright 기반 Wanted 크롤러"""

    # 실제 브라우저처럼 보이는 User-Agent
    USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

    def __init__(self):
        self.site_name = 'wanted'
        self.base_url = 'https://www.wanted.co.kr'
        self.search_url = 'https://www.wanted.co.kr/search'
        self.logger = setup_logger(f"crawler.{self.site_name}")
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context = None
        self.request_delay = settings.crawler.request_delay

    async def init_browser(self, headless: bool = True):
        """브라우저 초기화"""
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError("playwright가 설치되어 있지 않습니다. 'pip install playwright && playwright install chromium' 실행하세요.")

        if self.browser:
            return

        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=headless)

        # 브라우저 컨텍스트 생성
        self.context = await self.browser.new_context(
            user_agent=self.USER_AGENT,
            viewport={'width': 1920, 'height': 1080},
            locale='ko-KR',
        )

        self.logger.info("브라우저 초기화 완료")

    async def close_browser(self):
        """브라우저 종료"""
        if self.context:
            await self.context.close()
            self.context = None
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
            self.logger.info("브라우저 종료")

    async def search_jobs(self, keyword: str, max_pages: int = 5) -> List[Dict]:
        """
        Wanted 채용공고 검색

        검색 결과의 a[data-position-id] 태그에서 모든 정보를 추출합니다.
        """
        if not self.browser:
            await self.init_browser()

        page = await self.context.new_page()
        jobs = []

        try:
            search_url = f"{self.search_url}?query={quote(keyword)}&tab=position"
            self.logger.info(f"검색 URL: {search_url}")

            # 페이지 로드
            await page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(5)  # React 렌더링 대기

            # 핵심 셀렉터: data-position-id 속성이 있는 a 태그
            job_card_selector = 'a[data-position-id]'

            # 채용공고 카드 대기 (state='attached'로 DOM 존재만 확인)
            try:
                await page.wait_for_selector(job_card_selector, state='attached', timeout=15000)
                self.logger.info("채용공고 카드 발견")
            except Exception as e:
                self.logger.warning(f"채용공고 카드 대기 타임아웃: {e}")
                # 그래도 요소가 있는지 직접 확인
                cards = await page.query_selector_all(job_card_selector)
                if cards:
                    self.logger.info(f"타임아웃됐지만 {len(cards)}개 카드 발견, 계속 진행")
                else:
                    await self._save_debug_files(page, 'search')
                    return []

            # 스크롤하며 더 많은 결과 로드
            prev_count = 0
            no_change_count = 0

            for scroll_count in range(max_pages):
                job_cards = await page.query_selector_all(job_card_selector)
                current_count = len(job_cards)
                self.logger.info(f"스크롤 {scroll_count + 1}: {current_count}개 카드 발견")

                # 스크롤 다운
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await asyncio.sleep(self.request_delay + 1)

                # 새 카드 확인
                new_cards = await page.query_selector_all(job_card_selector)
                new_count = len(new_cards)

                if new_count == current_count:
                    no_change_count += 1
                    if no_change_count >= 2:
                        self.logger.info("더 이상 새로운 결과 없음")
                        break
                else:
                    no_change_count = 0

                prev_count = new_count

            # 최종 카드 수집
            job_cards = await page.query_selector_all(job_card_selector)
            self.logger.info(f"총 {len(job_cards)}개 카드 수집됨")

            # 각 카드에서 정보 추출 (data 속성 활용)
            seen_ids = set()
            for card in job_cards:
                try:
                    job = await self._parse_job_card(card)
                    if job and job.get('job_id'):
                        if job['job_id'] not in seen_ids:
                            seen_ids.add(job['job_id'])
                            jobs.append(job)
                except Exception as e:
                    self.logger.debug(f"카드 파싱 실패: {e}")

            self.logger.info(f"검색 완료: {len(jobs)}개 채용공고 수집")

        except Exception as e:
            self.logger.error(f"검색 실패: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            await self._save_debug_files(page, 'search_error')

        finally:
            await page.close()

        return jobs

    async def _parse_job_card(self, card) -> Optional[Dict]:
        """
        검색 결과 카드에서 정보 추출

        a 태그의 data 속성에서 대부분의 정보를 추출합니다:
        - data-position-id: 채용공고 ID
        - data-position-name: 포지션명
        - data-company-id: 회사 ID
        - data-company-name: 회사명
        - data-job-category: 직무 카테고리
        - data-job-category-id: 직무 카테고리 ID
        """
        try:
            # data 속성에서 정보 추출
            position_id = await card.get_attribute('data-position-id')
            if not position_id:
                return None

            job = {
                'source_site': self.site_name,
                'job_id': position_id,
                'wanted_position_id': position_id,
                'url': f"{self.base_url}/wd/{position_id}",
            }

            # data 속성들
            attrs = {
                'data-position-name': 'title',
                'data-company-id': 'wanted_company_id',
                'data-company-name': 'company_name',
                'data-job-category': 'job_category',
                'data-job-category-id': 'wanted_job_category_id',
            }

            for data_attr, field in attrs.items():
                value = await card.get_attribute(data_attr)
                if value:
                    job[field] = value

            # 카드 내부에서 추가 정보 추출
            # 제목 (data 속성에 없는 경우)
            if not job.get('title'):
                title_elem = await card.query_selector('strong[class*="JobCard_title"]')
                if title_elem:
                    job['title'] = clean_text(await title_elem.inner_text())

            # 회사명 (data 속성에 없는 경우)
            if not job.get('company_name'):
                company_elem = await card.query_selector('span[class*="CompanyNameWithLocationPeriod"][class*="company"]')
                if company_elem:
                    job['company_name'] = clean_text(await company_elem.inner_text())

            # 경력/위치 정보
            location_elem = await card.query_selector('span[class*="CompanyNameWithLocationPeriod"][class*="location"]')
            if location_elem:
                job['experience_level'] = clean_text(await location_elem.inner_text())

            # 보상금 정보
            reward_elem = await card.query_selector('span[class*="JobCard_reward"]')
            if reward_elem:
                job['reward_info'] = clean_text(await reward_elem.inner_text())

            return job

        except Exception as e:
            self.logger.debug(f"카드 파싱 오류: {e}")
            return None

    async def get_job_detail(self, job_id: str) -> Optional[Dict]:
        """
        채용공고 상세 정보 조회

        상세 페이지의 HTML 구조:
        - 제목: h1.wds-58fmok
        - 회사 링크: a[class*="JobHeader__Tools__Company__Link"]
        - 위치/경력: span[class*="JobHeader__Tools__Company__Info"]
        - 북마크 버튼: button[data-attribute-id="position__bookmark__click"]
        - 설명: div[class*="JobDescription__paragraph"]
        - 태그: button[data-tag-name]
        - 마감일: article[class*="JobDueTime"]
        - 근무지역: article[class*="JobWorkPlace"]
        - 산업분야: span[class*="CompanyInfo__industy"]
        """
        if not self.browser:
            await self.init_browser()

        page = await self.context.new_page()
        url = f"{self.base_url}/wd/{job_id}"

        try:
            self.logger.debug(f"상세 페이지 조회: {url}")
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(3)

            detail = {
                'job_id': job_id,
                'url': url,
                'source_site': self.site_name,
                'wanted_position_id': job_id,
            }

            # 1. 제목 추출
            title_elem = await page.query_selector('h1.wds-58fmok, h1[class*="wds-"]')
            if title_elem:
                detail['title'] = clean_text(await title_elem.inner_text())

            # 2. 회사 정보 (헤더의 회사 링크에서)
            company_link = await page.query_selector('a[class*="JobHeader"][class*="Company__Link"]')
            if company_link:
                detail['company_name'] = clean_text(await company_link.inner_text())
                company_id = await company_link.get_attribute('data-company-id')
                if company_id:
                    detail['wanted_company_id'] = company_id

            # 3. 위치 및 경력 정보 (헤더의 span들)
            info_spans = await page.query_selector_all('span[class*="JobHeader"][class*="Company__Info"]')
            for i, span in enumerate(info_spans):
                text = clean_text(await span.inner_text())
                if i == 0:
                    detail['location'] = text
                elif i == 1:
                    detail['experience_level'] = text

            # 4. 북마크 버튼에서 모든 data 속성 추출 (가장 풍부한 정보)
            bookmark_btn = await page.query_selector('button[data-attribute-id="position__bookmark__click"]')
            if bookmark_btn:
                data_attrs = {
                    'data-company-id': 'wanted_company_id',
                    'data-company-name': 'company_name',
                    'data-position-id': 'wanted_position_id',
                    'data-position-name': 'title',
                    'data-position-employment-type': 'employment_type_raw',
                    'data-job-category': 'job_category',
                    'data-job-category-id': 'wanted_job_category_id',
                }

                for data_attr, field in data_attrs.items():
                    value = await bookmark_btn.get_attribute(data_attr)
                    if value and not detail.get(field):
                        detail[field] = value

                # 고용 형태 변환
                if detail.get('employment_type_raw'):
                    employment_map = {
                        'regular': '정규직',
                        'contract': '계약직',
                        'intern': '인턴',
                        'freelance': '프리랜서',
                        'part-time': '파트타임'
                    }
                    raw = detail.pop('employment_type_raw')
                    detail['employment_type'] = employment_map.get(raw, raw)

            # 5. 보상금 정보
            reward_elem = await page.query_selector('span.wds-455m6j')
            if reward_elem:
                detail['reward_info'] = clean_text(await reward_elem.inner_text())

            # 6. 포지션 상세 설명 (전체)
            desc_wrapper = await page.query_selector('div[class*="JobDescription__paragraph__wrapper"]')
            if desc_wrapper:
                # 첫 번째 span이 회사/포지션 소개
                intro_span = await desc_wrapper.query_selector('span.wds-h4ga6o')
                if intro_span:
                    detail['description'] = clean_text(await intro_span.inner_text())

            # 7. 주요업무, 자격요건, 우대사항 (개별 섹션)
            paragraphs = await page.query_selector_all('div[class*="JobDescription__paragraph__"]')
            for para in paragraphs:
                header = await para.query_selector('h3')
                content = await para.query_selector('span.wds-h4ga6o')

                if header and content:
                    header_text = clean_text(await header.inner_text())
                    content_text = clean_text(await content.inner_text())

                    if '주요업무' in header_text or '담당업무' in header_text:
                        detail['main_tasks'] = content_text
                    elif '자격요건' in header_text or '자격' in header_text:
                        detail['requirements'] = content_text
                    elif '우대' in header_text:
                        detail['preferred'] = content_text

            # 8. 회사 태그들
            tags = []
            tag_buttons = await page.query_selector_all('button[data-tag-name]')
            for btn in tag_buttons:
                tag_name = await btn.get_attribute('data-tag-name')
                if tag_name:
                    tags.append(tag_name)
            if tags:
                detail['company_tags'] = tags

            # 9. 마감일
            deadline_article = await page.query_selector('article[class*="JobDueTime"]')
            if deadline_article:
                deadline_span = await deadline_article.query_selector('span[class*="wds-"]')
                if deadline_span:
                    detail['deadline'] = clean_text(await deadline_span.inner_text())

            # 10. 근무지역 상세 주소
            workplace_article = await page.query_selector('article[class*="JobWorkPlace"]')
            if workplace_article:
                address_span = await workplace_article.query_selector('span[class*="wds-"]')
                if address_span:
                    detail['work_address'] = clean_text(await address_span.inner_text())

            # 11. 회사 산업 분야
            industry_span = await page.query_selector('span[class*="CompanyInfo__industy"]')
            if industry_span:
                detail['company_industry'] = clean_text(await industry_span.inner_text())

            # 12. 스킬 추출 (설명에서)
            full_text = ' '.join([
                detail.get('description', ''),
                detail.get('main_tasks', ''),
                detail.get('requirements', ''),
                detail.get('preferred', '')
            ])
            if full_text.strip():
                skills = extract_skills_from_text(full_text)
                if skills.get('hard_skills'):
                    detail['required_skills'] = skills['hard_skills']
                if skills.get('soft_skills'):
                    detail['preferred_skills'] = skills['soft_skills']

            # 최소 정보 확인
            if not detail.get('title') and not detail.get('company_name'):
                self.logger.warning(f"상세 정보 부족: job_id={job_id}")
                await self._save_debug_files(page, f'detail_{job_id}')

            return detail

        except Exception as e:
            self.logger.error(f"상세 조회 실패 ({job_id}): {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None

        finally:
            await page.close()

    async def _save_debug_files(self, page, prefix: str):
        """디버그용 스크린샷 및 HTML 저장"""
        try:
            import os
            os.makedirs('logs', exist_ok=True)

            await page.screenshot(path=f'logs/wanted_{prefix}_debug.png', full_page=True)
            self.logger.info(f"디버그 스크린샷: logs/wanted_{prefix}_debug.png")

            html_content = await page.content()
            with open(f'logs/wanted_{prefix}_debug.html', 'w', encoding='utf-8') as f:
                f.write(html_content)
            self.logger.info(f"디버그 HTML: logs/wanted_{prefix}_debug.html")
        except Exception as e:
            self.logger.warning(f"디버그 파일 저장 실패: {e}")

    def _get_existing_job_ids(self) -> set:
        """DB에서 기존 job_id 목록 조회"""
        try:
            self.logger.info("DB에서 기존 job_id 조회 시작...")
            session = db.get_session()
            existing_ids = session.query(JobPosting.job_id).filter(
                JobPosting.source_site == self.site_name
            ).all()
            session.close()
            # job_id를 문자열로 변환하여 set 생성
            result = {str(row[0]) for row in existing_ids if row[0]}
            self.logger.info(f"DB 조회 완료: {len(result)}개 기존 job_id 발견")
            return result
        except Exception as e:
            self.logger.error(f"기존 job_id 조회 실패: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return set()

    async def crawl_keyword(self, keyword: str, max_pages: int = None) -> List[Dict]:
        """키워드로 전체 크롤링 실행"""
        if max_pages is None:
            max_pages = settings.crawler.max_pages_per_keyword

        self.logger.info(f"Wanted 크롤링 시작: {keyword}")

        try:
            await self.init_browser()

            # 기존 DB에 있는 job_id 조회
            existing_job_ids = self._get_existing_job_ids()
            self.logger.info(f"DB에 기존 채용공고 {len(existing_job_ids)}개 존재")

            # 1. 검색 결과 수집
            jobs = await self.search_jobs(keyword, max_pages)

            # 2. 기존 DB에 없는 채용공고만 필터링 (job_id를 문자열로 비교)
            new_jobs = [job for job in jobs if str(job.get('job_id', '')) not in existing_job_ids]
            skipped_count = len(jobs) - len(new_jobs)
            self.logger.info(f"필터링 결과: 전체 {len(jobs)}개 중 신규 {len(new_jobs)}개")

            if skipped_count > 0:
                self.logger.info(f"DB에 이미 존재하는 {skipped_count}개 채용공고 스킵")

            if not new_jobs:
                self.logger.info("새로운 채용공고 없음, 크롤링 종료")
                return []

            self.logger.info(f"새로운 채용공고 {len(new_jobs)}개 상세 조회 시작")

            # 3. 각 채용공고의 상세 정보 수집
            detailed_jobs = []
            for i, job in enumerate(new_jobs):
                if not job.get('job_id'):
                    continue

                self.logger.info(f"상세 조회 중: {i + 1}/{len(new_jobs)} - {job.get('title', '')[:30]}...")

                detail = await self.get_job_detail(job['job_id'])
                if detail:
                    # 기본 정보와 상세 정보 병합 (상세 정보 우선)
                    merged = {**job, **detail}
                    detailed_jobs.append(merged)
                else:
                    detailed_jobs.append(job)

                await asyncio.sleep(self.request_delay)

            self.logger.info(f"Wanted 크롤링 완료: {len(detailed_jobs)}개 신규 수집 (기존 {skipped_count}개 스킵)")
            return detailed_jobs

        finally:
            await self.close_browser()


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
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
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
            await crawler.init_browser(headless=False)

            print("=== 검색 테스트 ===")
            jobs = await crawler.search_jobs("데이터 분석가", max_pages=2)
            print(f"검색 결과: {len(jobs)}개")

            if jobs:
                print(f"\n첫 번째 결과:")
                for k, v in jobs[0].items():
                    print(f"  {k}: {v}")

                print("\n=== 상세 조회 테스트 ===")
                detail = await crawler.get_job_detail(jobs[0]['job_id'])
                if detail:
                    print(f"상세 정보:")
                    for k, v in detail.items():
                        if isinstance(v, str) and len(v) > 100:
                            print(f"  {k}: {v[:100]}...")
                        else:
                            print(f"  {k}: {v}")

        finally:
            await crawler.close_browser()

    asyncio.run(test())
