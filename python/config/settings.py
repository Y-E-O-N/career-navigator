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
    schedule_time: str = os.getenv("SCHEDULER_TIME", "09:00")  # 매일 실행 시간
    timezone: str = "Asia/Seoul"


@dataclass
class SearchKeywords:
    """검색 키워드 설정"""
    keywords: list = field(default_factory=lambda: [
        "데이터 분석가",
        "데이터 엔지니어",
        "머신러닝 엔지니어",
        "백엔드 개발자",
        "프론트엔드 개발자",
        "풀스택 개발자",
        "DevOps",
        "클라우드 엔지니어",
        "AI 엔지니어",
        "데이터 사이언티스트"
    ])
    
    # 사이트별 활성화 여부
    sites: dict = field(default_factory=lambda: {
        "linkedin": True,
        "wanted": True,
        "jobkorea": True,
        "saramin": True,
        "rocketpunch": True
    })


class Settings:
    """통합 설정 클래스"""
    def __init__(self, config_file: Optional[str] = None):
        self.crawler = CrawlerConfig()
        self.database = DatabaseConfig()
        self.analyzer = AnalyzerConfig()
        self.scheduler = SchedulerConfig()
        self.search_keywords = SearchKeywords()
        
        # 설정 파일이 있으면 로드
        if config_file and Path(config_file).exists():
            self.load_from_file(config_file)
    
    def load_from_file(self, config_file: str):
        """JSON 설정 파일에서 로드"""
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        if 'keywords' in config:
            self.search_keywords.keywords = config['keywords']
        if 'sites' in config:
            self.search_keywords.sites = config['sites']
        if 'crawler' in config:
            for key, value in config['crawler'].items():
                if hasattr(self.crawler, key):
                    setattr(self.crawler, key, value)
    
    def save_to_file(self, config_file: str):
        """설정을 JSON 파일로 저장"""
        config = {
            'keywords': self.search_keywords.keywords,
            'sites': self.search_keywords.sites,
            'crawler': {
                'request_delay': self.crawler.request_delay,
                'max_retries': self.crawler.max_retries,
                'max_pages_per_keyword': self.crawler.max_pages_per_keyword
            }
        }
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)


# 전역 설정 인스턴스
settings = Settings()
