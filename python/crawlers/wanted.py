"""
원티드 (Wanted) 크롤러
API 기반 크롤링
"""
import re
from typing import List, Optional, Dict
from bs4 import BeautifulSoup

from .base import BaseCrawler, JobPosting


class WantedCrawler(BaseCrawler):
    """원티드 크롤러"""
    
    BASE_URL = "https://www.wanted.co.kr"
    API_URL = "https://www.wanted.co.kr/api/v4"
    
    # 직군 코드 매핑
    JOB_CODES = {
        "개발": 518,
        "웹개발": 873,
        "서버": 872,
        "프론트엔드": 669,
        "자바": 660,
        "파이썬": 899,
        "데이터": 655,
        "머신러닝": 1634,
        "DevOps": 674,
    }
    
    def __init__(self):
        super().__init__("wanted")
    
    def search(self, keyword: str, max_pages: int = None) -> List[JobPosting]:
        """키워드로 채용 공고 검색"""
        max_pages = max_pages or self.config.max_pages
        jobs = []
        offset = 0
        limit = 20
        
        for page in range(max_pages):
            url = f"{self.API_URL}/jobs"
            params = {
                "country": "kr",
                "tag_type_ids": "518",  # 개발 전체
                "locations": "all",
                "years": "-1",
                "limit": limit,
                "offset": offset,
                "job_sort": "job.latest_order"
            }
            
            # 키워드 검색 파라미터
            if keyword:
                params["search"] = keyword
            
            data = self._get_json(url, params=params)
            
            if not data or "data" not in data:
                break
            
            job_list = data.get("data", [])
            if not job_list:
                break
            
            for item in job_list:
                job = self._parse_list_item(item)
                if job:
                    jobs.append(job)
            
            offset += limit
            self.logger.debug(f"페이지 {page + 1} 완료: {len(job_list)}개")
        
        # 상세 정보 가져오기 (선택적)
        detailed_jobs = []
        for job in jobs[:50]:  # 최대 50개만 상세 정보
            detailed = self.get_job_detail(job.url.split("/")[-1])
            if detailed:
                detailed_jobs.append(detailed)
            else:
                detailed_jobs.append(job)
        
        return detailed_jobs if detailed_jobs else jobs
    
    def _parse_list_item(self, item: Dict) -> Optional[JobPosting]:
        """목록 아이템 파싱"""
        try:
            job_id = item.get("id")
            company_info = item.get("company", {})
            
            return JobPosting(
                title=item.get("position", ""),
                company=company_info.get("name", ""),
                url=f"{self.BASE_URL}/wd/{job_id}",
                source=self.site_name,
                location=item.get("address", {}).get("full_location", ""),
                industry=company_info.get("industry_name", ""),
            )
        except Exception as e:
            self.logger.error(f"아이템 파싱 실패: {e}")
            return None
    
    def get_job_detail(self, job_id: str) -> Optional[JobPosting]:
        """채용 공고 상세 정보"""
        url = f"{self.API_URL}/jobs/{job_id}"
        data = self._get_json(url)
        
        if not data or "job" not in data:
            return None
        
        job_data = data["job"]
        company_data = job_data.get("company", {})
        
        # 스킬 태그 추출
        skill_tags = job_data.get("skill_tags", [])
        skills = [tag.get("title", "") for tag in skill_tags if tag.get("title")]
        
        # 상세 설명에서 추가 스킬 추출
        description = job_data.get("detail", {}).get("main_tasks", "")
        requirements = job_data.get("detail", {}).get("requirements", "")
        preferred = job_data.get("detail", {}).get("preferred_points", "")
        benefits = job_data.get("detail", {}).get("benefits", "")
        
        all_text = f"{description} {requirements} {preferred}"
        extracted_skills = self._extract_skills(all_text)
        
        # 경력 파싱
        exp_min, exp_max = self._parse_experience(
            job_data.get("detail", {}).get("position", "")
        )
        
        return JobPosting(
            title=job_data.get("position", ""),
            company=company_data.get("name", ""),
            url=f"{self.BASE_URL}/wd/{job_id}",
            source=self.site_name,
            location=job_data.get("address", {}).get("full_location", ""),
            experience_min=exp_min,
            experience_max=exp_max,
            required_skills=skills,
            preferred_skills=extracted_skills,
            description=description,
            requirements=requirements,
            benefits=benefits,
            company_info=company_data.get("industry_name", ""),
            industry=company_data.get("industry_name", ""),
            posted_date=job_data.get("due_time", ""),
        )
    
    def _parse_experience(self, text: str) -> tuple:
        """경력 요구사항 파싱"""
        if not text:
            return 0, 0
        
        # "신입" 체크
        if "신입" in text:
            return 0, 0
        
        # "N년 이상" 패턴
        match = re.search(r'(\d+)\s*년\s*이상', text)
        if match:
            min_exp = int(match.group(1))
            return min_exp, 99
        
        # "N~M년" 패턴
        match = re.search(r'(\d+)\s*[~-]\s*(\d+)\s*년', text)
        if match:
            return int(match.group(1)), int(match.group(2))
        
        return 0, 0
