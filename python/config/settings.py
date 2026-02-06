"""
Job Market Analyzer - 설정 관리
Windows/Linux 로컬 및 클라우드 환경 모두 지원
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import json

# .env 파일 로드
from dotenv import load_dotenv

# 프로젝트 루트 경로
PROJECT_ROOT = Path(__file__).parent.parent

# .env 파일 로드 (프로젝트 루트에서)
load_dotenv(PROJECT_ROOT / '.env')
DATA_DIR = PROJECT_ROOT / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"

# 디렉토리 생성
DATA_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)


@dataclass
class CrawlerConfig:
    """크롤러 설정"""
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    request_delay: float = 2.0  # 요청 간 딜레이 (초)
    max_retries: int = 3
    timeout: int = 30
    max_pages_per_keyword: int = 10  # 키워드당 최대 크롤링 페이지 수


@dataclass
class WantedConfig:
    """원티드 크롤링 설정 (1차 크롤링)"""
    # 대기 시간 (초)
    page_load_delay: float = float(os.getenv("WANTED_PAGE_LOAD_DELAY", "5.0"))  # React 렌더링 대기
    scroll_delay: float = float(os.getenv("WANTED_SCROLL_DELAY", "2.0"))
    detail_load_delay: float = float(os.getenv("WANTED_DETAIL_LOAD_DELAY", "2.0"))
    between_requests_delay: float = float(os.getenv("WANTED_BETWEEN_REQUESTS_DELAY", "3.0"))

    # 타임아웃 (밀리초)
    page_timeout: int = int(os.getenv("WANTED_PAGE_TIMEOUT", "30000"))
    selector_timeout: int = int(os.getenv("WANTED_SELECTOR_TIMEOUT", "15000"))

    # 기타 설정
    headless: bool = os.getenv("WANTED_HEADLESS", "true").lower() == "true"


@dataclass
class DatabaseConfig:
    """데이터베이스 설정 - SQLite, PostgreSQL, Supabase 지원"""
    # 환경변수로 클라우드 DB 설정 가능
    db_type: str = os.getenv("DB_TYPE", "sqlite")  # sqlite, postgresql, supabase

    # DATABASE_URL 환경변수 (Supabase, Railway, Heroku 등에서 사용)
    database_url: str = os.getenv("DATABASE_URL", "")

    # SQLite (로컬)
    sqlite_path: str = str(DATA_DIR / "job_market.db")

    # PostgreSQL (클라우드)
    pg_host: str = os.getenv("PG_HOST", "localhost")
    pg_port: int = int(os.getenv("PG_PORT", "5432"))
    pg_database: str = os.getenv("PG_DATABASE", "job_market")
    pg_user: str = os.getenv("PG_USER", "postgres")
    pg_password: str = os.getenv("PG_PASSWORD", "")

    # Supabase 설정
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_service_key: str = os.getenv("SUPABASE_SERVICE_KEY", "")

    @property
    def connection_string(self) -> str:
        """데이터베이스 연결 문자열 반환"""
        # DATABASE_URL이 설정되어 있으면 우선 사용 (Supabase, Railway 등)
        if self.database_url:
            return self.database_url

        if self.db_type == "sqlite":
            return f"sqlite:///{self.sqlite_path}"
        elif self.db_type in ("postgresql", "supabase"):
            return f"postgresql://{self.pg_user}:{self.pg_password}@{self.pg_host}:{self.pg_port}/{self.pg_database}"
        else:
            return f"sqlite:///{self.sqlite_path}"

    def get_connection_string(self) -> str:
        """하위 호환성을 위한 메서드"""
        return self.connection_string

    @property
    def is_supabase(self) -> bool:
        """Supabase 사용 여부"""
        return self.db_type == "supabase" or bool(self.supabase_url)


@dataclass
class AnalyzerConfig:
    """분석기 설정"""
    # LLM API 설정 (Gemini, Anthropic Claude, OpenAI)
    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini")  # gemini, anthropic, openai
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")

    # 분석 설정
    min_job_count_for_trend: int = 5  # 트렌드 분석을 위한 최소 채용공고 수
    skill_extraction_enabled: bool = True
    company_research_enabled: bool = True


@dataclass
class SchedulerConfig:
    """스케줄러 설정"""
    enabled: bool = os.getenv("SCHEDULER_ENABLED", "true").lower() == "true"
    schedule_time: str = os.getenv("SCHEDULER_TIME", "23:00")  # 매일 실행 시간 (KST)
    timezone: str = "Asia/Seoul"


@dataclass
class JobplanetConfig:
    """잡플래닛 크롤링 설정 (2차 크롤링)"""
    # 페이지 수 제한
    review_max_pages: int = int(os.getenv("JOBPLANET_REVIEW_MAX_PAGES", "50"))
    interview_max_pages: int = int(os.getenv("JOBPLANET_INTERVIEW_MAX_PAGES", "50"))
    benefit_max_pages: int = int(os.getenv("JOBPLANET_BENEFIT_MAX_PAGES", "20"))

    # 최대 수집 개수
    review_max_count: int = int(os.getenv("JOBPLANET_REVIEW_MAX_COUNT", "500"))
    interview_max_count: int = int(os.getenv("JOBPLANET_INTERVIEW_MAX_COUNT", "300"))

    # 대기 시간 (초)
    page_load_delay: float = float(os.getenv("JOBPLANET_PAGE_LOAD_DELAY", "3.0"))
    scroll_delay: float = float(os.getenv("JOBPLANET_SCROLL_DELAY", "2.0"))
    between_pages_delay: float = float(os.getenv("JOBPLANET_BETWEEN_PAGES_DELAY", "2.0"))
    login_delay: float = float(os.getenv("JOBPLANET_LOGIN_DELAY", "8.0"))
    popup_close_delay: float = float(os.getenv("JOBPLANET_POPUP_CLOSE_DELAY", "1.0"))
    tab_switch_delay: float = float(os.getenv("JOBPLANET_TAB_SWITCH_DELAY", "3.0"))
    element_wait_delay: float = float(os.getenv("JOBPLANET_ELEMENT_WAIT_DELAY", "1.0"))

    # 스크롤 설정
    scroll_min: int = int(os.getenv("JOBPLANET_SCROLL_MIN", "500"))  # 최소 스크롤 거리 (픽셀)
    scroll_max: int = int(os.getenv("JOBPLANET_SCROLL_MAX", "700"))  # 최대 스크롤 거리 (픽셀)
    scroll_delay_min: float = float(os.getenv("JOBPLANET_SCROLL_DELAY_MIN", "0.3"))  # 최소 스크롤 간격 (초)
    scroll_delay_max: float = float(os.getenv("JOBPLANET_SCROLL_DELAY_MAX", "0.6"))  # 최대 스크롤 간격 (초)

    # 브라우저 설정
    headless: bool = os.getenv("JOBPLANET_HEADLESS", "true").lower() == "true"

    # 로그인 정보
    email: str = os.getenv("JOBPLANET_EMAIL", "")
    password: str = os.getenv("JOBPLANET_PASSWORD", "")


@dataclass
class NewsConfig:
    """뉴스 크롤링 설정 (연합뉴스)"""
    # 페이지 수 제한
    max_pages: int = int(os.getenv("NEWS_MAX_PAGES", "10"))

    # 대기 시간 (초)
    page_load_delay: float = float(os.getenv("NEWS_PAGE_LOAD_DELAY", "3.0"))
    article_delay: float = float(os.getenv("NEWS_ARTICLE_DELAY", "1.0"))
    scroll_delay: float = float(os.getenv("NEWS_SCROLL_DELAY", "0.5"))

    # 스크롤 설정
    scroll_distance: int = int(os.getenv("NEWS_SCROLL_DISTANCE", "200"))  # 픽셀
    scroll_interval: int = int(os.getenv("NEWS_SCROLL_INTERVAL", "300"))  # 밀리초

    # 기타 설정
    headless: bool = os.getenv("NEWS_HEADLESS", "true").lower() == "true"


@dataclass
class SearchKeywords:
    """검색 키워드 설정"""
    # 1. 직무/기술 키워드
    job_keywords: list = field(default_factory=lambda: [
        "데이터 분석가",
        "데이터 엔지니어",
        "AI 엔지니어",
        "데이터 사이언티스트",
        "LLM"
    ])

    # 2. 연차 키워드
    experience_keywords: list = field(default_factory=lambda: [
        # 빈 문자열 = 연차 무관
        "신입",
        "1년차"
    ])

    # 3. 지역 키워드
    location_keywords: list = field(default_factory=lambda: [
        "",  # 빈 문자열 = 지역 무관
        "서울",
        "판교"
    ])

    # 사이트별 활성화 여부
    sites: dict = field(default_factory=lambda: {
        "linkedin": False,
        "wanted": True,
        "jobkorea": False,
        "saramin": False,
        "rocketpunch": False
    })

    # 조합 옵션
    combine_all: bool = False  # True: 모든 조합 생성, False: 직무 키워드만 사용

    @property
    def keywords(self) -> list:
        """하위 호환성을 위한 속성 - 직무 키워드 반환"""
        return self.job_keywords

    def get_combined_keywords(self) -> list:
        """3가지 키워드 조합 생성"""
        if not self.combine_all:
            return self.job_keywords

        combined = []
        for job in self.job_keywords:
            for exp in self.experience_keywords:
                for loc in self.location_keywords:
                    # 빈 문자열 제외하고 조합
                    parts = [p for p in [job, exp, loc] if p]
                    keyword = " ".join(parts)
                    if keyword and keyword not in combined:
                        combined.append(keyword)

        return combined

    def get_keywords_for_site(self, site: str) -> list:
        """사이트별 최적화된 키워드 반환

        일부 사이트는 필터 기능이 있어서 직무 키워드만 사용하고
        연차/지역은 필터로 처리하는 것이 효율적
        """
        # Wanted, Saramin 등은 자체 필터가 있음
        if site in ["wanted", "saramin", "jobkorea"]:
            return self.job_keywords

        # 필터가 없는 사이트는 조합 키워드 사용
        return self.get_combined_keywords() if self.combine_all else self.job_keywords


class Settings:
    """통합 설정 클래스"""
    def __init__(self, config_file: Optional[str] = None):
        self.crawler = CrawlerConfig()
        self.wanted = WantedConfig()
        self.database = DatabaseConfig()
        self.analyzer = AnalyzerConfig()
        self.scheduler = SchedulerConfig()
        self.search_keywords = SearchKeywords()
        self.jobplanet = JobplanetConfig()
        self.news = NewsConfig()

        # 설정 파일이 있으면 로드
        if config_file and Path(config_file).exists():
            self.load_from_file(config_file)
    
    def load_from_file(self, config_file: str):
        """JSON 설정 파일에서 로드"""
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # 새로운 키워드 구조
        if 'job_keywords' in config:
            self.search_keywords.job_keywords = config['job_keywords']
        if 'experience_keywords' in config:
            self.search_keywords.experience_keywords = config['experience_keywords']
        if 'location_keywords' in config:
            self.search_keywords.location_keywords = config['location_keywords']
        if 'combine_all' in config:
            self.search_keywords.combine_all = config['combine_all']

        # 하위 호환성: 기존 'keywords' 키 지원
        if 'keywords' in config and 'job_keywords' not in config:
            self.search_keywords.job_keywords = config['keywords']

        if 'sites' in config:
            self.search_keywords.sites = config['sites']
        if 'crawler' in config:
            for key, value in config['crawler'].items():
                if hasattr(self.crawler, key):
                    setattr(self.crawler, key, value)
        if 'jobplanet' in config:
            for key, value in config['jobplanet'].items():
                if hasattr(self.jobplanet, key):
                    setattr(self.jobplanet, key, value)

    def save_to_file(self, config_file: str):
        """설정을 JSON 파일로 저장"""
        config = {
            'job_keywords': self.search_keywords.job_keywords,
            'experience_keywords': self.search_keywords.experience_keywords,
            'location_keywords': self.search_keywords.location_keywords,
            'combine_all': self.search_keywords.combine_all,
            'sites': self.search_keywords.sites,
            'crawler': {
                'request_delay': self.crawler.request_delay,
                'max_retries': self.crawler.max_retries,
                'max_pages_per_keyword': self.crawler.max_pages_per_keyword
            },
            'jobplanet': {
                'review_max_pages': self.jobplanet.review_max_pages,
                'interview_max_pages': self.jobplanet.interview_max_pages,
                'benefit_max_pages': self.jobplanet.benefit_max_pages,
                'review_max_count': self.jobplanet.review_max_count,
                'interview_max_count': self.jobplanet.interview_max_count,
                'page_load_delay': self.jobplanet.page_load_delay,
                'scroll_delay': self.jobplanet.scroll_delay,
                'between_pages_delay': self.jobplanet.between_pages_delay,
                'login_delay': self.jobplanet.login_delay
            }
        }
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)


# 전역 설정 인스턴스
settings = Settings()
