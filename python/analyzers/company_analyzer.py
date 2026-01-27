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
            'review_count': jobplanet_info.get('review_count'),
            'pros_keywords': jobplanet_info.get('pros_keywords', []),
            'cons_keywords': jobplanet_info.get('cons_keywords', []),
        }

        # 5. 연봉 정보
        result['salary_info'] = {
            'average': jobplanet_info.get('salary_info'),
            'by_position': jobplanet_info.get('salary_by_position', []),
        }

        # 6. 면접 정보
        result['interview_info'] = {
            'count': jobplanet_info.get('interview_count'),
            'difficulty': jobplanet_info.get('interview_difficulty'),
            'experience': jobplanet_info.get('interview_experience'),
            'success_rate': jobplanet_info.get('interview_success_rate'),
        }

        # 7. 복지 정보
        result['benefits'] = jobplanet_info.get('benefits', [])

        # 8. 잡플래닛 채용공고 수
        result['jobplanet_job_count'] = jobplanet_info.get('active_job_count')

        # 9. 종합 평가
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
        """잡플래닛에서 회사 정보 조회 (Playwright 사용) - 모든 페이지 수집"""
        info = {
            # 기본 정보
            'jobplanet_rating': None,
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
            # 리뷰 정보
            'review_count': None,
            'review_summary': None,
            'pros_keywords': [],
            'cons_keywords': [],
            # 연봉 정보
            'salary_info': None,
            'salary_by_position': [],
            # 면접 정보
            'interview_count': None,
            'interview_difficulty': None,
            'interview_experience': None,
            'interview_success_rate': None,
            # 복지 정보
            'benefits': [],
            # 채용공고 정보
            'active_job_count': None,
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
                    self.logger.info(f"  → 잡플래닛 검색: {company_name}")
                    page.goto(search_url)
                    page.wait_for_load_state('networkidle', timeout=10000)

                    # 2. 검색 결과 카드에서 회사 찾기
                    company_cards = page.query_selector_all('a[href*="/companies/"]')
                    matched_card = None
                    company_id = None

                    for card in company_cards[:15]:
                        try:
                            name_elem = card.query_selector('h4')
                            if not name_elem:
                                continue

                            card_name = name_elem.text_content().strip()
                            normalized_card = self._normalize_company_name(card_name)

                            if normalized_search == normalized_card or \
                               normalized_search in normalized_card or \
                               normalized_card in normalized_search:
                                matched_card = card
                                # 회사 ID 추출: /companies/1289 -> 1289
                                href = card.get_attribute('href') or ''
                                id_match = re.search(r'/companies/(\d+)', href)
                                if id_match:
                                    company_id = id_match.group(1)
                                self.logger.info(f"  → 회사 발견: {card_name} (ID: {company_id})")
                                break
                        except Exception as e:
                            continue

                    if not matched_card or not company_id:
                        self.logger.warning(f"Company not found on Jobplanet: {company_name}")
                        browser.close()
                        return info

                    # 3. 검색 결과 카드에서 기본 정보 추출
                    self._extract_from_search_card(matched_card, info)

                    # 4. 각 페이지 방문하여 정보 수집
                    base_url = f"https://www.jobplanet.co.kr/companies/{company_id}"
                    info['jobplanet_url'] = base_url

                    # 4-1. 리뷰 페이지
                    self._extract_reviews(page, base_url, info)

                    # 4-2. 연봉 페이지
                    self._extract_salaries(page, base_url, info)

                    # 4-3. 면접 페이지
                    self._extract_interviews(page, base_url, info)

                    # 4-4. 복지 페이지
                    self._extract_benefits(page, base_url, info)

                    # 4-5. 채용공고 페이지
                    self._extract_job_postings(page, base_url, info)

                    # 5. 평점 기반 sentiment 설정
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
                    self.logger.warning(f"Jobplanet crawl failed: {e}")
                finally:
                    browser.close()

        except Exception as e:
            self.logger.error(f"Jobplanet search failed: {e}")

        return info

    def _extract_from_search_card(self, card, info: Dict[str, Any]):
        """검색 결과 카드에서 기본 정보 추출"""
        try:
            # 평점: <span class="ml-[2px] text-gray-800 ...">3.9</span>
            rating_elem = card.query_selector('span.text-gray-800')
            if rating_elem:
                rating_text = rating_elem.text_content().strip()
                rating_match = re.search(r'^(\d+\.?\d*)$', rating_text)
                if rating_match:
                    info['jobplanet_rating'] = float(rating_match.group(1))

            # 산업/지역: <div class="ml-[16px] text-gray-400 ...">제조/화학∙서울</div>
            industry_loc_elem = card.query_selector('div.text-gray-400')
            if industry_loc_elem:
                industry_loc_text = industry_loc_elem.text_content().strip()
                if '∙' in industry_loc_text:
                    parts = industry_loc_text.split('∙')
                    info['industry'] = parts[0].strip()
                    if len(parts) > 1:
                        info['location'] = parts[1].strip()
                else:
                    info['industry'] = industry_loc_text

            # 설립연도, 사원수
            info_spans = card.query_selector_all('span')
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

    def _extract_reviews(self, page, base_url: str, info: Dict[str, Any]):
        """리뷰 페이지에서 정보 추출"""
        try:
            self.rate_limiter.wait()
            page.goto(f"{base_url}/reviews", timeout=15000)
            page.wait_for_load_state('networkidle', timeout=10000)

            # 리뷰 수 추출
            review_count_elem = page.query_selector('[class*="review"] [class*="count"], .review_count, h2:has-text("리뷰")')
            if review_count_elem:
                count_text = review_count_elem.text_content()
                count_match = re.search(r'([\d,]+)', count_text)
                if count_match:
                    info['review_count'] = int(count_match.group(1).replace(',', ''))

            # 장점/단점 키워드 추출
            pros_elems = page.query_selector_all('[class*="pros"], [class*="merit"], .good_point')
            for elem in pros_elems[:5]:
                text = elem.text_content().strip()
                if text and len(text) < 50:
                    info['pros_keywords'].append(text)

            cons_elems = page.query_selector_all('[class*="cons"], [class*="demerit"], .bad_point')
            for elem in cons_elems[:5]:
                text = elem.text_content().strip()
                if text and len(text) < 50:
                    info['cons_keywords'].append(text)

            self.logger.info(f"  → 리뷰 수집 완료: {info.get('review_count', 0)}건")

        except Exception as e:
            self.logger.debug(f"Error extracting reviews: {e}")

    def _extract_salaries(self, page, base_url: str, info: Dict[str, Any]):
        """연봉 페이지에서 정보 추출"""
        try:
            self.rate_limiter.wait()
            page.goto(f"{base_url}/salaries", timeout=15000)
            page.wait_for_load_state('networkidle', timeout=10000)

            # 평균 연봉 추출
            salary_elem = page.query_selector('[class*="salary"] [class*="average"], .average_salary, [class*="avg"]')
            if salary_elem:
                salary_text = salary_elem.text_content().strip()
                info['salary_info'] = salary_text

            # 직급별/직군별 연봉 테이블
            salary_rows = page.query_selector_all('table tr, [class*="salary_item"], [class*="salary-row"]')
            for row in salary_rows[:10]:
                try:
                    cells = row.query_selector_all('td, [class*="cell"]')
                    if len(cells) >= 2:
                        position = cells[0].text_content().strip()
                        salary = cells[1].text_content().strip()
                        if position and salary and '만원' in salary:
                            info['salary_by_position'].append({
                                'position': position,
                                'salary': salary
                            })
                except:
                    continue

            self.logger.info(f"  → 연봉 정보 수집 완료")

        except Exception as e:
            self.logger.debug(f"Error extracting salaries: {e}")

    def _extract_interviews(self, page, base_url: str, info: Dict[str, Any]):
        """면접 페이지에서 정보 추출"""
        try:
            self.rate_limiter.wait()
            page.goto(f"{base_url}/interviews", timeout=15000)
            page.wait_for_load_state('networkidle', timeout=10000)

            # 면접 후기 수
            interview_count_elem = page.query_selector('[class*="interview"] [class*="count"], .interview_count')
            if interview_count_elem:
                count_text = interview_count_elem.text_content()
                count_match = re.search(r'([\d,]+)', count_text)
                if count_match:
                    info['interview_count'] = int(count_match.group(1).replace(',', ''))

            # 면접 난이도
            difficulty_elem = page.query_selector('[class*="difficulty"], [class*="level"]')
            if difficulty_elem:
                info['interview_difficulty'] = difficulty_elem.text_content().strip()

            # 면접 경험 (긍정/부정/보통)
            experience_elem = page.query_selector('[class*="experience"], [class*="feeling"]')
            if experience_elem:
                info['interview_experience'] = experience_elem.text_content().strip()

            # 합격률
            success_elem = page.query_selector('[class*="success"], [class*="pass_rate"], [class*="result"]')
            if success_elem:
                success_text = success_elem.text_content()
                rate_match = re.search(r'(\d+)%', success_text)
                if rate_match:
                    info['interview_success_rate'] = f"{rate_match.group(1)}%"

            self.logger.info(f"  → 면접 정보 수집 완료: {info.get('interview_count', 0)}건")

        except Exception as e:
            self.logger.debug(f"Error extracting interviews: {e}")

    def _extract_benefits(self, page, base_url: str, info: Dict[str, Any]):
        """복지 페이지에서 정보 추출"""
        try:
            self.rate_limiter.wait()
            page.goto(f"{base_url}/benefits", timeout=15000)
            page.wait_for_load_state('networkidle', timeout=10000)

            # 복지 항목 추출
            benefit_elems = page.query_selector_all('[class*="benefit"], [class*="welfare"], .benefit_item, li')
            seen = set()
            for elem in benefit_elems[:30]:
                try:
                    text = elem.text_content().strip()
                    # 복지 관련 키워드가 포함된 항목만
                    if text and len(text) < 100 and text not in seen:
                        # 일반적인 복지 키워드 체크
                        welfare_keywords = ['식', '보험', '휴가', '지원', '수당', '복지', '건강',
                                          '교육', '포인트', '카페', '헬스', '통근', '주차']
                        if any(kw in text for kw in welfare_keywords):
                            info['benefits'].append(text)
                            seen.add(text)
                except:
                    continue

            self.logger.info(f"  → 복지 정보 수집 완료: {len(info['benefits'])}개")

        except Exception as e:
            self.logger.debug(f"Error extracting benefits: {e}")

    def _extract_job_postings(self, page, base_url: str, info: Dict[str, Any]):
        """채용공고 페이지에서 정보 추출"""
        try:
            self.rate_limiter.wait()
            page.goto(f"{base_url}/job_postings", timeout=15000)
            page.wait_for_load_state('networkidle', timeout=10000)

            # 채용공고 수
            job_count_elem = page.query_selector('[class*="job"] [class*="count"], .job_count, [class*="total"]')
            if job_count_elem:
                count_text = job_count_elem.text_content()
                count_match = re.search(r'([\d,]+)', count_text)
                if count_match:
                    info['active_job_count'] = int(count_match.group(1).replace(',', ''))

            # 채용공고 카드 수로 대체
            if not info['active_job_count']:
                job_cards = page.query_selector_all('[class*="job_card"], [class*="job-item"], .posting_item')
                if job_cards:
                    info['active_job_count'] = len(job_cards)

            self.logger.info(f"  → 채용공고 수집 완료: {info.get('active_job_count', 0)}건")

        except Exception as e:
            self.logger.debug(f"Error extracting job postings: {e}")
    
    def _generate_summary(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """분석 결과 요약 생성"""
        basic_info = analysis.get('basic_info', {})
        job_stats = analysis.get('job_stats', {})
        reputation = analysis.get('reputation', {})
        salary_info = analysis.get('salary_info', {})
        interview_info = analysis.get('interview_info', {})
        benefits = analysis.get('benefits', [])

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
            job_summary_parts.append(f"DB 채용공고 {total}건")
            top_skills = job_stats.get('top_skills', [])[:3]
            if top_skills:
                skills_str = ', '.join([s['skill'] for s in top_skills])
                job_summary_parts.append(f"주요 스킬: {skills_str}")
        jp_jobs = analysis.get('jobplanet_job_count')
        if jp_jobs:
            job_summary_parts.append(f"잡플래닛 채용 중 {jp_jobs}건")

        job_summary = ' | '.join(job_summary_parts) if job_summary_parts else "채용공고 없음"

        # 평판 요약
        reputation_parts = []
        if reputation.get('jobplanet_rating'):
            reputation_parts.append(f"평점 {reputation['jobplanet_rating']}/5.0")
        if reputation.get('review_count'):
            reputation_parts.append(f"리뷰 {reputation['review_count']}건")
        if reputation.get('pros_keywords'):
            reputation_parts.append(f"장점: {', '.join(reputation['pros_keywords'][:3])}")
        if reputation.get('cons_keywords'):
            reputation_parts.append(f"단점: {', '.join(reputation['cons_keywords'][:3])}")

        reputation_summary = ' | '.join(reputation_parts) if reputation_parts else "평판 정보 없음"

        # 연봉 요약
        salary_summary = "연봉 정보 없음"
        if salary_info.get('average'):
            salary_summary = f"평균 연봉: {salary_info['average']}"
            if salary_info.get('by_position'):
                positions = [f"{p['position']}: {p['salary']}" for p in salary_info['by_position'][:3]]
                salary_summary += f" | {', '.join(positions)}"

        # 면접 요약
        interview_parts = []
        if interview_info.get('count'):
            interview_parts.append(f"면접 후기 {interview_info['count']}건")
        if interview_info.get('difficulty'):
            interview_parts.append(f"난이도: {interview_info['difficulty']}")
        if interview_info.get('success_rate'):
            interview_parts.append(f"합격률: {interview_info['success_rate']}")

        interview_summary = ' | '.join(interview_parts) if interview_parts else "면접 정보 없음"

        # 복지 요약
        benefits_summary = "복지 정보 없음"
        if benefits:
            benefits_summary = ', '.join(benefits[:5])
            if len(benefits) > 5:
                benefits_summary += f" 외 {len(benefits) - 5}개"

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
            'salary': salary_summary,
            'interview': interview_summary,
            'benefits': benefits_summary,
            'overall': overall,
        }

    def _save_to_db(self, analysis: Dict[str, Any]):
        """분석 결과 DB 저장"""
        try:
            basic_info = analysis.get('basic_info', {})
            reputation = analysis.get('reputation', {})
            summary = analysis.get('summary', {})
            salary_info = analysis.get('salary_info', {})
            interview_info = analysis.get('interview_info', {})
            benefits = analysis.get('benefits', [])

            # JSON으로 저장할 추가 정보
            import json
            additional_info = {
                'salary': salary_info,
                'interview': interview_info,
                'benefits': benefits,
                'pros_keywords': reputation.get('pros_keywords', []),
                'cons_keywords': reputation.get('cons_keywords', []),
                'review_count': reputation.get('review_count'),
                'jobplanet_job_count': analysis.get('jobplanet_job_count'),
            }

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
                'jobplanet_url': reputation.get('jobplanet_url'),
                'public_sentiment': summary.get('overall'),
                'additional_info': json.dumps(additional_info, ensure_ascii=False),
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
