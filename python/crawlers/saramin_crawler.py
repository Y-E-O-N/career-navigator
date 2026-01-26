"""
사람인 (Saramin) 크롤러
https://www.saramin.co.kr
"""

from typing import Generator, Dict, Any, Optional
import re
from datetime import datetime
from urllib.parse import urlencode, quote
from .base_crawler import BaseCrawler
from utils.helpers import clean_text, parse_date_korean


class SaraminCrawler(BaseCrawler):
    """사람인 채용공고 크롤러"""
    
    def __init__(self):
        super().__init__()
        self.site_name = "saramin"
        self.base_url = "https://www.saramin.co.kr"
        
        # 사람인 특화 헤더
        self.session.headers.update({
            'Referer': 'https://www.saramin.co.kr/',
        })
    
    def search_jobs(self, keyword: str, max_pages: int = 10) -> Generator[Dict[str, Any], None, None]:
        """
        사람인 채용공고 검색
        HTML 파싱 방식
        """
        total_count = 0
        
        for page in range(1, max_pages + 1):
            try:
                # 사람인 검색 URL
                search_url = f"{self.base_url}/zf_user/search/recruit"
                params = {
                    'searchType': 'search',
                    'searchword': keyword,
                    'recruitPage': page,
                    'recruitSort': 'relation',
                    'recruitPageCount': 40,
                }
                
                soup = self.get_page(search_url, params)
                
                if not soup:
                    break
                
                # 채용공고 목록 찾기
                job_list = soup.select('.item_recruit')
                
                if not job_list:
                    # 다른 셀렉터 시도
                    job_list = soup.select('.list_item')
                
                if not job_list:
                    self.logger.warning(f"No jobs found on page {page}")
                    break
                
                for job_elem in job_list:
                    job_data = self._parse_job_listing(job_elem)
                    if job_data:
                        yield job_data
                        total_count += 1
                
                # 다음 페이지 확인
                if len(job_list) < 40:
                    break
                    
            except Exception as e:
                self.logger.error(f"Error searching page {page}: {e}")
                break
        
        self.logger.info(f"Found {total_count} jobs for keyword: {keyword}")
    
    def _parse_job_listing(self, elem) -> Optional[Dict[str, Any]]:
        """HTML 요소에서 채용공고 정보 파싱"""
        try:
            # 회사명
            company_elem = elem.select_one('.corp_name a, .company_name a')
            company_name = clean_text(company_elem.text) if company_elem else ""
            
            # 채용공고 제목 및 링크
            title_elem = elem.select_one('.job_tit a, .title a')
            if not title_elem:
                return None
            
            title = clean_text(title_elem.text)
            href = title_elem.get('href', '')
            
            # job_id 추출
            job_id_match = re.search(r'rec_idx=(\d+)', href)
            job_id = job_id_match.group(1) if job_id_match else ""
            
            if not job_id:
                # 다른 패턴 시도
                job_id_match = re.search(r'/(\d+)\?', href)
                job_id = job_id_match.group(1) if job_id_match else ""
            
            if not job_id:
                return None
            
            # 조건 정보
            conditions = elem.select('.job_condition span, .conditions span')
            location = ""
            experience = ""
            education = ""
            employment_type = ""
            
            for i, cond in enumerate(conditions):
                text = clean_text(cond.text)
                if i == 0:
                    location = text
                elif i == 1:
                    experience = text
                elif i == 2:
                    education = text
                elif i == 3:
                    employment_type = text
            
            # 마감일
            deadline_elem = elem.select_one('.job_date .date, .deadline')
            deadline = clean_text(deadline_elem.text) if deadline_elem else ""
            
            # 직무 분야
            sector_elem = elem.select_one('.job_sector, .sector')
            job_category = clean_text(sector_elem.text) if sector_elem else ""
            
            return {
                'source_site': self.site_name,
                'job_id': job_id,
                'title': title,
                'company_name': company_name,
                'job_category': job_category,
                'position_level': experience,
                'location': location,
                'employment_type': employment_type,
                'education': education,
                'deadline_text': deadline,
                'url': f"{self.base_url}/zf_user/jobs/relay/view?rec_idx={job_id}",
                'crawled_at': datetime.now(),
            }
        except Exception as e:
            self.logger.error(f"Error parsing job listing: {e}")
            return None
    
    def get_job_detail(self, job_id: str) -> Optional[Dict[str, Any]]:
        """채용공고 상세 정보 가져오기"""
        try:
            detail_url = f"{self.base_url}/zf_user/jobs/relay/view"
            params = {'rec_idx': job_id, 'view_type': 'search'}
            
            soup = self.get_page(detail_url, params)
            
            if not soup:
                return None
            
            # 상세 설명
            description = ""
            desc_elem = soup.select_one('.user_content, .job_content, .wrap_jv_cont')
            if desc_elem:
                description = clean_text(desc_elem.get_text())
            
            # 자격요건/우대사항 추출
            requirements = ""
            preferred = ""
            
            # 섹션별 파싱
            sections = soup.select('.jv_cont, .recruit_view_sec')
            for section in sections:
                header = section.select_one('h3, .tit_cont')
                if header:
                    header_text = clean_text(header.text).lower()
                    content = clean_text(section.get_text())
                    
                    if any(word in header_text for word in ['자격', '필수', '요건']):
                        requirements = content
                    elif any(word in header_text for word in ['우대', '선호']):
                        preferred = content
            
            # 스킬 태그
            skill_tags = []
            skill_elems = soup.select('.skill_tag, .tag_item, .chip_keyword')
            for skill_elem in skill_elems:
                skill = clean_text(skill_elem.text)
                if skill:
                    skill_tags.append(skill)
            
            # 급여 정보
            salary_info = ""
            salary_elem = soup.select_one('.salary, .pay_info')
            if salary_elem:
                salary_info = clean_text(salary_elem.text)
            
            # 복리후생
            benefits = ""
            benefits_elem = soup.select_one('.welfare, .benefit_cont')
            if benefits_elem:
                benefits = clean_text(benefits_elem.get_text())
            
            return {
                'description': description,
                'requirements': requirements,
                'preferred': preferred,
                'required_skills': skill_tags,
                'salary_info': salary_info,
                'benefits': benefits,
            }
            
        except Exception as e:
            self.logger.error(f"Error getting job detail for {job_id}: {e}")
            return None


# 테스트용
if __name__ == "__main__":
    crawler = SaraminCrawler()
    
    for job in crawler.search_jobs("데이터 분석가", max_pages=1):
        print(f"[{job['company_name']}] {job['title']}")
        print(f"  Location: {job.get('location', 'N/A')}")
        print(f"  Experience: {job.get('position_level', 'N/A')}")
        print()
    
    crawler.close()
