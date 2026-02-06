"""
기업 분석 프롬프트 빌더 모듈

company_analysis_prompt_v4.md 템플릿에 데이터를 삽입하여
LLM에 전달할 최종 프롬프트를 생성합니다.
"""

import json
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

from analyzers.models import (
    AnalysisDataBundle,
    ApplicantProfile,
    PriorityWeights
)

logger = logging.getLogger(__name__)


class PromptBuilder:
    """분석 프롬프트 조립"""

    # 프롬프트 템플릿 (company_analysis_prompt_v4.md 핵심 부분)
    PROMPT_TEMPLATE = '''# Role & Persona

너는 지원 기업과 포지션에 최적화된 '채용 실사(Due Diligence) 분석가'다.
아래 규칙으로 페르소나를 먼저 정의하고, 그 관점과 목소리로 보고서 전체를 작성하라.

## 페르소나 자동 설정 규칙

| 기업 유형 | 직무 계열 | 페르소나 |
|-----------|-----------|----------|
| IT/플랫폼/스타트업 | 개발/데이터 | 기술 중심 테크 리크루팅 전문가 |
| 대기업/중견 | 기획/사업/전략 | 전략 경영 컨설턴트 |
| 외국계/소비재/브랜드 | 마케팅/세일즈 | 글로벌 커리어 코치 |
| 제조/하드웨어 | 생산/품질/공정 | 운영혁신(Operational Excellence) 컨설턴트 |
| B2B SaaS | CS/운영/프로덕트 | GTM/프로덕트 운영 분석가 |

위 규칙에 정확히 맞지 않으면, 기업 특성과 JD의 핵심 성과지표(KPI)에 맞춰 가장 타당한 페르소나를 직접 설계하라.

---

# Context

나는 [{company_name}]의 [{position_title}]에 지원하려고 한다.
제공하는 데이터 소스를 종합 분석하여 아래를 수행하라:
1. 입사 추천도를 판단하고
2. 실전 면접 전략(예상 질문 + 역질문)을 만들고
3. 최종 지원 의사결정에 필요한 인사이트를 도출하라

---

# Data Inputs

## 소스 A: 기업 기본 정보 (companies 테이블)
<company_info>
{company_info}
</company_info>

## 소스 B: 채용공고 (job_postings 테이블)
<job_postings>
{job_postings}
</job_postings>

※ 동일 기업의 다른 공고가 포함되어 있으면 복수 공고 교차 분석을 수행하라.

## 소스 C: 재직자 후기 (company_reviews 테이블)
<company_reviews>
{company_reviews}
</company_reviews>

## 소스 D: 면접 후기 (company_interviews 테이블)
<company_interviews>
{company_interviews}
</company_interviews>

## 소스 E: 급여 정보 (company_salaries 테이블)
<company_salaries>
{company_salaries}
</company_salaries>

## 소스 F: 복리후생 (company_benefits 테이블)
<company_benefits>
{company_benefits}
</company_benefits>

## 소스 G: 뉴스 기사 (company_news 테이블)
<company_news>
{company_news}
</company_news>

## [선택] 소스 H: 시장 분석 (market_analysis 테이블)
<market_analysis>
{market_analysis}
</market_analysis>

## [선택] 소스 I: 스킬 트렌드 (skill_trends 테이블)
<skill_trends>
{skill_trends}
</skill_trends>

{applicant_section}

{weights_section}

---

# Data Source Registry

아래는 각 소스의 라벨, 편향 특성, 활용 지침이다. 보고서 전체에서 이 라벨을 일관되게 사용하라.

| 라벨 | 소스 | 편향 특성 | 세부 등급 | 활용 지침 |
|------|------|-----------|-----------|-----------|
| **[A]** | 기업 기본정보 | 공식 등록 정보 | — | 팩트 기반, 그대로 인용 가능 |
| **[B]** | 채용공고 | 긍정 편향 (회사의 자기 PR) | — | 행간 분석 필수, 문자 그대로 신뢰 금지 |
| **[C]** | 재직자 후기 | 부정 편향 (불만족자 과대 대표) | C+ / C / C- | 패턴 중심 분석, 개별 리뷰 인용 금지 |
| **[D]** | 면접 후기 | 혼합 (결과에 따라 톤 변동) | D+ / D / D- | 난이도·질문 패턴에 집중, 감정적 평가 필터링 |
| **[E]** | 급여 정보 | 자기보고 편향 | — | industry_avg와 교차 비교 필수 |
| **[F]** | 복리후생 | 비교적 객관적 (제도 기반) | — | category_rating과 item_score 활용 |
| **[G]** | 뉴스 기사 | 매체별 차등 | G+ / G / G- | 기사 유형 분류 필수 |
| **[H]** | 시장 분석 | 집계 데이터 | — | 시장 맥락 제공용 |
| **[I]** | 스킬 트렌드 | 집계 데이터 | — | 기술 스택 미래 가치 평가용 |

---

# Global Rules

## 1. JD 중심 분석
모든 판단과 평가는 채용공고(소스 B)의 JD 항목과의 연결성을 기준으로 한다.

## 2. 사실 / 해석 / 판단의 명확한 분리
보고서의 모든 서술에 아래 라벨을 인라인으로 태깅하라:
- **[사실]**: 소스에 직접 명시된 내용
- **[해석]**: 사실로부터 논리적으로 추론한 내용. 반드시 근거를 함께 서술.
- **[판단]**: 해석을 종합한 최종 의견. 판단 기준을 명시.

## 3. 소스 편향 통제
각 소스 분석 시 아래 3축으로 정보의 가중치를 조절하라:
- **최근성**: 최근 데이터(created_at/published_at 기준)에 높은 가중치
- **반복성**: 여러 건에서 반복되는 내용에 높은 가중치
- **직무관련성**: 지원 포지션의 job_category와 일치하는 데이터에 높은 가중치

## 4. 불확실성 처리
- 근거 부족 → **[확인 필요]** 라벨 + 면접 검증 질문으로 전환
- 소스 간 불일치 → 양쪽 해석 모두 제시, 단정 금지
- 판단 곤란 → **"보수적 판단"** 원칙 (리스크를 과소평가하지 않는다)

## 5. 작성 스타일
- 언어: 한국어 / 톤: 전문적, 명확, 간결 (존댓말)
- 원문 나열 금지, 분석 결과를 서술형으로 작성
- 후기는 개별 인용 대신 반복 패턴 요약

---

# Evaluation Procedure (평가 절차)

종합 평가(Output 섹션 9)를 작성할 때 반드시 아래 4단계를 순서대로 수행하라.

**Step 1 — 채점:**
아래 5개 평가축을 각각 1~5점으로 채점하라.

| 평가축 | 평가 기준 | 주요 참조 소스 |
|--------|-----------|---------------|
| 직무적합성 | JD 요구 역량과 지원자 경험/스킬의 연결성. 지원자 미제공 시 JD 역할의 시장 매력도로 대체 | B, I, H |
| 성장성 | 역할의 학습 자산, 시장/산업 성장성, 기술 스택 미래 가치, 커리어 확장 가능성 | B, G, H, I |
| 안정성 | 사업 모델 건전성, 조직 리스크, 기업 규모/업력 | A, G, C |
| 보상·근무조건 | 시장 대비 급여 수준(industry_avg 비교), 복리후생, 워라밸 | E, F, C |
| 조직운영 적합성 | 의사결정 구조, 협업 방식, 리더십 스타일, 면접 프로세스 합리성 | C, D, G |

**Step 2 — 근거 제시:**
각 축별 1~2문장의 근거. 반드시 소스 라벨 + [사실/해석/판단] 태그 포함.

**Step 3 — 종합 점수 계산:**
- 개인 가중치 제공 시: 가중 평균
- 미제공 시: 단순 평균 (각 축 20%)

**Step 4 — 등급 판정:**

| 점수 구간 | 등급 | 의미 |
|-----------|------|------|
| 3.7 이상 | 긍정적 | 적극 지원 권장 |
| 2.4 ~ 3.6 | 보통 | 조건부 지원, 면접에서 리스크 검증 필요 |
| 2.3 이하 | 부정적 | 신중한 재고 필요 |

※ 입사 추천도 = 5개 축 전체로 판정
※ 회사 비전 전망 = 성장성 + 안정성 두 축의 평균으로 별도 판정

---

# Output Structure

반드시 아래 순서와 형식을 준수하라. 섹션을 건너뛰지 마라.

## 1. 페르소나 설정
## 2. Executive Summary
## 3. 회사 프로필 [소스 A + G 기반]
## 4. 채용 포지션 심층 분석 [소스 B 기반]
## 5. 기술 스택 미래 가치 분석 [소스 B + I 기반]
## 6. 내부 실태 분석 [소스 C + E + F 기반]
## 7. 외부 환경 분석 [소스 G + H 기반]
## 8. 교차 검증 (다중 소스 삼각 검증)
## 9. 종합 평가
## 10. 실전 면접 대비 [소스 D 적극 활용]
## 11. 페르소나 최종 코멘트
## 12. 참고 자료

---

이제 위 지침을 따라 보고서를 작성하라.
'''

    APPLICANT_SECTION_TEMPLATE = '''## [선택] 지원자 프로필
<applicant_context>
- 현재 경력: {current_experience}
- 핵심 스킬: {core_skills}
- 지원 동기: {motivation}
- 희망 커리어 방향: {career_direction}
</applicant_context>
'''

    WEIGHTS_SECTION_TEMPLATE = '''## [선택] 개인 우선순위 가중치 (합계 100)
<priority_weights>
- 성장성: {growth}
- 안정성: {stability}
- 보상: {compensation}
- 워라밸: {work_life_balance}
- 직무적합: {job_fit}
</priority_weights>

※ 가중치가 제공되지 않으면 균등 배분(각 20)으로 처리하라.
'''

    def __init__(self, template_path: Optional[str] = None):
        """
        Args:
            template_path: 커스텀 템플릿 경로 (미지정 시 내장 템플릿 사용)
        """
        self.template = self.PROMPT_TEMPLATE
        if template_path:
            self._load_template(template_path)

    def _load_template(self, template_path: str):
        """외부 템플릿 파일 로드"""
        path = Path(template_path)
        if path.exists():
            content = path.read_text(encoding='utf-8')
            # 프롬프트 본문 부분만 추출 (```와 ``` 사이)
            match = re.search(r'```\n(.*?)```', content, re.DOTALL)
            if match:
                self.template = match.group(1)
            else:
                logger.warning(f"템플릿에서 프롬프트 본문을 찾을 수 없음: {template_path}")

    def build_prompt(
        self,
        data_bundle: AnalysisDataBundle,
        applicant_profile: Optional[ApplicantProfile] = None,
        priority_weights: Optional[PriorityWeights] = None
    ) -> str:
        """
        프롬프트 조립

        Args:
            data_bundle: 수집된 데이터 번들
            applicant_profile: 지원자 프로필 (선택)
            priority_weights: 우선순위 가중치 (선택)

        Returns:
            LLM에 전달할 최종 프롬프트
        """
        # 회사명 및 포지션 추출
        company_name = data_bundle.company_name
        position_title = self._get_position_title(data_bundle)

        # 각 소스 포매팅 (정제된 데이터 우선 사용)
        company_info = self._format_company_info(data_bundle.company_info)
        job_postings = self._format_job_postings(data_bundle.job_postings)

        # 정제된 데이터가 있으면 활용
        reviews = self._format_reviews_processed(data_bundle.processed_reviews) \
            if data_bundle.processed_reviews else self._format_reviews(data_bundle.reviews)

        interviews = self._format_interviews_processed(data_bundle.processed_interviews) \
            if data_bundle.processed_interviews else self._format_interviews(data_bundle.interviews)

        salaries = self._format_salaries_processed(data_bundle.processed_salaries) \
            if data_bundle.processed_salaries else self._format_salaries(data_bundle.salaries)

        benefits = self._format_benefits_processed(data_bundle.processed_benefits) \
            if data_bundle.processed_benefits else self._format_benefits(data_bundle.benefits)

        news = self._format_news_processed(data_bundle.processed_news) \
            if data_bundle.processed_news else self._format_news(data_bundle.news)

        market = self._format_market_analysis(data_bundle.market_analysis)

        skills = self._format_skill_analysis(data_bundle.skill_analysis) \
            if data_bundle.skill_analysis else self._format_skill_trends(data_bundle.skill_trends)

        # 지원자 섹션
        applicant_section = ""
        if applicant_profile:
            applicant_section = self.APPLICANT_SECTION_TEMPLATE.format(
                current_experience=applicant_profile.current_experience or "미제공",
                core_skills=", ".join(applicant_profile.core_skills) if applicant_profile.core_skills else "미제공",
                motivation=applicant_profile.motivation or "미제공",
                career_direction=applicant_profile.career_direction or "미제공"
            )

        # 가중치 섹션
        weights_section = ""
        if priority_weights and priority_weights.validate():
            weights_section = self.WEIGHTS_SECTION_TEMPLATE.format(
                growth=priority_weights.growth,
                stability=priority_weights.stability,
                compensation=priority_weights.compensation,
                work_life_balance=priority_weights.work_life_balance,
                job_fit=priority_weights.job_fit
            )

        # 프롬프트 조립
        prompt = self.template.format(
            company_name=company_name,
            position_title=position_title,
            company_info=company_info,
            job_postings=job_postings,
            company_reviews=reviews,
            company_interviews=interviews,
            company_salaries=salaries,
            company_benefits=benefits,
            company_news=news,
            market_analysis=market,
            skill_trends=skills,
            applicant_section=applicant_section,
            weights_section=weights_section
        )

        # 토큰 최적화 (연속 공백/개행 제거)
        prompt = re.sub(r'\n{3,}', '\n\n', prompt)
        prompt = re.sub(r' {2,}', ' ', prompt)

        return prompt

    def _get_position_title(self, data_bundle: AnalysisDataBundle) -> str:
        """채용공고에서 포지션 타이틀 추출"""
        if data_bundle.job_postings:
            # 타겟 공고가 있으면 첫 번째 공고의 타이틀 사용
            return data_bundle.job_postings[0].get('title', '미지정 포지션')
        return '미지정 포지션'

    def _format_company_info(self, data: dict) -> str:
        """소스 A: 기업 기본정보 포매팅"""
        if not data:
            return "데이터 미제공"

        lines = []
        field_map = {
            'name': '회사명',
            'industry': '산업',
            'company_size': '기업 규모',
            'founded_year': '설립연도',
            'location': '위치',
            'employee_count': '직원 수',
            'description': '회사 소개',
            'website': '웹사이트',
            'jobplanet_rating': '잡플래닛 평점',
            'revenue': '매출',
        }

        for key, label in field_map.items():
            value = data.get(key)
            if value:
                lines.append(f"- {label}: {value}")

        return '\n'.join(lines) if lines else "데이터 미제공"

    def _format_job_postings(self, data: List[dict]) -> str:
        """소스 B: 채용공고 포매팅"""
        if not data:
            return "데이터 미제공"

        sections = []
        for i, job in enumerate(data, 1):
            job_lines = [f"### 공고 {i}: {job.get('title', 'N/A')}"]

            if job.get('job_category'):
                job_lines.append(f"- 직군: {job['job_category']}")
            if job.get('position_level'):
                job_lines.append(f"- 포지션 레벨: {job['position_level']}")
            if job.get('experience_level'):
                job_lines.append(f"- 경력 요건: {job['experience_level']}")
            if job.get('location'):
                job_lines.append(f"- 근무지: {job['location']}")
            if job.get('salary_info'):
                job_lines.append(f"- 급여: {job['salary_info']}")

            # 주요 업무
            if job.get('main_tasks'):
                job_lines.append(f"\n**주요 업무:**\n{job['main_tasks'][:1000]}")

            # 자격 요건
            if job.get('requirements'):
                job_lines.append(f"\n**자격 요건:**\n{job['requirements'][:1000]}")

            # 우대 사항
            if job.get('preferred'):
                job_lines.append(f"\n**우대 사항:**\n{job['preferred'][:500]}")

            # 필수 스킬
            required_skills = job.get('required_skills', [])
            if required_skills:
                job_lines.append(f"\n**required_skills (JSON):** {json.dumps(required_skills, ensure_ascii=False)}")

            # 우대 스킬
            preferred_skills = job.get('preferred_skills', [])
            if preferred_skills:
                job_lines.append(f"**preferred_skills (JSON):** {json.dumps(preferred_skills, ensure_ascii=False)}")

            if job.get('url'):
                job_lines.append(f"\n- URL: {job['url']}")

            sections.append('\n'.join(job_lines))

        return '\n\n'.join(sections)

    def _format_reviews(self, data: Optional[List[dict]]) -> str:
        """소스 C: 재직자 후기 포매팅"""
        if not data:
            return "데이터 미제공"

        # 통계 요약
        total = len(data)
        ratings = [r.get('total_rating') for r in data if r.get('total_rating')]
        avg_rating = sum(ratings) / len(ratings) if ratings else 0

        lines = [
            f"총 {total}건의 리뷰 (평균 평점: {avg_rating:.1f}/5.0)",
            ""
        ]

        # 샘플 리뷰 (최대 10건)
        for i, review in enumerate(data[:10], 1):
            review_lines = [f"### 리뷰 {i}"]
            if review.get('job_category'):
                review_lines.append(f"- 직군: {review['job_category']}")
            if review.get('total_rating'):
                review_lines.append(f"- 평점: {review['total_rating']}/5.0")
            if review.get('category_scores'):
                review_lines.append(f"- category_scores (JSON): {json.dumps(review['category_scores'], ensure_ascii=False)}")
            if review.get('pros'):
                review_lines.append(f"- 장점 (pros): {review['pros'][:300]}...")
            if review.get('cons'):
                review_lines.append(f"- 단점 (cons): {review['cons'][:300]}...")
            if review.get('advice'):
                review_lines.append(f"- 경영진에게 (advice): {review['advice'][:200]}...")
            if review.get('write_date'):
                review_lines.append(f"- 작성일: {review['write_date']}")

            lines.append('\n'.join(review_lines))

        return '\n\n'.join(lines)

    def _format_interviews(self, data: Optional[List[dict]]) -> str:
        """소스 D: 면접 후기 포매팅"""
        if not data:
            return "데이터 미제공"

        lines = [f"총 {len(data)}건의 면접 후기", ""]

        for i, interview in enumerate(data[:15], 1):
            int_lines = [f"### 면접 {i}"]
            if interview.get('job_category'):
                int_lines.append(f"- 직군: {interview['job_category']}")
            if interview.get('difficulty'):
                int_lines.append(f"- 난이도 (difficulty): {interview['difficulty']}")
            if interview.get('result'):
                int_lines.append(f"- 결과 (result): {interview['result']}")
            if interview.get('question'):
                int_lines.append(f"- 질문 (question): {interview['question'][:500]}")
            if interview.get('answer'):
                int_lines.append(f"- 답변 (answer): {interview['answer'][:300]}...")
            if interview.get('interview_date'):
                int_lines.append(f"- 면접일: {interview['interview_date']}")

            lines.append('\n'.join(int_lines))

        return '\n\n'.join(lines)

    def _format_salaries(self, data: Optional[List[dict]]) -> str:
        """소스 E: 급여 정보 포매팅"""
        if not data:
            return "데이터 미제공"

        lines = []

        # 전체 평균 찾기
        for s in data:
            if s.get('is_overall_avg'):
                lines.append("### 전체 평균")
                if s.get('salary_amount'):
                    lines.append(f"- 평균 연봉: {s['salary_amount']:,}만원")
                if s.get('industry_avg'):
                    lines.append(f"- 업계 평균 (industry_avg): {s['industry_avg']:,}만원")
                if s.get('industry_rank'):
                    lines.append(f"- 업계 순위: {s['industry_rank']}")
                if s.get('salary_min') and s.get('salary_max'):
                    lines.append(f"- 연봉 범위: {s['salary_min']:,} ~ {s['salary_max']:,}만원")
                lines.append("")
                break

        # 경력별
        lines.append("### 경력별 연봉")
        for s in data:
            if not s.get('is_overall_avg') and s.get('experience_year'):
                amount = s.get('salary_amount', 0)
                lines.append(f"- {s['experience_year']}: {amount:,}만원")

        return '\n'.join(lines)

    def _format_benefits(self, data: Optional[List[dict]]) -> str:
        """소스 F: 복리후생 포매팅"""
        if not data:
            return "데이터 미제공"

        # 카테고리별 그룹화
        by_category: Dict[str, List[dict]] = {}
        for b in data:
            cat = b.get('category', '기타')
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(b)

        lines = [f"총 {len(data)}건의 복지 후기", ""]

        for category, items in by_category.items():
            ratings = [i.get('category_rating') for i in items if i.get('category_rating')]
            avg = sum(ratings) / len(ratings) if ratings else 0

            lines.append(f"### {category} (category_rating 평균: {avg:.1f})")

            for item in items[:3]:
                if item.get('content'):
                    lines.append(f"- {item['content'][:200]}")
                if item.get('item_scores'):
                    lines.append(f"  - item_scores: {json.dumps(item['item_scores'], ensure_ascii=False)}")

            lines.append("")

        return '\n'.join(lines)

    def _format_news(self, data: Optional[List[dict]]) -> str:
        """소스 G: 뉴스 기사 포매팅"""
        if not data:
            return "데이터 미제공"

        lines = [f"총 {len(data)}건의 뉴스 기사 (시간순)", ""]

        for i, news in enumerate(data[:20], 1):
            news_lines = [f"### 기사 {i}: {news.get('title', 'N/A')}"]
            if news.get('published_at'):
                news_lines.append(f"- 발행일 (published_at): {news['published_at']}")
            if news.get('source_site'):
                news_lines.append(f"- 출처 (source_site): {news['source_site']}")
            if news.get('content'):
                news_lines.append(f"- 내용 요약: {news['content'][:300]}...")
            if news.get('news_url'):
                news_lines.append(f"- URL: {news['news_url']}")

            lines.append('\n'.join(news_lines))

        return '\n\n'.join(lines)

    def _format_market_analysis(self, data: Optional[dict]) -> str:
        """소스 H: 시장 분석 포매팅"""
        if not data:
            return "데이터 미제공"

        lines = []
        if data.get('keyword'):
            lines.append(f"- 분석 키워드: {data['keyword']}")
        if data.get('total_postings'):
            lines.append(f"- 전체 공고 수 (total_postings): {data['total_postings']}")
        if data.get('top_companies'):
            lines.append(f"- 상위 채용 기업 (top_companies): {json.dumps(data['top_companies'], ensure_ascii=False)}")
        if data.get('top_skills'):
            lines.append(f"- 상위 요구 스킬 (top_skills): {json.dumps(data['top_skills'], ensure_ascii=False)}")
        if data.get('market_summary'):
            lines.append(f"- 시장 요약 (market_summary): {data['market_summary'][:500]}")
        if data.get('recommendations'):
            lines.append(f"- 추천 사항 (recommendations): {data['recommendations'][:500]}")

        return '\n'.join(lines) if lines else "데이터 미제공"

    def _format_skill_trends(self, data: Optional[List[dict]]) -> str:
        """소스 I: 스킬 트렌드 포매팅"""
        if not data:
            return "데이터 미제공"

        lines = [f"총 {len(data)}개 스킬의 트렌드 데이터", ""]
        lines.append("| skill_name | mention_count | trend_direction | category |")
        lines.append("|------------|---------------|-----------------|----------|")

        for skill in data[:30]:
            name = skill.get('skill_name', 'N/A')
            count = skill.get('mention_count', 0)
            trend = skill.get('trend_direction', 'N/A')
            cat = skill.get('category', 'N/A')
            lines.append(f"| {name} | {count} | {trend} | {cat} |")

        return '\n'.join(lines)

    def estimate_tokens(self, prompt: str) -> int:
        """토큰 수 추정 (대략적)"""
        # 한국어는 대략 글자당 1.5토큰, 영어는 단어당 1토큰
        korean_chars = len(re.findall(r'[가-힣]', prompt))
        other_chars = len(prompt) - korean_chars

        estimated = int(korean_chars * 1.5 + other_chars * 0.3)
        return estimated

    # ========== 정제된 데이터 포매팅 메서드 (Phase 2) ==========

    def _format_reviews_processed(self, data) -> str:
        """정제된 리뷰 데이터 포매팅"""
        from analyzers.models import ProcessedReviews
        if not data or not isinstance(data, ProcessedReviews):
            return "데이터 미제공"

        lines = [
            f"## 리뷰 통계 분석 (총 {data.total_count}건)",
            f"- **평균 평점**: {data.avg_rating}/5.0",
            ""
        ]

        # 평점 분포
        if data.rating_distribution:
            lines.append("### 평점 분포")
            for rating, count in sorted(data.rating_distribution.items()):
                lines.append(f"- {rating}점: {count}건")
            lines.append("")

        # 항목별 세부 평점
        if data.category_score_stats:
            lines.append("### 항목별 세부 평점 (category_scores 분석)")
            lines.append("| 항목 | 평균 | 중앙값 | 최소 | 최대 |")
            lines.append("|------|------|--------|------|------|")
            for cat, stats in data.category_score_stats.items():
                lines.append(f"| {cat} | {stats['avg']} | {stats['median']} | {stats['min']} | {stats['max']} |")
            lines.append("")

        # 키워드 분석
        if data.pros_keywords:
            lines.append("### 장점 키워드 (pros 빈도 분석)")
            keywords_str = ", ".join([f"{kw}({cnt})" for kw, cnt in data.pros_keywords[:10]])
            lines.append(f"- {keywords_str}")
            lines.append("")

        if data.cons_keywords:
            lines.append("### 단점 키워드 (cons 빈도 분석)")
            keywords_str = ", ".join([f"{kw}({cnt})" for kw, cnt in data.cons_keywords[:10]])
            lines.append(f"- {keywords_str}")
            lines.append("")

        # advice 패턴
        if data.advice_patterns:
            lines.append("### 경영진에게 바라는 점 주요 패턴 (advice 분석)")
            for pattern in data.advice_patterns:
                lines.append(f"- {pattern}")
            lines.append("")

        # 시기별 트렌드
        if data.trend_by_period:
            lines.append("### 시기별 평점 추이")
            for period, rating in list(data.trend_by_period.items())[-6:]:  # 최근 6개 기간
                lines.append(f"- {period}: {rating}/5.0")
            lines.append("")

        # 직군별 분석
        if data.by_job_category:
            lines.append("### 직군별 분석")
            for cat, info in data.by_job_category.items():
                lines.append(f"- **{cat}** ({info['count']}건, 평균 {info['avg_rating']}/5.0)")
            lines.append("")

        # 샘플 리뷰 (최대 5건)
        if data.raw_reviews:
            lines.append("### 대표 리뷰 샘플 (최근 5건)")
            for i, review in enumerate(data.raw_reviews[:5], 1):
                lines.append(f"#### 리뷰 {i}")
                if review.get('job_category'):
                    lines.append(f"- 직군: {review['job_category']}")
                if review.get('total_rating'):
                    lines.append(f"- 평점: {review['total_rating']}/5.0")
                if review.get('pros'):
                    lines.append(f"- 장점: {review['pros'][:200]}...")
                if review.get('cons'):
                    lines.append(f"- 단점: {review['cons'][:200]}...")
                lines.append("")

        return '\n'.join(lines)

    def _format_interviews_processed(self, data) -> str:
        """정제된 면접 후기 포매팅"""
        from analyzers.models import ProcessedInterviews
        if not data or not isinstance(data, ProcessedInterviews):
            return "데이터 미제공"

        lines = [
            f"## 면접 분석 (총 {data.total_count}건)",
            ""
        ]

        # 난이도 분석
        if data.difficulty_distribution:
            lines.append("### 면접 난이도 분포 (difficulty)")
            for diff, count in data.difficulty_distribution.items():
                lines.append(f"- {diff}: {count}건")
            if data.avg_difficulty:
                lines.append(f"- **평균 난이도**: {data.avg_difficulty}")
            lines.append("")

        # 합격률
        if data.result_distribution:
            lines.append("### 면접 결과 분포 (result)")
            for result, count in data.result_distribution.items():
                lines.append(f"- {result}: {count}건")
            lines.append(f"- **추정 합격률**: {data.pass_rate}%")
            lines.append("")

        # 질문 유형별 분류
        if data.question_types:
            lines.append("### 면접 질문 유형 분류")
            for q_type, questions in data.question_types.items():
                if questions:
                    lines.append(f"\n#### {q_type} 질문 ({len(questions)}건)")
                    for q in questions[:3]:
                        lines.append(f"- {q[:150]}...")
            lines.append("")

        # 직군별 분석
        if data.by_job_category:
            lines.append("### 직군별 면접 특성")
            for cat, info in data.by_job_category.items():
                lines.append(f"- **{cat}**: {info['count']}건, 평균 난이도 {info['difficulty_avg']}")
            lines.append("")

        return '\n'.join(lines)

    def _format_salaries_processed(self, data) -> str:
        """정제된 급여 데이터 포매팅"""
        from analyzers.models import ProcessedSalaries
        if not data or not isinstance(data, ProcessedSalaries):
            return "데이터 미제공"

        lines = ["## 급여 분석", ""]

        # 전체 평균
        if data.overall_avg:
            lines.append("### 전체 평균 연봉")
            lines.append(f"- **평균 연봉**: {data.overall_avg:,}만원")
            if data.industry_avg:
                lines.append(f"- **업계 평균 (industry_avg)**: {data.industry_avg:,}만원")
            if data.vs_industry_percent is not None:
                sign = "+" if data.vs_industry_percent > 0 else ""
                lines.append(f"- **업계 대비**: {sign}{data.vs_industry_percent}%")
            if data.salary_min and data.salary_max:
                lines.append(f"- **연봉 범위**: {data.salary_min:,} ~ {data.salary_max:,}만원")
            lines.append("")

        # 경력별 연봉
        if data.by_experience:
            lines.append("### 경력별 연봉 (experience_year)")
            for exp, amount in sorted(data.by_experience.items()):
                lines.append(f"- {exp}: {amount:,}만원")
            lines.append("")

        # 직급별 연봉
        if data.by_position:
            lines.append("### 직급별 연봉 (position)")
            for pos, amount in data.by_position.items():
                lines.append(f"- {pos}: {amount:,}만원")
            lines.append("")

        return '\n'.join(lines) if len(lines) > 2 else "데이터 미제공"

    def _format_benefits_processed(self, data) -> str:
        """정제된 복리후생 포매팅"""
        from analyzers.models import ProcessedBenefits
        if not data or not isinstance(data, ProcessedBenefits):
            return "데이터 미제공"

        lines = [f"## 복리후생 분석 (총 {data.total_count}건)", ""]

        # 카테고리별 평점
        if data.category_ratings:
            lines.append("### 카테고리별 평점 (category_rating)")
            lines.append("| 카테고리 | 평점 |")
            lines.append("|----------|------|")
            for cat, rating in sorted(data.category_ratings.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"| {cat} | {rating}/5.0 |")
            lines.append("")

        # 강점/약점
        if data.strongest_categories:
            lines.append(f"### 강점 복지: {', '.join(data.strongest_categories)}")
        if data.weakest_categories:
            lines.append(f"### 약점 복지: {', '.join(data.weakest_categories)}")
        lines.append("")

        # 카테고리별 상세 항목
        if data.category_items:
            lines.append("### 카테고리별 주요 항목 (item_scores)")
            for cat, items in data.category_items.items():
                lines.append(f"\n#### {cat}")
                for item in items[:3]:
                    lines.append(f"- {item['item']}: {item['score']}")
            lines.append("")

        return '\n'.join(lines)

    def _format_news_processed(self, data) -> str:
        """정제된 뉴스 데이터 포매팅"""
        from analyzers.models import ProcessedNews
        if not data or not isinstance(data, ProcessedNews):
            return "데이터 미제공"

        lines = [f"## 뉴스 분석 (총 {data.total_count}건)", ""]

        # 기사 유형 분포
        if data.by_type:
            lines.append("### 기사 유형 분포")
            for news_type, articles in data.by_type.items():
                lines.append(f"- {news_type}: {len(articles)}건")
            lines.append("")

        # 신뢰도 분포
        if data.by_reliability:
            lines.append("### 신뢰도 등급 분포")
            for reliability, articles in data.by_reliability.items():
                lines.append(f"- {reliability}: {len(articles)}건")
            lines.append("")

        # 최근 기사 타임라인
        if data.recent_news:
            lines.append(f"### 최근 6개월 기사 ({len(data.recent_news)}건)")
            for article in data.recent_news[:10]:
                title = article.get('title', 'N/A')
                date = article.get('published_at', 'N/A')
                news_type = article.get('_type', '일반')
                reliability = article.get('_reliability', 'G')
                lines.append(f"- [{date}] [{reliability}] {title} ({news_type})")
            lines.append("")

        # 전체 타임라인 (시간순)
        if data.timeline:
            lines.append("### 전체 기사 타임라인 (최신순)")
            for article in data.timeline[:15]:
                title = article.get('title', 'N/A')
                date = article.get('published_at', 'N/A')
                news_type = article.get('_type', '일반')
                reliability = article.get('_reliability', 'G')
                url = article.get('news_url', '')
                lines.append(f"- [{date}] [{reliability}] **{news_type}**: {title}")
                if article.get('content'):
                    lines.append(f"  - 요약: {article['content'][:150]}...")
            lines.append("")

        return '\n'.join(lines)

    def _format_skill_analysis(self, data) -> str:
        """정제된 스킬 분석 포매팅"""
        from analyzers.models import SkillAnalysis
        if not data or not isinstance(data, SkillAnalysis):
            return "데이터 미제공"

        lines = ["## 기술 스택 분석", ""]

        # JD에서 추출한 스킬
        if data.required_skills:
            lines.append(f"### 필수 스킬 (required_skills): {', '.join(data.required_skills)}")
        if data.preferred_skills:
            lines.append(f"### 우대 스킬 (preferred_skills): {', '.join(data.preferred_skills)}")
        lines.append("")

        # 스킬 트렌드 매칭
        if data.skill_trends:
            lines.append("### 스킬별 시장 트렌드 (skill_trends 매칭)")
            lines.append("| 스킬 | 언급 수 | 트렌드 | 카테고리 |")
            lines.append("|------|---------|--------|----------|")
            for skill, info in data.skill_trends.items():
                lines.append(f"| {skill} | {info['mention_count']} | {info['trend']} | {info['category']} |")
            lines.append("")

        # 상승/하락/유지 분류
        if data.rising_skills:
            lines.append(f"### 상승 추세 스킬: {', '.join(data.rising_skills)}")
        if data.falling_skills:
            lines.append(f"### 하락 추세 스킬: {', '.join(data.falling_skills)}")
        if data.stable_skills:
            lines.append(f"### 유지 추세 스킬: {', '.join(data.stable_skills)}")

        return '\n'.join(lines) if len(lines) > 2 else "데이터 미제공"
