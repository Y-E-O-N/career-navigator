"""
데이터베이스 관리 모듈
SQLite (로컬) 및 PostgreSQL (클라우드) 지원
"""

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, JSON, Boolean, ForeignKey, ARRAY, Numeric
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from typing import Optional, List
import pytz

# 한국 시간대
KST = pytz.timezone('Asia/Seoul')

def get_kst_now():
    """현재 한국 시간 반환"""
    return datetime.now(KST)
import sys
sys.path.append(str(__file__).rsplit('/', 2)[0])

from config.settings import settings

Base = declarative_base()


class JobPosting(Base):
    """채용공고 테이블"""
    __tablename__ = 'job_postings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_site = Column(String(50), nullable=False)  # wanted, saramin, jobkorea
    job_id = Column(String(100), nullable=False)  # 사이트 내 고유 ID
    title = Column(String(500), nullable=False)
    company_name = Column(String(200), nullable=False)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=True)

    # 직무 정보
    job_category = Column(String(200))  # 직군/직무 카테고리
    position_level = Column(String(100))  # 경력 수준 (신입, 경력, 무관)
    employment_type = Column(String(100))  # 고용 형태 (정규직, 계약직 등)

    # 상세 정보
    description = Column(Text)  # 상세 설명
    requirements = Column(Text)  # 자격요건
    preferred = Column(Text)  # 우대사항

    # 스킬 정보 (JSON 배열)
    required_skills = Column(JSON)  # 필수 스킬
    preferred_skills = Column(JSON)  # 우대 스킬

    # 조건
    salary_info = Column(String(200))  # 급여 정보
    location = Column(String(200))  # 근무지

    # Wanted 추가 필드
    experience_level = Column(String(100))  # 경력 요구사항 (예: "경력 1년 이상")
    reward_info = Column(String(200))  # 합격 보상금
    main_tasks = Column(Text)  # 주요 업무
    company_tags = Column(JSON)  # 회사 태그 (복지, 규모 등)
    deadline = Column(String(100))  # 마감일
    work_address = Column(String(500))  # 상세 근무지 주소
    company_industry = Column(String(200))  # 회사 산업분야

    # Wanted 외부 ID (data 속성에서 추출)
    wanted_company_id = Column(String(50))  # Wanted 회사 ID
    wanted_position_id = Column(String(50))  # Wanted 포지션 ID
    wanted_job_category_id = Column(String(50))  # Wanted 직무 카테고리 ID

    # 메타
    url = Column(String(500))
    crawled_at = Column(DateTime, default=get_kst_now)
    posted_at = Column(DateTime)
    expires_at = Column(DateTime)
    status = Column(String(20), default='모집중')  # 모집중, 마감

    # 관계
    company = relationship("Company", back_populates="job_postings")


class Company(Base):
    """회사 정보 테이블"""
    __tablename__ = 'companies'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, unique=True)

    # 기본 정보
    business_number = Column(String(50))  # 사업자등록번호
    industry = Column(String(200))  # 산업 분야
    company_size = Column(String(100))  # 기업 규모
    founded_year = Column(Integer)
    location = Column(String(100))  # 지역 (서울, 경기 등)

    # 상세 정보
    description = Column(Text)
    website = Column(String(300))
    address = Column(String(500))

    # 평판 정보
    glassdoor_rating = Column(Float)
    jobplanet_id = Column(String(50))  # 잡플래닛 회사 ID (URL의 숫자)
    jobplanet_rating = Column(Float)
    jobplanet_url = Column(String(500))  # 잡플래닛 URL
    blind_summary = Column(Text)  # 블라인드 요약
    news_summary = Column(Text)  # 뉴스 요약
    public_sentiment = Column(Text)  # 대중 평가 요약

    # 재무 정보 (사업자 조회 결과)
    revenue = Column(String(100))
    employee_count = Column(Integer)

    # 잡플래닛 추가 정보 (JSON)
    additional_info = Column(Text)  # 연봉, 면접, 복지 등 JSON

    # 메타 (DB 컬럼명은 updated_at)
    updated_at = Column('updated_at', DateTime, default=get_kst_now)

    # 관계
    job_postings = relationship("JobPosting", back_populates="company")


class SkillTrend(Base):
    """스킬 트렌드 테이블"""
    __tablename__ = 'skill_trends'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    skill_name = Column(String(200), nullable=False)
    category = Column(String(100))  # hard_skill, soft_skill, tool, language
    
    # 통계
    mention_count = Column(Integer, default=0)
    job_category = Column(String(200))  # 해당 스킬이 많이 언급되는 직군
    trend_direction = Column(String(50))  # increasing, stable, decreasing
    
    # 분석 기간
    analysis_date = Column(DateTime, default=get_kst_now)
    period_start = Column(DateTime)
    period_end = Column(DateTime)


class CrawlResult(Base):
    """크롤링 결과 추적 테이블"""
    __tablename__ = 'crawl_results'

    id = Column(Integer, primary_key=True, autoincrement=True)
    crawl_date = Column(DateTime, default=get_kst_now, nullable=False)
    crawl_type = Column(String(50), nullable=False)  # 'jobs' or 'companies'
    source_site = Column(String(50))  # wanted, saramin, jobkorea 등
    keyword = Column(String(200))  # 검색 키워드

    # 크롤링 통계
    total_found = Column(Integer, default=0)  # 검색 결과 총 개수
    new_count = Column(Integer, default=0)  # 새로 추가된 공고
    existing_count = Column(Integer, default=0)  # 기존 공고 (업데이트)
    deleted_count = Column(Integer, default=0)  # 삭제된 공고 (이전 대비)

    # 상세 정보 (JSON)
    new_job_ids = Column(JSON)  # 새로 추가된 job_id 목록
    deleted_job_ids = Column(JSON)  # 삭제된 job_id 목록

    # 상태
    status = Column(String(50), default='completed')  # completed, failed
    error_message = Column(Text)
    duration_seconds = Column(Float)  # 크롤링 소요 시간


class MarketAnalysis(Base):
    """시장 분석 결과 테이블"""
    __tablename__ = 'market_analysis'

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_date = Column(DateTime, default=get_kst_now)
    keyword = Column(String(200))  # 분석 키워드

    # 분석 결과
    total_postings = Column(Integer)
    avg_salary_info = Column(Text)
    top_companies = Column(JSON)  # 상위 채용 기업
    top_skills = Column(JSON)  # 상위 요구 스킬

    # AI 분석 결과
    market_summary = Column(Text)  # 시장 요약
    trend_analysis = Column(Text)  # 트렌드 분석
    recommendations = Column(Text)  # 추천 사항
    llm_analysis = Column(Text)  # LLM 시장 트렌드 분석
    project_ideas = Column(Text)  # LLM 프로젝트 아이디어

    # 로드맵
    roadmap_3months = Column(Text)  # 3개월 로드맵
    roadmap_6months = Column(Text)  # 6개월 로드맵


class CompanyReview(Base):
    """회사 리뷰 테이블 (잡플래닛)"""
    __tablename__ = 'company_reviews'

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.id', ondelete='CASCADE'))
    company_name = Column(String(200), nullable=False)

    # 리뷰 식별
    source_site = Column(String(50), default='jobplanet')
    review_id = Column(String(100))

    # 작성자 정보
    job_category = Column(String(100))
    employment_status = Column(String(50))
    location = Column(String(100))
    write_date = Column(String(50))

    # 평점
    total_rating = Column(Float)
    category_scores = Column(JSON)  # 항목별 점수

    # 리뷰 내용
    title = Column(String(300))
    pros = Column(Text)
    cons = Column(Text)
    advice = Column(Text)

    # 추가 정보
    future_outlook = Column(String(200))
    recommendation = Column(String(100))

    # 메타
    crawled_at = Column(DateTime, default=get_kst_now)


class CompanyInterview(Base):
    """면접 후기 테이블 (잡플래닛)"""
    __tablename__ = 'company_interviews'

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.id', ondelete='CASCADE'))
    company_name = Column(String(200), nullable=False)

    # 면접 식별
    source_site = Column(String(50), default='jobplanet')
    interview_id = Column(String(100))

    # 면접 정보
    job_category = Column(String(100))
    position = Column(String(100))
    interview_date = Column(String(50))

    # 면접 상세
    difficulty = Column(String(50))
    route = Column(String(200))
    title = Column(String(300))
    question = Column(Text)
    answer = Column(Text)

    # 결과
    announcement_timing = Column(String(100))
    result = Column(String(100))
    experience = Column(String(100))

    # 메타
    crawled_at = Column(DateTime, default=get_kst_now)


class CompanyBenefit(Base):
    """복지 후기 테이블 (잡플래닛)"""
    __tablename__ = 'company_benefits'

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.id', ondelete='CASCADE'))
    company_name = Column(String(200), nullable=False)

    # 복지 식별
    source_site = Column(String(50), default='jobplanet')
    benefit_id = Column(String(100))

    # 카테고리 정보
    category = Column(String(100))
    category_rating = Column(Float)

    # 작성자 정보
    job_category = Column(String(100))
    employment_status = Column(String(50))
    location = Column(String(100))
    employment_type = Column(String(50))

    # 후기 내용
    content = Column(Text)
    item_scores = Column(JSON)

    # 메타
    crawled_at = Column(DateTime, default=get_kst_now)


class CompanySalary(Base):
    """연봉 정보 테이블 (잡플래닛)"""
    __tablename__ = 'company_salaries'

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.id', ondelete='CASCADE'))
    company_name = Column(String(200), nullable=False)

    # 연봉 식별
    source_site = Column(String(50), default='jobplanet')

    # 년차/직급 정보
    experience_year = Column(String(50))  # '1년차', '3년차' 등
    position = Column(String(100))  # 직급/직군

    # 연봉 정보
    salary_amount = Column(Integer)  # 연봉 (만원 단위)
    salary_text = Column(String(100))  # '4,500만원' 형태
    increase_rate = Column(String(50))  # 연봉 인상률

    # 통계 정보 (전체 평균일 경우)
    is_overall_avg = Column(Boolean, default=False)  # 전체 평균 여부
    industry_avg = Column(Integer)  # 업계 평균 (만원)
    industry_rank = Column(String(50))  # 업계 내 순위
    response_rate = Column(String(20))  # 응답률

    # 연봉 분포 (전체 평균일 경우)
    salary_min = Column(Integer)
    salary_lower = Column(Integer)
    salary_upper = Column(Integer)
    salary_max = Column(Integer)

    # 메타
    crawled_at = Column(DateTime, default=get_kst_now)


class CompanyNews(Base):
    """회사 뉴스 기사 테이블 (연합뉴스 등)"""
    __tablename__ = 'company_news'

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.id', ondelete='CASCADE'))
    company_name = Column(String(200), nullable=False)

    # 뉴스 식별
    source_site = Column(String(50), default='yna')  # 연합뉴스
    news_url = Column(String(500), nullable=False)
    news_id = Column(String(100))  # URL에서 추출한 기사 ID

    # 기사 기본 정보 (목록에서 수집)
    title = Column(String(500))
    published_at = Column(String(50))  # '2026-01-29 17:16'

    # 기사 상세 정보 (상세 페이지에서 수집)
    subtitle = Column(String(500))
    reporter_name = Column(String(100))
    content = Column(Text)

    # 메타
    crawled_at = Column(DateTime, default=get_kst_now)


class CompanyReport(Base):
    """기업 분석 보고서 테이블"""
    __tablename__ = 'company_reports'

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 회사 및 채용공고 연결
    company_id = Column(Integer, ForeignKey('companies.id', ondelete='SET NULL'))
    company_name = Column(String(200), nullable=False)
    job_posting_id = Column(Integer)  # FK 제거 (스키마 호환성)

    # 보고서 메타데이터
    report_version = Column(String(20), default='v4')
    llm_provider = Column(String(50))
    llm_model = Column(String(100))

    # 분석 결과
    verdict = Column(String(50))  # Go, Conditional Go, No-Go
    total_score = Column(Numeric(3, 2))  # 0.00 ~ 5.00
    scores = Column(JSON)  # 개별 평가축 점수

    # 핵심 요약
    key_attractions = Column(JSON)  # 핵심 매력 포인트 (배열)
    key_risks = Column(JSON)  # 핵심 리스크 (배열)
    verification_items = Column(JSON)  # [확인 필요] 항목 (배열)

    # 보고서 본문
    full_markdown = Column(Text)
    full_html = Column(Text)

    # Quality Gate 결과
    quality_passed = Column(Boolean, default=False)
    quality_details = Column(JSON)

    # 데이터 소스 정보
    data_sources = Column(JSON)

    # 지원자 컨텍스트 (선택)
    applicant_profile = Column(JSON)
    priority_weights = Column(JSON)

    # 캐시 관리
    cache_key = Column(String(255), unique=True)
    cache_expires_at = Column(DateTime)

    # 타임스탬프
    generated_at = Column(DateTime, default=get_kst_now)
    created_at = Column(DateTime, default=get_kst_now)
    updated_at = Column(DateTime, default=get_kst_now)


class Database:
    """데이터베이스 관리 클래스"""

    def __init__(self, connection_string: Optional[str] = None):
        conn_str = connection_string or settings.database.connection_string
        self.engine = create_engine(
            conn_str,
            echo=False,
            pool_pre_ping=True
        )
        self.Session = sessionmaker(bind=self.engine)
    
    def create_tables(self):
        """테이블 생성"""
        Base.metadata.create_all(self.engine)
    
    def get_session(self):
        """세션 반환"""
        return self.Session()
    
    def add_job_posting(self, job_data: dict) -> JobPosting:
        """채용공고 추가"""
        session = self.get_session()
        try:
            # JobPosting 모델에 있는 필드만 필터링
            valid_fields = {c.name for c in JobPosting.__table__.columns}
            filtered_data = {k: v for k, v in job_data.items() if k in valid_fields}

            # 중복 체크
            existing = session.query(JobPosting).filter_by(
                source_site=filtered_data.get('source_site'),
                job_id=filtered_data.get('job_id')
            ).first()

            if existing:
                # 업데이트
                for key, value in filtered_data.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
                existing.crawled_at = get_kst_now()
                session.commit()
                session.refresh(existing)
                session.expunge(existing)
                return existing
            else:
                # 새로 추가
                job = JobPosting(**filtered_data)
                session.add(job)
                session.commit()
                session.refresh(job)
                session.expunge(job)
                return job
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    
    def add_company(self, company_data: dict) -> Company:
        """회사 정보 추가/업데이트"""
        session = self.get_session()
        try:
            existing = session.query(Company).filter_by(
                name=company_data.get('name')
            ).first()
            
            if existing:
                for key, value in company_data.items():
                    if hasattr(existing, key) and value is not None:
                        setattr(existing, key, value)
                existing.updated_at = get_kst_now()
                session.commit()
                return existing
            else:
                company = Company(**company_data)
                session.add(company)
                session.commit()
                return company
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    
    def get_job_postings(
        self,
        keyword: Optional[str] = None,
        source_site: Optional[str] = None,
        days: int = 7
    ) -> List[JobPosting]:
        """채용공고 조회"""
        session = self.get_session()
        try:
            query = session.query(JobPosting)
            
            if keyword:
                query = query.filter(
                    (JobPosting.title.contains(keyword)) |
                    (JobPosting.description.contains(keyword))
                )
            
            if source_site:
                query = query.filter(JobPosting.source_site == source_site)
            
            # 최근 N일 데이터
            from datetime import timedelta
            cutoff = get_kst_now() - timedelta(days=days)
            query = query.filter(JobPosting.crawled_at >= cutoff)
            
            return query.all()
        finally:
            session.close()
    
    def get_companies(self) -> List[Company]:
        """모든 회사 조회"""
        session = self.get_session()
        try:
            return session.query(Company).all()
        finally:
            session.close()
    
    def save_market_analysis(self, analysis_data: dict) -> MarketAnalysis:
        """시장 분석 결과 저장"""
        session = self.get_session()
        try:
            analysis = MarketAnalysis(**analysis_data)
            session.add(analysis)
            session.commit()
            return analysis
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    
    def get_latest_analysis(self, keyword: str) -> Optional[MarketAnalysis]:
        """최신 분석 결과 조회"""
        session = self.get_session()
        try:
            return session.query(MarketAnalysis)\
                .filter(MarketAnalysis.keyword == keyword)\
                .order_by(MarketAnalysis.analysis_date.desc())\
                .first()
        finally:
            session.close()

    def get_active_job_ids(self, source_site: str, days: int = 1) -> set:
        """특정 사이트의 활성 job_id 목록 조회 (최근 N일 내 크롤링된)"""
        session = self.get_session()
        try:
            from datetime import timedelta
            cutoff = get_kst_now() - timedelta(days=days)
            result = session.query(JobPosting.job_id).filter(
                JobPosting.source_site == source_site,
                JobPosting.status == '모집중',
                JobPosting.crawled_at >= cutoff
            ).all()
            return {str(row[0]) for row in result if row[0]}
        finally:
            session.close()

    def get_all_active_job_ids(self, source_site: str) -> set:
        """특정 사이트의 모든 활성 job_id 목록 조회"""
        session = self.get_session()
        try:
            result = session.query(JobPosting.job_id).filter(
                JobPosting.source_site == source_site,
                JobPosting.status == '모집중'
            ).all()
            return {str(row[0]) for row in result if row[0]}
        finally:
            session.close()

    def mark_jobs_as_closed(self, source_site: str, job_ids: List[str]) -> int:
        """특정 job_id들을 마감 처리"""
        if not job_ids:
            return 0
        session = self.get_session()
        try:
            updated = session.query(JobPosting).filter(
                JobPosting.source_site == source_site,
                JobPosting.job_id.in_(job_ids)
            ).update({JobPosting.status: '마감'}, synchronize_session=False)
            session.commit()
            return updated
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def save_crawl_result(self, crawl_data: dict) -> CrawlResult:
        """크롤링 결과 저장"""
        session = self.get_session()
        try:
            crawl_result = CrawlResult(**crawl_data)
            session.add(crawl_result)
            session.commit()
            return crawl_result
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_unique_companies_from_postings(self) -> List[str]:
        """채용공고에서 고유 회사명 목록 조회"""
        session = self.get_session()
        try:
            result = session.query(JobPosting.company_name).distinct().all()
            return [name[0] for name in result if name[0]]
        finally:
            session.close()

    def get_companies_without_info(self, include_incomplete: bool = True) -> List[str]:
        """잡플래닛 정보가 없거나 불완전한 회사 목록 조회

        Args:
            include_incomplete: True이면 불완전한 회사도 포함 (재수집 대상)
                - jobplanet_rating이 NULL인 회사
                - jobplanet_url이 NULL 또는 빈 문자열인 회사

        Returns:
            수집이 필요한 회사명 목록
        """
        session = self.get_session()
        try:
            from sqlalchemy import or_

            # 채용공고에 있는 모든 회사
            all_companies = session.query(JobPosting.company_name).distinct().all()
            all_company_names = set(name[0] for name in all_companies if name[0])

            # 완전한 정보가 있는 회사 (jobplanet_rating과 jobplanet_url 모두 있는 경우)
            complete = session.query(Company.name).filter(
                Company.jobplanet_rating.isnot(None),
                Company.jobplanet_url.isnot(None),
                Company.jobplanet_url != ''
            ).all()
            complete_names = set(name[0] for name in complete if name[0])

            if include_incomplete:
                # 불완전한 정보 회사도 재수집 대상에 포함
                # (jobplanet_rating이 NULL이거나 jobplanet_url이 NULL/빈 문자열인 경우)
                incomplete = session.query(Company.name).filter(
                    or_(
                        Company.jobplanet_rating.is_(None),
                        Company.jobplanet_url.is_(None),
                        Company.jobplanet_url == ''
                    )
                ).all()
                incomplete_names = set(name[0] for name in incomplete if name[0])

                # 완전한 정보가 있는 회사만 제외
                missing = all_company_names - complete_names
            else:
                # 기존 동작: Company 테이블에 있는 모든 회사 제외
                existing = session.query(Company.name).all()
                existing_names = set(name[0] for name in existing if name[0])
                missing = all_company_names - existing_names

            return list(missing)
        finally:
            session.close()

    def add_company_reviews(self, company_name: str, reviews: List[dict], company_id: Optional[int] = None) -> int:
        """회사 리뷰 추가/업데이트 (잡플래닛)

        Args:
            company_name: 회사명
            reviews: 리뷰 데이터 리스트
            company_id: 회사 ID (선택)

        Returns:
            추가/업데이트된 리뷰 수
        """
        if not reviews:
            return 0

        session = self.get_session()
        count = 0
        try:
            for review_data in reviews:
                # 필드명 매핑 (크롤링 데이터 -> DB 컬럼)
                review_id = review_data.get('review_id') or review_data.get('id')
                job_category = review_data.get('job_category') or review_data.get('job')
                source_site = review_data.get('source_site', 'jobplanet')

                existing = None
                if review_id:
                    existing = session.query(CompanyReview).filter_by(
                        source_site=source_site,
                        review_id=str(review_id)
                    ).first()

                if existing:
                    # 업데이트
                    for key, value in review_data.items():
                        if hasattr(existing, key) and value is not None:
                            setattr(existing, key, value)
                    existing.crawled_at = get_kst_now()
                else:
                    # 새로 추가
                    review = CompanyReview(
                        company_id=company_id,
                        company_name=company_name,
                        source_site=source_site,
                        review_id=str(review_id) if review_id else None,
                        job_category=job_category,
                        employment_status=review_data.get('employment_status'),
                        location=review_data.get('location'),
                        write_date=review_data.get('write_date'),
                        total_rating=review_data.get('total_rating'),
                        category_scores=review_data.get('category_scores'),
                        title=review_data.get('title'),
                        pros=review_data.get('pros'),
                        cons=review_data.get('cons'),
                        advice=review_data.get('advice'),
                        future_outlook=review_data.get('future_outlook'),
                        recommendation=review_data.get('recommendation')
                    )
                    session.add(review)
                count += 1

            session.commit()
            return count
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def add_company_interviews(self, company_name: str, interviews: List[dict], company_id: Optional[int] = None) -> int:
        """면접 후기 추가/업데이트 (잡플래닛)

        Args:
            company_name: 회사명
            interviews: 면접 후기 데이터 리스트
            company_id: 회사 ID (선택)

        Returns:
            추가/업데이트된 면접 후기 수
        """
        if not interviews:
            return 0

        session = self.get_session()
        count = 0
        try:
            for interview_data in interviews:
                # 필드명 매핑 (크롤링 데이터 -> DB 컬럼)
                interview_id = interview_data.get('interview_id') or interview_data.get('id')
                job_category = interview_data.get('job_category') or interview_data.get('job')
                interview_date = interview_data.get('interview_date') or interview_data.get('date')
                source_site = interview_data.get('source_site', 'jobplanet')

                existing = None
                if interview_id:
                    existing = session.query(CompanyInterview).filter_by(
                        source_site=source_site,
                        interview_id=str(interview_id)
                    ).first()

                if existing:
                    # 업데이트
                    for key, value in interview_data.items():
                        if hasattr(existing, key) and value is not None:
                            setattr(existing, key, value)
                    existing.crawled_at = get_kst_now()
                else:
                    # 새로 추가
                    interview = CompanyInterview(
                        company_id=company_id,
                        company_name=company_name,
                        source_site=source_site,
                        interview_id=str(interview_id) if interview_id else None,
                        job_category=job_category,
                        position=interview_data.get('position'),
                        interview_date=interview_date,
                        difficulty=interview_data.get('difficulty'),
                        route=interview_data.get('route'),
                        title=interview_data.get('title'),
                        question=interview_data.get('question'),
                        answer=interview_data.get('answer'),
                        announcement_timing=interview_data.get('announcement_timing'),
                        result=interview_data.get('result'),
                        experience=interview_data.get('experience')
                    )
                    session.add(interview)
                count += 1

            session.commit()
            return count
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def add_company_benefits(self, company_name: str, benefits: List[dict], company_id: Optional[int] = None) -> int:
        """복지 후기 추가/업데이트 (잡플래닛)

        Args:
            company_name: 회사명
            benefits: 복지 후기 데이터 리스트
            company_id: 회사 ID (선택)

        Returns:
            추가/업데이트된 복지 후기 수
        """
        if not benefits:
            return 0

        session = self.get_session()
        count = 0
        try:
            for benefit_data in benefits:
                # 필드명 매핑 (profile 내부 필드 추출)
                profile = benefit_data.get('profile', {})
                job_category = benefit_data.get('job_category') or profile.get('job')
                employment_status = benefit_data.get('employment_status') or profile.get('employment_status')
                location = benefit_data.get('location') or profile.get('location')
                employment_type = benefit_data.get('employment_type') or profile.get('employment_type')

                benefit_id = benefit_data.get('benefit_id')
                source_site = benefit_data.get('source_site', 'jobplanet')

                existing = None
                if benefit_id:
                    existing = session.query(CompanyBenefit).filter_by(
                        source_site=source_site,
                        benefit_id=str(benefit_id)
                    ).first()

                if existing:
                    # 업데이트
                    for key, value in benefit_data.items():
                        if hasattr(existing, key) and value is not None:
                            setattr(existing, key, value)
                    existing.crawled_at = get_kst_now()
                else:
                    # 새로 추가 (복지 후기는 benefit_id가 없는 경우가 많음)
                    benefit = CompanyBenefit(
                        company_id=company_id,
                        company_name=company_name,
                        source_site=source_site,
                        benefit_id=str(benefit_id) if benefit_id else None,
                        category=benefit_data.get('category'),
                        category_rating=benefit_data.get('category_rating'),
                        job_category=job_category,
                        employment_status=employment_status,
                        location=location,
                        employment_type=employment_type,
                        content=benefit_data.get('content'),
                        item_scores=benefit_data.get('item_scores')
                    )
                    session.add(benefit)
                count += 1

            session.commit()
            return count
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_company_id_by_name(self, company_name: str) -> Optional[int]:
        """회사명으로 company_id 조회"""
        session = self.get_session()
        try:
            company = session.query(Company).filter_by(name=company_name).first()
            return company.id if company else None
        finally:
            session.close()

    def add_company_salaries(self, company_name: str, salary_data: dict, company_id: Optional[int] = None) -> int:
        """회사 연봉 정보 저장

        Args:
            company_name: 회사명
            salary_data: 연봉 데이터 (overall_avg, by_year, salary_distribution 등)
            company_id: companies 테이블의 ID (없으면 조회)

        Returns:
            저장된 연봉 정보 개수
        """
        session = self.get_session()
        try:
            if not company_id:
                company_id = self.get_company_id_by_name(company_name)

            count = 0
            source_site = 'jobplanet'

            # 기존 데이터 삭제 (전체 갱신)
            session.query(CompanySalary).filter_by(
                company_name=company_name,
                source_site=source_site
            ).delete()

            # 1. 전체 평균 연봉 저장
            if salary_data.get('overall_avg'):
                # 숫자 추출 (예: "4,500만원" -> 4500)
                avg_text = salary_data['overall_avg']
                avg_amount = None
                import re
                amount_match = re.search(r'([\d,]+)', avg_text)
                if amount_match:
                    avg_amount = int(amount_match.group(1).replace(',', ''))

                dist = salary_data.get('salary_distribution', {})
                overall = CompanySalary(
                    company_id=company_id,
                    company_name=company_name,
                    source_site=source_site,
                    is_overall_avg=True,
                    salary_amount=avg_amount,
                    salary_text=avg_text,
                    industry_avg=self._parse_salary_amount(salary_data.get('industry_avg')),
                    industry_rank=salary_data.get('industry_rank'),
                    response_rate=salary_data.get('response_rate'),
                    salary_min=self._parse_salary_amount(dist.get('min')),
                    salary_lower=self._parse_salary_amount(dist.get('lower')),
                    salary_upper=self._parse_salary_amount(dist.get('upper')),
                    salary_max=self._parse_salary_amount(dist.get('max'))
                )
                session.add(overall)
                count += 1

            # 2. 년차별 연봉 저장
            for year_data in salary_data.get('by_year', []):
                salary_text = year_data.get('salary', '')
                salary_amount = self._parse_salary_amount(salary_text)

                year_salary = CompanySalary(
                    company_id=company_id,
                    company_name=company_name,
                    source_site=source_site,
                    is_overall_avg=False,
                    experience_year=year_data.get('year'),
                    salary_amount=salary_amount,
                    salary_text=salary_text,
                    increase_rate=year_data.get('increase_rate')
                )
                session.add(year_salary)
                count += 1

            # 3. 직급별 연봉 저장 (by_position이 by_year와 다른 경우)
            for pos_data in salary_data.get('by_position_detail', []):
                salary_text = pos_data.get('salary', '')
                salary_amount = self._parse_salary_amount(salary_text)

                pos_salary = CompanySalary(
                    company_id=company_id,
                    company_name=company_name,
                    source_site=source_site,
                    is_overall_avg=False,
                    position=pos_data.get('position'),
                    salary_amount=salary_amount,
                    salary_text=salary_text
                )
                session.add(pos_salary)
                count += 1

            session.commit()
            return count
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def _parse_salary_amount(self, salary_str) -> Optional[int]:
        """연봉 문자열에서 숫자 추출 (만원 단위)"""
        if not salary_str:
            return None
        import re
        # "4,500만원", "4500", "4,500" 등에서 숫자 추출
        if isinstance(salary_str, (int, float)):
            return int(salary_str)
        match = re.search(r'([\d,]+)', str(salary_str))
        if match:
            return int(match.group(1).replace(',', ''))
        return None

    def add_company_news(self, company_name: str, news_list: List[dict], company_id: Optional[int] = None) -> dict:
        """회사 뉴스 기사 저장 (회사 단위로 저장, 중복 방지)

        Args:
            company_name: 회사명
            news_list: 뉴스 기사 목록 [{news_url, title, published_at, subtitle, reporter_name, content}, ...]
            company_id: companies 테이블의 ID (없으면 조회)

        Returns:
            저장 결과 {new_count, duplicate_count, updated_count}
        """
        session = self.get_session()
        try:
            if not company_id:
                company_id = self.get_company_id_by_name(company_name)

            import re
            source_site = 'yna'  # 연합뉴스
            new_count = 0
            duplicate_count = 0
            updated_count = 0

            for news_data in news_list:
                news_url = news_data.get('news_url') or news_data.get('url')
                if not news_url:
                    continue

                # URL에서 뉴스 ID 추출 (예: AKR20260129166300017)
                news_id = None
                id_match = re.search(r'/view/([A-Z0-9]+)', news_url)
                if id_match:
                    news_id = id_match.group(1)

                # 중복 체크 (news_url 기준)
                existing = session.query(CompanyNews).filter_by(
                    source_site=source_site,
                    news_url=news_url
                ).first()

                if existing:
                    # 이미 존재하는 기사
                    if news_data.get('content') and not existing.content:
                        # 상세 정보가 없었으면 업데이트
                        existing.content = news_data['content']
                        existing.subtitle = news_data.get('subtitle')
                        existing.reporter_name = news_data.get('reporter_name')
                        existing.crawled_at = get_kst_now()
                        updated_count += 1
                    else:
                        duplicate_count += 1
                else:
                    # 새로 추가
                    news = CompanyNews(
                        company_id=company_id,
                        company_name=company_name,
                        source_site=source_site,
                        news_url=news_url,
                        news_id=news_id,
                        title=news_data.get('title'),
                        published_at=news_data.get('published_at'),
                        subtitle=news_data.get('subtitle'),
                        reporter_name=news_data.get('reporter_name'),
                        content=news_data.get('content')
                    )
                    session.add(news)
                    new_count += 1

            session.commit()
            return {
                'new_count': new_count,
                'duplicate_count': duplicate_count,
                'updated_count': updated_count,
                'total': new_count + duplicate_count + updated_count
            }
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_companies_for_news_crawling(self, limit: int = 100, only_no_news: bool = False) -> List[str]:
        """뉴스 크롤링이 필요한 회사 목록 조회 (1차 크롤링 기준)

        1차 크롤링(채용공고)에서 수집된 회사들 중 뉴스가 없거나 오래된 회사를 대상으로 합니다.

        Args:
            limit: 최대 회사 수
            only_no_news: True이면 뉴스가 0건인 회사만 반환

        Returns:
            회사명 목록
        """
        session = self.get_session()
        try:
            from sqlalchemy import func, distinct

            # 1차 크롤링으로 수집된 회사들 (채용공고가 있는 회사)
            companies_with_jobs = session.query(
                JobPosting.company_name.label('name')
            ).distinct().subquery()

            # 뉴스가 있는 회사와 최근 크롤링 일시
            news_subquery = session.query(
                CompanyNews.company_name,
                func.max(CompanyNews.crawled_at).label('last_crawled'),
                func.count(CompanyNews.id).label('news_count')
            ).group_by(CompanyNews.company_name).subquery()

            # 기본 쿼리
            query = session.query(Company.name).join(
                companies_with_jobs,
                Company.name == companies_with_jobs.c.name
            ).outerjoin(
                news_subquery,
                Company.name == news_subquery.c.company_name
            )

            if only_no_news:
                # 뉴스가 0건인 회사만 (한번도 수집 안됐거나 결과가 없었던 회사)
                query = query.filter(news_subquery.c.news_count.is_(None))

            # 뉴스 없는 회사 우선으로 정렬
            companies = query.order_by(
                news_subquery.c.last_crawled.asc().nullsfirst()
            ).limit(limit).all()

            return [c[0] for c in companies]
        finally:
            session.close()

    def get_existing_news_urls(self, company_name: str) -> set:
        """회사의 기존 뉴스 URL 목록 조회

        Args:
            company_name: 회사명

        Returns:
            기존 뉴스 URL 세트
        """
        session = self.get_session()
        try:
            urls = session.query(CompanyNews.news_url).filter(
                CompanyNews.company_name == company_name
            ).all()
            return {url[0] for url in urls}
        finally:
            session.close()


# 전역 데이터베이스 인스턴스
db = Database()
