"""
프로그래머스 (Programmers) 크롤러
https://career.programmers.co.kr
"""

from typing import Generator, Dict, Any, Optional
import re
from datetime import datetime
from .base_crawler import BaseCrawler
from utils.helpers import clean_text


class ProgrammersCrawler(BaseCrawler):
    """프로그래머스 채용공고 크롤러"""
    
    def __init__(self):
        super().__init__()
        self.site_name = "programmers"
        self.base_url = "https://career.programmers.co.kr"
        self.api_url = "https://career.programmers.co.kr/api"
        
        # 프로그래머스 특화 헤더
        self.session.headers.update({
            'Referer': 'https://career.programmers.co.kr/',
            'Accept': 'application/json',
        })
    
    def search_jobs(self, keyword: str, max_pages: int = 10) -> Generator[Dict[str, Any], None, None]:
        """
        프로그래머스 API를 통한 채용공고 검색
        """
        total_count = 0
        
        for page in range(1, max_pages + 1):
            try:
                # 프로그래머스 검색 API
                search_url = f"{self.api_url}/job_positions"
                params = {
                    'page': page,
                    'per_page': 20,
                    'query': keyword,
                    'order': 'recent',
                }
                
                data = self.get_json(search_url, params)
                
                if not data or 'jobPositions' not in data:
                    # HTML 파싱 fallback
                    yield from self._search_jobs_html(keyword, page)
                    continue
                
                jobs = data.get('jobPositions', [])
                
                if not jobs:
                    break
                
                for job in jobs:
                    job_data = self._parse_job_listing(job)
                    if job_data:
                        yield job_data
                        total_count += 1
                
                # 다음 페이지 확인
                if len(jobs) < 20:
                    break
                    
            except Exception as e:
                self.logger.error(f"Error searching page {page}: {e}")
                # HTML 파싱 fallback
                yield from self._search_jobs_html(keyword, page)
        
        self.logger.info(f"Found {total_count} jobs for keyword: {keyword}")
    
    def _search_jobs_html(self, keyword: str, page: int) -> Generator[Dict[str, Any], None, None]:
        """HTML 파싱 방식 검색 (fallback)"""
        try:
            search_url = f"{self.base_url}/job_positions"
            params = {
                'page': page,
                'query': keyword,
            }
            
            soup = self.get_page(search_url, params)
            
            if not soup:
                return
            
            job_list = soup.select('.job-position-item, .list-position-item')
            
            for job_elem in job_list:
                job_data = self._parse_job_listing_html(job_elem)
                if job_data:
                    yield job_data
                    
        except Exception as e:
            self.logger.error(f"Error in HTML search: {e}")
    
    def _parse_job_listing(self, job: Dict) -> Optional[Dict[str, Any]]:
        """API 응답에서 채용공고 정보 파싱"""
        try:
            job_id = str(job.get('id', ''))
            
            # 기술 스택
            tech_stacks = []
            if 'technicalTags' in job:
                tech_stacks = [tag.get('name', '') for tag in job.get('technicalTags', [])]
            
            return {
                'source_site': self.site_name,
                'job_id': job_id,
                'title': job.get('title', ''),
                'company_name': job.get('company', {}).get('name', ''),
                'company_id_external': job.get('company', {}).get('id'),
                'job_category': job.get('jobCategory', {}).get('name', ''),
                'position_level': self._parse_career_level(job),
                'location': job.get('address', ''),
                'employment_type': job.get('employmentType', {}).get('name', '정규직'),
                'required_skills': tech_stacks,
                'url': f"{self.base_url}/job_positions/{job_id}",
                'crawled_at': datetime.now(),
                'min_career': job.get('minCareer'),
                'max_career': job.get('maxCareer'),
            }
        except Exception as e:
            self.logger.error(f"Error parsing job listing: {e}")
            return None
    
    def _parse_job_listing_html(self, elem) -> Optional[Dict[str, Any]]:
        """HTML 요소에서 채용공고 정보 파싱"""
        try:
            # 링크 및 ID 추출
            link_elem = elem.select_one('a')
            if not link_elem:
                return None
            
            href = link_elem.get('href', '')
            job_id_match = re.search(r'/job_positions/(\d+)', href)
            job_id = job_id_match.group(1) if job_id_match else ""
            
            if not job_id:
                return None
            
            # 제목
            title_elem = elem.select_one('.position-title, .job-title')
            title = clean_text(title_elem.text) if title_elem else ""
            
            # 회사명
            company_elem = elem.select_one('.company-name, .company')
            company_name = clean_text(company_elem.text) if company_elem else ""
            
            # 기술 스택
            tech_elems = elem.select('.tag, .skill-tag, .tech-tag')
            tech_stacks = [clean_text(t.text) for t in tech_elems]
            
            return {
                'source_site': self.site_name,
                'job_id': job_id,
                'title': title,
                'company_name': company_name,
                'required_skills': tech_stacks,
                'url': f"{self.base_url}/job_positions/{job_id}",
                'crawled_at': datetime.now(),
            }
        except Exception as e:
            self.logger.error(f"Error parsing HTML job listing: {e}")
            return None
    
    def _parse_career_level(self, job: Dict) -> str:
        """경력 수준 파싱"""
        min_career = job.get('minCareer', 0)
        max_career = job.get('maxCareer', 0)
        
        if min_career == 0 and max_career == 0:
            return "경력무관"
        elif min_career == 0:
            return "신입"
        elif max_career == 0 or max_career is None:
            return f"경력 {min_career}년 이상"
        else:
            return f"경력 {min_career}~{max_career}년"
    
    def get_job_detail(self, job_id: str) -> Optional[Dict[str, Any]]:
        """채용공고 상세 정보 가져오기"""
        try:
            # API 시도
            detail_url = f"{self.api_url}/job_positions/{job_id}"
            data = self.get_json(detail_url)
            
            if data and 'jobPosition' in data:
                job = data['jobPosition']
                
                return {
                    'description': clean_text(job.get('description', '')),
                    'requirements': clean_text(job.get('requirement', '')),
                    'preferred': clean_text(job.get('preferredExperience', '')),
                    'required_skills': [t.get('name', '') for t in job.get('technicalTags', [])],
                    'salary_info': self._format_salary(job),
                    'benefits': clean_text(job.get('welfare', '')),
                }
            
            # HTML 파싱 fallback
            return self._get_job_detail_html(job_id)
            
        except Exception as e:
            self.logger.error(f"Error getting job detail for {job_id}: {e}")
            return self._get_job_detail_html(job_id)
    
    def _get_job_detail_html(self, job_id: str) -> Optional[Dict[str, Any]]:
        """HTML 파싱으로 상세 정보 가져오기"""
        try:
            detail_url = f"{self.base_url}/job_positions/{job_id}"
            soup = self.get_page(detail_url)
            
            if not soup:
                return None
            
            description = ""
            requirements = ""
            preferred = ""
            
            # 섹션별 파싱
            sections = soup.select('.job-content-section, .section')
            for section in sections:
                header = section.select_one('h3, .section-title')
                content = section.select_one('.content, .section-content')
                
                if header and content:
                    header_text = clean_text(header.text).lower()
                    content_text = clean_text(content.get_text())
                    
                    if any(word in header_text for word in ['소개', '담당', '업무']):
                        description = content_text
                    elif any(word in header_text for word in ['자격', '필수']):
                        requirements = content_text
                    elif any(word in header_text for word in ['우대']):
                        preferred = content_text
            
            # 기술 스택
            tech_elems = soup.select('.tech-stack-tag, .skill-tag')
            tech_stacks = [clean_text(t.text) for t in tech_elems]
            
            return {
                'description': description,
                'requirements': requirements,
                'preferred': preferred,
                'required_skills': tech_stacks,
            }
            
        except Exception as e:
            self.logger.error(f"Error in HTML detail parsing: {e}")
            return None
    
    def _format_salary(self, job: Dict) -> str:
        """급여 정보 포맷팅"""
        min_salary = job.get('minSalary')
        max_salary = job.get('maxSalary')
        
        if min_salary and max_salary:
            return f"{min_salary:,}~{max_salary:,}만원"
        elif min_salary:
            return f"{min_salary:,}만원 이상"
        else:
            return "회사내규에 따름"


# 테스트용
if __name__ == "__main__":
    crawler = ProgrammersCrawler()
    
    for job in crawler.search_jobs("백엔드", max_pages=1):
        print(f"[{job['company_name']}] {job['title']}")
        print(f"  Skills: {job.get('required_skills', [])}")
        print()
    
    crawler.close()
