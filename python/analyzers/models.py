"""
기업 분석 보고서 생성을 위한 데이터 모델

이 모듈은 company_analysis_prompt_v4.md의 데이터 소스 A~I에 대응하는
데이터 클래스들을 정의합니다.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime

from utils.database import get_kst_now


@dataclass
class ProcessedReviews:
    """정제된 리뷰 데이터 (소스 C)"""
    total_count: int = 0
    avg_rating: float = 0.0
    rating_distribution: Dict[int, int] = field(default_factory=dict)  # {1: 5, 2: 10, ...}

    # 항목별 세부 평점 통계 (category_scores에서 추출)
    category_score_stats: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # 예: {"승진기회": {"avg": 3.2, "median": 3.0, "min": 1.0, "max": 5.0}, ...}

    # 키워드 분석
    pros_keywords: List[tuple] = field(default_factory=list)  # [(키워드, 빈도), ...]
    cons_keywords: List[tuple] = field(default_factory=list)
    advice_patterns: List[str] = field(default_factory=list)  # 경영진에게 바라는 점 주요 패턴

    # 시계열 분석
    trend_by_period: Dict[str, float] = field(default_factory=dict)  # {"2024-H1": 3.5, "2024-H2": 3.8}

    # 직군별 분석
    by_job_category: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # 원본 데이터 (LLM 분석용)
    raw_reviews: List[dict] = field(default_factory=list)


@dataclass
class ProcessedInterviews:
    """정제된 면접 후기 데이터 (소스 D)"""
    total_count: int = 0

    # 난이도 분석
    difficulty_distribution: Dict[str, int] = field(default_factory=dict)  # {"쉬움": 5, "보통": 10, ...}
    avg_difficulty: float = 0.0

    # 질문 유형 분류
    question_types: Dict[str, List[str]] = field(default_factory=dict)
    # {"기술": [...], "행동": [...], "상황": [...], "컬쳐핏": [...]}

    # 합격률
    result_distribution: Dict[str, int] = field(default_factory=dict)  # {"합격": 10, "불합격": 5, ...}
    pass_rate: float = 0.0

    # 직군별 분석
    by_job_category: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # 원본 데이터
    raw_interviews: List[dict] = field(default_factory=list)


@dataclass
class ProcessedSalaries:
    """정제된 급여 데이터 (소스 E)"""
    total_count: int = 0

    # 전체 평균
    overall_avg: Optional[int] = None  # 만원 단위
    industry_avg: Optional[int] = None
    vs_industry_percent: Optional[float] = None  # 업계 대비 비율 (예: +15.5%)

    # 경력별 급여
    by_experience: Dict[str, int] = field(default_factory=dict)  # {"1년차": 4000, "3년차": 5500, ...}

    # 직급별 급여
    by_position: Dict[str, int] = field(default_factory=dict)

    # 급여 분포
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_lower: Optional[int] = None  # 하위 25%
    salary_upper: Optional[int] = None  # 상위 25%

    # 원본 데이터
    raw_salaries: List[dict] = field(default_factory=list)


@dataclass
class ProcessedBenefits:
    """정제된 복리후생 데이터 (소스 F)"""
    total_count: int = 0

    # 카테고리별 평점
    category_ratings: Dict[str, float] = field(default_factory=dict)
    # {"휴가/휴식": 4.2, "보험/건강": 3.8, ...}

    # 카테고리별 주요 항목
    category_items: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    # {"휴가/휴식": [{"item": "연차", "score": 4.5}, ...], ...}

    # 강점/약점 카테고리
    strongest_categories: List[str] = field(default_factory=list)
    weakest_categories: List[str] = field(default_factory=list)

    # 원본 데이터
    raw_benefits: List[dict] = field(default_factory=list)


@dataclass
class ProcessedNews:
    """정제된 뉴스 데이터 (소스 G)"""
    total_count: int = 0

    # 기사 유형 분류
    by_type: Dict[str, List[dict]] = field(default_factory=dict)
    # {"PR/보도자료": [...], "산업분석": [...], "실적/투자": [...], ...}

    # 시간순 정렬된 기사 (모멘텀 파악용)
    timeline: List[dict] = field(default_factory=list)

    # 최근 6개월 내 기사
    recent_news: List[dict] = field(default_factory=list)

    # 신뢰도 등급별 기사
    by_reliability: Dict[str, List[dict]] = field(default_factory=dict)
    # {"G+": [...], "G": [...], "G-": [...]}

    # 원본 데이터
    raw_news: List[dict] = field(default_factory=list)


@dataclass
class SkillAnalysis:
    """기술 스택 분석 결과 (소스 B + I)"""
    # JD에서 추출한 스킬
    required_skills: List[str] = field(default_factory=list)
    preferred_skills: List[str] = field(default_factory=list)

    # 트렌드 매칭 결과
    skill_trends: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # {"Python": {"mention_count": 500, "trend": "상승", "category": "language"}, ...}

    # 상승/하락 분류
    rising_skills: List[str] = field(default_factory=list)
    falling_skills: List[str] = field(default_factory=list)
    stable_skills: List[str] = field(default_factory=list)


@dataclass
class AnalysisDataBundle:
    """
    수집된 모든 데이터 소스 번들

    company_analysis_prompt_v4.md의 소스 A~I에 대응:
    - A: company_info (기업 기본정보)
    - B: job_postings (채용공고)
    - C: reviews (재직자 후기)
    - D: interviews (면접 후기)
    - E: salaries (급여 정보)
    - F: benefits (복리후생)
    - G: news (뉴스 기사)
    - H: market_analysis (시장 분석)
    - I: skill_trends (스킬 트렌드)
    """
    # 필수 데이터
    company_info: dict = field(default_factory=dict)           # A - companies 테이블
    job_postings: List[dict] = field(default_factory=list)     # B - job_postings 테이블

    # 선택 데이터 (정제 전 원본)
    reviews: Optional[List[dict]] = None                       # C - company_reviews 테이블
    interviews: Optional[List[dict]] = None                    # D - company_interviews 테이블
    salaries: Optional[List[dict]] = None                      # E - company_salaries 테이블
    benefits: Optional[List[dict]] = None                      # F - company_benefits 테이블
    news: Optional[List[dict]] = None                          # G - company_news 테이블
    market_analysis: Optional[dict] = None                     # H - market_analysis 테이블
    skill_trends: Optional[List[dict]] = None                  # I - skill_trends 테이블

    # 정제된 데이터
    processed_reviews: Optional[ProcessedReviews] = None
    processed_interviews: Optional[ProcessedInterviews] = None
    processed_salaries: Optional[ProcessedSalaries] = None
    processed_benefits: Optional[ProcessedBenefits] = None
    processed_news: Optional[ProcessedNews] = None
    skill_analysis: Optional[SkillAnalysis] = None

    # 메타데이터
    company_id: Optional[int] = None
    company_name: str = ""
    target_job_posting_id: Optional[int] = None
    collected_at: datetime = field(default_factory=get_kst_now)

    def get_data_availability(self) -> Dict[str, Any]:
        """각 소스의 존재 여부 및 건수 반환"""
        return {
            "A_company_info": bool(self.company_info),
            "B_job_postings": len(self.job_postings) if self.job_postings else 0,
            "C_reviews": len(self.reviews) if self.reviews else 0,
            "D_interviews": len(self.interviews) if self.interviews else 0,
            "E_salaries": len(self.salaries) if self.salaries else 0,
            "F_benefits": len(self.benefits) if self.benefits else 0,
            "G_news": len(self.news) if self.news else 0,
            "H_market_analysis": bool(self.market_analysis),
            "I_skill_trends": len(self.skill_trends) if self.skill_trends else 0,
        }

    def has_minimum_data(self) -> bool:
        """최소 분석 요건 충족 여부 (회사정보 + 채용공고)"""
        return bool(self.company_info) and len(self.job_postings) > 0


@dataclass
class QualityCheckResult:
    """Quality Gate 검증 결과"""
    passed: bool = False

    # 섹션별 완결성
    sections_complete: Dict[str, bool] = field(default_factory=dict)

    # 태깅 검증
    fact_interpretation_judgment_tagged: bool = False
    source_labels_tagged: bool = False

    # 정량 데이터 활용
    category_scores_analyzed: bool = False
    salary_compared: bool = False
    skill_trends_analyzed: bool = False

    # 평가 정합성
    score_calculation_correct: bool = False
    verdict_consistent: bool = False

    # 누락 항목
    missing_items: List[str] = field(default_factory=list)


@dataclass
class GeneratedReport:
    """생성된 분석 보고서"""
    # 핵심 결과
    verdict: str = ""  # "Go" / "Conditional Go" / "No-Go"
    total_score: float = 0.0
    scores: Dict[str, float] = field(default_factory=dict)
    # {"직무적합성": 4.0, "성장성": 3.5, "안정성": 3.0, "보상·근무조건": 3.5, "조직운영 적합성": 3.0}

    # 핵심 인사이트
    key_attractions: List[str] = field(default_factory=list)  # 핵심 매력 포인트 3가지
    key_risks: List[str] = field(default_factory=list)        # 핵심 리스크 3가지
    verification_items: List[str] = field(default_factory=list)  # [확인 필요] 항목 3가지

    # 전체 보고서
    full_markdown: str = ""

    # Quality Gate 결과
    quality_check: Optional[QualityCheckResult] = None

    # 메타데이터
    llm_model: str = ""
    prompt_version: str = "v4"
    generated_at: datetime = field(default_factory=get_kst_now)
    token_usage: Dict[str, int] = field(default_factory=dict)  # {"input": ..., "output": ...}


@dataclass
class ApplicantProfile:
    """지원자 프로필 (선택)"""
    current_experience: str = ""  # 현재 경력
    core_skills: List[str] = field(default_factory=list)  # 핵심 스킬
    motivation: str = ""  # 지원 동기
    career_direction: str = ""  # 희망 커리어 방향


@dataclass
class PriorityWeights:
    """개인 우선순위 가중치 (합계 100)"""
    growth: int = 20       # 성장성
    stability: int = 20    # 안정성
    compensation: int = 20 # 보상
    work_life_balance: int = 20  # 워라밸
    job_fit: int = 20      # 직무적합

    def validate(self) -> bool:
        """가중치 합이 100인지 검증"""
        total = self.growth + self.stability + self.compensation + self.work_life_balance + self.job_fit
        return total == 100

    def to_dict(self) -> Dict[str, int]:
        return {
            "성장성": self.growth,
            "안정성": self.stability,
            "보상": self.compensation,
            "워라밸": self.work_life_balance,
            "직무적합": self.job_fit,
        }
