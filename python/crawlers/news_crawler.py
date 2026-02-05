"""
뉴스 크롤러 - 연합뉴스 기사 수집
3차 크롤링: 기업명 기준 뉴스 기사 검색 및 수집

nodriver를 사용하여 동적 렌더링 페이지 크롤링
"""

import asyncio
import logging
import re
from typing import Dict, List, Any, Optional
from urllib.parse import quote

# nodriver import
try:
    import nodriver
    NODRIVER_AVAILABLE = True
except ImportError:
    NODRIVER_AVAILABLE = False

from config.settings import settings

logger = logging.getLogger('crawler.news')


class NewsCrawler:
    """연합뉴스 크롤러 (nodriver 사용)"""

    def __init__(self, db, since_date: str = None):
        self.db = db
        self.logger = logger
        self._browser = None
        self.since_date = since_date  # YYYY-MM-DD 형식
        # 설정에서 값 로드
        self.max_pages = settings.news.max_pages
        self.page_load_delay = settings.news.page_load_delay
        self.article_delay = settings.news.article_delay
        self.scroll_delay = settings.news.scroll_delay
        self.scroll_distance = settings.news.scroll_distance
        self.scroll_interval = settings.news.scroll_interval
        self.headless = settings.news.headless

    async def _get_browser(self):
        """브라우저 인스턴스 반환 (재사용)"""
        if not self._browser:
            self._browser = await nodriver.start(headless=self.headless)
            self.logger.info(f"  → 새 브라우저 시작 (headless={self.headless})")
        return self._browser

    async def _scroll_to_bottom(self, page, delay: float = None):
        """페이지 하단까지 천천히 스크롤"""
        if delay is None:
            delay = self.scroll_delay
        scroll_js = f'''
            async function scrollToBottom() {{
                const distance = {self.scroll_distance};
                const delay = {self.scroll_interval};
                while (document.documentElement.scrollTop + window.innerHeight < document.documentElement.scrollHeight) {{
                    window.scrollBy(0, distance);
                    await new Promise(r => setTimeout(r, delay));
                }}
            }}
            scrollToBottom();
        '''
        await page.evaluate(scroll_js)
        await asyncio.sleep(delay)

    def _clean_company_name(self, company_name: str) -> str:
        """회사명에서 괄호 제거 및 한국어만 추출

        예: "글루가(ohora/오호라)" -> "글루가"
            "베이글코드(Bagelcode)" -> "베이글코드"
            "ABC컴퍼니" -> "컴퍼니"
            "네이버 NAVER" -> "네이버"
        """
        # 반각 소괄호 ()
        cleaned = re.sub(r'\([^)]*\)', '', company_name)
        # 전각 소괄호 （）
        cleaned = re.sub(r'（[^）]*）', '', cleaned)
        # 반각 대괄호 []
        cleaned = re.sub(r'\[[^\]]*\]', '', cleaned)
        # 전각 대괄호 【】
        cleaned = re.sub(r'【[^】]*】', '', cleaned)
        # 슬래시 이후 제거 (예: "글루가/ohora" -> "글루가")
        if '/' in cleaned:
            cleaned = cleaned.split('/')[0]

        # 한국어(한글), 숫자, 공백만 남기기
        # 한글 범위: 가-힣 (완성형), ㄱ-ㅎ, ㅏ-ㅣ (자모)
        cleaned = re.sub(r'[^가-힣ㄱ-ㅎㅏ-ㅣ0-9\s]', '', cleaned)

        # 연속 공백 제거 및 trim
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        return cleaned

    async def search_news(self, company_name: str, existing_urls: set = None) -> List[Dict[str, Any]]:
        """회사명으로 뉴스 검색 및 URL 목록 수집 (1단계)

        Args:
            company_name: 검색할 회사명
            existing_urls: 이미 DB에 있는 URL 세트 (중복 체크용)

        Returns:
            뉴스 목록 [{news_url, title, published_at}, ...]
        """
        if existing_urls is None:
            existing_urls = set()
        if not NODRIVER_AVAILABLE:
            self.logger.warning("nodriver not available")
            return []

        news_list = []
        total_article_count = 0

        # 회사명에서 괄호 제거 및 한국어만 추출
        search_name = self._clean_company_name(company_name)

        # 한글이 없는 경우 (영문만 있는 회사명 등) 스킵
        if not search_name:
            self.logger.warning(f"    검색 스킵: 한글 회사명 없음 (원본: {company_name})")
            return news_list

        self.logger.info(f"    검색어: {search_name}" + (f" (원본: {company_name})" if search_name != company_name else ""))

        encoded_name = quote(f'"{search_name}"')
        base_url = f'https://www.yna.co.kr/search/index?query={encoded_name}&scope=title&ctype=A'

        try:
            browser = await self._get_browser()

            # ========== 1단계: 첫 페이지 로드 및 총 기사 수 확인 ==========
            self.logger.info(f"    [1단계] 검색 결과 확인 중...")
            page = await browser.get(f'{base_url}&page_no=1')
            await asyncio.sleep(self.page_load_delay)

            # 총 기사 수 확인
            for wait_attempt in range(10):
                count_js = r'''
                    JSON.stringify((() => {
                        const result = {
                            readyState: document.readyState,
                            count: -1,
                            debug: {}
                        };

                        // 방법 1: header.title-con05 내의 txt-type011 em
                        const header = document.querySelector('header.title-con05');
                        if (header) {
                            const countEl = header.querySelector('.txt-type011 em');
                            if (countEl) {
                                result.count = parseInt(countEl.innerText.trim()) || 0;
                                result.debug.method = 'header.title-con05';
                                return result;
                            }
                        }

                        // 방법 2: .txt-type011 em (여러 개일 수 있음)
                        const allCounts = document.querySelectorAll('.txt-type011 em');
                        if (allCounts.length > 0) {
                            result.count = parseInt(allCounts[0].innerText.trim()) || 0;
                            result.debug.method = '.txt-type011 em (first)';
                            result.debug.allCountsLength = allCounts.length;
                            return result;
                        }

                        // 방법 3: "N건" 텍스트 패턴 검색
                        const bodyText = document.body.innerText;
                        const match = bodyText.match(/(\d+)\s*건/);
                        if (match) {
                            result.count = parseInt(match[1]) || 0;
                            result.debug.method = 'text pattern';
                            return result;
                        }

                        // 방법 4: 기사 개수 직접 카운트
                        const articles = document.querySelectorAll('.item-box01');
                        if (articles.length > 0) {
                            result.count = articles.length;
                            result.debug.method = 'direct count';
                            return result;
                        }

                        result.debug.method = 'none found';
                        return result;
                    })())
                '''
                try:
                    result = await page.evaluate(count_js)
                    if isinstance(result, str):
                        import json
                        data = json.loads(result)
                        self.logger.debug(f"    기사 수 확인: {data}")

                        if data.get('readyState') == 'complete':
                            total_article_count = data.get('count', -1)
                            if total_article_count >= 0:
                                self.logger.info(f"    총 기사 수: {total_article_count}건 (방법: {data.get('debug', {}).get('method', '?')})")
                                break
                except Exception as e:
                    self.logger.debug(f"    기사 수 확인 오류: {e}")
                await asyncio.sleep(1)

            # 기사 수를 못 찾았으면 페이지에서 직접 확인
            if total_article_count < 0:
                self.logger.warning(f"    기사 수 확인 실패, 페이지 탐색으로 진행")
                total_article_count = 999  # 최대값으로 설정하고 페이지 탐색

            # 기사가 0건이면 즉시 종료
            if total_article_count == 0:
                self.logger.info(f"    검색 결과 없음, 종료")
                return news_list

            # ========== 2단계: 페이지별 기사 URL 수집 ==========
            self.logger.info(f"    [2단계] 기사 URL 수집 시작")

            for page_num in range(1, self.max_pages + 1):
                # 첫 페이지가 아니면 페이지 이동
                if page_num > 1:
                    self.logger.info(f"    페이지 {page_num}로 이동...")
                    await page.get(f'{base_url}&page_no={page_num}')
                    await asyncio.sleep(self.page_load_delay)

                # 동적 로딩 완료 대기
                await self._wait_for_articles(page)

                # 스크롤
                await self._scroll_to_bottom(page)
                await asyncio.sleep(1)

                # 기사 목록 추출 (검색 결과 + 제목에 키워드 포함 + 날짜 필터)
                since_date_js = f'"{self.since_date}"' if self.since_date else 'null'
                articles_js = f'''
                    JSON.stringify((function() {{
                        const keyword = "{search_name}";
                        const sinceDate = {since_date_js};  // YYYY-MM-DD 또는 null
                        const articles = [];
                        const seenUrls = new Set();

                        // section=search 쿼리가 포함된 링크만 선택 (검색 결과 링크)
                        const links = document.querySelectorAll('a[href*="section=search"]');

                        links.forEach(function(link) {{
                            const href = link.href || '';
                            if (!href.includes('/view/')) return;

                            // 부모 item-box01에서 제목 추출
                            const item = link.closest('.item-box01');
                            if (!item) return;

                            const titleEl = item.querySelector('.title01');
                            if (!titleEl) return;

                            const title = titleEl.innerText.trim();

                            // 제목에 검색 키워드가 포함되어 있는지 확인
                            if (!title.includes(keyword)) return;

                            // 날짜 추출 및 필터링
                            const timeEl = item.querySelector('.txt-time');
                            const publishedAt = timeEl ? timeEl.innerText.trim() : '';

                            // 날짜 필터가 설정되어 있으면 적용
                            if (sinceDate && publishedAt) {{
                                // 날짜 형식: "2023-01-09 10:11" -> "2023-01-09"
                                const articleDate = publishedAt.split(' ')[0];
                                if (articleDate < sinceDate) {{
                                    return;  // 지정 날짜보다 이전 기사는 스킵
                                }}
                            }}

                            // URL 정리 (쿼리 파라미터 제거)
                            let url = href;
                            try {{
                                const urlObj = new URL(href);
                                url = urlObj.origin + urlObj.pathname;
                            }} catch(e) {{}}

                            // 중복 체크
                            if (seenUrls.has(url)) return;
                            seenUrls.add(url);

                            articles.push({{
                                news_url: url,
                                title: title,
                                published_at: publishedAt
                            }});
                        }});

                        return articles;
                    }})())
                '''

                page_articles = []
                try:
                    result = await page.evaluate(articles_js)
                    if isinstance(result, str):
                        import json
                        page_articles = json.loads(result)
                    elif isinstance(result, list):
                        page_articles = result
                except Exception as e:
                    self.logger.warning(f"    페이지 {page_num} 추출 오류: {e}")

                # 이 페이지에서 수집한 기사 추가 (중복 제거)
                page_new_count = 0
                page_new_urls = []  # 이 페이지에서 새로 수집한 URL
                for article in page_articles:
                    url = article.get('news_url')
                    if url and url not in [n['news_url'] for n in news_list]:
                        news_list.append(article)
                        page_new_urls.append(url)
                        page_new_count += 1

                self.logger.info(f"    페이지 {page_num}: {page_new_count}개 수집 (누적: {len(news_list)}/{total_article_count})")

                # 첫 페이지에서 모든 URL이 이미 DB에 있으면 조기 종료
                if page_num == 1 and page_new_count > 0 and existing_urls:
                    new_urls_not_in_db = [url for url in page_new_urls if url not in existing_urls]
                    if len(new_urls_not_in_db) == 0:
                        self.logger.info(f"    첫 페이지 URL 모두 기존 수집됨, 다음 회사로 이동")
                        return news_list

                # 모든 기사 수집 완료 확인
                if len(news_list) >= total_article_count:
                    self.logger.info(f"    전체 {total_article_count}건 URL 수집 완료")
                    break

                # 이 페이지에서 기사가 없으면 종료 (날짜 필터로 인한 종료 포함)
                if page_new_count == 0:
                    if self.since_date:
                        self.logger.info(f"    {self.since_date} 이후 기사 없음, URL 수집 종료")
                    else:
                        self.logger.info(f"    더 이상 기사 없음, URL 수집 종료")
                    break

            self.logger.info(f"    [2단계 완료] 총 {len(news_list)}개 URL 수집")

        except Exception as e:
            self.logger.error(f"뉴스 검색 오류: {e}")

        return news_list

    async def _wait_for_articles(self, page, timeout: int = 15):
        """동적 로딩 완료 대기 (기사가 로드될 때까지)"""
        last_count = 0
        stable = 0

        for _ in range(timeout):
            try:
                count = await page.evaluate('document.querySelectorAll(".item-box01").length')
                if count and count > 0:
                    if count == last_count:
                        stable += 1
                        if stable >= 2:  # 2초 연속 같으면 로딩 완료
                            return True
                    else:
                        stable = 0
                        last_count = count
            except:
                pass
            await asyncio.sleep(1)

        return last_count > 0

    async def get_article_detail(self, news_url: str) -> Dict[str, Any]:
        """기사 상세 페이지에서 정보 수집

        Args:
            news_url: 기사 URL

        Returns:
            기사 상세 정보 {title, published_at, subtitle, reporter_name, content}
        """
        detail = {
            'news_url': news_url,
            'title': None,
            'published_at': None,
            'subtitle': None,
            'reporter_name': None,
            'content': None
        }

        if not NODRIVER_AVAILABLE:
            return detail

        try:
            browser = await self._get_browser()
            page = await browser.get(news_url)
            await asyncio.sleep(self.page_load_delay)

            # 기사 제목 요소 로드 대기 (최대 10초)
            for wait_attempt in range(10):
                try:
                    has_title = await page.evaluate('document.querySelector("h1.tit01") !== null')
                    if has_title:
                        break
                except:
                    pass
                await asyncio.sleep(1)

            # 페이지 하단까지 스크롤
            await self._scroll_to_bottom(page)

            # 기사 상세 정보 추출
            detail_js = r'''
                JSON.stringify((() => {
                    const data = {
                        title: null,
                        published_at: null,
                        subtitle: null,
                        reporter_name: null,
                        content: null
                    };

                    // 제목: <h1 class="tit01">
                    const titleEl = document.querySelector('h1.tit01');
                    if (titleEl) data.title = titleEl.innerText.trim();

                    // 게시일시: <p class="txt-time01">
                    const timeEl = document.querySelector('.txt-time01');
                    if (timeEl) {
                        // "송고2026-01-29 17:16" 형태에서 날짜만 추출
                        const timeText = timeEl.innerText.trim();
                        const match = timeText.match(/(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})/);
                        if (match) data.published_at = match[1];
                    }

                    // 기자이름: <strong class="tit-name"> 내 <a>
                    const reporterEl = document.querySelector('.tit-name a');
                    if (reporterEl) data.reporter_name = reporterEl.innerText.trim();

                    // 부제목: <div class="tit-sub"> 내 <h2 class="tit01">
                    const subtitleEl = document.querySelector('.tit-sub h2.tit01');
                    if (subtitleEl) data.subtitle = subtitleEl.innerText.trim();

                    // 내용: <div class="story-news article"> 내 <p> 태그들
                    const contentArea = document.querySelector('.story-news.article');
                    if (contentArea) {
                        const paragraphs = contentArea.querySelectorAll('p');
                        const contentParts = [];

                        paragraphs.forEach(p => {
                            // 광고, 저작권 등 제외
                            const text = p.innerText.trim();
                            if (text &&
                                !text.includes('저작권자') &&
                                !text.includes('무단 전재') &&
                                !text.includes('제보는 카카오톡') &&
                                !p.classList.contains('txt-copyright') &&
                                !p.classList.contains('txt-desc')) {
                                contentParts.push(text);
                            }
                        });

                        data.content = contentParts.join('\n\n');
                    }

                    return data;
                })())
            '''

            result = await page.evaluate(detail_js)

            if isinstance(result, str):
                import json
                detail.update(json.loads(result))
            elif isinstance(result, dict):
                detail.update(result)

        except Exception as e:
            self.logger.error(f"기사 상세 수집 오류: {e}")

        return detail

    async def crawl_company_news(self, company_name: str, company_id: Optional[int] = None) -> Dict[str, Any]:
        """회사의 뉴스 기사 전체 수집

        가이드에 따른 수집 흐름:
        1. 검색 결과에서 총 기사 수 확인
        2. 페이지별로 기사 URL 수집 (총 기사 수만큼)
        3. 수집한 URL을 순회하며 상세 내용 수집
        4. DB 저장

        Args:
            company_name: 회사명
            company_id: DB의 company_id

        Returns:
            수집 결과 {company_name, total_found, saved_count, articles}
        """
        result = {
            'company_name': company_name,
            'total_found': 0,
            'saved_count': 0,
            'new_count': 0,
            'duplicate_count': 0,
            'articles': []
        }

        self.logger.info(f"  ========== {company_name} 뉴스 수집 ==========")

        # 기존 URL 조회 (중복 체크 및 조기 종료 판단용)
        existing_urls = self.db.get_existing_news_urls(company_name)

        # ========== 1단계 & 2단계: 기사 URL 목록 수집 ==========
        news_list = await self.search_news(company_name, existing_urls=existing_urls)
        result['total_found'] = len(news_list)

        if not news_list:
            self.logger.info(f"  검색된 뉴스 없음")
            return result

        # 기존 URL 필터링 (이미 DB에 있는 URL은 스킵) - existing_urls는 위에서 이미 조회됨
        new_articles = [a for a in news_list if a.get('news_url') not in existing_urls]
        skipped_count = len(news_list) - len(new_articles)

        self.logger.info(f"  URL 수집 결과: 총 {len(news_list)}개, 신규 {len(new_articles)}개, 기존 {skipped_count}개")

        if not new_articles:
            self.logger.info(f"  모든 기사 이미 수집됨, 다음 회사로 이동")
            result['duplicate_count'] = skipped_count
            return result

        # ========== 3단계: 각 URL 방문하여 상세 내용 수집 ==========
        self.logger.info(f"  [3단계] 기사 상세 내용 수집 시작 ({len(new_articles)}개)")

        consecutive_errors = 0
        for i, article in enumerate(new_articles, 1):
            try:
                self.logger.info(f"    [{i}/{len(new_articles)}] {article.get('title', '')[:30]}...")

                # 상세 정보 수집
                detail = await self.get_article_detail(article['news_url'])

                if detail.get('content'):
                    # 목록 정보와 상세 정보 병합
                    article.update({
                        'subtitle': detail.get('subtitle'),
                        'reporter_name': detail.get('reporter_name'),
                        'content': detail.get('content')
                    })
                    if detail.get('title'):
                        article['title'] = detail['title']
                    if detail.get('published_at'):
                        article['published_at'] = detail['published_at']

                    result['articles'].append(article)
                    consecutive_errors = 0
                    self.logger.info(f"    [{i}/{len(new_articles)}] 수집 완료 (내용 {len(detail.get('content', ''))}자)")
                else:
                    self.logger.warning(f"    [{i}/{len(new_articles)}] 내용 없음")

                # 다음 기사 전 대기 (가이드: 1초)
                await asyncio.sleep(self.article_delay)

            except Exception as e:
                self.logger.warning(f"    [{i}/{len(new_articles)}] 수집 실패: {e}")
                consecutive_errors += 1

                if consecutive_errors >= 3:
                    self.logger.warning("    연속 에러 발생, 브라우저 재시작")
                    self.close()
                    await asyncio.sleep(3)
                    consecutive_errors = 0

        self.logger.info(f"  [3단계 완료] {len(result['articles'])}/{len(new_articles)}개 상세 수집 완료")

        # ========== 4단계: DB 저장 ==========
        if result['articles']:
            try:
                save_result = self.db.add_company_news(company_name, result['articles'], company_id)
                result['new_count'] = save_result['new_count']
                result['duplicate_count'] = save_result.get('duplicate_count', 0) + skipped_count
                result['updated_count'] = save_result['updated_count']
                self.logger.info(f"  [DB 저장] 신규 {save_result['new_count']}건, 업데이트 {save_result['updated_count']}건")
            except Exception as e:
                self.logger.error(f"  [DB 저장 실패] {e}")
        else:
            result['duplicate_count'] = skipped_count

        self.logger.info(f"  ========== {company_name} 완료 ==========\n")
        return result

    def crawl_company_news_sync(self, company_name: str, company_id: Optional[int] = None) -> Dict[str, Any]:
        """동기 방식으로 회사 뉴스 크롤링 (main.py에서 호출용)"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self.crawl_company_news(company_name, company_id))

    def close(self):
        """브라우저 종료"""
        if self._browser:
            try:
                self._browser.stop()
            except:
                pass
            self._browser = None
            self.logger.info("브라우저 종료됨")
