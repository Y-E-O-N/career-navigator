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

    # 실제 브라우저처럼 보이는 User-Agent
    USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

    def __init__(self):
        self.site_name = 'wanted'
        self.base_url = 'https://www.wanted.co.kr'
        self.search_url = 'https://www.wanted.co.kr/search'
        self.logger = setup_logger(f"crawler.{self.site_name}")
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context = None  # 브라우저 컨텍스트 추가
        self.request_delay = settings.crawler.request_delay

    async def init_browser(self, headless: bool = True):
        """브라우저 초기화"""
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError("playwright가 설치되어 있지 않습니다. 'pip install playwright && playwright install chromium' 실행하세요.")

        if self.browser:
            return  # 이미 초기화됨

        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=headless)

        # 브라우저 컨텍스트 생성 (User-Agent, viewport 설정)
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

        Args:
            keyword: 검색 키워드
            max_pages: 최대 스크롤 횟수

        Returns:
            채용공고 목록 (기본 정보만)
        """
        if not self.browser:
            await self.init_browser()

        # 컨텍스트에서 새 페이지 생성
        page = await self.context.new_page()
        jobs = []

        try:
            # 검색 페이지로 이동
            search_url = f"{self.search_url}?query={quote(keyword)}&tab=position"
            self.logger.info(f"검색 URL: {search_url}")

            # networkidle 사용 - React 앱이 API 호출 완료할 때까지 대기
            await page.goto(search_url, wait_until='networkidle', timeout=30000)

            # React 렌더링 완료 대기 (추가 시간)
            await asyncio.sleep(5)

            # 여러 셀렉터로 채용공고 카드 존재 확인
            card_selectors = [
                'a[href*="/wd/"]',
                '[class*="JobCard"]',
                '[class*="job-card"]',
                '[data-cy="job-card"]',
                'div[class*="position"]',
            ]

            found_selector = None
            for selector in card_selectors:
                try:
                    await page.wait_for_selector(selector, timeout=5000)
                    count = len(await page.query_selector_all(selector))
                    if count > 0:
                        found_selector = selector
                        self.logger.info(f"셀렉터 '{selector}'로 {count}개 요소 발견")
                        break
                except:
                    continue

            if not found_selector:
                # 디버깅: 페이지 상태 저장
                page_title = await page.title()
                page_url = page.url
                self.logger.warning(f"채용공고를 찾을 수 없음. 페이지: {page_title} ({page_url})")

                # 스크린샷 저장 (GitHub Actions 아티팩트로 확인 가능)
                try:
                    import os
                    os.makedirs('logs', exist_ok=True)
                    await page.screenshot(path='logs/wanted_search_debug.png', full_page=True)
                    self.logger.info("디버그 스크린샷 저장: logs/wanted_search_debug.png")

                    # HTML 저장
                    html_content = await page.content()
                    with open('logs/wanted_search_debug.html', 'w', encoding='utf-8') as f:
                        f.write(html_content)
                    self.logger.info("디버그 HTML 저장: logs/wanted_search_debug.html")
                except Exception as debug_err:
                    self.logger.warning(f"디버그 파일 저장 실패: {debug_err}")

                return []

            # 스크롤하며 더 많은 결과 로드
            prev_count = 0
            no_change_count = 0

            for scroll_count in range(max_pages):
                # 현재 채용공고 링크 수집
                job_links = await page.query_selector_all('a[href*="/wd/"]')
                current_count = len(job_links)

                self.logger.info(f"스크롤 {scroll_count + 1}: {current_count}개 링크 발견")

                # 스크롤 다운
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')

                # 새 컨텐츠 로드 대기
                await asyncio.sleep(self.request_delay + 1)

                # 새로운 링크 확인
                new_links = await page.query_selector_all('a[href*="/wd/"]')
                new_count = len(new_links)

                if new_count == current_count:
                    no_change_count += 1
                    if no_change_count >= 2:  # 2회 연속 변화 없으면 종료
                        self.logger.info("더 이상 새로운 결과 없음")
                        break
                else:
                    no_change_count = 0

                prev_count = new_count

            # 최종 채용공고 링크 수집
            job_links = await page.query_selector_all('a[href*="/wd/"]')
            self.logger.info(f"총 {len(job_links)}개 링크 수집됨")

            # 링크 파싱
            parse_success = 0
            parse_fail = 0
            seen_ids = set()

            for link in job_links:
                try:
                    job = await self._parse_job_link(link)
                    if job and job.get('job_id'):
                        job_id = job['job_id']
                        # 중복 제거
                        if job_id not in seen_ids:
                            seen_ids.add(job_id)
                            jobs.append(job)
                            parse_success += 1
                    else:
                        parse_fail += 1
                except Exception as e:
                    parse_fail += 1
                    self.logger.debug(f"링크 파싱 실패: {e}")

            self.logger.info(f"검색 완료: {len(jobs)}개 채용공고 (파싱 성공: {parse_success}, 실패: {parse_fail})")

        except Exception as e:
            self.logger.error(f"검색 실패: {e}")
            import traceback
            self.logger.error(traceback.format_exc())

            # 오류 시 스크린샷 저장
            try:
                import os
                os.makedirs('logs', exist_ok=True)
                await page.screenshot(path='logs/wanted_search_error.png')
                self.logger.info("에러 스크린샷 저장됨")
            except:
                pass

        finally:
            await page.close()

        return jobs

    async def _parse_job_link(self, link) -> Optional[Dict]:
        """채용공고 링크에서 정보 추출"""
        try:
            # href에서 job_id 추출
            href = await link.get_attribute('href')
            if not href:
                self.logger.debug("링크에 href 없음")
                return None

            match = re.search(r'/wd/(\d+)', href)
            if not match:
                self.logger.debug(f"job_id 추출 실패: {href}")
                return None

            job_id = match.group(1)
            url = f"{self.base_url}/wd/{job_id}"

            # 링크 전체 텍스트에서 정보 추출 시도
            full_text = await link.inner_text()
            text_lines = [line.strip() for line in full_text.split('\n') if line.strip()]

            # 제목 추출 시도 (여러 방법)
            title = ''
            title_elem = await link.query_selector('[class*="JobCard_title"], [class*="title"], strong, h2, h3')
            if title_elem:
                title = await title_elem.inner_text()
            elif text_lines:
                # 첫 번째 줄이 보통 제목
                title = text_lines[0]

            if not title:
                # 제목이 없어도 job_id가 있으면 일단 수집 (상세 페이지에서 가져올 수 있음)
                self.logger.debug(f"제목 없이 수집: job_id={job_id}")
                return {
                    'source_site': self.site_name,
                    'job_id': job_id,
                    'title': '',  # 상세 페이지에서 채워짐
                    'company_name': '',
                    'url': url
                }

            # 회사명 추출
            company_name = ''
            company_elem = await link.query_selector('[class*="company"], [class*="Company"]')
            if company_elem:
                company_name = await company_elem.inner_text()
            elif len(text_lines) > 1:
                # 두 번째 줄이 보통 회사명
                company_name = text_lines[1]

            # 경력/위치 정보
            experience_level = ''
            location_elem = await link.query_selector('[class*="location"], [class*="Location"], [class*="period"]')
            if location_elem:
                experience_level = await location_elem.inner_text()
            elif len(text_lines) > 2:
                experience_level = text_lines[2]

            # 보상금
            reward_info = ''
            reward_elem = await link.query_selector('[class*="reward"], [class*="Reward"]')
            if reward_elem:
                reward_info = await reward_elem.inner_text()

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
            import traceback
            self.logger.debug(traceback.format_exc())
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

        page = await self.context.new_page()
        url = f"{self.base_url}/wd/{job_id}"

        try:
            self.logger.debug(f"상세 페이지 조회: {url}")
            await page.goto(url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(2)  # React 렌더링 대기

            detail = {
                'job_id': job_id,
                'url': url,
                'source_site': self.site_name
            }

            # 제목 (여러 셀렉터 시도)
            title_selectors = [
                'h1',
                '[class*="JobHeader"] h1',
                'h1[class*="wds-"]',
                '[data-cy="job-title"]',
            ]
            for selector in title_selectors:
                title_elem = await page.query_selector(selector)
                if title_elem:
                    title_text = clean_text(await title_elem.inner_text())
                    if title_text:
                        detail['title'] = title_text
                        break

            # 회사 정보 (여러 셀렉터 시도)
            company_selectors = [
                '[class*="JobHeader"] a[href*="/company/"]',
                'a[href*="/company/"]',
                '[class*="company-name"]',
                '[data-cy="company-name"]',
            ]
            for selector in company_selectors:
                company_elem = await page.query_selector(selector)
                if company_elem:
                    company_text = clean_text(await company_elem.inner_text())
                    if company_text:
                        detail['company_name'] = company_text
                        # data 속성에서 추가 정보 추출
                        company_id = await company_elem.get_attribute('data-company-id')
                        if company_id:
                            detail['wanted_company_id'] = company_id
                        break

            # 위치 및 경력 정보
            # 헤더 영역에서 위치/경력 정보 추출
            header_info = await page.query_selector_all('[class*="JobHeader"] span')
            location_keywords = ['서울', '경기', '인천', '부산', '대구', '대전', '광주', '울산', '세종', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주', '한국', 'Korea']
            experience_keywords = ['신입', '경력', '년', '연차']

            for span in header_info:
                text = clean_text(await span.inner_text())
                if any(kw in text for kw in location_keywords):
                    if not detail.get('location'):
                        detail['location'] = text
                if any(kw in text for kw in experience_keywords):
                    if not detail.get('experience_level'):
                        detail['experience_level'] = text

            # 보상금 정보
            reward_selectors = [
                '[class*="reward"]',
                '[class*="Reward"]',
            ]
            for selector in reward_selectors:
                try:
                    reward_elem = await page.query_selector(selector)
                    if reward_elem:
                        detail['reward_info'] = clean_text(await reward_elem.inner_text())
                        break
                except:
                    continue

            # 보상금을 텍스트에서 찾기
            if not detail.get('reward_info'):
                page_text = await page.inner_text('body')
                reward_match = re.search(r'(합격\s*보상금[^\n]*)', page_text)
                if reward_match:
                    detail['reward_info'] = clean_text(reward_match.group(1))

            # 포지션 상세 설명 추출
            # 전체 설명 영역 먼저 찾기
            desc_selectors = [
                '[class*="JobDescription"]',
                '[class*="job-description"]',
                '[class*="job-content"]',
                'article',
                'main section',
            ]

            full_description = ''
            for selector in desc_selectors:
                desc_elem = await page.query_selector(selector)
                if desc_elem:
                    full_description = await desc_elem.inner_text()
                    if full_description and len(full_description) > 100:
                        detail['description'] = clean_text(full_description)
                        break

            # 섹션별 파싱 (주요업무, 자격요건, 우대사항)
            if full_description:
                # 정규식으로 섹션 분리
                sections_pattern = [
                    (r'(?:주요\s*업무|담당\s*업무)[:\s]*\n?([\s\S]*?)(?=(?:자격|우대|혜택|복지|기술|스킬|$))', 'main_tasks'),
                    (r'(?:자격\s*요건|필수\s*자격)[:\s]*\n?([\s\S]*?)(?=(?:우대|혜택|복지|기술|스킬|$))', 'requirements'),
                    (r'(?:우대\s*사항|우대\s*조건)[:\s]*\n?([\s\S]*?)(?=(?:혜택|복지|기술|스킬|채용|$))', 'preferred'),
                ]

                for pattern, field in sections_pattern:
                    match = re.search(pattern, full_description, re.IGNORECASE)
                    if match:
                        content = clean_text(match.group(1))
                        if content and len(content) > 10:
                            detail[field] = content

            # 회사 태그들 (복지, 규모 등)
            tags = []
            tag_selectors = [
                '[class*="CompanyTag"] button',
                '[class*="company-tag"]',
                '[data-tag-name]',
            ]
            for selector in tag_selectors:
                tag_elems = await page.query_selector_all(selector)
                for elem in tag_elems:
                    tag_name = await elem.get_attribute('data-tag-name')
                    if tag_name:
                        tags.append(tag_name)
                    else:
                        tag_text = clean_text(await elem.inner_text())
                        if tag_text and len(tag_text) < 50:  # 태그는 보통 짧음
                            tags.append(tag_text)
                if tags:
                    break
            detail['company_tags'] = list(set(tags))  # 중복 제거

            # 마감일
            deadline_selectors = [
                '[class*="deadline"]',
                '[class*="DueTime"]',
                '[class*="due-time"]',
            ]
            for selector in deadline_selectors:
                try:
                    deadline_elem = await page.query_selector(selector)
                    if deadline_elem:
                        detail['deadline'] = clean_text(await deadline_elem.inner_text())
                        break
                except:
                    continue

            # 마감일을 텍스트에서 직접 찾기
            if not detail.get('deadline'):
                page_text = await page.inner_text('body')
                if '상시채용' in page_text or '상시 채용' in page_text:
                    detail['deadline'] = '상시채용'
                else:
                    # 마감일 패턴 찾기
                    deadline_match = re.search(r'마감[:\s]*(\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})', page_text)
                    if deadline_match:
                        detail['deadline'] = deadline_match.group(1)
                    else:
                        # 날짜 형식만 찾기
                        date_match = re.search(r'(\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})\s*마감', page_text)
                        if date_match:
                            detail['deadline'] = date_match.group(1)

            # 근무지역 상세 주소
            address_selectors = [
                '[class*="WorkPlace"]',
                '[class*="workplace"]',
                '[class*="location"]',
                '[class*="address"]',
            ]
            for selector in address_selectors:
                try:
                    address_elem = await page.query_selector(selector)
                    if address_elem:
                        addr_text = clean_text(await address_elem.inner_text())
                        if addr_text and len(addr_text) > 5:
                            detail['work_address'] = addr_text
                            break
                except:
                    continue

            # 주소를 텍스트에서 찾기
            if not detail.get('work_address'):
                page_text = await page.inner_text('body')
                # 한국 주소 패턴
                addr_match = re.search(r'((?:서울|경기|인천|부산|대구|대전|광주|울산|세종|강원|충북|충남|전북|전남|경북|경남|제주)[^\n]{10,50})', page_text)
                if addr_match:
                    detail['work_address'] = clean_text(addr_match.group(1))

            # 회사 산업 분야
            industry_selectors = [
                '[class*="industry"]',
                '[class*="Industry"]',
            ]
            for selector in industry_selectors:
                industry_elem = await page.query_selector(selector)
                if industry_elem:
                    detail['company_industry'] = clean_text(await industry_elem.inner_text())
                    break

            # data 속성에서 상세 정보 추출 (여러 요소에서 시도)
            data_attr_selectors = [
                'button[data-position-id]',
                'button[data-company-id]',
                '[data-attribute-id*="bookmark"]',
                '[class*="Bookmark"] button',
            ]

            for selector in data_attr_selectors:
                btn = await page.query_selector(selector)
                if btn:
                    # 회사 정보
                    company_id = await btn.get_attribute('data-company-id')
                    if company_id and not detail.get('wanted_company_id'):
                        detail['wanted_company_id'] = company_id

                    company_name = await btn.get_attribute('data-company-name')
                    if company_name and not detail.get('company_name'):
                        detail['company_name'] = company_name

                    # 포지션 정보
                    position_id = await btn.get_attribute('data-position-id')
                    if position_id:
                        detail['wanted_position_id'] = position_id

                    position_name = await btn.get_attribute('data-position-name')
                    if position_name and not detail.get('title'):
                        detail['title'] = position_name

                    # 고용 형태 (regular, contract 등)
                    employment_type = await btn.get_attribute('data-position-employment-type')
                    if employment_type:
                        employment_map = {
                            'regular': '정규직',
                            'contract': '계약직',
                            'intern': '인턴',
                            'freelance': '프리랜서',
                            'part-time': '파트타임'
                        }
                        detail['employment_type'] = employment_map.get(employment_type, employment_type)

                    # 직무 카테고리
                    job_category = await btn.get_attribute('data-job-category')
                    if job_category:
                        detail['job_category'] = job_category

                    job_category_id = await btn.get_attribute('data-job-category-id')
                    if job_category_id:
                        detail['wanted_job_category_id'] = job_category_id

                    break  # 하나라도 찾으면 종료

            # 스킬 추출 (설명에서)
            full_text = f"{detail.get('description', '')} {detail.get('main_tasks', '')} {detail.get('requirements', '')} {detail.get('preferred', '')}"
            if full_text.strip():
                skills = extract_skills_from_text(full_text)
                detail['required_skills'] = skills.get('hard_skills', [])
                detail['preferred_skills'] = skills.get('soft_skills', [])

            # 최소한의 정보가 있는지 확인
            if not detail.get('title') and not detail.get('company_name'):
                self.logger.warning(f"상세 정보 추출 실패: job_id={job_id}")
                # 디버깅용 스크린샷
                try:
                    import os
                    os.makedirs('logs', exist_ok=True)
                    await page.screenshot(path=f'logs/wanted_detail_{job_id}_debug.png')
                    self.logger.info(f"디버그 스크린샷: logs/wanted_detail_{job_id}_debug.png")
                except:
                    pass

            return detail

        except Exception as e:
            self.logger.error(f"상세 조회 실패 ({job_id}): {e}")
            import traceback
            self.logger.error(traceback.format_exc())
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
