"""
데이터베이스 관리 모듈
SQLite (로컬) 및 PostgreSQL (클라우드) 지원
"""

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, JSON, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from typing import Optional, List
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

    # 메타
    url = Column(String(500))
    crawled_at = Column(DateTime, default=datetime.now)
    posted_at = Column(DateTime)
    expires_at = Column(DateTime)
    is_active = Column(Boolean, default=True)

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
    
    # 상세 정보
    description = Column(Text)
    website = Column(String(300))
    address = Column(String(500))
    
    # 평판 정보
    glassdoor_rating = Column(Float)
    jobplanet_rating = Column(Float)
    blind_summary = Column(Text)  # 블라인드 요약
    news_summary = Column(Text)  # 뉴스 요약
    public_sentiment = Column(Text)  # 대중 평가 요약
    
    # 재무 정보 (사업자 조회 결과)
    revenue = Column(String(100))
    employee_count = Column(Integer)
    
    # 메타
    last_updated = Column(DateTime, default=datetime.now)
    
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
    analysis_date = Column(DateTime, default=datetime.now)
    period_start = Column(DateTime)
    period_end = Column(DateTime)


class MarketAnalysis(Base):
    """시장 분석 결과 테이블"""
    __tablename__ = 'market_analysis'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_date = Column(DateTime, default=datetime.now)
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
    
    # 로드맵
    roadmap_3months = Column(Text)  # 3개월 로드맵
    roadmap_6months = Column(Text)  # 6개월 로드맵


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
                existing.crawled_at = datetime.now()
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
                existing.last_updated = datetime.now()
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
            cutoff = datetime.now() - timedelta(days=days)
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


# 전역 데이터베이스 인스턴스
db = Database()
