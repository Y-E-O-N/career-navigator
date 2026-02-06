"""
기업 분석 보고서 저장 모듈 (Phase 4)

보고서를 DB에 저장하고 캐싱을 관리합니다.
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import asdict

from utils.database import Database, CompanyReport, get_kst_now, KST
from analyzers.models import (
    GeneratedReport,
    ApplicantProfile,
    PriorityWeights,
    QualityCheckResult
)

logger = logging.getLogger(__name__)


class ReportStorage:
    """보고서 저장 및 캐싱 관리"""

    # 기본 캐시 유효 기간 (일)
    DEFAULT_CACHE_DAYS = 7

    def __init__(self, db: Database):
        self.db = db

    def generate_cache_key(
        self,
        company_name: str,
        job_posting_id: Optional[int] = None,
        priority_weights: Optional[PriorityWeights] = None
    ) -> str:
        """
        캐시 키 생성

        동일한 회사/채용공고/가중치 조합에 대해 동일한 키 생성
        """
        key_parts = [company_name]

        if job_posting_id:
            key_parts.append(f"job:{job_posting_id}")

        if priority_weights:
            # 가중치를 정렬된 문자열로 변환
            weights_str = json.dumps(asdict(priority_weights), sort_keys=True)
            weights_hash = hashlib.md5(weights_str.encode()).hexdigest()[:8]
            key_parts.append(f"w:{weights_hash}")

        return ":".join(key_parts)

    def get_cached_report(
        self,
        company_name: str,
        job_posting_id: Optional[int] = None,
        priority_weights: Optional[PriorityWeights] = None,
        max_age_days: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        캐시된 보고서 조회

        Args:
            company_name: 회사명
            job_posting_id: 채용공고 ID
            priority_weights: 우선순위 가중치
            max_age_days: 최대 캐시 유효 기간 (일)

        Returns:
            캐시된 보고서 딕셔너리 또는 None
        """
        cache_key = self.generate_cache_key(
            company_name, job_posting_id, priority_weights
        )

        session = self.db.get_session()
        try:
            report = session.query(CompanyReport).filter(
                CompanyReport.cache_key == cache_key
            ).first()

            if not report:
                return None

            # 만료 확인 (KST 기준)
            if report.cache_expires_at:
                now = get_kst_now()
                # DB에서 가져온 datetime을 KST로 변환
                expires_at = report.cache_expires_at
                if expires_at.tzinfo is None:
                    expires_at = KST.localize(expires_at)

                if now > expires_at:
                    logger.info(f"캐시 만료됨: {cache_key}")
                    return None

            # max_age_days 체크 (KST 기준)
            if max_age_days and report.generated_at:
                generated_at = report.generated_at
                if generated_at.tzinfo is None:
                    generated_at = KST.localize(generated_at)
                now = get_kst_now()
                age = now - generated_at

                if age.days > max_age_days:
                    logger.info(f"캐시 너무 오래됨 ({age.days}일): {cache_key}")
                    return None

            logger.info(f"캐시 히트: {cache_key}")
            return self._report_to_dict(report)

        finally:
            session.close()

    def save_report(
        self,
        company_name: str,
        company_id: Optional[int],
        job_posting_id: Optional[int],
        generated_report: GeneratedReport,
        data_sources: Dict[str, Any],
        applicant_profile: Optional[ApplicantProfile] = None,
        priority_weights: Optional[PriorityWeights] = None,
        llm_provider: str = "openai",
        html_content: Optional[str] = None,
        cache_days: int = DEFAULT_CACHE_DAYS
    ) -> int:
        """
        보고서 DB 저장

        Returns:
            저장된 report_id
        """
        cache_key = self.generate_cache_key(
            company_name, job_posting_id, priority_weights
        )

        session = self.db.get_session()
        try:
            # 기존 캐시 삭제
            session.query(CompanyReport).filter(
                CompanyReport.cache_key == cache_key
            ).delete()

            # Quality Gate 결과 변환
            quality_details = None
            if generated_report.quality_check:
                qc = generated_report.quality_check
                quality_details = {
                    "passed": qc.passed,
                    "sections_complete": qc.sections_complete,
                    "fact_interpretation_judgment_tagged": qc.fact_interpretation_judgment_tagged,
                    "source_labels_tagged": qc.source_labels_tagged,
                    "score_calculation_correct": qc.score_calculation_correct,
                    "verdict_consistent": qc.verdict_consistent,
                    "missing_items": qc.missing_items
                }

            # 새 보고서 생성
            report = CompanyReport(
                company_id=company_id,
                company_name=company_name,
                job_posting_id=job_posting_id,
                report_version=generated_report.prompt_version,
                llm_provider=llm_provider,
                llm_model=generated_report.llm_model,
                verdict=generated_report.verdict,
                total_score=generated_report.total_score,
                scores=generated_report.scores,
                key_attractions=generated_report.key_attractions,
                key_risks=generated_report.key_risks,
                verification_items=generated_report.verification_items,
                full_markdown=generated_report.full_markdown,
                full_html=html_content,
                quality_passed=generated_report.quality_check.passed if generated_report.quality_check else False,
                quality_details=quality_details,
                data_sources=data_sources,
                applicant_profile=asdict(applicant_profile) if applicant_profile else None,
                priority_weights=asdict(priority_weights) if priority_weights else None,
                cache_key=cache_key,
                cache_expires_at=get_kst_now() + timedelta(days=cache_days),
                generated_at=generated_report.generated_at or get_kst_now()
            )

            session.add(report)
            session.commit()
            session.refresh(report)

            logger.info(f"보고서 저장 완료: {company_name} (id={report.id})")
            return report.id

        except Exception as e:
            session.rollback()
            logger.error(f"보고서 저장 실패: {e}")
            raise e
        finally:
            session.close()

    def get_report_by_id(self, report_id: int) -> Optional[Dict[str, Any]]:
        """ID로 보고서 조회"""
        session = self.db.get_session()
        try:
            report = session.query(CompanyReport).filter(
                CompanyReport.id == report_id
            ).first()

            return self._report_to_dict(report) if report else None
        finally:
            session.close()

    def get_reports_for_company(
        self,
        company_name: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """회사별 보고서 목록 조회"""
        session = self.db.get_session()
        try:
            reports = session.query(CompanyReport).filter(
                CompanyReport.company_name == company_name
            ).order_by(
                CompanyReport.generated_at.desc()
            ).limit(limit).all()

            return [self._report_to_dict(r) for r in reports]
        finally:
            session.close()

    def get_recent_reports(
        self,
        limit: int = 20,
        verdict_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """최근 보고서 목록 조회"""
        session = self.db.get_session()
        try:
            query = session.query(CompanyReport)

            if verdict_filter:
                query = query.filter(CompanyReport.verdict == verdict_filter)

            reports = query.order_by(
                CompanyReport.generated_at.desc()
            ).limit(limit).all()

            return [self._report_to_dict(r) for r in reports]
        finally:
            session.close()

    def delete_expired_cache(self) -> int:
        """만료된 캐시 삭제 (KST 기준)"""
        session = self.db.get_session()
        try:
            # DB는 naive datetime으로 저장되므로 naive로 변환하여 비교
            now_kst_naive = get_kst_now().replace(tzinfo=None)
            deleted = session.query(CompanyReport).filter(
                CompanyReport.cache_expires_at.isnot(None),
                CompanyReport.cache_expires_at < now_kst_naive
            ).delete()

            session.commit()
            logger.info(f"만료된 캐시 {deleted}건 삭제")
            return deleted

        except Exception as e:
            session.rollback()
            logger.error(f"캐시 삭제 실패: {e}")
            raise e
        finally:
            session.close()

    def update_report_html(self, report_id: int, html_content: str) -> bool:
        """보고서 HTML 업데이트"""
        session = self.db.get_session()
        try:
            report = session.query(CompanyReport).filter(
                CompanyReport.id == report_id
            ).first()

            if not report:
                return False

            report.full_html = html_content
            report.updated_at = get_kst_now()
            session.commit()
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"HTML 업데이트 실패: {e}")
            return False
        finally:
            session.close()

    def get_statistics(self) -> Dict[str, Any]:
        """보고서 통계 조회"""
        session = self.db.get_session()
        try:
            from sqlalchemy import func

            total = session.query(func.count(CompanyReport.id)).scalar()

            by_verdict = session.query(
                CompanyReport.verdict,
                func.count(CompanyReport.id)
            ).group_by(CompanyReport.verdict).all()

            avg_score = session.query(
                func.avg(CompanyReport.total_score)
            ).scalar()

            quality_passed = session.query(
                func.count(CompanyReport.id)
            ).filter(CompanyReport.quality_passed == True).scalar()

            return {
                "total_reports": total,
                "by_verdict": {v: c for v, c in by_verdict if v},
                "avg_total_score": float(avg_score) if avg_score else 0,
                "quality_passed_count": quality_passed,
                "quality_pass_rate": (quality_passed / total * 100) if total > 0 else 0
            }
        finally:
            session.close()

    def _report_to_dict(self, report: CompanyReport) -> Dict[str, Any]:
        """CompanyReport 객체를 딕셔너리로 변환"""
        if not report:
            return {}

        return {
            "id": report.id,
            "company_id": report.company_id,
            "company_name": report.company_name,
            "job_posting_id": report.job_posting_id,
            "report_version": report.report_version,
            "llm_provider": report.llm_provider,
            "llm_model": report.llm_model,
            "verdict": report.verdict,
            "total_score": float(report.total_score) if report.total_score else None,
            "scores": report.scores,
            "key_attractions": report.key_attractions,
            "key_risks": report.key_risks,
            "verification_items": report.verification_items,
            "full_markdown": report.full_markdown,
            "full_html": report.full_html,
            "quality_passed": report.quality_passed,
            "quality_details": report.quality_details,
            "data_sources": report.data_sources,
            "applicant_profile": report.applicant_profile,
            "priority_weights": report.priority_weights,
            "generated_at": report.generated_at.isoformat() if report.generated_at else None,
            "cache_expires_at": report.cache_expires_at.isoformat() if report.cache_expires_at else None
        }
