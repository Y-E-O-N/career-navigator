"""
회사 분석 모듈
사업자 조회, 평판 조사, 뉴스 수집
"""

from typing import Dict, Any, Optional, List
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.database import db, Company
from utils.helpers import setup_logger, clean_text, retry_on_failure, RateLimiter
from config.settings import settings


class CompanyAnalyzer:
    """회사 분석기"""

    def __init__(self, database=None):
        self.logger = setup_logger("analyzer.company")
        self.db = database if database else db
        self.rate_limiter = RateLimiter(0.5)  # 2초에 1회

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': settings.crawler.user_agent,
        })
    
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
        
        # 1. 기업 기본 정보 조회 (공공 API 활용)
        basic_info = self._get_basic_info(company_name)
        result['basic_info'] = basic_info
        
        # 2. 기업 평판 조회
        reputation = self._get_reputation(company_name)
        result['reputation'] = reputation
        
        # 3. 최근 뉴스 수집
        news = self._get_news(company_name)
        result['news'] = news
        
        # 4. 종합 평가
        result['summary'] = self._generate_summary(result)
        
        # DB에 저장
        self._save_to_db(result)
        
        return result
    
    def _get_basic_info(self, company_name: str) -> Dict[str, Any]:
        """기업 기본 정보 조회"""
        info = {
            'name': company_name,
            'business_number': None,
            'industry': None,
            'company_size': None,
            'founded_year': None,
            'address': None,
            'website': None,
        }
        
        try:
            # 사업자등록 조회 (공공데이터포털 API 활용 가능)
            # 여기서는 크롤링으로 대체
            search_results = self._search_company_info(company_name)
            info.update(search_results)
            
        except Exception as e:
            self.logger.error(f"Error getting basic info for {company_name}: {e}")
        
        return info
    
    def _search_company_info(self, company_name: str) -> Dict[str, Any]:
        """기업 정보 검색"""
        info = {}
        
        try:
            self.rate_limiter.wait()
            
            # 여러 소스에서 정보 수집 시도
            # 1. 크레딧잡 (기업 정보 사이트)
            creditjob_info = self._search_creditjob(company_name)
            info.update(creditjob_info)
            
        except Exception as e:
            self.logger.warning(f"Could not get company info: {e}")
        
        return info
    
    @retry_on_failure(max_retries=2, delay=1.0)
    def _search_creditjob(self, company_name: str) -> Dict[str, Any]:
        """크레딧잡에서 기업 정보 검색"""
        info = {}
        
        try:
            # 크레딧잡 검색
            search_url = f"https://www.creditjob.co.kr/search?q={company_name}"
            response = self.session.get(search_url, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 검색 결과에서 정보 추출
                company_card = soup.select_one('.company-card, .search-result-item')
                
                if company_card:
                    # 산업 분야
                    industry_elem = company_card.select_one('.industry, .sector')
                    if industry_elem:
                        info['industry'] = clean_text(industry_elem.text)
                    
                    # 기업 규모
                    size_elem = company_card.select_one('.company-size, .employee')
                    if size_elem:
                        info['company_size'] = clean_text(size_elem.text)
                    
                    # 설립년도
                    founded_elem = company_card.select_one('.founded, .establish')
                    if founded_elem:
                        year_match = re.search(r'\d{4}', clean_text(founded_elem.text))
                        if year_match:
                            info['founded_year'] = int(year_match.group())
                            
        except Exception as e:
            self.logger.debug(f"Creditjob search failed: {e}")
        
        return info
    
    def _get_reputation(self, company_name: str) -> Dict[str, Any]:
        """기업 평판 조회"""
        reputation = {
            'jobplanet_rating': None,
            'jobplanet_summary': None,
            'glassdoor_rating': None,
            'blind_summary': None,
            'overall_sentiment': 'neutral',
        }
        
        try:
            # 잡플래닛 평점 조회
            jobplanet_data = self._get_jobplanet_rating(company_name)
            reputation.update(jobplanet_data)
            
        except Exception as e:
            self.logger.warning(f"Error getting reputation: {e}")
        
        return reputation
    
    @retry_on_failure(max_retries=2, delay=1.0)
    def _get_jobplanet_rating(self, company_name: str) -> Dict[str, Any]:
        """잡플래닛 평점 조회"""
        result = {}
        
        try:
            self.rate_limiter.wait()
            
            # 잡플래닛 검색
            search_url = f"https://www.jobplanet.co.kr/search?query={company_name}"
            response = self.session.get(search_url, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 평점 추출
                rating_elem = soup.select_one('.rating_score, .rate_point, .score')
                if rating_elem:
                    rating_text = clean_text(rating_elem.text)
                    rating_match = re.search(r'[\d.]+', rating_text)
                    if rating_match:
                        result['jobplanet_rating'] = float(rating_match.group())
                
                # 리뷰 요약 추출
                summary_elem = soup.select_one('.review_summary, .summary_text')
                if summary_elem:
                    result['jobplanet_summary'] = clean_text(summary_elem.text)[:500]
                    
        except Exception as e:
            self.logger.debug(f"Jobplanet search failed: {e}")
        
        return result
    
    def _get_news(self, company_name: str, max_news: int = 10) -> List[Dict[str, Any]]:
        """최근 뉴스 수집"""
        news_list = []
        
        try:
            self.rate_limiter.wait()
            
            # 네이버 뉴스 검색
            search_url = "https://search.naver.com/search.naver"
            params = {
                'where': 'news',
                'query': company_name,
                'sort': 1,  # 최신순
            }
            
            response = self.session.get(search_url, params=params, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 뉴스 기사 추출
                news_items = soup.select('.news_wrap, .news_area, .bx')[:max_news]
                
                for item in news_items:
                    try:
                        title_elem = item.select_one('.news_tit, .title, a.link')
                        source_elem = item.select_one('.info_group a, .source, .press')
                        date_elem = item.select_one('.info_group span, .date, .time')
                        
                        if title_elem:
                            news_data = {
                                'title': clean_text(title_elem.text),
                                'url': title_elem.get('href', ''),
                                'source': clean_text(source_elem.text) if source_elem else '',
                                'date': clean_text(date_elem.text) if date_elem else '',
                            }
                            news_list.append(news_data)
                            
                    except Exception as e:
                        self.logger.debug(f"Error parsing news item: {e}")
                        
        except Exception as e:
            self.logger.warning(f"Error getting news: {e}")
        
        return news_list
    
    def _generate_summary(self, analysis: Dict[str, Any]) -> Dict[str, str]:
        """분석 결과 요약 생성"""
        company_name = analysis.get('company_name', '')
        basic_info = analysis.get('basic_info', {})
        reputation = analysis.get('reputation', {})
        news = analysis.get('news', [])
        
        # 기본 정보 요약
        info_parts = []
        if basic_info.get('industry'):
            info_parts.append(f"산업: {basic_info['industry']}")
        if basic_info.get('company_size'):
            info_parts.append(f"규모: {basic_info['company_size']}")
        if basic_info.get('founded_year'):
            info_parts.append(f"설립: {basic_info['founded_year']}년")
        
        basic_summary = ', '.join(info_parts) if info_parts else "기본 정보를 찾을 수 없습니다."
        
        # 평판 요약
        reputation_parts = []
        if reputation.get('jobplanet_rating'):
            reputation_parts.append(f"잡플래닛 평점: {reputation['jobplanet_rating']}/5.0")
        if reputation.get('jobplanet_summary'):
            reputation_parts.append(reputation['jobplanet_summary'][:200])
        
        reputation_summary = ' | '.join(reputation_parts) if reputation_parts else "평판 정보를 찾을 수 없습니다."
        
        # 뉴스 요약
        news_summary = ""
        if news:
            news_titles = [n['title'] for n in news[:5]]
            news_summary = f"최근 뉴스 {len(news)}건: " + ' / '.join(news_titles[:3])
        else:
            news_summary = "최근 뉴스를 찾을 수 없습니다."
        
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
        
        return {
            'basic': basic_summary,
            'reputation': reputation_summary,
            'news': news_summary,
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
                'company_size': basic_info.get('company_size'),
                'founded_year': basic_info.get('founded_year'),
                'address': basic_info.get('address'),
                'website': basic_info.get('website'),
                'business_number': basic_info.get('business_number'),
                'jobplanet_rating': reputation.get('jobplanet_rating'),
                'public_sentiment': summary.get('overall'),
                'news_summary': summary.get('news'),
            }
            
            db.add_company(company_data)
            
        except Exception as e:
            self.logger.error(f"Error saving to DB: {e}")
    
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
    
    def close(self):
        """세션 종료"""
        self.session.close()


# 테스트용
if __name__ == "__main__":
    analyzer = CompanyAnalyzer()
    
    result = analyzer.analyze_company("카카오")
    print(f"\n회사: {result['company_name']}")
    print(f"요약: {result.get('summary', {})}")
    
    analyzer.close()
