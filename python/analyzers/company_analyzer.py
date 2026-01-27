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
        result['basic_info'] = job_based_info.get('basic_info', {})
        result['job_stats'] = job_based_info.get('job_stats', {})

        # 2. 잡플래닛 평판 조회 (Playwright 사용)
        reputation = self._get_jobplanet_rating(company_name)
        result['reputation'] = reputation

        # 3. 종합 평가
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

    def _get_jobplanet_rating(self, company_name: str) -> Dict[str, Any]:
        """잡플래닛에서 회사 평점 조회 (Playwright 사용)"""
        reputation = {
            'jobplanet_rating': None,
            'jobplanet_review_count': None,
            'jobplanet_url': None,
            'overall_sentiment': 'unknown',
        }

        if not PLAYWRIGHT_AVAILABLE:
            self.logger.warning("Playwright not available, skipping Jobplanet")
            return reputation

        try:
            self.rate_limiter.wait()
            search_url = f"https://www.jobplanet.co.kr/search?query={company_name}"

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()

                try:
                    page.goto(search_url, timeout=15000)
                    page.wait_for_load_state('networkidle', timeout=10000)

                    # 검색 결과에서 회사 카드 찾기
                    company_cards = page.query_selector_all('[class*="CompanyCard"], [class*="company_card"], .result_card')

                    for card in company_cards[:3]:  # 상위 3개만 확인
                        try:
                            # 회사명 확인
                            name_elem = card.query_selector('[class*="name"], [class*="title"], h2, h3')
                            if name_elem:
                                card_name = name_elem.text_content().strip()
                                if company_name.lower() in card_name.lower():
                                    # 평점 추출
                                    rating_elem = card.query_selector('[class*="rating"], [class*="score"], [class*="rate"]')
                                    if rating_elem:
                                        rating_text = rating_elem.text_content()
                                        rating_match = re.search(r'(\d+\.?\d*)', rating_text)
                                        if rating_match:
                                            reputation['jobplanet_rating'] = float(rating_match.group(1))

                                    # 리뷰 수 추출
                                    review_elem = card.query_selector('[class*="review"], [class*="count"]')
                                    if review_elem:
                                        review_text = review_elem.text_content()
                                        review_match = re.search(r'(\d+)', review_text.replace(',', ''))
                                        if review_match:
                                            reputation['jobplanet_review_count'] = int(review_match.group(1))

                                    # 회사 페이지 URL
                                    link_elem = card.query_selector('a[href*="/companies/"]')
                                    if link_elem:
                                        reputation['jobplanet_url'] = link_elem.get_attribute('href')

                                    break
                        except Exception as e:
                            self.logger.debug(f"Error parsing company card: {e}")

                    # 평점 기반 sentiment 설정
                    if reputation['jobplanet_rating']:
                        rating = reputation['jobplanet_rating']
                        if rating >= 4.0:
                            reputation['overall_sentiment'] = 'very_positive'
                        elif rating >= 3.5:
                            reputation['overall_sentiment'] = 'positive'
                        elif rating >= 3.0:
                            reputation['overall_sentiment'] = 'neutral'
                        elif rating >= 2.5:
                            reputation['overall_sentiment'] = 'negative'
                        else:
                            reputation['overall_sentiment'] = 'very_negative'

                except Exception as e:
                    self.logger.warning(f"Jobplanet page load failed: {e}")
                finally:
                    browser.close()

        except Exception as e:
            self.logger.error(f"Jobplanet search failed: {e}")

        return reputation
    
    def _generate_summary(self, analysis: Dict[str, Any]) -> Dict[str, str]:
        """분석 결과 요약 생성"""
        company_name = analysis.get('company_name', '')
        basic_info = analysis.get('basic_info', {})
        job_stats = analysis.get('job_stats', {})
        reputation = analysis.get('reputation', {})

        # 기본 정보 요약
        info_parts = []
        if basic_info.get('industry'):
            info_parts.append(f"산업: {basic_info['industry']}")
        if basic_info.get('location'):
            info_parts.append(f"주요 근무지: {basic_info['location']}")

        basic_summary = ', '.join(info_parts) if info_parts else "기본 정보 없음"

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
        if reputation.get('jobplanet_review_count'):
            reputation_parts.append(f"리뷰 {reputation['jobplanet_review_count']}개")

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
                'address': basic_info.get('location'),
                'jobplanet_rating': reputation.get('jobplanet_rating'),
                'public_sentiment': summary.get('overall'),
            }

            self.db.add_company(company_data)

        except Exception as e:
            self.logger.error(f"Error saving to DB: {e}")

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
