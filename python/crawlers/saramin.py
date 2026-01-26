"""
사람인 (Saramin) 크롤러
HTML 파싱 기반
"""
import re
from typing import List, Optional
from urllib.parse import urlencode, quote
from bs4 import BeautifulSoup

from .base import BaseCrawler, JobPosting


class SaraminCrawler(BaseCrawler):
    """사람인 크롤러"""
    
    BASE_URL = "https://www.saramin.co.kr"
    SEARCH_URL = f"{BASE_URL}/zf_user/search/recruit"
    
    def __init__(self):
        super().__init__("saramin")
    
    def search(self, keyword: str, max_pages: int = None) -> List[JobPosting]:
        """키워드로 채용 공고 검색"""
        max_pages = max_pages or self.config.max_pages
        jobs = []
        
        for page in range(1, max_pages + 1):
            params = {
                "searchType": "search",
                "searchword": keyword,
                "recruitPage": page,
                "recruitSort": "relation",
                "recruitPageCount": 40,
            }
            
            url = f"{self.SEARCH_URL}?{urlencode(params)}"
            html = self._get_page(url)
            
            if not html:
                break
            
            soup = BeautifulSoup(html, "html.parser")
            job_items = soup.select(".item_recruit")
            
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
            title_elem = item.select_one(".job_tit a")
            if not title_elem:
                return None
            
            title = title_elem.get_text(strip=True)
            href = title_elem.get("href", "")
            job_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href
            
            # 회사명
            company_elem = item.select_one(".corp_name a")
            company = company_elem.get_text(strip=True) if company_elem else ""
            
            # 조건 정보
            conditions = item.select(".job_condition span")
            location = ""
            experience = ""
            education = ""
            employment_type = ""
            
            for i, cond in enumerate(conditions):
                text = cond.get_text(strip=True)
                if i == 0:
                    location = text
                elif i == 1:
                    experience = text
                elif i == 2:
                    education = text
                elif i == 3:
                    employment_type = text
            
            # 경력 파싱
            exp_min, exp_max = self._parse_experience(experience)
            
            # 직무 섹터
            sector_elem = item.select_one(".job_sector")
            sector_text = sector_elem.get_text(" ", strip=True) if sector_elem else ""
            
            # 스킬 추출
            skills = self._extract_skills(f"{title} {sector_text}")
            
            # 마감일
            deadline_elem = item.select_one(".job_date .date")
            deadline = deadline_elem.get_text(strip=True) if deadline_elem else ""
            
            return JobPosting(
                title=title,
                company=company,
                url=job_url,
                source=self.site_name,
                location=location,
                experience_min=exp_min,
                experience_max=exp_max,
                education=education,
                employment_type=employment_type,
                required_skills=skills,
                deadline=deadline,
            )
        except Exception as e:
            self.logger.error(f"아이템 파싱 실패: {e}")
            return None
    
    def get_job_detail(self, job_url: str) -> Optional[JobPosting]:
        """채용 공고 상세 정보"""
        html = self._get_page(job_url)
        
        if not html:
            return None
        
        soup = BeautifulSoup(html, "html.parser")
        
        try:
            # 제목
            title_elem = soup.select_one(".job_tit")
            title = title_elem.get_text(strip=True) if title_elem else ""
            
            # 회사명
            company_elem = soup.select_one(".company_name")
            company = company_elem.get_text(strip=True) if company_elem else ""
            
            # 상세 정보 섹션
            description = ""
            requirements = ""
            benefits = ""
            
            detail_sections = soup.select(".jv_cont")
            for section in detail_sections:
                header = section.select_one(".jv_header")
                if not header:
                    continue
                
                header_text = header.get_text(strip=True)
                content = section.select_one(".jv_detail")
                content_text = content.get_text("\n", strip=True) if content else ""
                
                if "주요업무" in header_text or "담당업무" in header_text:
                    description = content_text
                elif "자격요건" in header_text:
                    requirements = content_text
                elif "우대사항" in header_text:
                    requirements += f"\n\n[우대사항]\n{content_text}"
                elif "혜택" in header_text or "복리후생" in header_text:
                    benefits = content_text
            
            # 조건 정보
            condition_items = soup.select(".jv_summary dt, .jv_summary dd")
            conditions = {}
            current_key = ""
            for item in condition_items:
                if item.name == "dt":
                    current_key = item.get_text(strip=True)
                elif item.name == "dd" and current_key:
                    conditions[current_key] = item.get_text(strip=True)
            
            location = conditions.get("근무지역", "")
            experience_text = conditions.get("경력", "")
            education = conditions.get("학력", "")
            employment_type = conditions.get("고용형태", "")
            
            exp_min, exp_max = self._parse_experience(experience_text)
            
            # 스킬 추출
            all_text = f"{title} {description} {requirements}"
            skills = self._extract_skills(all_text)
            
            return JobPosting(
                title=title,
                company=company,
                url=job_url,
                source=self.site_name,
                location=location,
                experience_min=exp_min,
                experience_max=exp_max,
                education=education,
                employment_type=employment_type,
                required_skills=skills,
                description=description,
                requirements=requirements,
                benefits=benefits,
            )
        except Exception as e:
            self.logger.error(f"상세 페이지 파싱 실패: {e}")
            return None
    
    def _parse_experience(self, text: str) -> tuple:
        """경력 요구사항 파싱"""
        if not text:
            return 0, 0
        
        if "신입" in text and "경력" not in text:
            return 0, 0
        
        if "신입·경력" in text or "경력무관" in text:
            return 0, 99
        
        # "경력 N년↑" 패턴
        match = re.search(r'경력\s*(\d+)년', text)
        if match:
            min_exp = int(match.group(1))
            return min_exp, 99
        
        # "N~M년" 패턴
        match = re.search(r'(\d+)\s*[~-]\s*(\d+)\s*년', text)
        if match:
            return int(match.group(1)), int(match.group(2))
        
        return 0, 0
