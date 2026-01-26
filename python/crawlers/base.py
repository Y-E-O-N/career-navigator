"""
채용 공고 데이터 모델 및 기본 크롤러 클래스
"""
import hashlib
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Dict, Optional, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import sys
sys.path.append(str(__file__).rsplit('/', 2)[0])
from config import crawler_config, SKILL_CATEGORIES


@dataclass
class JobPosting:
    """채용 공고 데이터 모델"""
    # 기본 정보
    title: str
    company: str
    url: str
    source: str  # 크롤링 소스 (wanted, saramin 등)
    
    # 직무 정보
    job_category: str = ""
    location: str = ""
    experience_min: int = 0
    experience_max: int = 0
    education: str = ""
    employment_type: str = ""  # 정규직, 계약직 등
    
    # 급여
    salary_min: int = 0
    salary_max: int = 0
    salary_type: str = ""  # 연봉, 월급, 협의
    
    # 스킬
    required_skills: List[str] = field(default_factory=list)
    preferred_skills: List[str] = field(default_factory=list)
    hard_skills: List[str] = field(default_factory=list)
    soft_skills: List[str] = field(default_factory=list)
    
    # 상세 정보
    description: str = ""
    requirements: str = ""
    benefits: str = ""
    
    # 회사 정보
    company_info: str = ""
    industry: str = ""
    company_size: str = ""
    
    # 메타 정보
    posted_date: str = ""
    deadline: str = ""
    crawled_at: str = field(
        default_factory=lambda: datetime.now().isoformat()
    )
    content_hash: str = ""
    
    def __post_init__(self):
        """해시 생성 및 스킬 분류"""
        if not self.content_hash:
            content = f"{self.title}{self.company}{self.url}"
            self.content_hash = hashlib.md5(content.encode()).hexdigest()
        
        # 스킬 분류
        self._classify_skills()
    
    def _classify_skills(self):
        """스킬을 하드스킬/소프트스킬로 분류"""
        all_skills = set(self.required_skills + self.preferred_skills)
        
        soft_skill_keywords = SKILL_CATEGORIES.get("soft_skills", [])
        
        for skill in all_skills:
            skill_lower = skill.lower()
            is_soft = any(ss in skill_lower for ss in soft_skill_keywords)
            
            if is_soft:
                if skill not in self.soft_skills:
                    self.soft_skills.append(skill)
            else:
                if skill not in self.hard_skills:
                    self.hard_skills.append(skill)
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'JobPosting':
        """딕셔너리에서 생성"""
        return cls(**data)


class BaseCrawler(ABC):
    """크롤러 기본 클래스"""
    
    def __init__(self, site_name: str):
        self.site_name = site_name
        self.config = crawler_config
        self.logger = logging.getLogger(f"crawler.{site_name}")
        self.session = self._create_session()
        self.last_request_time = 0
    
    def _create_session(self) -> requests.Session:
        """HTTP 세션 생성 (재시도 로직 포함)"""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=self.config.max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        session.headers.update({
            "User-Agent": self.config.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        })
        
        return session
    
    def _rate_limit(self):
        """요청 간 대기"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.config.request_delay:
            time.sleep(self.config.request_delay - elapsed)
        self.last_request_time = time.time()
    
    def _get_page(self, url: str, **kwargs) -> Optional[str]:
        """페이지 HTML 가져오기"""
        self._rate_limit()
        
        try:
            response = self.session.get(
                url, 
                timeout=self.config.timeout,
                **kwargs
            )
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            self.logger.error(f"페이지 요청 실패: {url} - {e}")
            return None
    
    def _get_json(self, url: str, **kwargs) -> Optional[Dict]:
        """JSON 데이터 가져오기"""
        self._rate_limit()
        
        try:
            response = self.session.get(
                url,
                timeout=self.config.timeout,
                **kwargs
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            self.logger.error(f"JSON 요청 실패: {url} - {e}")
            return None
    
    def _extract_skills(self, text: str) -> List[str]:
        """텍스트에서 스킬 추출"""
        if not text:
            return []
        
        text_lower = text.lower()
        found_skills = []
        
        for category, skills in SKILL_CATEGORIES.items():
            for skill in skills:
                if skill.lower() in text_lower:
                    found_skills.append(skill)
        
        return list(set(found_skills))
    
    @abstractmethod
    def search(self, keyword: str, max_pages: int = None) -> List[JobPosting]:
        """키워드로 채용 공고 검색"""
        pass
    
    @abstractmethod
    def get_job_detail(self, job_id: str) -> Optional[JobPosting]:
        """채용 공고 상세 정보 가져오기"""
        pass
    
    def crawl_all_keywords(self) -> List[JobPosting]:
        """설정된 모든 키워드로 크롤링"""
        all_jobs = []
        seen_hashes = set()
        
        for keyword in self.config.search_keywords:
            self.logger.info(f"키워드 크롤링: {keyword}")
            jobs = self.search(keyword, self.config.max_pages)
            
            for job in jobs:
                if job.content_hash not in seen_hashes:
                    seen_hashes.add(job.content_hash)
                    all_jobs.append(job)
            
            self.logger.info(f"  - {len(jobs)}개 수집 (중복 제외 총 {len(all_jobs)}개)")
        
        return all_jobs
