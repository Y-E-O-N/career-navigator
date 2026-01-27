"""
회사 분석 모듈
채용공고 기반 회사 정보 분석 + 잡플래닛 평판 조회
"""

from typing import Dict, Any, Optional, List
from collections import Counter
import re
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.database import db, Company, JobPosting
from utils.helpers import setup_logger, clean_text, RateLimiter
from config.settings import settings

# Playwright 사용 가능 여부
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class CompanyAnalyzer:
    """회사 분석기 - 채용공고 DB + 잡플래닛 기반"""

    def __init__(self, database=None):
        self.logger = setup_logger("analyzer.company")
        self.db = database if database else db
        self.rate_limiter = RateLimiter(0.5)

    def analyze_company(self, company_name: str) -> Dict[str, Any]:
        """
        회사 종합 분석

        Args:
            company_name: 회사명

        Returns:
            회사 분석 결과
        """
        self.logger.info(f"Analyzing company: {company_name}")

        result = {
            'company_name': company_name,
            'analysis_date': datetime.now().isoformat(),
        }

        # 1. 채용공고 DB에서 회사 정보 집계
        job_based_info = self._analyze_from_job_postings(company_name)
        result['job_stats'] = job_based_info.get('job_stats', {})

        # 2. 잡플래닛에서 회사 정보 조회 (Playwright 사용)
        jobplanet_info = self._get_jobplanet_info(company_name)

        # 3. 기본 정보 병합 (잡플래닛 정보 우선, 없으면 채용공고 DB 정보 사용)
        db_basic = job_based_info.get('basic_info', {})
        result['basic_info'] = {
            'name': company_name,
            'industry': jobplanet_info.get('industry') or db_basic.get('industry'),
            'company_type': jobplanet_info.get('company_type'),
            'employee_count': jobplanet_info.get('employee_count'),
            'founded_date': jobplanet_info.get('founded_date'),
            'ceo': jobplanet_info.get('ceo'),
            'revenue': jobplanet_info.get('revenue'),
            'location': jobplanet_info.get('location') or db_basic.get('location'),
            'address': jobplanet_info.get('address'),
            'website': jobplanet_info.get('website'),
        }

        # 4. 평판 정보
        result['reputation'] = {
            'jobplanet_rating': jobplanet_info.get('jobplanet_rating'),
            'jobplanet_url': jobplanet_info.get('jobplanet_url'),
            'overall_sentiment': jobplanet_info.get('overall_sentiment', 'unknown'),
        }

        # 5. 종합 평가
        result['summary'] = self._generate_summary(result)

        # DB에 저장
        self._save_to_db(result)

        return result

    def _analyze_from_job_postings(self, company_name: str) -> Dict[str, Any]:
        """채용공고 DB에서 회사 정보 분석"""
        session = self.db.get_session()

        try:
            # 해당 회사의 채용공고 조회
            jobs = session.query(JobPosting).filter(
                JobPosting.company_name.ilike(f"%{company_name}%")
            ).all()

            if not jobs:
                return {
                    'basic_info': {'name': company_name},
                    'job_stats': {'total_postings': 0}
                }

            # 기본 정보 추출 (첫 번째 공고에서)
            first_job = jobs[0]
            basic_info = {
                'name': company_name,
                'industry': getattr(first_job, 'company_industry', None),
                'location': None,
                'website': None,
            }

            # 지역 정보 집계
            locations = [job.location for job in jobs if job.location]
            if locations:
                location_counts = Counter(locations)
                basic_info['location'] = location_counts.most_common(1)[0][0]

            # 채용 통계
            skills = []
            job_categories = []
            experience_levels = []

            for job in jobs:
                if job.required_skills:
                    if isinstance(job.required_skills, list):
                        skills.extend(job.required_skills)
                if job.job_category:
                    job_categories.append(job.job_category)
                if job.position_level:
                    experience_levels.append(job.position_level)

            job_stats = {
                'total_postings': len(jobs),
                'top_skills': [{'skill': s, 'count': c} for s, c in Counter(skills).most_common(10)],
                'job_categories': [{'category': c, 'count': cnt} for c, cnt in Counter(job_categories).most_common(5)],
                'experience_levels': [{'level': l, 'count': c} for l, c in Counter(experience_levels).most_common()],
                'sources': [{'site': s, 'count': c} for s, c in Counter(job.source_site for job in jobs).most_common()],
            }

            return {
                'basic_info': basic_info,
                'job_stats': job_stats
            }

        finally:
            session.close()

    def _normalize_company_name(self, name: str) -> str:
        """회사명 정규화 (띄어쓰기, 특수문자 제거)"""
        if not name:
            return ""
        # (주), (유), 주식회사 등 제거
        normalized = re.sub(r'\(주\)|\(유\)|주식회사|㈜|\s+', '', name)
        # 소문자로 변환
        return normalized.lower().strip()

    def _get_jobplanet_info(self, company_name: str) -> Dict[str, Any]:
        """잡플래닛에서 회사 정보 조회 (Playwright 사용)"""
        info = {
            'jobplanet_rating': None,
            'jobplanet_review_count': None,
            'jobplanet_url': None,
            'industry': None,
            'company_type': None,
            'employee_count': None,
            'founded_date': None,
            'location': None,
            'ceo': None,
            'revenue': None,
            'address': None,
            'website': None,
            'overall_sentiment': 'unknown',
        }

        if not PLAYWRIGHT_AVAILABLE:
            self.logger.warning("Playwright not available, skipping Jobplanet")
            return info

        try:
            self.rate_limiter.wait()
            search_url = f"https://www.jobplanet.co.kr/search?query={company_name}"
            normalized_search = self._normalize_company_name(company_name)

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_default_timeout(15000)

                try:
                    # 1. 검색 페이지로 이동
                    page.goto(search_url)
                    page.wait_for_load_state('networkidle', timeout=10000)

                    # 2. 검색 결과 카드에서 회사 찾기
                    # 카드 구조: <a href="/companies/..."><h4>회사명</h4>...</a>
                    company_cards = page.query_selector_all('a[href*="/companies/"]')
                    matched_card = None

                    for card in company_cards[:15]:
                        try:
                            # h4 태그에서 회사명 찾기
                            name_elem = card.query_selector('h4')
                            if not name_elem:
                                continue

                            card_name = name_elem.text_content().strip()
                            normalized_card = self._normalize_company_name(card_name)

                            # 정규화된 이름이 일치하면 선택
                            if normalized_search == normalized_card:
                                matched_card = card
                                self.logger.info(f"  → 정확히 일치: {card_name}")
                                break
                            # 부분 일치도 허용 (검색어가 카드 이름에 포함되거나 반대)
                            elif normalized_search in normalized_card or normalized_card in normalized_search:
                                matched_card = card
                                self.logger.info(f"  → 부분 일치: {card_name}")
                                break
                        except Exception as e:
                            self.logger.debug(f"Error checking card: {e}")
                            continue

                    if not matched_card:
                        self.logger.warning(f"Company not found on Jobplanet: {company_name}")
                        browser.close()
                        return info

                    # 3. 검색 결과 카드에서 정보 추출
                    try:
                        # 평점 추출: <span class="ml-[2px] text-gray-800 ...">3.9</span>
                        rating_elem = matched_card.query_selector('span.text-gray-800')
                        if rating_elem:
                            rating_text = rating_elem.text_content().strip()
                            rating_match = re.search(r'^(\d+\.?\d*)$', rating_text)
                            if rating_match:
                                info['jobplanet_rating'] = float(rating_match.group(1))

                        # 산업/지역: <div class="ml-[16px] text-gray-400 ...">제조/화학∙서울</div>
                        industry_loc_elem = matched_card.query_selector('div.text-gray-400')
                        if industry_loc_elem:
                            industry_loc_text = industry_loc_elem.text_content().strip()
                            # "제조/화학∙서울" 형태 파싱
                            if '∙' in industry_loc_text:
                                parts = industry_loc_text.split('∙')
                                info['industry'] = parts[0].strip()
                                if len(parts) > 1:
                                    info['location'] = parts[1].strip()
                            else:
                                info['industry'] = industry_loc_text

                        # 설립연도, 사원수: <span>57년차 (1969)</span>, <span>71666명</span>
                        info_spans = matched_card.query_selector_all('span')
                        for span in info_spans:
                            span_text = span.text_content().strip()
                            # 설립연도: "57년차 (1969)" 패턴
                            founded_match = re.search(r'\((\d{4})\)', span_text)
                            if founded_match:
                                info['founded_date'] = founded_match.group(1)
                            # 사원수: "71666명" 패턴
                            employee_match = re.match(r'^([\d,]+)명$', span_text)
                            if employee_match:
                                info['employee_count'] = span_text

                    except Exception as e:
                        self.logger.debug(f"Error extracting card info: {e}")

                    # 4. 회사 상세 페이지로 이동
                    company_link = matched_card.get_attribute('href')
                    if not company_link:
                        browser.close()
                        return info

                    if not company_link.startswith('http'):
                        company_link = f"https://www.jobplanet.co.kr{company_link}"

                    info['jobplanet_url'] = company_link
                    page.goto(company_link)
                    page.wait_for_load_state('networkidle', timeout=10000)

                    # 5. 상세 페이지에서 추가 정보 추출
                    info_items = page.query_selector_all('ul li')
                    for item in info_items:
                        try:
                            label_elem = item.query_selector('.text-gray-300, [class*="label"]')
                            value_elem = item.query_selector('.text-gray-800, [class*="value"], strong')

                            if label_elem and value_elem:
                                label = label_elem.text_content().strip()
                                value = value_elem.text_content().strip()

                                if '기업형태' in label or '기업 형태' in label:
                                    info['company_type'] = value
                                elif '대표' in label:
                                    info['ceo'] = value
                                elif '매출' in label:
                                    info['revenue'] = value
                                elif '주소' in label:
                                    info['address'] = value
                                elif '웹사이트' in label or '홈페이지' in label:
                                    website_link = item.query_selector('a[href]')
                                    if website_link:
                                        info['website'] = website_link.get_attribute('href')
                                    else:
                                        info['website'] = value
                        except Exception as e:
                            self.logger.debug(f"Error parsing detail item: {e}")

                    # 6. 평점 기반 sentiment 설정
                    if info['jobplanet_rating']:
                        rating = info['jobplanet_rating']
                        if rating >= 4.0:
                            info['overall_sentiment'] = 'very_positive'
                        elif rating >= 3.5:
                            info['overall_sentiment'] = 'positive'
                        elif rating >= 3.0:
                            info['overall_sentiment'] = 'neutral'
                        elif rating >= 2.5:
                            info['overall_sentiment'] = 'negative'
                        else:
                            info['overall_sentiment'] = 'very_negative'

                except Exception as e:
                    self.logger.warning(f"Jobplanet page load failed: {e}")
                finally:
                    browser.close()

        except Exception as e:
            self.logger.error(f"Jobplanet search failed: {e}")

        return info
    
    def _generate_summary(self, analysis: Dict[str, Any]) -> Dict[str, str]:
        """분석 결과 요약 생성"""
        basic_info = analysis.get('basic_info', {})
        job_stats = analysis.get('job_stats', {})
        reputation = analysis.get('reputation', {})

        # 기본 정보 요약
        info_parts = []
        if basic_info.get('industry'):
            info_parts.append(f"산업: {basic_info['industry']}")
        if basic_info.get('location'):
            info_parts.append(f"지역: {basic_info['location']}")
        if basic_info.get('company_type'):
            info_parts.append(f"형태: {basic_info['company_type']}")
        if basic_info.get('employee_count'):
            info_parts.append(f"사원수: {basic_info['employee_count']}")
        if basic_info.get('founded_date'):
            info_parts.append(f"설립: {basic_info['founded_date']}")
        if basic_info.get('revenue'):
            info_parts.append(f"매출: {basic_info['revenue']}")

        basic_summary = ' | '.join(info_parts) if info_parts else "기본 정보 없음"

        # 채용 현황 요약
        job_summary_parts = []
        total = job_stats.get('total_postings', 0)
        if total > 0:
            job_summary_parts.append(f"채용공고 {total}건")
            top_skills = job_stats.get('top_skills', [])[:3]
            if top_skills:
                skills_str = ', '.join([s['skill'] for s in top_skills])
                job_summary_parts.append(f"주요 스킬: {skills_str}")

        job_summary = ' | '.join(job_summary_parts) if job_summary_parts else "채용공고 없음"

        # 평판 요약
        reputation_parts = []
        if reputation.get('jobplanet_rating'):
            reputation_parts.append(f"잡플래닛 {reputation['jobplanet_rating']}/5.0")
        if reputation.get('jobplanet_url'):
            reputation_parts.append("상세정보 있음")

        reputation_summary = ' | '.join(reputation_parts) if reputation_parts else "평판 정보 없음"

        # 종합 평가
        overall = "정보 부족"
        if reputation.get('jobplanet_rating'):
            rating = reputation['jobplanet_rating']
            if rating >= 4.0:
                overall = "매우 좋음"
            elif rating >= 3.5:
                overall = "좋음"
            elif rating >= 3.0:
                overall = "보통"
            elif rating >= 2.5:
                overall = "주의 필요"
            else:
                overall = "신중한 검토 필요"
        elif total > 10:
            overall = "활발한 채용 중"

        return {
            'basic': basic_summary,
            'jobs': job_summary,
            'reputation': reputation_summary,
            'overall': overall,
        }

    def _save_to_db(self, analysis: Dict[str, Any]):
        """분석 결과 DB 저장"""
        try:
            basic_info = analysis.get('basic_info', {})
            reputation = analysis.get('reputation', {})
            summary = analysis.get('summary', {})

            company_data = {
                'name': analysis['company_name'],
                'industry': basic_info.get('industry'),
                'company_size': basic_info.get('company_type'),
                'location': basic_info.get('location'),
                'address': basic_info.get('address'),
                'website': basic_info.get('website'),
                'founded_year': self._extract_year(basic_info.get('founded_date')),
                'employee_count': self._extract_number(basic_info.get('employee_count')),
                'revenue': basic_info.get('revenue'),
                'jobplanet_rating': reputation.get('jobplanet_rating'),
                'public_sentiment': summary.get('overall'),
            }

            self.db.add_company(company_data)

        except Exception as e:
            self.logger.error(f"Error saving to DB: {e}")

    def _extract_year(self, date_str: str) -> Optional[int]:
        """날짜 문자열에서 연도 추출"""
        if not date_str:
            return None
        match = re.search(r'(\d{4})', date_str)
        return int(match.group(1)) if match else None

    def _extract_number(self, num_str: str) -> Optional[int]:
        """문자열에서 숫자 추출 (예: '115명' -> 115)"""
        if not num_str:
            return None
        match = re.search(r'([\d,]+)', num_str.replace(',', ''))
        return int(match.group(1)) if match else None

    def get_top_hiring_companies(self, keyword: str = None, days: int = 30, limit: int = 20) -> List[Dict[str, Any]]:
        """채용공고가 많은 상위 회사 목록"""
        session = self.db.get_session()

        try:
            from datetime import timedelta
            from sqlalchemy import func

            query = session.query(
                JobPosting.company_name,
                func.count(JobPosting.id).label('job_count')
            )

            if keyword:
                query = query.filter(
                    (JobPosting.title.ilike(f"%{keyword}%")) |
                    (JobPosting.description.ilike(f"%{keyword}%"))
                )

            # 최근 N일
            from utils.database import get_kst_now
            cutoff = get_kst_now() - timedelta(days=days)
            query = query.filter(JobPosting.crawled_at >= cutoff)

            results = query.group_by(JobPosting.company_name)\
                .order_by(func.count(JobPosting.id).desc())\
                .limit(limit)\
                .all()

            return [
                {'company_name': r[0], 'job_count': r[1]}
                for r in results
            ]

        finally:
            session.close()

    def analyze_companies_batch(self, company_names: List[str]) -> List[Dict[str, Any]]:
        """여러 회사 일괄 분석"""
        results = []

        for company_name in company_names:
            try:
                result = self.analyze_company(company_name)
                results.append(result)
            except Exception as e:
                self.logger.error(f"Error analyzing {company_name}: {e}")
                results.append({
                    'company_name': company_name,
                    'error': str(e)
                })

        return results


# 테스트용
if __name__ == "__main__":
    analyzer = CompanyAnalyzer()

    # 채용 많은 회사 조회
    top_companies = analyzer.get_top_hiring_companies(keyword="백엔드", limit=10)
    print("채용 많은 회사:")
    for c in top_companies:
        print(f"  {c['company_name']}: {c['job_count']}건")

    # 특정 회사 분석
    if top_companies:
        result = analyzer.analyze_company(top_companies[0]['company_name'])
        print(f"\n회사 분석: {result['company_name']}")
        print(f"요약: {result.get('summary', {})}")
