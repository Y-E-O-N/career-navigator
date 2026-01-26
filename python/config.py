"""
채용 시장 분석 시스템 - 설정 파일
"""
import os
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from pathlib import Path

# 프로젝트 루트 경로
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

# 디렉토리 생성
for dir_path in [DATA_DIR, LOGS_DIR, OUTPUTS_DIR]:
    dir_path.mkdir(exist_ok=True)


@dataclass
class CrawlerConfig:
    """크롤러 설정"""
    # 크롤링 대상 사이트
    enabled_sites: List[str] = field(default_factory=lambda: [
        "wanted", "saramin", "jobkorea", "jumpit", "programmers"
    ])
    
    # 검색 키워드
    search_keywords: List[str] = field(default_factory=lambda: [
        "python", "데이터분석", "백엔드", "프론트엔드", 
        "머신러닝", "데이터엔지니어", "DevOps"
    ])
    
    # 요청 설정
    request_delay: float = 1.5  # 요청 간 대기 시간(초)
    max_retries: int = 3
    timeout: int = 30
    max_pages: int = 10  # 사이트당 최대 페이지
    
    # User-Agent
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )


@dataclass
class AnalysisConfig:
    """분석 설정"""
    # 트렌드 분석 기간 (일)
    trend_period_days: int = 30
    
    # 최소 데이터 수
    min_jobs_for_analysis: int = 10
    
    # 스킬 분석
    top_skills_count: int = 20
    
    # LLM 분석 (선택적)
    use_llm_analysis: bool = False
    llm_provider: str = "anthropic"  # anthropic, openai
    llm_model: str = "claude-sonnet-4-20250514"


@dataclass 
class CompanyResearchConfig:
    """회사 조사 설정"""
    # 사업자 정보 API (공공데이터포털)
    bizinfo_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("BIZINFO_API_KEY")
    )
    
    # 검색 소스
    search_sources: List[str] = field(default_factory=lambda: [
        "blind", "jobplanet", "google", "naver"
    ])
    
    # 캐시 시간 (시간)
    cache_hours: int = 24


@dataclass
class SchedulerConfig:
    """스케줄러 설정"""
    # 실행 시간 (24시간 형식)
    daily_run_hour: int = 6
    daily_run_minute: int = 0
    
    # 환경
    environment: str = "local"  # local, cloud
    
    # 알림
    enable_notifications: bool = False
    notification_email: Optional[str] = None
    slack_webhook: Optional[str] = field(
        default_factory=lambda: os.getenv("SLACK_WEBHOOK_URL")
    )


@dataclass
class ReportConfig:
    """리포트 설정"""
    # 출력 형식
    output_formats: List[str] = field(default_factory=lambda: [
        "markdown", "html", "json"
    ])
    
    # 로드맵 설정
    roadmap_months: List[int] = field(default_factory=lambda: [3, 6])
    
    # 언어
    language: str = "ko"


# 스킬 카테고리 정의
SKILL_CATEGORIES = {
    "programming_languages": [
        "python", "java", "javascript", "typescript", "go", "rust", 
        "c++", "c#", "kotlin", "swift", "ruby", "php", "scala", "r"
    ],
    "backend_frameworks": [
        "django", "flask", "fastapi", "spring", "spring boot", "node.js",
        "express", "nestjs", "rails", "laravel", "asp.net"
    ],
    "frontend_frameworks": [
        "react", "vue", "angular", "svelte", "next.js", "nuxt",
        "jquery", "tailwind", "bootstrap"
    ],
    "databases": [
        "mysql", "postgresql", "mongodb", "redis", "elasticsearch",
        "oracle", "mssql", "dynamodb", "cassandra", "sqlite"
    ],
    "cloud_devops": [
        "aws", "gcp", "azure", "docker", "kubernetes", "terraform",
        "jenkins", "github actions", "gitlab ci", "ansible", "prometheus",
        "grafana", "nginx", "linux"
    ],
    "data_ml": [
        "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch",
        "keras", "spark", "hadoop", "airflow", "kafka", "flink",
        "tableau", "power bi", "sql", "bigquery", "snowflake",
        "mlflow", "kubeflow", "huggingface"
    ],
    "tools": [
        "git", "jira", "confluence", "slack", "figma", "notion"
    ],
    "soft_skills": [
        "커뮤니케이션", "협업", "문제해결", "리더십", "프로젝트관리",
        "애자일", "스크럼", "기획력", "분석력", "창의성"
    ]
}

# 직군 분류
JOB_CATEGORIES = {
    "backend": ["백엔드", "서버", "backend", "server", "api"],
    "frontend": ["프론트엔드", "frontend", "웹개발", "web"],
    "fullstack": ["풀스택", "fullstack", "full-stack"],
    "data_analyst": ["데이터분석", "데이터 분석", "data analyst", "bi", "비즈니스 인텔리전스"],
    "data_engineer": ["데이터엔지니어", "데이터 엔지니어", "data engineer", "데이터파이프라인"],
    "ml_engineer": ["머신러닝", "ml", "ai", "인공지능", "딥러닝", "machine learning"],
    "devops": ["devops", "데브옵스", "sre", "인프라", "클라우드"],
    "mobile": ["ios", "android", "모바일", "앱개발", "flutter", "react native"],
    "security": ["보안", "security", "정보보안"],
    "pm_po": ["pm", "po", "프로덕트", "기획", "product manager", "product owner"]
}


# 전역 설정 인스턴스
crawler_config = CrawlerConfig()
analysis_config = AnalysisConfig()
company_config = CompanyResearchConfig()
scheduler_config = SchedulerConfig()
report_config = ReportConfig()
