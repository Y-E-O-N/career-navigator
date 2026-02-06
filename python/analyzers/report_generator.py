"""
기업 분석 보고서 생성 모듈 (Phase 3)

LLM을 활용하여 company_analysis_prompt_v4.md 형식의
종합 기업 분석 보고서를 생성합니다.
"""

import re
import json
import time
import logging
from typing import Optional, Dict, Any, Callable
from datetime import datetime
from pathlib import Path

from utils.database import get_kst_now

# API 클라이언트 임포트 (선택적)
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

from config.settings import settings
from analyzers.models import GeneratedReport, QualityCheckResult

logger = logging.getLogger(__name__)


class ReportGenerator:
    """LLM을 통한 기업 분석 보고서 생성"""

    # 기본 모델 설정
    MODEL_CONFIG = {
        'openai': {
            'model': 'gpt-4o',  # gpt-4o for long context
            'max_tokens': 8000,
            'temperature': 0.7,
        },
        'anthropic': {
            'model': 'claude-sonnet-4-20250514',
            'max_tokens': 8000,
            'temperature': 0.7,
        },
        'gemini': {
            'model': 'gemini-2.0-flash',
            'max_tokens': 8000,
            'temperature': 0.7,
        }
    }

    def __init__(self, provider: Optional[str] = None):
        """
        Args:
            provider: LLM 제공자 (openai, anthropic, gemini)
                     미지정 시 settings에서 로드
        """
        self.provider = provider or settings.analyzer.llm_provider
        self.client = None
        self.model_config = self.MODEL_CONFIG.get(self.provider, {})
        self._init_client()

    def _init_client(self):
        """API 클라이언트 초기화"""
        if self.provider == "openai" and OPENAI_AVAILABLE:
            api_key = settings.analyzer.openai_api_key
            if api_key:
                self.client = OpenAI(api_key=api_key)
                logger.info(f"OpenAI client initialized (model: {self.model_config.get('model')})")
            else:
                logger.warning("OpenAI API key not set")

        elif self.provider == "anthropic" and ANTHROPIC_AVAILABLE:
            api_key = settings.analyzer.anthropic_api_key
            if api_key:
                self.client = anthropic.Anthropic(api_key=api_key)
                logger.info(f"Anthropic client initialized (model: {self.model_config.get('model')})")
            else:
                logger.warning("Anthropic API key not set")

        elif self.provider == "gemini" and GEMINI_AVAILABLE:
            api_key = settings.analyzer.gemini_api_key
            if api_key:
                self.client = genai.Client(api_key=api_key)
                logger.info(f"Gemini client initialized (model: {self.model_config.get('model')})")
            else:
                logger.warning("Gemini API key not set")

        else:
            logger.warning(f"LLM provider '{self.provider}' not available")

    def is_available(self) -> bool:
        """LLM 사용 가능 여부"""
        return self.client is not None

    def generate_report(
        self,
        prompt: str,
        stream_callback: Optional[Callable[[str], None]] = None,
        max_retries: int = 3
    ) -> GeneratedReport:
        """
        기업 분석 보고서 생성

        Args:
            prompt: 프롬프트 (데이터 포함된 전체 프롬프트)
            stream_callback: 스트리밍 콜백 함수 (청크 수신 시 호출)
            max_retries: 최대 재시도 횟수

        Returns:
            GeneratedReport: 생성된 보고서
        """
        result = GeneratedReport(
            llm_model=self.model_config.get('model', 'unknown'),
            prompt_version='v4'
        )

        if not self.client:
            logger.error("LLM client not initialized")
            result.full_markdown = "# 오류\n\nLLM 클라이언트가 초기화되지 않았습니다."
            return result

        # LLM 호출
        start_time = time.time()
        response_text = self._call_llm(
            prompt=prompt,
            stream_callback=stream_callback,
            max_retries=max_retries
        )
        elapsed = time.time() - start_time

        if not response_text:
            logger.error("LLM response is empty")
            result.full_markdown = "# 오류\n\nLLM 응답이 비어있습니다."
            return result

        logger.info(f"LLM response received: {len(response_text)} chars in {elapsed:.1f}s")
        result.full_markdown = response_text
        result.generated_at = get_kst_now()

        # 보고서 파싱 (핵심 정보 추출)
        self._parse_report(result)

        # Quality Gate 검증
        result.quality_check = self._validate_quality_gate(response_text)

        return result

    def _call_llm(
        self,
        prompt: str,
        stream_callback: Optional[Callable[[str], None]] = None,
        max_retries: int = 3
    ) -> Optional[str]:
        """LLM API 호출"""
        for attempt in range(max_retries):
            try:
                if self.provider == "openai":
                    return self._call_openai(prompt, stream_callback)
                elif self.provider == "anthropic":
                    return self._call_anthropic(prompt, stream_callback)
                elif self.provider == "gemini":
                    return self._call_gemini(prompt, stream_callback)

            except Exception as e:
                error_str = str(e)
                logger.error(f"LLM call error (attempt {attempt + 1}): {error_str}")

                # Rate limit 처리
                if '429' in error_str or 'rate' in error_str.lower():
                    wait_time = (attempt + 1) * 30
                    logger.warning(f"Rate limit hit, waiting {wait_time}s...")
                    time.sleep(wait_time)
                elif attempt < max_retries - 1:
                    time.sleep(5)
                else:
                    raise

        return None

    def _call_openai(
        self,
        prompt: str,
        stream_callback: Optional[Callable[[str], None]] = None
    ) -> str:
        """OpenAI API 호출"""
        model = self.model_config.get('model', 'gpt-4o')
        max_tokens = self.model_config.get('max_tokens', 8000)
        temperature = self.model_config.get('temperature', 0.7)

        messages = [{"role": "user", "content": prompt}]

        if stream_callback:
            # 스트리밍 모드
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                max_completion_tokens=max_tokens,
                temperature=temperature,
                stream=True
            )

            full_response = []
            for chunk in response:
                if chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    full_response.append(text)
                    stream_callback(text)

            return ''.join(full_response)
        else:
            # 일반 모드
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                max_completion_tokens=max_tokens,
                temperature=temperature
            )
            return response.choices[0].message.content

    def _call_anthropic(
        self,
        prompt: str,
        stream_callback: Optional[Callable[[str], None]] = None
    ) -> str:
        """Anthropic API 호출"""
        model = self.model_config.get('model', 'claude-sonnet-4-20250514')
        max_tokens = self.model_config.get('max_tokens', 8000)
        temperature = self.model_config.get('temperature', 0.7)

        if stream_callback:
            # 스트리밍 모드
            full_response = []
            with self.client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}]
            ) as stream:
                for text in stream.text_stream:
                    full_response.append(text)
                    stream_callback(text)

            return ''.join(full_response)
        else:
            # 일반 모드
            message = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}]
            )
            return message.content[0].text

    def _call_gemini(
        self,
        prompt: str,
        stream_callback: Optional[Callable[[str], None]] = None
    ) -> str:
        """Gemini API 호출"""
        model = self.model_config.get('model', 'gemini-2.0-flash')
        max_tokens = self.model_config.get('max_tokens', 8000)
        temperature = self.model_config.get('temperature', 0.7)

        config = types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
        )

        if stream_callback:
            # 스트리밍 모드
            full_response = []
            response = self.client.models.generate_content_stream(
                model=model,
                contents=prompt,
                config=config
            )
            for chunk in response:
                if chunk.text:
                    full_response.append(chunk.text)
                    stream_callback(chunk.text)

            return ''.join(full_response)
        else:
            # 일반 모드
            response = self.client.models.generate_content(
                model=model,
                contents=prompt,
                config=config
            )
            return response.text

    def _parse_report(self, result: GeneratedReport):
        """생성된 보고서에서 핵심 정보 추출"""
        text = result.full_markdown

        # 1. 가중 총점 추출 (다양한 형식 지원) - 먼저 추출하여 판정에 활용
        score_patterns = [
            r'(?:가중\s*총점|총점|Total\s*Score)[:\s*]*(\d+\.?\d*)\s*/\s*5',
            r'\*?\*?종합\s*점수\*?\*?[:\s*]*(\d+\.?\d*)\s*/\s*5',
            r'(?:종합\s*점수\s*계산|종합\s*점수)[:\s]*(\d+\.?\d*)',
            r'(?:Overall|Total)[:\s]*(\d+\.?\d*)\s*(?:점|/5)',
        ]
        for pattern in score_patterns:
            score_match = re.search(pattern, text, re.IGNORECASE)
            if score_match:
                result.total_score = float(score_match.group(1))
                break

        # 2. 개별 평가축 점수 추출 (다양한 형식 지원)
        axes = ['직무적합성', '성장성', '안정성', '보상', '조직운영']
        for axis in axes:
            # 테이블 형식: | 직무적합성 | 20% | 4.5 |
            axis_match = re.search(
                rf'{axis}[^|]*\|\s*\d+%?\s*\|\s*(\d+\.?\d*)',
                text
            )
            if axis_match:
                result.scores[axis] = float(axis_match.group(1))
            else:
                # 마크다운 볼드 형식: **직무적합성:** 4/5
                bold_match = re.search(
                    rf'\*?\*?{axis}[^:]*\*?\*?[:\s*]*(\d+\.?\d*)\s*/\s*5',
                    text
                )
                if bold_match:
                    result.scores[axis] = float(bold_match.group(1))
                else:
                    # 인라인 형식: 직무적합성: 4점
                    inline_match = re.search(
                        rf'\*?\*?{axis}\*?\*?[:\s]*(\d+\.?\d*)\s*점',
                        text
                    )
                    if inline_match:
                        result.scores[axis] = float(inline_match.group(1))

        # 3. 종합 판단 추출 (Go / Conditional Go / No-Go)
        verdict_match = re.search(
            r'(?:종합\s*판단|Overall\s*Verdict)[:\s]*([^\n]*(?:Go|No-Go)[^\n]*)',
            text, re.IGNORECASE
        )
        if verdict_match:
            verdict_text = verdict_match.group(1).strip()
            if 'No-Go' in verdict_text:
                result.verdict = 'No-Go'
            elif 'Conditional' in verdict_text:
                result.verdict = 'Conditional Go'
            else:
                result.verdict = 'Go'
        else:
            # 한글 표현으로 판단 추출 시도
            if re.search(r'지원\s*(비)?추천|적극\s*지원', text):
                if re.search(r'조건부|신중|주의', text):
                    result.verdict = 'Conditional Go'
                elif re.search(r'비추천|지양', text):
                    result.verdict = 'No-Go'
                else:
                    result.verdict = 'Go'
            # 점수 기반 자동 판정 (마지막 수단)
            elif result.total_score > 0:
                if result.total_score >= 4.0:
                    result.verdict = 'Go'
                elif result.total_score >= 2.5:
                    result.verdict = 'Conditional Go'
                else:
                    result.verdict = 'No-Go'

        # 4. 핵심 매력 포인트 추출
        attractions = re.findall(
            r'핵심\s*매력[^:]*:\s*\n?((?:[-•]\s*[^\n]+\n?){1,3})',
            text
        )
        if attractions:
            for line in attractions[0].split('\n'):
                line = re.sub(r'^[-•\s]+', '', line).strip()
                if line:
                    result.key_attractions.append(line[:200])

        # 5. 핵심 리스크 추출
        risks = re.findall(
            r'(?:핵심\s*)?리스크[^:]*:\s*\n?((?:[-•]\s*[^\n]+\n?){1,3})',
            text
        )
        if risks:
            for line in risks[0].split('\n'):
                line = re.sub(r'^[-•\s]+', '', line).strip()
                if line:
                    result.key_risks.append(line[:200])

        # 6. [확인 필요] 항목 추출
        verify_items = re.findall(r'\[확인\s*필요\][^"]*"([^"]+)"', text)
        result.verification_items = verify_items[:3]

    def _validate_quality_gate(self, report_text: str) -> QualityCheckResult:
        """Quality Gate 검증"""
        result = QualityCheckResult()

        # 1. 12개 섹션 완결성 체크
        required_sections = [
            '페르소나 설정', 'Executive Summary', '회사 프로필',
            '채용 포지션', '기술 스택', '내부 실태', '외부 환경',
            '교차 검증', '종합 평가', '면접 대비', '페르소나 최종',
            '참고 자료'
        ]

        for section in required_sections:
            # 섹션 제목이 존재하는지 체크 (유연하게)
            pattern = rf'#{{1,3}}\s*\d*\.?\s*{section}'
            found = bool(re.search(pattern, report_text, re.IGNORECASE))
            result.sections_complete[section] = found

        # 2. [사실/해석/판단] 태깅 체크
        fact_tags = len(re.findall(r'\[사실\]', report_text))
        interp_tags = len(re.findall(r'\[해석\]', report_text))
        judge_tags = len(re.findall(r'\[판단\]', report_text))
        result.fact_interpretation_judgment_tagged = (fact_tags + interp_tags + judge_tags) >= 10

        # 3. 소스 라벨 태깅 체크 ([A], [B], [C] 등)
        source_labels = len(re.findall(r'\[[A-I]\]', report_text))
        result.source_labels_tagged = source_labels >= 15

        # 4. 스코어카드 존재 체크
        result.score_calculation_correct = bool(
            re.search(r'가중\s*총점|Total.*Score', report_text, re.IGNORECASE)
        )

        # 5. 판정 일관성 체크
        result.verdict_consistent = bool(
            re.search(r'(Go|No-Go|Conditional)', report_text)
        )

        # 누락 항목 집계
        result.missing_items = [
            section for section, found in result.sections_complete.items()
            if not found
        ]

        if not result.fact_interpretation_judgment_tagged:
            result.missing_items.append("[사실/해석/판단] 태깅 부족")
        if not result.source_labels_tagged:
            result.missing_items.append("소스 라벨 태깅 부족")

        # 최종 판정
        sections_passed = sum(result.sections_complete.values()) >= 10
        result.passed = (
            sections_passed and
            result.fact_interpretation_judgment_tagged and
            result.source_labels_tagged and
            result.verdict_consistent
        )

        return result


def create_generator(provider: Optional[str] = None) -> ReportGenerator:
    """ReportGenerator 생성 헬퍼 함수"""
    return ReportGenerator(provider=provider)
