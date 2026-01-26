#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Job Market Analyzer - 리포트 생성기

마크다운, HTML, PDF 형식의 분석 리포트 생성
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

sys.path.insert(0, str(Path(__file__).parent))

from utils.database import Database
from utils.helpers import setup_logger


class ReportGenerator:
    """분석 리포트 생성기"""
    
    def __init__(self, db: Database = None, output_dir: str = 'reports'):
        self.db = db
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.logger = setup_logger('report_generator')
    
    def _get_timestamp(self) -> str:
        """리포트 파일명용 타임스탬프"""
        return datetime.now().strftime('%Y%m%d_%H%M%S')
    
    def _safe_filename(self, keyword: str) -> str:
        """안전한 파일명 생성"""
        # 파일명에 사용할 수 없는 문자 제거
        invalid_chars = '<>:"/\\|?*'
        safe_name = keyword
        for char in invalid_chars:
            safe_name = safe_name.replace(char, '_')
        return safe_name
    
    def generate_markdown_report(self, keyword: str, analysis: Dict[str, Any]) -> str:
        """마크다운 형식 리포트 생성"""
        
        timestamp = self._get_timestamp()
        safe_keyword = self._safe_filename(keyword)
        filename = f"{safe_keyword}_report_{timestamp}.md"
        filepath = self.output_dir / filename
        
        # 분석 데이터 추출
        total_postings = analysis.get('total_postings', 0)
        top_companies = analysis.get('top_companies', [])
        top_skills = analysis.get('top_skills', [])
        market_summary = analysis.get('market_summary', '')
        trend_analysis = analysis.get('trend_analysis', '')
        roadmap_3months = analysis.get('roadmap_3months', '')
        roadmap_6months = analysis.get('roadmap_6months', '')
        
        # 마크다운 생성
        md_content = f"""# 채용 시장 분석 리포트: {keyword}

생성일: {datetime.now().strftime('%Y년 %m월 %d일 %H:%M')}

---

## 📊 개요

- **분석 키워드**: {keyword}
- **총 채용공고 수**: {total_postings:,}개
- **분석 기간**: 최근 30일

---

## 🏢 상위 채용 기업

| 순위 | 기업명 | 채용공고 수 |
|:----:|--------|:-----------:|
"""
        
        # 상위 기업 테이블
        if isinstance(top_companies, list):
            for i, company in enumerate(top_companies[:15], 1):
                if isinstance(company, dict):
                    name = company.get('company_name', company.get('name', 'N/A'))
                    count = company.get('count', company.get('posting_count', 0))
                else:
                    name = str(company)
                    count = '-'
                md_content += f"| {i} | {name} | {count} |\n"
        
        md_content += """
---

## 💻 주요 기술 스택

| 순위 | 기술 | 언급 횟수 | 비율 |
|:----:|------|:---------:|:----:|
"""
        
        # 상위 스킬 테이블
        if isinstance(top_skills, list):
            for i, skill in enumerate(top_skills[:20], 1):
                if isinstance(skill, dict):
                    name = skill.get('skill', skill.get('name', 'N/A'))
                    count = skill.get('count', 0)
                    ratio = skill.get('ratio', 0)
                    ratio_str = f"{ratio:.1f}%" if ratio else '-'
                else:
                    name = str(skill)
                    count = '-'
                    ratio_str = '-'
                md_content += f"| {i} | {name} | {count} | {ratio_str} |\n"
        
        md_content += """
---

## 📈 시장 분석 요약

"""
        
        if market_summary:
            md_content += f"{market_summary}\n\n"
        else:
            md_content += "_분석 요약 없음_\n\n"
        
        md_content += """---

## 📊 트렌드 분석

"""
        
        if trend_analysis:
            if isinstance(trend_analysis, str):
                md_content += f"{trend_analysis}\n\n"
            elif isinstance(trend_analysis, dict):
                md_content += f"```json\n{json.dumps(trend_analysis, ensure_ascii=False, indent=2)}\n```\n\n"
        else:
            md_content += "_트렌드 분석 없음_\n\n"
        
        md_content += """---

## 🗺️ 3개월 커리어 로드맵

"""
        
        if roadmap_3months:
            md_content += f"{roadmap_3months}\n\n"
        else:
            md_content += "_로드맵 없음_\n\n"
        
        md_content += """---

## 🗺️ 6개월 커리어 로드맵

"""
        
        if roadmap_6months:
            md_content += f"{roadmap_6months}\n\n"
        else:
            md_content += "_로드맵 없음_\n\n"
        
        md_content += """---

## 📝 참고사항

- 이 리포트는 자동 생성되었습니다.
- 데이터는 LinkedIn, 원티드, 잡코리아, 사람인, 로켓펀치에서 수집되었습니다.
- 실제 채용 시장 상황과 다를 수 있으니 참고용으로 활용해 주세요.

---

*Generated by Job Market Analyzer*
"""
        
        # 파일 저장
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        self.logger.info(f"마크다운 리포트 생성: {filepath}")
        return str(filepath)
    
    def generate_html_report(self, keyword: str, analysis: Dict[str, Any]) -> str:
        """HTML 형식 리포트 생성"""
        
        timestamp = self._get_timestamp()
        safe_keyword = self._safe_filename(keyword)
        filename = f"{safe_keyword}_report_{timestamp}.html"
        filepath = self.output_dir / filename
        
        # 분석 데이터 추출
        total_postings = analysis.get('total_postings', 0)
        top_companies = analysis.get('top_companies', [])
        top_skills = analysis.get('top_skills', [])
        market_summary = analysis.get('market_summary', '')
        roadmap_3months = analysis.get('roadmap_3months', '')
        roadmap_6months = analysis.get('roadmap_6months', '')
        
        # HTML 생성
        html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>채용 시장 분석 리포트: {keyword}</title>
    <style>
        :root {{
            --primary-color: #2563eb;
            --secondary-color: #64748b;
            --background-color: #f8fafc;
            --card-background: #ffffff;
            --text-color: #1e293b;
            --border-color: #e2e8f0;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background-color: var(--background-color);
            color: var(--text-color);
            line-height: 1.6;
            padding: 2rem;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        
        .header {{
            text-align: center;
            margin-bottom: 3rem;
            padding: 2rem;
            background: linear-gradient(135deg, var(--primary-color), #7c3aed);
            color: white;
            border-radius: 1rem;
        }}
        
        .header h1 {{
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
        }}
        
        .header .date {{
            opacity: 0.9;
            font-size: 1rem;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}
        
        .stat-card {{
            background: var(--card-background);
            padding: 1.5rem;
            border-radius: 0.75rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            text-align: center;
        }}
        
        .stat-card .number {{
            font-size: 2.5rem;
            font-weight: 700;
            color: var(--primary-color);
        }}
        
        .stat-card .label {{
            color: var(--secondary-color);
            margin-top: 0.5rem;
        }}
        
        .section {{
            background: var(--card-background);
            padding: 2rem;
            border-radius: 0.75rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 2rem;
        }}
        
        .section h2 {{
            color: var(--primary-color);
            margin-bottom: 1.5rem;
            padding-bottom: 0.75rem;
            border-bottom: 2px solid var(--border-color);
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 1rem;
        }}
        
        th, td {{
            padding: 0.75rem 1rem;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }}
        
        th {{
            background-color: var(--background-color);
            font-weight: 600;
            color: var(--secondary-color);
        }}
        
        tr:hover {{
            background-color: var(--background-color);
        }}
        
        .skill-bar {{
            background: var(--border-color);
            border-radius: 0.25rem;
            height: 8px;
            overflow: hidden;
        }}
        
        .skill-bar-fill {{
            background: var(--primary-color);
            height: 100%;
            border-radius: 0.25rem;
        }}
        
        .roadmap {{
            white-space: pre-wrap;
            background: var(--background-color);
            padding: 1.5rem;
            border-radius: 0.5rem;
            font-size: 0.95rem;
            line-height: 1.8;
        }}
        
        .footer {{
            text-align: center;
            color: var(--secondary-color);
            margin-top: 3rem;
            padding-top: 2rem;
            border-top: 1px solid var(--border-color);
        }}
        
        @media (max-width: 768px) {{
            body {{
                padding: 1rem;
            }}
            
            .header h1 {{
                font-size: 1.75rem;
            }}
            
            .stat-card .number {{
                font-size: 1.75rem;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header class="header">
            <h1>📊 채용 시장 분석 리포트</h1>
            <p class="date">{keyword} | {datetime.now().strftime('%Y년 %m월 %d일')}</p>
        </header>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="number">{total_postings:,}</div>
                <div class="label">총 채용공고</div>
            </div>
            <div class="stat-card">
                <div class="number">{len(top_companies)}</div>
                <div class="label">채용 기업</div>
            </div>
            <div class="stat-card">
                <div class="number">{len(top_skills)}</div>
                <div class="label">분석된 스킬</div>
            </div>
        </div>
        
        <section class="section">
            <h2>🏢 상위 채용 기업</h2>
            <table>
                <thead>
                    <tr>
                        <th>순위</th>
                        <th>기업명</th>
                        <th>채용공고 수</th>
                    </tr>
                </thead>
                <tbody>
"""
        
        # 상위 기업 테이블
        if isinstance(top_companies, list):
            for i, company in enumerate(top_companies[:15], 1):
                if isinstance(company, dict):
                    name = company.get('company_name', company.get('name', 'N/A'))
                    count = company.get('count', company.get('posting_count', 0))
                else:
                    name = str(company)
                    count = '-'
                html_content += f"""                    <tr>
                        <td>{i}</td>
                        <td>{name}</td>
                        <td>{count}</td>
                    </tr>
"""
        
        html_content += """                </tbody>
            </table>
        </section>
        
        <section class="section">
            <h2>💻 주요 기술 스택</h2>
            <table>
                <thead>
                    <tr>
                        <th>순위</th>
                        <th>기술</th>
                        <th>언급 횟수</th>
                        <th>비율</th>
                    </tr>
                </thead>
                <tbody>
"""
        
        # 스킬 테이블
        max_count = 1
        if isinstance(top_skills, list) and top_skills:
            first_skill = top_skills[0]
            if isinstance(first_skill, dict):
                max_count = first_skill.get('count', 1)
            
            for i, skill in enumerate(top_skills[:20], 1):
                if isinstance(skill, dict):
                    name = skill.get('skill', skill.get('name', 'N/A'))
                    count = skill.get('count', 0)
                    ratio = skill.get('ratio', 0)
                    ratio_str = f"{ratio:.1f}%" if ratio else '-'
                    bar_width = (count / max_count * 100) if max_count > 0 else 0
                else:
                    name = str(skill)
                    count = '-'
                    ratio_str = '-'
                    bar_width = 0
                
                html_content += f"""                    <tr>
                        <td>{i}</td>
                        <td>{name}</td>
                        <td>
                            {count}
                            <div class="skill-bar"><div class="skill-bar-fill" style="width: {bar_width}%"></div></div>
                        </td>
                        <td>{ratio_str}</td>
                    </tr>
"""
        
        html_content += """                </tbody>
            </table>
        </section>
"""
        
        # 시장 분석 요약
        if market_summary:
            html_content += f"""
        <section class="section">
            <h2>📈 시장 분석 요약</h2>
            <div class="roadmap">{self._escape_html(market_summary)}</div>
        </section>
"""
        
        # 3개월 로드맵
        if roadmap_3months:
            html_content += f"""
        <section class="section">
            <h2>🗺️ 3개월 커리어 로드맵</h2>
            <div class="roadmap">{self._escape_html(roadmap_3months)}</div>
        </section>
"""
        
        # 6개월 로드맵
        if roadmap_6months:
            html_content += f"""
        <section class="section">
            <h2>🗺️ 6개월 커리어 로드맵</h2>
            <div class="roadmap">{self._escape_html(roadmap_6months)}</div>
        </section>
"""
        
        html_content += """
        <footer class="footer">
            <p>이 리포트는 Job Market Analyzer에 의해 자동 생성되었습니다.</p>
            <p>데이터 출처: LinkedIn, 원티드, 잡코리아, 사람인, 로켓펀치</p>
        </footer>
    </div>
</body>
</html>
"""
        
        # 파일 저장
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        self.logger.info(f"HTML 리포트 생성: {filepath}")
        return str(filepath)
    
    def _escape_html(self, text: str) -> str:
        """HTML 이스케이프"""
        if not text:
            return ''
        return (
            text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&#39;')
        )
    
    def generate_json_report(self, keyword: str, analysis: Dict[str, Any]) -> str:
        """JSON 형식 리포트 생성"""
        
        timestamp = self._get_timestamp()
        safe_keyword = self._safe_filename(keyword)
        filename = f"{safe_keyword}_report_{timestamp}.json"
        filepath = self.output_dir / filename
        
        report_data = {
            'meta': {
                'keyword': keyword,
                'generated_at': datetime.now().isoformat(),
                'report_type': 'job_market_analysis'
            },
            'summary': {
                'total_postings': analysis.get('total_postings', 0),
                'unique_companies': analysis.get('unique_companies', 0)
            },
            'top_companies': analysis.get('top_companies', []),
            'top_skills': analysis.get('top_skills', []),
            'market_summary': analysis.get('market_summary', ''),
            'trend_analysis': analysis.get('trend_analysis', ''),
            'roadmap': {
                '3_months': analysis.get('roadmap_3months', ''),
                '6_months': analysis.get('roadmap_6months', '')
            }
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"JSON 리포트 생성: {filepath}")
        return str(filepath)
    
    def generate_all_reports(self, keyword: str, analysis: Dict[str, Any]) -> Dict[str, str]:
        """모든 형식의 리포트 생성"""
        
        results = {
            'markdown': self.generate_markdown_report(keyword, analysis),
            'html': self.generate_html_report(keyword, analysis),
            'json': self.generate_json_report(keyword, analysis)
        }
        
        return results
    
    def generate_summary_report(self, analyses: Dict[str, Dict[str, Any]]) -> str:
        """여러 키워드의 종합 요약 리포트 생성"""
        
        timestamp = self._get_timestamp()
        filename = f"summary_report_{timestamp}.md"
        filepath = self.output_dir / filename
        
        md_content = f"""# 채용 시장 종합 분석 리포트

생성일: {datetime.now().strftime('%Y년 %m월 %d일 %H:%M')}

---

## 📊 분석 개요

| 키워드 | 채용공고 수 | 상위 기업 |
|--------|:-----------:|-----------|
"""
        
        total_all = 0
        for keyword, analysis in analyses.items():
            total = analysis.get('total_postings', 0)
            total_all += total
            
            top_companies = analysis.get('top_companies', [])
            if top_companies:
                if isinstance(top_companies[0], dict):
                    top_3 = [c.get('company_name', c.get('name', '')) for c in top_companies[:3]]
                else:
                    top_3 = [str(c) for c in top_companies[:3]]
                companies_str = ', '.join(top_3)
            else:
                companies_str = '-'
            
            md_content += f"| {keyword} | {total:,} | {companies_str} |\n"
        
        md_content += f"""
**총 채용공고**: {total_all:,}개

---

## 💻 전체 기술 트렌드

"""
        
        # 모든 키워드의 스킬 통합
        all_skills = {}
        for keyword, analysis in analyses.items():
            skills = analysis.get('top_skills', [])
            for skill in skills:
                if isinstance(skill, dict):
                    name = skill.get('skill', skill.get('name', ''))
                    count = skill.get('count', 0)
                else:
                    name = str(skill)
                    count = 1
                
                if name:
                    all_skills[name] = all_skills.get(name, 0) + count
        
        # 상위 20개 스킬
        sorted_skills = sorted(all_skills.items(), key=lambda x: x[1], reverse=True)[:20]
        
        md_content += "| 순위 | 기술 | 총 언급 횟수 |\n"
        md_content += "|:----:|------|:------------:|\n"
        
        for i, (skill, count) in enumerate(sorted_skills, 1):
            md_content += f"| {i} | {skill} | {count:,} |\n"
        
        md_content += """
---

*Generated by Job Market Analyzer*
"""
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        self.logger.info(f"종합 리포트 생성: {filepath}")
        return str(filepath)


def main():
    """리포트 생성기 테스트"""
    import argparse
    
    parser = argparse.ArgumentParser(description='리포트 생성기')
    parser.add_argument('--keyword', '-k', required=True, help='키워드')
    parser.add_argument('--format', '-f', choices=['md', 'html', 'json', 'all'], default='all')
    parser.add_argument('--output', '-o', default='reports', help='출력 디렉토리')
    
    args = parser.parse_args()
    
    # DB에서 분석 결과 로드
    from config.settings import Settings
    settings = Settings()
    db = Database(settings.database.connection_string)
    
    analysis = db.get_latest_analysis(args.keyword)
    
    if not analysis:
        print(f"'{args.keyword}'에 대한 분석 결과가 없습니다.")
        return
    
    # 리포트 생성
    generator = ReportGenerator(db, args.output)
    
    if args.format == 'md':
        path = generator.generate_markdown_report(args.keyword, analysis)
    elif args.format == 'html':
        path = generator.generate_html_report(args.keyword, analysis)
    elif args.format == 'json':
        path = generator.generate_json_report(args.keyword, analysis)
    else:
        paths = generator.generate_all_reports(args.keyword, analysis)
        print("생성된 리포트:")
        for fmt, path in paths.items():
            print(f"  {fmt}: {path}")
        return
    
    print(f"리포트 생성: {path}")


if __name__ == '__main__':
    main()
