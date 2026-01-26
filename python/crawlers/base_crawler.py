"""
베이스 크롤러 클래스
모든 사이트별 크롤러의 부모 클래스
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Generator
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings
from utils.helpers import (
    setup_logger, retry_on_failure, clean_text, 
    extract_skills_from_text, RateLimiter
)


class BaseCrawler(ABC):
    """크롤러 베이스 클래스"""
    
    def __init__(self):
        self.site_name = "base"
        self.base_url = ""
        self.logger = setup_logger(f"crawler.{self.site_name}")
        self.rate_limiter = RateLimiter(1.0 / settings.crawler.request_delay)
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': settings.crawler.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        })
    
    @retry_on_failure(max_retries=3, delay=2.0)
    def get_page(self, url: str, params: Optional[Dict] = None) -> Optional[BeautifulSoup]:
        """페이지 가져오기"""
        self.rate_limiter.wait()
        
        try:
            response = self.session.get(
                url, 
                params=params,
                timeout=settings.crawler.timeout
            )
            response.raise_for_status()
            return BeautifulSoup(response.text, 'html.parser')
        except requests.RequestException as e:
            self.logger.error(f"Error fetching {url}: {e}")
            raise
    
    @retry_on_failure(max_retries=3, delay=2.0)
    def get_json(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """JSON API 호출"""
        self.rate_limiter.wait()
        
        try:
            response = self.session.get(
                url,
                params=params,
                timeout=settings.crawler.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            self.logger.error(f"Error fetching JSON from {url}: {e}")
            raise
    
    @abstractmethod
    def search_jobs(self, keyword: str, max_pages: int = 10) -> Generator[Dict[str, Any], None, None]:
        """
        키워드로 채용공고 검색
        
        Args:
            keyword: 검색 키워드
            max_pages: 최대 페이지 수
            
        Yields:
            채용공고 정보 딕셔너리
        """
        pass
    
    @abstractmethod
    def get_job_detail(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        채용공고 상세 정보 가져오기
        
        Args:
            job_id: 채용공고 ID
            
        Returns:
            상세 정보 딕셔너리
        """
        pass
    
    def crawl_keyword(self, keyword: str) -> List[Dict[str, Any]]:
        """
        특정 키워드에 대한 전체 크롤링 실행
        
        Args:
            keyword: 검색 키워드
            
        Returns:
            채용공고 리스트
        """
        self.logger.info(f"Starting crawl for keyword: {keyword}")
        
        jobs = []
        max_pages = settings.crawler.max_pages_per_keyword
        
        try:
            for job_summary in self.search_jobs(keyword, max_pages):
                try:
                    # 상세 정보 가져오기
                    job_detail = self.get_job_detail(job_summary.get('job_id'))
                    
                    if job_detail:
                        # 요약 정보와 상세 정보 병합
                        job_data = {**job_summary, **job_detail}
                        
                        # 스킬 추출
                        full_text = f"{job_data.get('description', '')} {job_data.get('requirements', '')} {job_data.get('preferred', '')}"
                        skills = extract_skills_from_text(full_text)
                        job_data['extracted_hard_skills'] = skills['hard_skills']
                        job_data['extracted_soft_skills'] = skills['soft_skills']
                        
                        jobs.append(job_data)
                        self.logger.debug(f"Crawled job: {job_data.get('title')}")
                    else:
                        jobs.append(job_summary)
                        
                except Exception as e:
                    self.logger.error(f"Error getting job detail: {e}")
                    jobs.append(job_summary)
                    
        except Exception as e:
            self.logger.error(f"Error during crawl: {e}")
        
        self.logger.info(f"Finished crawling {keyword}: {len(jobs)} jobs found")
        return jobs
    
    def close(self):
        """세션 종료"""
        self.session.close()
