"""
시장 분석 모듈
채용 시장 트렌드, 통계 분석
"""

from typing import List, Dict, Any, Optional
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.database import db, JobPosting, MarketAnalysis
from utils.helpers import setup_logger, extract_skills_from_text


class MarketAnalyzer:
    """채용 시장 분석기"""

    def __init__(self, database=None):
        self.logger = setup_logger("analyzer.market")
        self.db = database if database else db
    
    def analyze_keyword(self, keyword: str, days: int = 30) -> Dict[str, Any]:
        """
        특정 키워드에 대한 시장 분석
        
        Args:
            keyword: 분석 키워드
            days: 분석 기간 (일)
            
        Returns:
            분석 결과 딕셔너리
        """
        self.logger.info(f"Analyzing market for keyword: {keyword}")

        # 데이터 조회
        jobs = self.db.get_job_postings(keyword=keyword, days=days)
        
        if not jobs:
            return {'error': 'No job postings found', 'keyword': keyword}
        
        analysis = {
            'keyword': keyword,
            'analysis_date': datetime.now().isoformat(),
            'period_days': days,
            'total_postings': len(jobs),
            'unique_companies': len(set(j.company_name for j in jobs)),
        }

        # 기본 통계
        analysis['statistics'] = self._calculate_statistics(jobs)
        
        # 회사별 분석
        analysis['top_companies'] = self._analyze_companies(jobs)
        
        # 스킬 분석
        analysis['skill_analysis'] = self._analyze_skills(jobs)
        
        # 지역별 분석
        analysis['location_analysis'] = self._analyze_locations(jobs)
        
        # 경력 요구사항 분석
        analysis['experience_analysis'] = self._analyze_experience(jobs)
        
        # 고용 형태 분석
        analysis['employment_type_analysis'] = self._analyze_employment_types(jobs)
        
        # 사이트별 분포
        analysis['site_distribution'] = self._analyze_sites(jobs)
        
        return analysis
    
    def _calculate_statistics(self, jobs: List[JobPosting]) -> Dict[str, Any]:
        """기본 통계 계산"""
        return {
            'total_count': len(jobs),
            'unique_companies': len(set(j.company_name for j in jobs)),
            'date_range': {
                'earliest': min(j.crawled_at for j in jobs).isoformat() if jobs else None,
                'latest': max(j.crawled_at for j in jobs).isoformat() if jobs else None,
            }
        }
    
    def _analyze_companies(self, jobs: List[JobPosting], top_n: int = 20) -> List[Dict]:
        """회사별 채용 현황 분석"""
        company_counts = Counter(j.company_name for j in jobs)
        
        return [
            {'company': company, 'job_count': count}
            for company, count in company_counts.most_common(top_n)
        ]
    
    def _analyze_skills(self, jobs: List[JobPosting], top_n: int = 30) -> Dict[str, Any]:
        """스킬 요구사항 분석"""
        hard_skills = Counter()
        soft_skills = Counter()
        
        for job in jobs:
            # DB에 저장된 스킬
            if job.required_skills:
                skills = job.required_skills if isinstance(job.required_skills, list) else []
                for skill in skills:
                    hard_skills[skill] += 1
            
            # 텍스트에서 추출
            full_text = f"{job.description or ''} {job.requirements or ''} {job.preferred or ''}"
            extracted = extract_skills_from_text(full_text)
            
            for skill in extracted.get('hard_skills', []):
                hard_skills[skill] += 1
            for skill in extracted.get('soft_skills', []):
                soft_skills[skill] += 1
        
        return {
            'hard_skills': [
                {'skill': skill, 'count': count, 'percentage': round(count / len(jobs) * 100, 1)}
                for skill, count in hard_skills.most_common(top_n)
            ],
            'soft_skills': [
                {'skill': skill, 'count': count, 'percentage': round(count / len(jobs) * 100, 1)}
                for skill, count in soft_skills.most_common(top_n)
            ],
        }
    
    def _analyze_locations(self, jobs: List[JobPosting], top_n: int = 15) -> List[Dict]:
        """지역별 분석"""
        location_counts = Counter()
        
        for job in jobs:
            if job.location:
                # 주요 지역명 추출
                location = job.location
                for region in ['서울', '경기', '인천', '부산', '대구', '광주', '대전', '울산', '세종', '판교', '강남', '성남']:
                    if region in location:
                        location_counts[region] += 1
                        break
                else:
                    location_counts['기타'] += 1
        
        total = sum(location_counts.values())
        return [
            {'location': loc, 'count': count, 'percentage': round(count / total * 100, 1) if total else 0}
            for loc, count in location_counts.most_common(top_n)
        ]
    
    def _analyze_experience(self, jobs: List[JobPosting]) -> Dict[str, Any]:
        """경력 요구사항 분석"""
        experience_counts = defaultdict(int)
        
        for job in jobs:
            level = job.position_level or '미상'
            
            # 분류
            level_lower = level.lower()
            if any(word in level_lower for word in ['신입', '0년', 'entry', 'junior']):
                experience_counts['신입'] += 1
            elif any(word in level_lower for word in ['무관', '경력무관']):
                experience_counts['경력무관'] += 1
            elif any(word in level_lower for word in ['1년', '2년', '3년']):
                experience_counts['주니어 (1-3년)'] += 1
            elif any(word in level_lower for word in ['4년', '5년', '6년', '7년']):
                experience_counts['미들 (4-7년)'] += 1
            elif any(word in level_lower for word in ['8년', '9년', '10년', '시니어', 'senior']):
                experience_counts['시니어 (8년+)'] += 1
            else:
                experience_counts['기타'] += 1
        
        total = sum(experience_counts.values())
        return {
            'distribution': [
                {'level': level, 'count': count, 'percentage': round(count / total * 100, 1) if total else 0}
                for level, count in sorted(experience_counts.items(), key=lambda x: x[1], reverse=True)
            ]
        }
    
    def _analyze_employment_types(self, jobs: List[JobPosting]) -> List[Dict]:
        """고용 형태 분석"""
        type_counts = Counter()
        
        for job in jobs:
            emp_type = job.employment_type or '미상'
            type_lower = emp_type.lower()
            
            if any(word in type_lower for word in ['정규', 'full-time', '정규직']):
                type_counts['정규직'] += 1
            elif any(word in type_lower for word in ['계약', 'contract']):
                type_counts['계약직'] += 1
            elif any(word in type_lower for word in ['인턴', 'intern']):
                type_counts['인턴'] += 1
            else:
                type_counts['기타'] += 1
        
        total = sum(type_counts.values())
        return [
            {'type': emp_type, 'count': count, 'percentage': round(count / total * 100, 1) if total else 0}
            for emp_type, count in type_counts.most_common()
        ]
    
    def _analyze_sites(self, jobs: List[JobPosting]) -> List[Dict]:
        """사이트별 분포 분석"""
        site_counts = Counter(j.source_site for j in jobs)
        total = len(jobs)
        
        return [
            {'site': site, 'count': count, 'percentage': round(count / total * 100, 1) if total else 0}
            for site, count in site_counts.most_common()
        ]
    
    def get_trend_comparison(self, keyword: str, periods: int = 4, period_days: int = 7) -> Dict[str, Any]:
        """
        기간별 트렌드 비교
        
        Args:
            keyword: 분석 키워드
            periods: 비교할 기간 수
            period_days: 각 기간의 일수
            
        Returns:
            트렌드 비교 결과
        """
        trends = []
        
        for i in range(periods):
            end_date = datetime.now() - timedelta(days=i * period_days)
            start_date = end_date - timedelta(days=period_days)
            
            session = self.db.get_session()
            try:
                jobs = session.query(JobPosting).filter(
                    JobPosting.crawled_at >= start_date,
                    JobPosting.crawled_at < end_date
                ).filter(
                    (JobPosting.title.contains(keyword)) |
                    (JobPosting.description.contains(keyword))
                ).all()
                
                period_data = {
                    'period': f"{start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}",
                    'job_count': len(jobs),
                    'unique_companies': len(set(j.company_name for j in jobs)),
                }
                
                # 해당 기간 스킬 분석
                if jobs:
                    skill_analysis = self._analyze_skills(jobs, top_n=10)
                    period_data['top_skills'] = [s['skill'] for s in skill_analysis['hard_skills'][:5]]
                
                trends.append(period_data)
            finally:
                session.close()
        
        return {
            'keyword': keyword,
            'trends': trends,
            'trend_direction': self._calculate_trend_direction(trends)
        }
    
    def _calculate_trend_direction(self, trends: List[Dict]) -> str:
        """트렌드 방향 계산"""
        if len(trends) < 2:
            return 'insufficient_data'
        
        counts = [t['job_count'] for t in trends]
        
        # 최근 vs 이전 비교
        recent = sum(counts[:len(counts)//2])
        older = sum(counts[len(counts)//2:])
        
        if older == 0:
            return 'new'
        
        change_rate = (recent - older) / older * 100
        
        if change_rate > 20:
            return 'increasing'
        elif change_rate < -20:
            return 'decreasing'
        else:
            return 'stable'
    
    def generate_summary(self, analysis: Dict[str, Any]) -> str:
        """분석 결과 요약 생성"""
        keyword = analysis.get('keyword', '')
        total = analysis.get('total_postings', 0)
        
        summary_parts = [
            f"## {keyword} 채용 시장 분석 요약\n",
            f"**분석 기간**: {analysis.get('period_days', 0)}일",
            f"**총 채용공고 수**: {total}건",
            f"**채용 기업 수**: {analysis.get('statistics', {}).get('unique_companies', 0)}개\n",
        ]
        
        # 상위 채용 기업
        top_companies = analysis.get('top_companies', [])[:5]
        if top_companies:
            summary_parts.append("### 상위 채용 기업")
            for i, company in enumerate(top_companies, 1):
                summary_parts.append(f"{i}. {company['company']} ({company['job_count']}건)")
        
        # 상위 요구 스킬
        skill_analysis = analysis.get('skill_analysis', {})
        top_skills = skill_analysis.get('hard_skills', [])[:10]
        if top_skills:
            summary_parts.append("\n### 상위 요구 스킬 (하드스킬)")
            for i, skill in enumerate(top_skills, 1):
                summary_parts.append(f"{i}. {skill['skill']} ({skill['percentage']}%)")
        
        # 지역 분포
        locations = analysis.get('location_analysis', [])[:5]
        if locations:
            summary_parts.append("\n### 주요 채용 지역")
            for loc in locations:
                summary_parts.append(f"- {loc['location']}: {loc['percentage']}%")
        
        return '\n'.join(summary_parts)


# 테스트용
if __name__ == "__main__":
    analyzer = MarketAnalyzer()
    
    # 테스트 분석
    result = analyzer.analyze_keyword("데이터 분석가", days=30)
    print(json.dumps(result, ensure_ascii=False, indent=2))
