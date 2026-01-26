"""
잡코리아 (JobKorea) 크롤러
https://www.jobkorea.co.kr
"""

from typing import Generator, Dict, Any, Optional
import re
from datetime import datetime
from .base_crawler import BaseCrawler
from utils.helpers import clean_text


class JobKoreaCrawler(BaseCrawler):
    """잡코리아 채용공고 크롤러"""
    
    def __init__(self):
        super().__init__()
        self.site_name = "jobkorea"
        self.base_url = "https://www.jobkorea.co.kr"
        
        # 잡코리아 특화 헤더
        self.session.headers.update({
            'Referer': 'https://www.jobkorea.co.kr/',
        })
    
    def search_jobs(self, keyword: str, max_pages: int = 10) -> Generator[Dict[str, Any], None, None]:
        """
        잡코리아 채용공고 검색
        """
        total_count = 0
        
        for page in range(1, max_pages + 1):
            try:
                # 잡코리아 검색 URL
                search_url = f"{self.base_url}/Search/"
                params = {
                    'stext': keyword,
                    'tabType': 'recruit',
                    'Page_No': page,
                }
                
                soup = self.get_page(search_url, params)
                
                if not soup:
                    break
                
                # 채용공고 목록 찾기
                job_list = soup.select('.list-item, .recruit-info')
                
                # 다른 셀렉터 시도
                if not job_list:
                    job_list = soup.select('.post-list-info')
                
                if not job_list:
                    job_list = soup.select('article.list-item')
                
                if not job_list:
                    self.logger.warning(f"No jobs found on page {page}")
                    break
                
                for job_elem in job_list:
                    job_data = self._parse_job_listing(job_elem)
                    if job_data:
                        yield job_data
                        total_count += 1
                
                # 마지막 페이지 확인
                if len(job_list) < 20:
                    break
                    
            except Exception as e:
                self.logger.error(f"Error searching page {page}: {e}")
                break
        
        self.logger.info(f"Found {total_count} jobs for keyword: {keyword}")
    
    def _parse_job_listing(self, elem) -> Optional[Dict[str, Any]]:
        """HTML 요소에서 채용공고 정보 파싱"""
        try:
            # 채용공고 제목 및 링크
            title_elem = elem.select_one('.information-title a, .post-list-corp a, .title a')
            if not title_elem:
                title_elem = elem.select_one('a.title')
            
            if not title_elem:
                return None
            
            title = clean_text(title_elem.text)
            href = title_elem.get('href', '')
            
            # job_id 추출
            job_id = ""
            job_id_match = re.search(r'[Gg]no=(\d+)', href)
            if job_id_match:
                job_id = job_id_match.group(1)
            else:
                # URL에서 ID 추출 시도
                job_id_match = re.search(r'/(\d+)\??', href)
                if job_id_match:
                    job_id = job_id_match.group(1)
            
            if not job_id:
                return None
            
            # 회사명
            company_elem = elem.select_one('.corp-name a, .company-name, .name')
            company_name = clean_text(company_elem.text) if company_elem else ""
            
            # 조건 정보
            option_elems = elem.select('.chip-information-group .chip, .option span, .info-item')
            location = ""
            experience = ""
            employment_type = ""
            salary = ""
            
            option_texts = [clean_text(opt.text) for opt in option_elems]
            
            for text in option_texts:
                if any(loc in text for loc in ['서울', '경기', '인천', '부산', '대구', '광주', '대전', '울산', '세종', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주']):
                    location = text
                elif any(exp in text for exp in ['신입', '경력', '년', '무관']):
                    experience = text
                elif any(emp in text for emp in ['정규', '계약', '인턴', '파견', '프리']):
                    employment_type = text
                elif '만원' in text or '원' in text:
                    salary = text
            
            # 직무 분야
            sector_elem = elem.select_one('.sector, .job-sector')
            job_category = clean_text(sector_elem.text) if sector_elem else ""
            
            # 마감일
            deadline_elem = elem.select_one('.date, .deadline')
            deadline = clean_text(deadline_elem.text) if deadline_elem else ""
            
            return {
                'source_site': self.site_name,
                'job_id': job_id,
                'title': title,
                'company_name': company_name,
                'job_category': job_category,
                'position_level': experience,
                'location': location,
                'employment_type': employment_type,
                'salary_info': salary,
                'deadline_text': deadline,
                'url': f"{self.base_url}/Recruit/GI_Read/{job_id}" if job_id.isdigit() else href,
                'crawled_at': datetime.now(),
            }
        except Exception as e:
            self.logger.error(f"Error parsing job listing: {e}")
            return None
    
    def get_job_detail(self, job_id: str) -> Optional[Dict[str, Any]]:
        """채용공고 상세 정보 가져오기"""
        try:
            detail_url = f"{self.base_url}/Recruit/GI_Read/{job_id}"
            
            soup = self.get_page(detail_url)
            
            if not soup:
                return None
            
            # 상세 설명
            description = ""
            desc_elems = soup.select('.view-content, .recruit-view-content, .content-area')
            for desc_elem in desc_elems:
                description += clean_text(desc_elem.get_text()) + "\n"
            
            # 직무 내용 섹션 파싱
            requirements = ""
            preferred = ""
            
            # 테이블 형식의 상세 정보
            info_rows = soup.select('.tbRow, .detail-row, tr')
            for row in info_rows:
                header = row.select_one('th, .label')
                content = row.select_one('td, .value')
                
                if header and content:
                    header_text = clean_text(header.text).lower()
                    content_text = clean_text(content.get_text())
                    
                    if any(word in header_text for word in ['자격', '필수', '요건']):
                        requirements += content_text + "\n"
                    elif any(word in header_text for word in ['우대', '선호']):
                        preferred += content_text + "\n"
            
            # 스킬/기술 태그
            skill_tags = []
            skill_elems = soup.select('.skill-tag, .keyword, .tech-stack span')
            for skill_elem in skill_elems:
                skill = clean_text(skill_elem.text)
                if skill and len(skill) < 50:  # 너무 긴 텍스트 제외
                    skill_tags.append(skill)
            
            # 급여 정보
            salary_info = ""
            salary_elem = soup.select_one('.salary-info, .pay')
            if salary_elem:
                salary_info = clean_text(salary_elem.text)
            
            # 복리후생
            benefits = ""
            benefits_elem = soup.select_one('.welfare-list, .benefit')
            if benefits_elem:
                benefits = clean_text(benefits_elem.get_text())
            
            return {
                'description': description.strip(),
                'requirements': requirements.strip(),
                'preferred': preferred.strip(),
                'required_skills': skill_tags,
                'salary_info': salary_info,
                'benefits': benefits,
            }
            
        except Exception as e:
            self.logger.error(f"Error getting job detail for {job_id}: {e}")
            return None


# 테스트용
if __name__ == "__main__":
    crawler = JobKoreaCrawler()
    
    for job in crawler.search_jobs("데이터 분석가", max_pages=1):
        print(f"[{job['company_name']}] {job['title']}")
        print(f"  Location: {job.get('location', 'N/A')}")
        print(f"  URL: {job.get('url', 'N/A')}")
        print()
    
    crawler.close()
