"""
잡코리아, 점핏, 프로그래머스 크롤러
"""
import re
from typing import List, Optional, Dict
from urllib.parse import urlencode
from bs4 import BeautifulSoup

from .base import BaseCrawler, JobPosting


class JobKoreaCrawler(BaseCrawler):
    """잡코리아 크롤러"""
    
    BASE_URL = "https://www.jobkorea.co.kr"
    SEARCH_URL = f"{BASE_URL}/Search"
    
    def __init__(self):
        super().__init__("jobkorea")
    
    def search(self, keyword: str, max_pages: int = None) -> List[JobPosting]:
        """키워드로 채용 공고 검색"""
        max_pages = max_pages or self.config.max_pages
        jobs = []
        
        for page in range(1, max_pages + 1):
            params = {
                "stext": keyword,
                "tabType": "recruit",
                "Page_No": page,
            }
            
            url = f"{self.SEARCH_URL}?{urlencode(params)}"
            html = self._get_page(url)
            
            if not html:
                break
            
            soup = BeautifulSoup(html, "html.parser")
            job_items = soup.select(".list-post")
            
            if not job_items:
                # 대체 선택자 시도
                job_items = soup.select(".recruit-info")
            
            if not job_items:
                break
            
            for item in job_items:
                job = self._parse_list_item(item)
                if job:
                    jobs.append(job)
            
            self.logger.debug(f"페이지 {page} 완료: {len(job_items)}개")
        
        return jobs
    
    def _parse_list_item(self, item) -> Optional[JobPosting]:
        """목록 아이템 파싱"""
        try:
            # 제목 및 URL
            title_elem = item.select_one(".post-list-info a, .title a")
            if not title_elem:
                return None
            
            title = title_elem.get_text(strip=True)
            href = title_elem.get("href", "")
            job_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href
            
            # 회사명
            company_elem = item.select_one(".post-list-corp a, .name a")
            company = company_elem.get_text(strip=True) if company_elem else ""
            
            # 조건 정보
            option_elem = item.select_one(".post-list-info .option, .etc")
            conditions = []
            if option_elem:
                conditions = [span.get_text(strip=True) 
                            for span in option_elem.select("span")]
            
            location = conditions[0] if len(conditions) > 0 else ""
            experience = conditions[1] if len(conditions) > 1 else ""
            education = conditions[2] if len(conditions) > 2 else ""
            
            exp_min, exp_max = self._parse_experience(experience)
            
            # 스킬 추출
            skills = self._extract_skills(title)
            
            return JobPosting(
                title=title,
                company=company,
                url=job_url,
                source=self.site_name,
                location=location,
                experience_min=exp_min,
                experience_max=exp_max,
                education=education,
                required_skills=skills,
            )
        except Exception as e:
            self.logger.error(f"아이템 파싱 실패: {e}")
            return None
    
    def get_job_detail(self, job_url: str) -> Optional[JobPosting]:
        """상세 정보 가져오기"""
        # 간단 구현 - 필요시 확장
        return None
    
    def _parse_experience(self, text: str) -> tuple:
        if not text:
            return 0, 0
        if "신입" in text:
            return 0, 0
        match = re.search(r'(\d+)\s*년', text)
        if match:
            return int(match.group(1)), 99
        return 0, 0


class JumpitCrawler(BaseCrawler):
    """점핏 크롤러"""
    
    BASE_URL = "https://www.jumpit.co.kr"
    API_URL = "https://api.jumpit.co.kr/api"
    
    def __init__(self):
        super().__init__("jumpit")
    
    def search(self, keyword: str, max_pages: int = None) -> List[JobPosting]:
        """키워드로 채용 공고 검색"""
        max_pages = max_pages or self.config.max_pages
        jobs = []
        
        for page in range(1, max_pages + 1):
            url = f"{self.API_URL}/positions"
            params = {
                "page": page,
                "sort": "rsp_rate",
                "keyword": keyword,
            }
            
            data = self._get_json(url, params=params)
            
            if not data or "result" not in data:
                break
            
            positions = data.get("result", {}).get("positions", [])
            
            if not positions:
                break
            
            for item in positions:
                job = self._parse_list_item(item)
                if job:
                    jobs.append(job)
            
            self.logger.debug(f"페이지 {page} 완료: {len(positions)}개")
        
        return jobs
    
    def _parse_list_item(self, item: Dict) -> Optional[JobPosting]:
        """목록 아이템 파싱"""
        try:
            job_id = item.get("id")
            company_info = item.get("company", {})
            
            # 기술 스택
            tech_stacks = item.get("techStacks", [])
            skills = [tech.get("stack", "") for tech in tech_stacks]
            
            # 경력
            min_career = item.get("minCareer", 0) or 0
            max_career = item.get("maxCareer", 0) or 99
            
            return JobPosting(
                title=item.get("title", ""),
                company=company_info.get("name", ""),
                url=f"{self.BASE_URL}/position/{job_id}",
                source=self.site_name,
                location=item.get("locations", [""])[0] if item.get("locations") else "",
                experience_min=min_career,
                experience_max=max_career,
                required_skills=skills,
                industry=company_info.get("industryName", ""),
            )
        except Exception as e:
            self.logger.error(f"아이템 파싱 실패: {e}")
            return None
    
    def get_job_detail(self, job_id: str) -> Optional[JobPosting]:
        """상세 정보 가져오기"""
        url = f"{self.API_URL}/position/{job_id}"
        data = self._get_json(url)
        
        if not data or "result" not in data:
            return None
        
        result = data["result"]
        company = result.get("company", {})
        
        # 기술 스택
        tech_stacks = result.get("techStacks", [])
        skills = [tech.get("stack", "") for tech in tech_stacks]
        
        # 우대 기술
        preferred_stacks = result.get("preferredTechStacks", [])
        preferred = [tech.get("stack", "") for tech in preferred_stacks]
        
        return JobPosting(
            title=result.get("title", ""),
            company=company.get("name", ""),
            url=f"{self.BASE_URL}/position/{job_id}",
            source=self.site_name,
            location=result.get("location", ""),
            experience_min=result.get("minCareer", 0) or 0,
            experience_max=result.get("maxCareer", 0) or 99,
            required_skills=skills,
            preferred_skills=preferred,
            description=result.get("responsibility", ""),
            requirements=result.get("qualification", ""),
            benefits=result.get("preferentialTreatment", ""),
            industry=company.get("industryName", ""),
        )


class ProgrammersCrawler(BaseCrawler):
    """프로그래머스 크롤러"""
    
    BASE_URL = "https://career.programmers.co.kr"
    API_URL = f"{BASE_URL}/api/job_positions"
    
    def __init__(self):
        super().__init__("programmers")
    
    def search(self, keyword: str, max_pages: int = None) -> List[JobPosting]:
        """키워드로 채용 공고 검색"""
        max_pages = max_pages or self.config.max_pages
        jobs = []
        
        for page in range(1, max_pages + 1):
            params = {
                "page": page,
                "query": keyword,
                "order": "recent",
            }
            
            data = self._get_json(self.API_URL, params=params)
            
            if not data or "jobPositions" not in data:
                break
            
            positions = data.get("jobPositions", [])
            
            if not positions:
                break
            
            for item in positions:
                job = self._parse_list_item(item)
                if job:
                    jobs.append(job)
            
            self.logger.debug(f"페이지 {page} 완료: {len(positions)}개")
        
        return jobs
    
    def _parse_list_item(self, item: Dict) -> Optional[JobPosting]:
        """목록 아이템 파싱"""
        try:
            job_id = item.get("id")
            company = item.get("company", {})
            
            # 기술 스택
            tech_stacks = item.get("technicalTags", [])
            skills = [tech.get("name", "") for tech in tech_stacks]
            
            # 경력
            min_career = item.get("minCareer")
            max_career = item.get("maxCareer")
            
            return JobPosting(
                title=item.get("title", ""),
                company=company.get("name", ""),
                url=f"{self.BASE_URL}/job_positions/{job_id}",
                source=self.site_name,
                location=item.get("address", ""),
                experience_min=min_career if min_career else 0,
                experience_max=max_career if max_career else 99,
                required_skills=skills,
                industry=company.get("industryName", ""),
            )
        except Exception as e:
            self.logger.error(f"아이템 파싱 실패: {e}")
            return None
    
    def get_job_detail(self, job_id: str) -> Optional[JobPosting]:
        """상세 정보 가져오기"""
        url = f"{self.API_URL}/{job_id}"
        data = self._get_json(url)
        
        if not data:
            return None
        
        company = data.get("company", {})
        
        tech_stacks = data.get("technicalTags", [])
        skills = [tech.get("name", "") for tech in tech_stacks]
        
        return JobPosting(
            title=data.get("title", ""),
            company=company.get("name", ""),
            url=f"{self.BASE_URL}/job_positions/{job_id}",
            source=self.site_name,
            location=data.get("address", ""),
            experience_min=data.get("minCareer") or 0,
            experience_max=data.get("maxCareer") or 99,
            required_skills=skills,
            description=data.get("description", ""),
            requirements=data.get("requirement", ""),
            benefits=data.get("preference", ""),
            industry=company.get("industryName", ""),
        )
