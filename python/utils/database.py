"""
데이터베이스 관리 모듈
SQLite (로컬) 및 PostgreSQL (클라우드) 지원
"""

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, JSON, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
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
            include_incomplete: True이면 jobplanet_rating이 NULL인 회사도 포함 (재수집 대상)

        Returns:
            수집이 필요한 회사명 목록
        """
        session = self.get_session()
        try:
            # 채용공고에 있는 모든 회사
            all_companies = session.query(JobPosting.company_name).distinct().all()
            all_company_names = set(name[0] for name in all_companies if name[0])

            # 완전한 정보가 있는 회사 (jobplanet_rating이 있는 경우)
            complete = session.query(Company.name).filter(
                Company.jobplanet_rating.isnot(None)
            ).all()
            complete_names = set(name[0] for name in complete if name[0])

            if include_incomplete:
                # 불완전한 정보 회사도 재수집 (jobplanet_rating이 NULL인 경우)
                incomplete = session.query(Company.name).filter(
                    Company.jobplanet_rating.is_(None)
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


# 전역 데이터베이스 인스턴스
db = Database()
