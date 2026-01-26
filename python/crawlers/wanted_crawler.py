"""
원티드 (Wanted) 크롤러
https://www.wanted.co.kr
"""

from typing import Generator, Dict, Any, Optional
import re
from datetime import datetime
from .base_crawler import BaseCrawler
from utils.helpers import clean_text


class WantedCrawler(BaseCrawler):
    """원티드 채용공고 크롤러"""
    
    def __init__(self):
        super().__init__()
        self.site_name = "wanted"
        self.base_url = "https://www.wanted.co.kr"
        self.api_url = "https://www.wanted.co.kr/api/v4"
        
        # 추가 헤더
        self.session.headers.update({
            'Referer': 'https://www.wanted.co.kr/',
            'wanted-user-country': 'KR',
            'wanted-user-language': 'ko',
        })
    
    def search_jobs(self, keyword: str, max_pages: int = 10) -> Generator[Dict[str, Any], None, None]:
        """
        원티드 API를 통한 채용공고 검색
        
        원티드는 무한 스크롤 방식이므로 offset 사용
        """
        offset = 0
        limit = 20  # 원티드 기본 limit
        total_count = 0
        
        while offset < max_pages * limit:
            try:
                # 원티드 검색 API
                url = f"{self.api_url}/jobs"
                params = {
                    'country': 'kr',
                    'job_sort': 'job.latest_order',
                    'locations': 'all',
                    'years': -1,
                    'limit': limit,
                    'offset': offset,
                    'search': keyword
                }
                
                data = self.get_json(url, params)
                
                if not data or 'data' not in data:
                    break
                
                jobs = data.get('data', [])
                
                if not jobs:
                    break
                
                for job in jobs:
                    job_data = self._parse_job_listing(job)
                    if job_data:
                        yield job_data
                        total_count += 1
                
                offset += limit
                
                # 다음 페이지가 없으면 종료
                if len(jobs) < limit:
                    break
                    
            except Exception as e:
                self.logger.error(f"Error searching jobs: {e}")
                break
        
        self.logger.info(f"Found {total_count} jobs for keyword: {keyword}")
    
    def _parse_job_listing(self, job: Dict) -> Optional[Dict[str, Any]]:
        """API 응답에서 채용공고 정보 파싱"""
        try:
            job_id = str(job.get('id', ''))
            
            return {
                'source_site': self.site_name,
                'job_id': job_id,
                'title': job.get('position', ''),
                'company_name': job.get('company', {}).get('name', ''),
                'company_id_external': job.get('company', {}).get('id'),
                'job_category': job.get('category', {}).get('name', ''),
                'position_level': self._parse_experience_level(job),
                'location': job.get('address', {}).get('full_location', ''),
                'url': f"{self.base_url}/wd/{job_id}",
                'crawled_at': datetime.now(),
                'logo_url': job.get('company', {}).get('logo_img', {}).get('origin', ''),
            }
        except Exception as e:
            self.logger.error(f"Error parsing job listing: {e}")
            return None
    
    def _parse_experience_level(self, job: Dict) -> str:
        """경력 수준 파싱"""
        years = job.get('years', {})
        if isinstance(years, dict):
            min_years = years.get('min', 0)
            max_years = years.get('max', 0)
            
            if min_years == 0 and max_years == 0:
                return "경력무관"
            elif min_years == 0:
                return "신입"
            else:
                return f"경력 {min_years}~{max_years}년"
        return "경력무관"
    
    def get_job_detail(self, job_id: str) -> Optional[Dict[str, Any]]:
        """채용공고 상세 정보 가져오기"""
        try:
            url = f"{self.api_url}/jobs/{job_id}"
            data = self.get_json(url)
            
            if not data or 'job' not in data:
                return None
            
            job = data['job']
            
            return {
                'description': clean_text(job.get('detail', {}).get('intro', '')),
                'requirements': clean_text(job.get('detail', {}).get('requirements', '')),
                'preferred': clean_text(job.get('detail', {}).get('preferred', '')),
                'benefits': clean_text(job.get('detail', {}).get('benefits', '')),
                'required_skills': job.get('skill_tags', []),
                'salary_info': self._parse_salary(job),
                'employment_type': self._parse_employment_type(job),
                'deadline': job.get('due_time'),
            }
        except Exception as e:
            self.logger.error(f"Error getting job detail for {job_id}: {e}")
            return None
    
    def _parse_salary(self, job: Dict) -> str:
        """급여 정보 파싱"""
        reward = job.get('reward', {})
        if reward:
            formatted = reward.get('formatted_total', '')
            if formatted:
                return f"추천보상금: {formatted}"
        return "회사내규에 따름"
    
    def _parse_employment_type(self, job: Dict) -> str:
        """고용 형태 파싱"""
        # 원티드는 대부분 정규직
        return "정규직"


# 테스트용
if __name__ == "__main__":
    crawler = WantedCrawler()
    
    for job in crawler.search_jobs("데이터 분석가", max_pages=2):
        print(f"[{job['company_name']}] {job['title']}")
        detail = crawler.get_job_detail(job['job_id'])
        if detail:
            print(f"  Skills: {detail.get('required_skills', [])}")
        print()
    
    crawler.close()
