"""
기업 분석 보고서 생성 오케스트레이터

전체 분석 파이프라인을 관리합니다:
1. 데이터 수집 (DataCollector)
2. 프롬프트 생성 (PromptBuilder)
3. LLM 호출 (ReportGenerator)
4. 결과 저장 (ReportStorage)
5. HTML/PDF 변환 (ReportExporter)
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from utils.database import Database, get_kst_now, KST
from analyzers.models import (
    AnalysisDataBundle,
    ApplicantProfile,
    PriorityWeights,
    GeneratedReport
)
from analyzers.data_collector import CompanyDataCollector
from analyzers.data_processor import DataProcessor
from analyzers.prompt_builder import PromptBuilder
from analyzers.report_generator import ReportGenerator
from analyzers.report_storage import ReportStorage
from analyzers.report_exporter import ReportExporter

logger = logging.getLogger(__name__)


class CompanyReportOrchestrator:
    """기업 분석 보고서 생성 오케스트레이터"""

    def __init__(
        self,
        db: Database,
        llm_provider: str = "openai",
        output_dir: str = "./reports/company_analysis"
    ):
        self.db = db
        self.llm_provider = llm_provider
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 모듈 초기화
        self.collector = CompanyDataCollector(db)
        self.processor = DataProcessor()
        self.prompt_builder = PromptBuilder()
        self.generator = ReportGenerator(provider=llm_provider)

        # Phase 4: 저장 및 내보내기 모듈
        self.storage = ReportStorage(db)
        self.exporter = ReportExporter()

    def analyze_company(
        self,
        company_name: str,
        job_posting_id: Optional[int] = None,
        applicant_profile: Optional[ApplicantProfile] = None,
        priority_weights: Optional[PriorityWeights] = None,
        save_prompt: bool = True,
        generate_report: bool = False,
        # Phase 4: 저장 및 내보내기 옵션
        save_to_db: bool = False,
        export_html: bool = False,
        export_pdf: bool = False,
        use_cache: bool = True,
        cache_max_days: int = 7
    ) -> Dict[str, Any]:
        """
        기업 분석 실행

        Args:
            company_name: 분석할 회사명
            job_posting_id: 특정 채용공고 ID (선택)
            applicant_profile: 지원자 프로필 (선택)
            priority_weights: 우선순위 가중치 (선택)
            save_prompt: 프롬프트를 파일로 저장할지 여부
            generate_report: LLM 호출하여 보고서 생성할지 여부
            save_to_db: DB에 저장할지 여부
            export_html: HTML로 내보낼지 여부
            export_pdf: PDF로 내보낼지 여부
            use_cache: 캐시 사용 여부
            cache_max_days: 캐시 유효 기간 (일)

        Returns:
            분석 결과 딕셔너리
        """
        logger.info(f"=== 기업 분석 시작: {company_name} ===")

        result = {
            "company_name": company_name,
            "status": "success",
            "data_availability": {},
            "prompt_file": None,
            "report_file": None,
            "html_file": None,
            "pdf_file": None,
            "db_report_id": None,
            "from_cache": False,
            "error": None
        }

        try:
            # 0. 캐시 확인 (Phase 4)
            if use_cache and generate_report:
                cached = self.storage.get_cached_report(
                    company_name=company_name,
                    job_posting_id=job_posting_id,
                    priority_weights=priority_weights,
                    max_age_days=cache_max_days
                )
                if cached:
                    logger.info(f"캐시에서 보고서 로드: {company_name}")
                    result["status"] = "success"
                    result["from_cache"] = True
                    result["db_report_id"] = cached.get("id")
                    result["verdict"] = cached.get("verdict")
                    result["total_score"] = cached.get("total_score")
                    result["data_availability"] = cached.get("data_sources", {})

                    # 캐시된 보고서로 HTML/PDF 내보내기
                    if (export_html or export_pdf) and cached.get("full_markdown"):
                        # ISO format에서 datetime 파싱 후 KST로 처리
                        cached_generated_at = None
                        if cached.get("generated_at"):
                            cached_generated_at = datetime.fromisoformat(cached["generated_at"])
                            if cached_generated_at.tzinfo is None:
                                cached_generated_at = KST.localize(cached_generated_at)
                        export_result = self.exporter.export_report(
                            markdown_content=cached["full_markdown"],
                            output_dir=str(self.output_dir),
                            company_name=company_name,
                            generated_at=cached_generated_at,
                            verdict=cached.get("verdict"),
                            total_score=cached.get("total_score"),
                            export_html=export_html,
                            export_pdf=export_pdf
                        )
                        result["html_file"] = str(export_result.get("html")) if export_result.get("html") else None
                        result["pdf_file"] = str(export_result.get("pdf")) if export_result.get("pdf") else None

                    return result

            # 1. 데이터 수집
            logger.info("Step 1: 데이터 수집 중...")
            data_bundle = self.collector.collect_all_sources(
                company_name=company_name,
                job_posting_id=job_posting_id
            )

            result["data_availability"] = data_bundle.get_data_availability()

            # 최소 데이터 검증
            if not data_bundle.has_minimum_data():
                logger.warning(f"최소 분석 요건 미충족: {company_name}")
                result["status"] = "insufficient_data"
                result["error"] = "회사 정보 또는 채용공고가 없습니다."
                return result

            logger.info(f"데이터 수집 완료: {result['data_availability']}")

            # 2. 데이터 정제
            logger.info("Step 2: 데이터 정제 중...")
            data_bundle = self.processor.process_all(data_bundle)

            # 정제 결과 요약
            if data_bundle.processed_reviews:
                logger.info(f"  - 리뷰: 평균 {data_bundle.processed_reviews.avg_rating}/5.0, "
                           f"키워드 {len(data_bundle.processed_reviews.pros_keywords)}개")
            if data_bundle.processed_interviews:
                logger.info(f"  - 면접: 합격률 {data_bundle.processed_interviews.pass_rate}%, "
                           f"질문 유형 {len([k for k, v in data_bundle.processed_interviews.question_types.items() if v])}개")
            if data_bundle.processed_news:
                logger.info(f"  - 뉴스: 유형 {len(data_bundle.processed_news.by_type)}종, "
                           f"최근 6개월 {len(data_bundle.processed_news.recent_news)}건")

            # 3. 프롬프트 생성
            logger.info("Step 3: 프롬프트 생성 중...")
            prompt = self.prompt_builder.build_prompt(
                data_bundle=data_bundle,
                applicant_profile=applicant_profile,
                priority_weights=priority_weights
            )

            estimated_tokens = self.prompt_builder.estimate_tokens(prompt)
            logger.info(f"프롬프트 생성 완료 (추정 토큰: {estimated_tokens:,})")

            # 프롬프트 저장
            if save_prompt:
                prompt_file = self._save_prompt(company_name, prompt, data_bundle)
                result["prompt_file"] = str(prompt_file)
                logger.info(f"프롬프트 저장: {prompt_file}")

            # 4. LLM 호출
            if generate_report:
                logger.info("Step 4: LLM 호출하여 보고서 생성 중...")

                if not self.generator.is_available():
                    logger.error("LLM 클라이언트가 초기화되지 않았습니다.")
                    result["status"] = "llm_unavailable"
                    result["error"] = "LLM API 키가 설정되지 않았거나 클라이언트 초기화에 실패했습니다."
                else:
                    # 안전한 스트리밍 출력 (Windows 인코딩 문제 해결)
                    def safe_print(chunk: str):
                        try:
                            # Windows cp949에서 인코딩 불가능한 문자를 ASCII로 대체
                            safe_chunk = chunk.encode(
                                sys.stdout.encoding or 'utf-8', errors='replace'
                            ).decode(sys.stdout.encoding or 'utf-8', errors='replace')
                            print(safe_chunk, end='', flush=True)
                        except Exception:
                            # 최후의 수단: 출력 생략
                            pass

                    # 보고서 생성
                    generated = self.generator.generate_report(
                        prompt=prompt,
                        stream_callback=safe_print
                    )

                    # 결과 저장
                    if generated.full_markdown:
                        # 마크다운 파일 저장
                        report_file = self._save_report(
                            company_name, generated, data_bundle
                        )
                        result["report_file"] = str(report_file)
                        result["verdict"] = generated.verdict
                        result["total_score"] = generated.total_score
                        result["quality_passed"] = generated.quality_check.passed if generated.quality_check else False

                        logger.info(f"\n보고서 생성 완료: {report_file}")
                        logger.info(f"  - 판정: {generated.verdict}")
                        logger.info(f"  - 총점: {generated.total_score}/5.0")
                        logger.info(f"  - Quality Gate: {'통과' if result['quality_passed'] else '미통과'}")

                        if generated.quality_check and generated.quality_check.missing_items:
                            logger.warning(f"  - 누락 항목: {generated.quality_check.missing_items}")

                        # Phase 4: HTML/PDF 내보내기
                        html_content = None
                        if export_html or export_pdf:
                            logger.info("Step 5: HTML/PDF 내보내기 중...")
                            export_result = self.exporter.export_report(
                                markdown_content=generated.full_markdown,
                                output_dir=str(self.output_dir),
                                company_name=company_name,
                                generated_at=generated.generated_at,
                                verdict=generated.verdict,
                                total_score=generated.total_score,
                                export_html=export_html,
                                export_pdf=export_pdf
                            )
                            if export_result.get("html"):
                                result["html_file"] = str(export_result["html"])
                                logger.info(f"  - HTML: {result['html_file']}")
                                # HTML 내용 저장 (DB용)
                                html_content = export_result["html"].read_text(encoding='utf-8') if export_result["html"].exists() else None
                            if export_result.get("pdf"):
                                result["pdf_file"] = str(export_result["pdf"])
                                logger.info(f"  - PDF: {result['pdf_file']}")

                        # Phase 4: DB 저장
                        if save_to_db:
                            logger.info("Step 6: DB에 저장 중...")
                            try:
                                report_id = self.storage.save_report(
                                    company_name=company_name,
                                    company_id=data_bundle.company_id,
                                    job_posting_id=job_posting_id,
                                    generated_report=generated,
                                    data_sources=result["data_availability"],
                                    applicant_profile=applicant_profile,
                                    priority_weights=priority_weights,
                                    llm_provider=self.llm_provider,
                                    html_content=html_content,
                                    cache_days=cache_max_days
                                )
                                result["db_report_id"] = report_id
                                logger.info(f"  - DB 저장 완료 (id={report_id})")
                            except Exception as e:
                                logger.error(f"  - DB 저장 실패: {e}")

                    else:
                        result["status"] = "generation_failed"
                        result["error"] = "보고서 생성에 실패했습니다."
            else:
                logger.info("Step 4: LLM 호출 건너뜀 (generate_report=False)")

            logger.info(f"=== 기업 분석 완료: {company_name} ===")

        except Exception as e:
            logger.error(f"분석 중 오류 발생: {e}")
            result["status"] = "error"
            result["error"] = str(e)

        return result

    def _save_prompt(
        self,
        company_name: str,
        prompt: str,
        data_bundle: AnalysisDataBundle
    ) -> Path:
        """프롬프트를 파일로 저장 (KST 기준)"""
        timestamp = get_kst_now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c for c in company_name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_name = safe_name.replace(' ', '_')

        filename = f"{safe_name}_{timestamp}_prompt.md"
        filepath = self.output_dir / filename

        # 메타데이터 헤더 추가
        header = f"""---
company: {company_name}
company_id: {data_bundle.company_id}
generated_at: {get_kst_now().isoformat()}
data_availability: {json.dumps(data_bundle.get_data_availability(), ensure_ascii=False)}
---

"""
        content = header + prompt

        filepath.write_text(content, encoding='utf-8')
        return filepath

    def _save_report(
        self,
        company_name: str,
        generated: GeneratedReport,
        data_bundle: AnalysisDataBundle
    ) -> Path:
        """생성된 보고서를 파일로 저장 (KST 기준)"""
        timestamp = get_kst_now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c for c in company_name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_name = safe_name.replace(' ', '_')

        filename = f"{safe_name}_{timestamp}_report.md"
        filepath = self.output_dir / filename

        # 메타데이터 헤더 추가
        quality_check = generated.quality_check
        header = f"""---
company: {company_name}
company_id: {data_bundle.company_id}
generated_at: {generated.generated_at.isoformat() if generated.generated_at else get_kst_now().isoformat()}
llm_model: {generated.llm_model}
prompt_version: {generated.prompt_version}
verdict: {generated.verdict}
total_score: {generated.total_score}
quality_gate_passed: {quality_check.passed if quality_check else False}
data_availability: {json.dumps(data_bundle.get_data_availability(), ensure_ascii=False)}
---

"""
        content = header + generated.full_markdown

        filepath.write_text(content, encoding='utf-8')
        return filepath

    def get_company_data_summary(self, company_name: str) -> Dict[str, Any]:
        """회사 데이터 요약 조회 (분석 전 확인용)"""
        data_bundle = self.collector.collect_all_sources(
            company_name=company_name,
            include_market_data=False  # 빠른 조회를 위해 시장 데이터 제외
        )

        return {
            "company_name": company_name,
            "company_id": data_bundle.company_id,
            "data_availability": data_bundle.get_data_availability(),
            "has_minimum_data": data_bundle.has_minimum_data(),
            "company_info": data_bundle.company_info,
            "job_postings_count": len(data_bundle.job_postings),
            "job_titles": [jp.get('title') for jp in data_bundle.job_postings[:5]]
        }


def parse_weights_string(weights_str: str) -> Optional[PriorityWeights]:
    """
    가중치 문자열 파싱

    형식: "성장성:30,안정성:20,보상:20,워라밸:15,직무적합:15"
    """
    if not weights_str:
        return None

    mapping = {
        "성장성": "growth",
        "안정성": "stability",
        "보상": "compensation",
        "워라밸": "work_life_balance",
        "직무적합": "job_fit"
    }

    weights = PriorityWeights()

    try:
        parts = weights_str.split(',')
        for part in parts:
            key, value = part.strip().split(':')
            key = key.strip()
            value = int(value.strip())

            if key in mapping:
                setattr(weights, mapping[key], value)

        if not weights.validate():
            logger.warning(f"가중치 합이 100이 아님: {weights_str}")
            return None

        return weights

    except Exception as e:
        logger.error(f"가중치 파싱 실패: {e}")
        return None


def load_applicant_profile(filepath: str) -> Optional[ApplicantProfile]:
    """지원자 프로필 JSON 파일 로드"""
    path = Path(filepath)
    if not path.exists():
        logger.error(f"프로필 파일을 찾을 수 없음: {filepath}")
        return None

    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return ApplicantProfile(
            current_experience=data.get('current_experience', ''),
            core_skills=data.get('core_skills', []),
            motivation=data.get('motivation', ''),
            career_direction=data.get('career_direction', '')
        )
    except Exception as e:
        logger.error(f"프로필 로드 실패: {e}")
        return None
