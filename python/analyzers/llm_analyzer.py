"""
LLM 기반 분석 모듈
Claude/OpenAI API를 활용한 고급 분석 및 로드맵 생성
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings
from utils.helpers import setup_logger

# API 클라이언트 임포트 (선택적)
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class LLMAnalyzer:
    """LLM 기반 분석기"""
    
    def __init__(self):
        self.logger = setup_logger("analyzer.llm")
        self.provider = settings.analyzer.llm_provider
        
        # API 클라이언트 초기화
        self.client = None
        self._init_client()
    
    def _init_client(self):
        """API 클라이언트 초기화"""
        if self.provider == "anthropic" and ANTHROPIC_AVAILABLE:
            api_key = settings.analyzer.anthropic_api_key
            if api_key:
                self.client = anthropic.Anthropic(api_key=api_key)
                self.logger.info("Initialized Anthropic client")
            else:
                self.logger.warning("Anthropic API key not set")
                
        elif self.provider == "openai" and OPENAI_AVAILABLE:
            api_key = settings.analyzer.openai_api_key
            if api_key:
                openai.api_key = api_key
                self.client = openai
                self.logger.info("Initialized OpenAI client")
            else:
                self.logger.warning("OpenAI API key not set")
        else:
            self.logger.warning(f"LLM provider {self.provider} not available")
    
    def _call_llm(self, prompt: str, system_prompt: str = "", max_tokens: int = 4096) -> Optional[str]:
        """LLM API 호출"""
        if not self.client:
            self.logger.warning("LLM client not initialized")
            return None
        
        try:
            if self.provider == "anthropic":
                message = self.client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                return message.content[0].text
                
            elif self.provider == "openai":
                response = self.client.ChatCompletion.create(
                    model="gpt-4",
                    max_tokens=max_tokens,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ]
                )
                return response.choices[0].message.content
                
        except Exception as e:
            self.logger.error(f"LLM API call failed: {e}")
            return None
    
    def analyze_market_trends(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        시장 트렌드 분석 (LLM 활용)
        
        Args:
            market_data: 시장 분석 데이터
            
        Returns:
            LLM 분석 결과
        """
        system_prompt = """당신은 한국 채용 시장 전문 분석가입니다. 
주어진 데이터를 바탕으로 채용 시장 트렌드를 분석하고, 
구직자에게 유용한 인사이트를 제공해주세요.
분석은 구체적이고 실용적인 조언을 포함해야 합니다."""
        
        prompt = f"""다음 채용 시장 데이터를 분석해주세요:

키워드: {market_data.get('keyword', '')}
총 채용공고 수: {market_data.get('total_postings', 0)}건

상위 채용 기업:
{json.dumps(market_data.get('top_companies', [])[:10], ensure_ascii=False, indent=2)}

요구 스킬 분석:
{json.dumps(market_data.get('skill_analysis', {}), ensure_ascii=False, indent=2)}

경력 요구사항:
{json.dumps(market_data.get('experience_analysis', {}), ensure_ascii=False, indent=2)}

지역 분포:
{json.dumps(market_data.get('location_analysis', [])[:10], ensure_ascii=False, indent=2)}

다음 항목들을 분석해주세요:
1. 현재 채용 시장 상황 요약
2. 주요 트렌드 3-5가지
3. 많이 뽑는 직군/직무
4. 필수로 요구되는 하드스킬 TOP 10
5. 중요한 소프트스킬
6. 경력별 채용 현황 분석
7. 지역별 기회 분석
8. 구직자를 위한 조언"""
        
        response = self._call_llm(prompt, system_prompt)
        
        return {
            'analysis_date': datetime.now().isoformat(),
            'keyword': market_data.get('keyword', ''),
            'llm_analysis': response or "LLM 분석을 수행할 수 없습니다.",
            'raw_data_summary': {
                'total_jobs': market_data.get('total_postings', 0),
                'top_skills': [s['skill'] for s in market_data.get('skill_analysis', {}).get('hard_skills', [])[:10]],
                'top_companies': [c['company'] for c in market_data.get('top_companies', [])[:5]],
            }
        }
    
    def generate_career_roadmap(
        self,
        target_role: str,
        skill_data: Dict[str, Any],
        duration_months: int = 6
    ) -> Dict[str, Any]:
        """
        커리어 로드맵 생성
        
        Args:
            target_role: 목표 직무
            skill_data: 필요한 스킬 데이터
            duration_months: 로드맵 기간 (개월)
            
        Returns:
            커리어 로드맵
        """
        system_prompt = """당신은 IT 커리어 코치이자 멘토입니다.
구직자의 목표 직무에 맞는 구체적이고 실행 가능한 학습 로드맵을 제시해주세요.
각 단계별로 학습할 내용, 프로젝트 아이디어, 추천 자료를 포함해주세요."""
        
        # 3개월 / 6개월 로드맵 요청
        prompt = f"""다음 정보를 바탕으로 '{target_role}' 직무 준비 로드맵을 만들어주세요:

## 시장에서 요구하는 스킬
하드스킬:
{json.dumps(skill_data.get('hard_skills', [])[:15], ensure_ascii=False, indent=2)}

소프트스킬:
{json.dumps(skill_data.get('soft_skills', [])[:10], ensure_ascii=False, indent=2)}

## 요청사항
1. **3개월 단기 로드맵** (주 단위 세분화)
   - 매주 학습 목표와 내용
   - 실습 프로젝트 1-2개
   - 추천 학습 자료 (무료/유료)

2. **6개월 중기 로드맵** (월 단위)
   - 월별 학습 주제와 목표
   - 포트폴리오 프로젝트 2-3개 (상세 기획)
   - 자격증/인증 취득 계획

3. **프로젝트 아이디어** (최소 5개)
   - 프로젝트명
   - 난이도 (초급/중급/고급)
   - 사용 기술 스택
   - 예상 소요 기간
   - 학습 포인트

4. **추천 학습 자료**
   - 온라인 강의 (국내/해외)
   - 추천 도서
   - 실습 플랫폼
   - 커뮤니티/스터디

5. **취업 준비 팁**
   - 이력서/포트폴리오 작성 조언
   - 기술 면접 준비
   - 코딩 테스트 대비"""
        
        response = self._call_llm(prompt, system_prompt, max_tokens=6000)
        
        return {
            'target_role': target_role,
            'duration_months': duration_months,
            'generated_date': datetime.now().isoformat(),
            'roadmap': response or "로드맵 생성에 실패했습니다.",
            'required_skills': {
                'hard_skills': [s['skill'] for s in skill_data.get('hard_skills', [])[:15]],
                'soft_skills': [s['skill'] for s in skill_data.get('soft_skills', [])[:10]],
            }
        }
    
    def analyze_company_fit(
        self,
        company_data: Dict[str, Any],
        job_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        회사-구직자 적합도 분석
        
        Args:
            company_data: 회사 분석 데이터
            job_data: 채용공고 데이터
            
        Returns:
            적합도 분석 결과
        """
        system_prompt = """당신은 채용 컨설턴트입니다.
회사 정보와 채용공고를 분석하여 구직자에게 유용한 정보를 제공해주세요.
객관적이고 균형 잡힌 시각으로 분석해주세요."""
        
        prompt = f"""다음 회사와 채용공고 정보를 분석해주세요:

## 회사 정보
회사명: {company_data.get('company_name', '')}
산업: {company_data.get('basic_info', {}).get('industry', '정보 없음')}
규모: {company_data.get('basic_info', {}).get('company_size', '정보 없음')}
평판: {company_data.get('reputation', {})}
최근 뉴스: {company_data.get('news', [])[:3]}

## 채용공고 정보
직무: {job_data.get('title', '')}
요구사항: {job_data.get('requirements', '')}
우대사항: {job_data.get('preferred', '')}
근무조건: {job_data.get('employment_type', '')} / {job_data.get('location', '')}

다음 항목을 분석해주세요:
1. 회사 개요 및 특징
2. 업계에서의 위치
3. 직원 만족도 및 기업 문화 (추정)
4. 성장 가능성
5. 이 포지션의 장단점
6. 면접 준비 시 주의사항
7. 예상 질문 및 답변 팁"""
        
        response = self._call_llm(prompt, system_prompt)
        
        return {
            'company_name': company_data.get('company_name', ''),
            'job_title': job_data.get('title', ''),
            'analysis_date': datetime.now().isoformat(),
            'fit_analysis': response or "분석을 수행할 수 없습니다.",
        }
    
    def generate_skill_learning_guide(self, skill_name: str, current_level: str = "beginner") -> Dict[str, Any]:
        """
        특정 스킬 학습 가이드 생성
        
        Args:
            skill_name: 스킬명
            current_level: 현재 수준 (beginner, intermediate, advanced)
            
        Returns:
            학습 가이드
        """
        level_korean = {
            "beginner": "입문",
            "intermediate": "중급", 
            "advanced": "고급"
        }.get(current_level, "입문")
        
        system_prompt = """당신은 IT 기술 교육 전문가입니다.
특정 기술 스킬에 대한 체계적인 학습 가이드를 제공해주세요.
실무에서 바로 활용할 수 있는 실용적인 내용을 포함해주세요."""
        
        prompt = f"""'{skill_name}' 스킬을 {level_korean} 수준에서 시작하여 마스터하기 위한 학습 가이드를 만들어주세요.

다음 내용을 포함해주세요:

1. **스킬 개요**
   - 이 스킬이 왜 중요한지
   - 어떤 직무에서 필요한지
   - 관련 기술 생태계

2. **학습 로드맵** ({level_korean} → 고급)
   - 단계별 학습 목표
   - 각 단계별 예상 소요 시간
   - 핵심 학습 주제

3. **추천 학습 자료**
   - 온라인 강의 (무료/유료)
   - 공식 문서/튜토리얼
   - 추천 도서
   - YouTube 채널

4. **실습 프로젝트** (3개 이상)
   - 프로젝트 설명
   - 난이도
   - 학습 포인트

5. **실무 활용 팁**
   - 실무에서 자주 사용되는 패턴
   - 주의사항
   - 베스트 프랙티스

6. **포트폴리오 어필 포인트**
   - 이 스킬로 어필할 수 있는 것들
   - 면접에서 예상되는 질문"""
        
        response = self._call_llm(prompt, system_prompt)
        
        return {
            'skill_name': skill_name,
            'current_level': current_level,
            'generated_date': datetime.now().isoformat(),
            'learning_guide': response or "가이드 생성에 실패했습니다.",
        }
    
    def is_available(self) -> bool:
        """LLM 사용 가능 여부 확인"""
        return self.client is not None


class FallbackAnalyzer:
    """LLM 없이 사용할 수 있는 대체 분석기"""
    
    def __init__(self):
        self.logger = setup_logger("analyzer.fallback")
    
    def generate_basic_roadmap(
        self,
        target_role: str,
        required_skills: List[str]
    ) -> Dict[str, Any]:
        """기본 로드맵 생성 (템플릿 기반)"""
        
        # 직무별 기본 로드맵 템플릿
        templates = {
            "데이터 분석가": {
                "3_months": [
                    {"week": "1-2주차", "topic": "Python 기초 & 데이터 타입", "project": "기초 문법 실습"},
                    {"week": "3-4주차", "topic": "Pandas, NumPy 기초", "project": "CSV 데이터 분석"},
                    {"week": "5-6주차", "topic": "데이터 시각화 (Matplotlib, Seaborn)", "project": "EDA 프로젝트"},
                    {"week": "7-8주차", "topic": "SQL 기초~중급", "project": "DB 쿼리 실습"},
                    {"week": "9-10주차", "topic": "통계 기초", "project": "A/B 테스트 분석"},
                    {"week": "11-12주차", "topic": "대시보드 도구 (Tableau/Power BI)", "project": "대시보드 제작"},
                ],
                "6_months": [
                    {"month": 1, "topic": "Python & 데이터 처리 기초", "milestone": "데이터 전처리 자동화"},
                    {"month": 2, "topic": "SQL & 데이터베이스", "milestone": "복잡한 쿼리 작성"},
                    {"month": 3, "topic": "통계 & 데이터 시각화", "milestone": "EDA 포트폴리오"},
                    {"month": 4, "topic": "머신러닝 기초", "milestone": "예측 모델 프로젝트"},
                    {"month": 5, "topic": "BI 도구 & 대시보드", "milestone": "실시간 대시보드"},
                    {"month": 6, "topic": "실전 프로젝트 & 포트폴리오", "milestone": "End-to-End 프로젝트"},
                ],
            },
            "백엔드 개발자": {
                "3_months": [
                    {"week": "1-2주차", "topic": "프로그래밍 언어 기초 (Python/Java)", "project": "기초 문법"},
                    {"week": "3-4주차", "topic": "웹 기초 (HTTP, REST)", "project": "간단한 API 서버"},
                    {"week": "5-6주차", "topic": "데이터베이스 (SQL, ORM)", "project": "CRUD API"},
                    {"week": "7-8주차", "topic": "프레임워크 (Django/Spring)", "project": "게시판 API"},
                    {"week": "9-10주차", "topic": "인증/보안 기초", "project": "JWT 인증 구현"},
                    {"week": "11-12주차", "topic": "배포 기초 (Docker, AWS)", "project": "서비스 배포"},
                ],
                "6_months": [
                    {"month": 1, "topic": "프로그래밍 기초", "milestone": "알고리즘 문제 50개"},
                    {"month": 2, "topic": "웹 개발 기초", "milestone": "REST API 서버"},
                    {"month": 3, "topic": "데이터베이스 & ORM", "milestone": "복잡한 쿼리 최적화"},
                    {"month": 4, "topic": "인프라 & DevOps", "milestone": "CI/CD 파이프라인"},
                    {"month": 5, "topic": "고급 주제 (캐싱, 메시지큐)", "milestone": "성능 최적화"},
                    {"month": 6, "topic": "프로젝트 & 포트폴리오", "milestone": "실서비스 수준 프로젝트"},
                ],
            },
        }
        
        # 일치하는 템플릿 찾기 또는 기본 템플릿 사용
        role_lower = target_role.lower()
        template = None
        
        for key, value in templates.items():
            if key in target_role or target_role in key:
                template = value
                break
        
        if not template:
            # 기본 템플릿
            template = {
                "3_months": [
                    {"week": f"{i*2+1}-{i*2+2}주차", "topic": f"기초 학습 {i+1}", "project": f"실습 프로젝트 {i+1}"}
                    for i in range(6)
                ],
                "6_months": [
                    {"month": i+1, "topic": f"학습 주제 {i+1}", "milestone": f"마일스톤 {i+1}"}
                    for i in range(6)
                ],
            }
        
        return {
            'target_role': target_role,
            'generated_date': datetime.now().isoformat(),
            'required_skills': required_skills[:10],
            'roadmap_3_months': template['3_months'],
            'roadmap_6_months': template['6_months'],
            'note': "이 로드맵은 기본 템플릿입니다. LLM API를 설정하면 더 맞춤화된 로드맵을 받을 수 있습니다."
        }


# 테스트용
if __name__ == "__main__":
    # LLM 분석기 테스트
    analyzer = LLMAnalyzer()
    
    if analyzer.is_available():
        print("LLM 분석기 사용 가능")
        
        # 로드맵 생성 테스트
        skill_data = {
            'hard_skills': [
                {'skill': 'Python', 'count': 100},
                {'skill': 'SQL', 'count': 90},
                {'skill': 'Pandas', 'count': 80},
            ],
            'soft_skills': [
                {'skill': '커뮤니케이션', 'count': 50},
                {'skill': '문제해결', 'count': 45},
            ]
        }
        
        roadmap = analyzer.generate_career_roadmap("데이터 분석가", skill_data, 6)
        print(roadmap['roadmap'][:1000])
    else:
        print("LLM 분석기 사용 불가 - Fallback 분석기 사용")
        
        fallback = FallbackAnalyzer()
        roadmap = fallback.generate_basic_roadmap(
            "데이터 분석가",
            ['Python', 'SQL', 'Pandas', 'Tableau']
        )
        print(json.dumps(roadmap, ensure_ascii=False, indent=2))
