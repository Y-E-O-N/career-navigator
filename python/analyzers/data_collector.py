"""
기업 분석용 데이터 수집 모듈

9개의 데이터 소스(A~I)를 Supabase에서 수집하여
AnalysisDataBundle로 반환합니다.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import logging

from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from utils.database import (
    Database, Company, JobPosting, CompanyReview, CompanyInterview,
    CompanyBenefit, CompanySalary, CompanyNews, MarketAnalysis, SkillTrend,
    get_kst_now
)
from analyzers.models import AnalysisDataBundle

logger = logging.getLogger(__name__)


class CompanyDataCollector:
    """기업 분석에 필요한 9개 데이터 소스 수집"""

    def __init__(self, db: Database):
        self.db = db
        self.executor = ThreadPoolExecutor(max_workers=5)

    def collect_all_sources(
        self,
        company_name: str,
        job_posting_id: Optional[int] = None,
        include_market_data: bool = True,
        news_months: int = 12,
        review_months: int = 24
    ) -> AnalysisDataBundle:
        """
        모든 데이터 소스 수집 (동기 버전)

        Args:
            company_name: 회사명
            job_posting_id: 특정 채용공고 ID (미지정 시 전체 공고)
            include_market_data: 시장 분석/스킬 트렌드 포함 여부
            news_months: 뉴스 수집 기간 (개월)
            review_months: 리뷰 수집 기간 (개월)

        Returns:
            AnalysisDataBundle: 모든 소스 데이터를 담은 데이터 번들
        """
        bundle = AnalysisDataBundle(company_name=company_name)

        session = self.db.get_session()
        try:
            # 1. 회사 ID 조회
            company = session.query(Company).filter(
                Company.name == company_name
            ).first()

            if not company:
                logger.warning(f"회사를 찾을 수 없음: {company_name}")
                return bundle

            company_id = company.id
            bundle.company_id = company_id

            # 2. 소스 A: 기업 기본정보
            bundle.company_info = self._collect_company_info(session, company)
            logger.info(f"[A] 기업 기본정보 수집 완료")

            # 3. 소스 B: 채용공고 (company_id로 먼저 찾고, 없으면 company_name으로 찾기)
            bundle.job_postings = self._collect_job_postings(
                session, company_id, job_posting_id
            )

            # company_id로 못 찾으면 company_name으로 재시도
            if not bundle.job_postings:
                bundle.job_postings = self._collect_job_postings_by_name(
                    session, company_name
                )

            logger.info(f"[B] 채용공고 {len(bundle.job_postings)}건 수집")

            if job_posting_id:
                bundle.target_job_posting_id = job_posting_id

            # 4. 소스 C: 재직자 후기
            bundle.reviews = self._collect_reviews(
                session, company_id, months=review_months
            )
            logger.info(f"[C] 재직자 후기 {len(bundle.reviews) if bundle.reviews else 0}건 수집")

            # 5. 소스 D: 면접 후기
            bundle.interviews = self._collect_interviews(
                session, company_id, months=review_months
            )
            logger.info(f"[D] 면접 후기 {len(bundle.interviews) if bundle.interviews else 0}건 수집")

            # 6. 소스 E: 급여 정보
            bundle.salaries = self._collect_salaries(session, company_id)
            logger.info(f"[E] 급여 정보 {len(bundle.salaries) if bundle.salaries else 0}건 수집")

            # 7. 소스 F: 복리후생
            bundle.benefits = self._collect_benefits(session, company_id)
            logger.info(f"[F] 복리후생 {len(bundle.benefits) if bundle.benefits else 0}건 수집")

            # 8. 소스 G: 뉴스 기사
            bundle.news = self._collect_news(
                session, company_id, months=news_months
            )
            logger.info(f"[G] 뉴스 기사 {len(bundle.news) if bundle.news else 0}건 수집")

            # 9. 소스 H, I: 시장 분석 및 스킬 트렌드 (선택)
            if include_market_data and bundle.job_postings:
                # 채용공고에서 직무 카테고리 추출
                job_categories = list(set(
                    jp.get('job_category') for jp in bundle.job_postings
                    if jp.get('job_category')
                ))

                if job_categories:
                    bundle.market_analysis = self._collect_market_analysis(
                        session, job_categories[0]  # 첫 번째 카테고리 기준
                    )
                    logger.info(f"[H] 시장 분석 {'수집 완료' if bundle.market_analysis else '데이터 없음'}")

                # 스킬 트렌드 (JD에서 스킬 추출 후 매칭)
                all_skills = self._extract_skills_from_postings(bundle.job_postings)
                if all_skills:
                    bundle.skill_trends = self._collect_skill_trends(
                        session, all_skills
                    )
                    logger.info(f"[I] 스킬 트렌드 {len(bundle.skill_trends) if bundle.skill_trends else 0}건 수집")

            bundle.collected_at = get_kst_now()
            return bundle

        except Exception as e:
            logger.error(f"데이터 수집 중 오류: {e}")
            raise
        finally:
            session.close()

    def _collect_company_info(self, session: Session, company: Company) -> dict:
        """소스 A: 기업 기본정보 수집"""
        return {
            "id": company.id,
            "name": company.name,
            "industry": company.industry,
            "company_size": company.company_size,
            "founded_year": company.founded_year,
            "location": company.location,
            "description": company.description,
            "website": company.website,
            "address": company.address,
            "jobplanet_rating": company.jobplanet_rating,
            "jobplanet_url": company.jobplanet_url,
            "employee_count": company.employee_count,
            "revenue": company.revenue,
            "updated_at": company.updated_at.isoformat() if company.updated_at else None,
        }

    def _collect_job_postings(
        self,
        session: Session,
        company_id: int,
        job_posting_id: Optional[int] = None,
        include_closed: bool = True
    ) -> List[dict]:
        """소스 B: 채용공고 수집"""
        query = session.query(JobPosting).filter(
            JobPosting.company_id == company_id
        )

        # 마감되지 않은 공고만 필터 (기본: 마감 공고도 포함)
        if not include_closed:
            query = query.filter(JobPosting.status == '모집중')

        if job_posting_id:
            # 특정 공고 + 같은 회사의 다른 공고도 함께 (교차 분석용)
            target = session.query(JobPosting).filter(
                JobPosting.id == job_posting_id
            ).first()
            if target:
                # 타겟 공고를 첫 번째로
                others = query.filter(JobPosting.id != job_posting_id).order_by(
                    desc(JobPosting.crawled_at)
                ).limit(9).all()  # 최대 10개
                jobs = [target] + others
            else:
                jobs = query.order_by(desc(JobPosting.crawled_at)).limit(10).all()
        else:
            jobs = query.order_by(desc(JobPosting.crawled_at)).limit(10).all()

        return [self._job_to_dict(job) for job in jobs]

    def _collect_job_postings_by_name(
        self,
        session: Session,
        company_name: str
    ) -> List[dict]:
        """소스 B: 채용공고 수집 (회사명 기준)"""
        jobs = session.query(JobPosting).filter(
            JobPosting.company_name == company_name
        ).order_by(desc(JobPosting.crawled_at)).limit(10).all()

        return [self._job_to_dict(job) for job in jobs]

    def _job_to_dict(self, job: JobPosting) -> dict:
        """JobPosting ORM 객체를 dict로 변환"""
        return {
            "id": job.id,
            "title": job.title,
            "job_category": job.job_category,
            "position_level": job.position_level,
            "employment_type": job.employment_type,
            "description": job.description,
            "requirements": job.requirements,
            "preferred": job.preferred,
            "required_skills": job.required_skills or [],
            "preferred_skills": job.preferred_skills or [],
            "salary_info": job.salary_info,
            "location": job.location,
            "experience_level": job.experience_level,
            "main_tasks": job.main_tasks,
            "company_tags": job.company_tags,
            "deadline": job.deadline,
            "url": job.url,
            "source_site": job.source_site,
            "crawled_at": job.crawled_at.isoformat() if job.crawled_at else None,
        }

    def _collect_reviews(
        self,
        session: Session,
        company_id: int,
        months: int = 24
    ) -> Optional[List[dict]]:
        """소스 C: 재직자 후기 수집 (KST 기준)"""
        cutoff = get_kst_now() - timedelta(days=months * 30)

        reviews = session.query(CompanyReview).filter(
            CompanyReview.company_id == company_id,
            CompanyReview.crawled_at >= cutoff
        ).order_by(desc(CompanyReview.crawled_at)).limit(100).all()

        if not reviews:
            # 기간 제한 없이 전체 조회
            reviews = session.query(CompanyReview).filter(
                CompanyReview.company_id == company_id
            ).order_by(desc(CompanyReview.crawled_at)).limit(100).all()

        if not reviews:
            return None

        return [{
            "id": r.id,
            "job_category": r.job_category,
            "employment_status": r.employment_status,
            "location": r.location,
            "write_date": r.write_date,
            "total_rating": r.total_rating,
            "category_scores": r.category_scores,
            "title": r.title,
            "pros": r.pros,
            "cons": r.cons,
            "advice": r.advice,
            "future_outlook": r.future_outlook,
            "recommendation": r.recommendation,
            "source_site": r.source_site,
            "crawled_at": r.crawled_at.isoformat() if r.crawled_at else None,
        } for r in reviews]

    def _collect_interviews(
        self,
        session: Session,
        company_id: int,
        months: int = 24
    ) -> Optional[List[dict]]:
        """소스 D: 면접 후기 수집 (KST 기준)"""
        cutoff = get_kst_now() - timedelta(days=months * 30)

        interviews = session.query(CompanyInterview).filter(
            CompanyInterview.company_id == company_id,
            CompanyInterview.crawled_at >= cutoff
        ).order_by(desc(CompanyInterview.crawled_at)).limit(50).all()

        if not interviews:
            interviews = session.query(CompanyInterview).filter(
                CompanyInterview.company_id == company_id
            ).order_by(desc(CompanyInterview.crawled_at)).limit(50).all()

        if not interviews:
            return None

        return [{
            "id": i.id,
            "job_category": i.job_category,
            "position": i.position,
            "interview_date": i.interview_date,
            "difficulty": i.difficulty,
            "route": i.route,
            "title": i.title,
            "question": i.question,
            "answer": i.answer,
            "announcement_timing": i.announcement_timing,
            "result": i.result,
            "experience": i.experience,
            "source_site": i.source_site,
            "crawled_at": i.crawled_at.isoformat() if i.crawled_at else None,
        } for i in interviews]

    def _collect_salaries(
        self,
        session: Session,
        company_id: int
    ) -> Optional[List[dict]]:
        """소스 E: 급여 정보 수집"""
        salaries = session.query(CompanySalary).filter(
            CompanySalary.company_id == company_id
        ).order_by(CompanySalary.experience_year).all()

        if not salaries:
            return None

        return [{
            "id": s.id,
            "experience_year": s.experience_year,
            "position": s.position,
            "salary_amount": s.salary_amount,
            "salary_text": s.salary_text,
            "increase_rate": s.increase_rate,
            "is_overall_avg": s.is_overall_avg,
            "industry_avg": s.industry_avg,
            "industry_rank": s.industry_rank,
            "salary_min": s.salary_min,
            "salary_max": s.salary_max,
            "salary_lower": s.salary_lower,
            "salary_upper": s.salary_upper,
            "source_site": s.source_site,
            "crawled_at": s.crawled_at.isoformat() if s.crawled_at else None,
        } for s in salaries]

    def _collect_benefits(
        self,
        session: Session,
        company_id: int
    ) -> Optional[List[dict]]:
        """소스 F: 복리후생 수집"""
        benefits = session.query(CompanyBenefit).filter(
            CompanyBenefit.company_id == company_id
        ).order_by(CompanyBenefit.category).all()

        if not benefits:
            return None

        return [{
            "id": b.id,
            "category": b.category,
            "category_rating": b.category_rating,
            "job_category": b.job_category,
            "employment_status": b.employment_status,
            "location": b.location,
            "employment_type": b.employment_type,
            "content": b.content,
            "item_scores": b.item_scores,
            "source_site": b.source_site,
            "crawled_at": b.crawled_at.isoformat() if b.crawled_at else None,
        } for b in benefits]

    def _collect_news(
        self,
        session: Session,
        company_id: int,
        months: int = 12
    ) -> Optional[List[dict]]:
        """소스 G: 뉴스 기사 수집 (KST 기준)"""
        cutoff = get_kst_now() - timedelta(days=months * 30)

        news = session.query(CompanyNews).filter(
            CompanyNews.company_id == company_id,
            CompanyNews.crawled_at >= cutoff
        ).order_by(desc(CompanyNews.published_at)).limit(50).all()

        if not news:
            news = session.query(CompanyNews).filter(
                CompanyNews.company_id == company_id
            ).order_by(desc(CompanyNews.published_at)).limit(50).all()

        if not news:
            return None

        return [{
            "id": n.id,
            "title": n.title,
            "subtitle": n.subtitle,
            "content": n.content[:500] if n.content else None,  # 토큰 절약
            "published_at": n.published_at,
            "reporter_name": n.reporter_name,
            "news_url": n.news_url,
            "source_site": n.source_site,
            "crawled_at": n.crawled_at.isoformat() if n.crawled_at else None,
        } for n in news]

    def _collect_market_analysis(
        self,
        session: Session,
        keyword: str
    ) -> Optional[dict]:
        """소스 H: 시장 분석 수집"""
        analysis = session.query(MarketAnalysis).filter(
            MarketAnalysis.keyword == keyword
        ).order_by(desc(MarketAnalysis.analysis_date)).first()

        if not analysis:
            return None

        return {
            "id": analysis.id,
            "keyword": analysis.keyword,
            "total_postings": analysis.total_postings,
            "top_companies": analysis.top_companies,
            "top_skills": analysis.top_skills,
            "market_summary": analysis.market_summary,
            "recommendations": analysis.recommendations,
            "analysis_date": analysis.analysis_date.isoformat() if analysis.analysis_date else None,
        }

    def _collect_skill_trends(
        self,
        session: Session,
        skills: List[str]
    ) -> Optional[List[dict]]:
        """소스 I: 스킬 트렌드 수집"""
        if not skills:
            return None

        trends = session.query(SkillTrend).filter(
            SkillTrend.skill_name.in_(skills)
        ).order_by(desc(SkillTrend.mention_count)).all()

        if not trends:
            return None

        return [{
            "id": t.id,
            "skill_name": t.skill_name,
            "category": t.category,
            "mention_count": t.mention_count,
            "job_category": t.job_category,
            "trend_direction": t.trend_direction,
            "analysis_date": t.analysis_date.isoformat() if t.analysis_date else None,
        } for t in trends]

    def _extract_skills_from_postings(self, job_postings: List[dict]) -> List[str]:
        """채용공고에서 스킬 목록 추출"""
        skills = set()
        for jp in job_postings:
            required = jp.get('required_skills') or []
            preferred = jp.get('preferred_skills') or []
            if isinstance(required, list):
                skills.update(required)
            if isinstance(preferred, list):
                skills.update(preferred)
        return list(skills)

    async def collect_all_sources_async(
        self,
        company_name: str,
        job_posting_id: Optional[int] = None,
        include_market_data: bool = True
    ) -> AnalysisDataBundle:
        """
        모든 데이터 소스 수집 (비동기 버전)

        병렬로 데이터를 수집하여 성능을 최적화합니다.
        """
        loop = asyncio.get_event_loop()

        # 동기 함수를 비동기로 실행
        return await loop.run_in_executor(
            self.executor,
            lambda: self.collect_all_sources(
                company_name,
                job_posting_id,
                include_market_data
            )
        )


def get_company_id_by_name(db: Database, company_name: str) -> Optional[int]:
    """회사명으로 company_id 조회 (유틸리티 함수)"""
    session = db.get_session()
    try:
        company = session.query(Company).filter(
            Company.name == company_name
        ).first()
        return company.id if company else None
    finally:
        session.close()
