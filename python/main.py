#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Job Market Analyzer - 메인 실행 스크립트

사용법:
    python main.py crawl              # 크롤링만 실행
    python main.py analyze            # 분석만 실행
    python main.py report             # 리포트 생성
    python main.py all                # 전체 실행 (크롤링 → 분석 → 리포트)
    python main.py schedule           # 스케줄러 시작
    python main.py company "회사이름"  # 특정 회사 분석
"""

import argparse
import sys
import os
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import Settings
from utils.database import Database
from utils.helpers import setup_logger
from crawlers import get_crawler, get_all_crawlers
from analyzers.market_analyzer import MarketAnalyzer
from analyzers.company_analyzer import CompanyAnalyzer
from analyzers.llm_analyzer import LLMAnalyzer, FallbackAnalyzer


def create_directories():
    """필요한 디렉토리 생성"""
    dirs = ['data', 'reports', 'logs']
    for d in dirs:
        Path(d).mkdir(exist_ok=True)


def run_crawling(settings: Settings, db: Database, logger):
    """크롤링 실행"""
    logger.info("=" * 60)
    logger.info("크롤링 시작")
    logger.info("=" * 60)

    sites = settings.search_keywords.sites

    # 키워드 정보 로깅
    logger.info(f"직무 키워드: {settings.search_keywords.job_keywords}")
    if settings.search_keywords.combine_all:
        logger.info(f"연차 키워드: {[k for k in settings.search_keywords.experience_keywords if k]}")
        logger.info(f"지역 키워드: {[k for k in settings.search_keywords.location_keywords if k]}")

    total_jobs = 0

    for site_name, enabled in sites.items():
        if not enabled:
            logger.info(f"[{site_name}] 비활성화됨 - 건너뜀")
            continue

        try:
            crawler = get_crawler(site_name)
            if not crawler:
                logger.warning(f"[{site_name}] 크롤러를 찾을 수 없음")
                continue

            # 사이트별 최적화된 키워드 가져오기
            keywords = settings.search_keywords.get_keywords_for_site(site_name)
            logger.info(f"\n[{site_name}] 크롤링 시작 ({len(keywords)}개 키워드)")

            for keyword in keywords:
                logger.info(f"  키워드: {keyword}")
                try:
                    jobs = crawler.crawl_keyword(keyword)

                    for job in jobs:
                        db.add_job_posting(job)

                    logger.info(f"    → {len(jobs)}개 수집")
                    total_jobs += len(jobs)

                except Exception as e:
                    logger.error(f"    → 크롤링 실패: {e}")

        except Exception as e:
            logger.error(f"[{site_name}] 크롤러 초기화 실패: {e}")

    logger.info(f"\n크롤링 완료: 총 {total_jobs}개 채용공고 수집")
    return total_jobs


def run_analysis(settings: Settings, db: Database, logger):
    """시장 분석 실행"""
    logger.info("=" * 60)
    logger.info("시장 분석 시작")
    logger.info("=" * 60)
    
    keywords = settings.search_keywords.keywords
    market_analyzer = MarketAnalyzer(db)
    
    # LLM 분석기 초기화
    llm_analyzer = LLMAnalyzer()
    use_llm = llm_analyzer.is_available()
    
    if use_llm:
        logger.info("LLM 분석 활성화됨")
    else:
        logger.info("LLM 분석 비활성화 - Fallback 모드 사용")
    
    results = {}
    
    for keyword in keywords:
        logger.info(f"\n키워드 분석: {keyword}")
        
        try:
            # 기본 시장 분석
            analysis = market_analyzer.analyze_keyword(keyword, days=30)
            
            if analysis['total_postings'] == 0:
                logger.warning(f"  → 데이터 없음")
                continue
            
            logger.info(f"  → 총 {analysis['total_postings']}개 공고 분석")
            logger.info(f"  → 고유 기업 {analysis['unique_companies']}개")
            
            # 트렌드 분석
            trends = market_analyzer.get_trend_comparison(keyword)
            analysis['trends'] = trends
            
            # LLM 분석 (사용 가능한 경우)
            if use_llm:
                try:
                    logger.info("  → LLM 트렌드 분석 중...")
                    llm_analysis = llm_analyzer.analyze_market_trends(analysis)
                    analysis['llm_analysis'] = llm_analysis.get('analysis', '')
                    
                    logger.info("  → 커리어 로드맵 생성 중...")
                    roadmap = llm_analyzer.generate_career_roadmap(
                        keyword, 
                        analysis['skill_analysis'],
                        duration_months=6
                    )
                    analysis['roadmap_3_months'] = roadmap.get('roadmap_3_months', '')
                    analysis['roadmap_6_months'] = roadmap.get('roadmap_6_months', '')
                    analysis['project_ideas'] = roadmap.get('project_ideas', '')
                    
                except Exception as e:
                    logger.error(f"  → LLM 분석 실패: {e}")
            else:
                # Fallback 로드맵
                fallback = FallbackAnalyzer()
                top_skills = [s['skill'] for s in analysis['skill_analysis'].get('hard_skills', [])[:10]]
                roadmap = fallback.generate_basic_roadmap(keyword, top_skills)
                analysis['roadmap_3_months'] = roadmap.get('roadmap_3_months', '')
                analysis['roadmap_6_months'] = roadmap.get('roadmap_6_months', '')
            
            # 요약 생성
            summary = market_analyzer.generate_summary(analysis)
            analysis['summary'] = summary
            
            # DB 저장
            db.save_market_analysis({
                'keyword': keyword,
                'total_postings': analysis['total_postings'],
                'top_companies': analysis.get('top_companies', []),
                'top_skills': analysis['skill_analysis'].get('hard_skills', [])[:20],
                'market_summary': summary,
                'trend_analysis': str(trends),
                'roadmap_3months': analysis.get('roadmap_3_months', ''),
                'roadmap_6months': analysis.get('roadmap_6_months', '')
            })
            
            results[keyword] = analysis
            logger.info(f"  → 분석 완료 및 저장됨")
            
        except Exception as e:
            logger.error(f"  → 분석 실패: {e}")
            import traceback
            traceback.print_exc()
    
    logger.info(f"\n시장 분석 완료: {len(results)}개 키워드 분석됨")
    return results


def run_company_analysis(company_name: str, db: Database, logger):
    """특정 회사 분석"""
    logger.info("=" * 60)
    logger.info(f"회사 분석: {company_name}")
    logger.info("=" * 60)
    
    analyzer = CompanyAnalyzer(db)
    result = analyzer.analyze_company(company_name)
    
    if result:
        logger.info(f"\n기본 정보:")
        for key, value in result.get('basic_info', {}).items():
            if value:
                logger.info(f"  {key}: {value}")
        
        logger.info(f"\n평판:")
        rep = result.get('reputation', {})
        if rep.get('jobplanet_rating'):
            logger.info(f"  잡플래닛 평점: {rep['jobplanet_rating']}")
        
        logger.info(f"\n종합 평가: {result.get('summary', {}).get('overall', 'N/A')}")
        
        # LLM 분석 (사용 가능한 경우)
        llm = LLMAnalyzer()
        if llm.is_available():
            logger.info("\nLLM 상세 분석 중...")
            # 최근 채용공고 조회
            jobs = db.get_job_postings(company_name=company_name, days=30)
            if jobs:
                job_data = [{
                    'title': j.title,
                    'job_category': j.job_category,
                    'required_skills': j.required_skills
                } for j in jobs[:5]]
                
                fit_analysis = llm.analyze_company_fit(result, job_data)
                if fit_analysis:
                    logger.info("\n=== 회사 적합도 분석 ===")
                    logger.info(fit_analysis.get('analysis', ''))
    
    return result


def generate_reports(settings: Settings, db: Database, logger):
    """리포트 생성"""
    logger.info("=" * 60)
    logger.info("리포트 생성 시작")
    logger.info("=" * 60)

    try:
        from report_generator import ReportGenerator

        generator = ReportGenerator(db)
        keywords = settings.search_keywords.keywords

        for keyword in keywords:
            logger.info(f"\n키워드 리포트 생성: {keyword}")

            # 최신 분석 결과 조회
            analysis_obj = db.get_latest_analysis(keyword)
            if not analysis_obj:
                logger.warning(f"  → 분석 결과 없음")
                continue

            # MarketAnalysis 객체를 딕셔너리로 변환
            analysis = {
                'keyword': analysis_obj.keyword,
                'total_postings': analysis_obj.total_postings,
                'top_companies': analysis_obj.top_companies or [],
                'top_skills': analysis_obj.top_skills or [],
                'market_summary': analysis_obj.market_summary or '',
                'trend_analysis': analysis_obj.trend_analysis or '',
                'roadmap_3months': analysis_obj.roadmap_3months or '',
                'roadmap_6months': analysis_obj.roadmap_6months or '',
                'analysis_date': analysis_obj.analysis_date.isoformat() if analysis_obj.analysis_date else '',
            }

            # 마크다운 리포트
            md_path = generator.generate_markdown_report(keyword, analysis)
            logger.info(f"  → 마크다운: {md_path}")

            # HTML 리포트
            html_path = generator.generate_html_report(keyword, analysis)
            logger.info(f"  → HTML: {html_path}")
        
        logger.info("\n리포트 생성 완료")
        
    except ImportError:
        logger.warning("report_generator 모듈을 찾을 수 없습니다.")
    except Exception as e:
        logger.error(f"리포트 생성 실패: {e}")


def run_scheduler(settings: Settings, db: Database, logger):
    """스케줄러 시작"""
    logger.info("=" * 60)
    logger.info("스케줄러 시작")
    logger.info("=" * 60)
    
    try:
        from scheduler import JobScheduler
        
        scheduler = JobScheduler(settings, db)
        scheduler.start()
        
    except ImportError:
        logger.error("scheduler 모듈을 찾을 수 없습니다.")
    except Exception as e:
        logger.error(f"스케줄러 시작 실패: {e}")


def run_all(settings: Settings, db: Database, logger, force_analyze: bool = False):
    """전체 파이프라인 실행"""
    logger.info("=" * 60)
    logger.info("전체 파이프라인 시작")
    logger.info(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    start_time = datetime.now()

    # 1. 크롤링
    total_jobs = run_crawling(settings, db, logger)

    # 2. 분석
    if total_jobs > 0 or force_analyze:
        if force_analyze and total_jobs == 0:
            logger.info("강제 분석 모드: DB에 있는 기존 데이터로 분석을 실행합니다.")
        results = run_analysis(settings, db, logger)

        # 3. 리포트 생성
        if results:
            generate_reports(settings, db, logger)
    else:
        logger.warning("수집된 데이터가 없어 분석을 건너뜁니다. (--force-analyze 옵션으로 강제 실행 가능)")

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    logger.info("=" * 60)
    logger.info("전체 파이프라인 완료")
    logger.info(f"소요 시간: {duration:.1f}초")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description='채용 시장 분석 및 커리어 로드맵 생성 시스템',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
    python main.py crawl              # 크롤링만 실행
    python main.py analyze            # 분석만 실행  
    python main.py report             # 리포트 생성
    python main.py all                # 전체 실행
    python main.py schedule           # 스케줄러 시작
    python main.py company "카카오"    # 특정 회사 분석
    python main.py --config my.json all  # 설정 파일 지정
        """
    )
    
    parser.add_argument(
        'command',
        choices=['crawl', 'analyze', 'report', 'all', 'schedule', 'company'],
        help='실행할 명령'
    )
    
    parser.add_argument(
        'target',
        nargs='?',
        default=None,
        help='company 명령 시 회사 이름'
    )
    
    parser.add_argument(
        '--config', '-c',
        default=None,
        help='설정 파일 경로 (JSON)'
    )
    
    parser.add_argument(
        '--keywords', '-k',
        nargs='+',
        default=None,
        help='직무/기술 키워드 (공백으로 구분)'
    )

    parser.add_argument(
        '--experience', '-e',
        nargs='+',
        default=None,
        help='연차 키워드 (예: 신입 1년차 3년차 경력)'
    )

    parser.add_argument(
        '--location', '-l',
        nargs='+',
        default=None,
        help='지역 키워드 (예: 서울 판교 부산 원격)'
    )

    parser.add_argument(
        '--combine',
        action='store_true',
        help='키워드 조합 모드 활성화 (직무+연차+지역)'
    )

    parser.add_argument(
        '--sites', '-s',
        nargs='+',
        default=None,
        help='크롤링 사이트 (linkedin, wanted, jobkorea, saramin, rocketpunch)'
    )

    parser.add_argument(
        '--debug',
        action='store_true',
        help='디버그 모드'
    )

    parser.add_argument(
        '--force-analyze',
        action='store_true',
        help='크롤링 결과와 관계없이 분석 강제 실행 (DB에 있는 기존 데이터 사용)'
    )
    
    args = parser.parse_args()
    
    # 디렉토리 생성
    create_directories()
    
    # 로거 설정
    log_level = 'DEBUG' if args.debug else 'INFO'
    logger = setup_logger('job_market_analyzer', log_level=log_level)
    
    # 설정 로드
    settings = Settings()
    
    if args.config:
        settings.load_from_file(args.config)
        logger.info(f"설정 파일 로드: {args.config}")
    
    # 명령줄 옵션 적용
    if args.keywords:
        settings.search_keywords.job_keywords = args.keywords
        logger.info(f"직무 키워드 설정: {args.keywords}")

    if args.experience:
        settings.search_keywords.experience_keywords = [""] + args.experience
        logger.info(f"연차 키워드 설정: {args.experience}")

    if args.location:
        settings.search_keywords.location_keywords = [""] + args.location
        logger.info(f"지역 키워드 설정: {args.location}")

    if args.combine:
        settings.search_keywords.combine_all = True
        combined = settings.search_keywords.get_combined_keywords()
        logger.info(f"키워드 조합 모드 활성화: {len(combined)}개 조합 생성")

    if args.sites:
        # 모든 사이트 비활성화 후 지정된 것만 활성화
        for site in settings.search_keywords.sites:
            settings.search_keywords.sites[site] = site in args.sites
        logger.info(f"사이트 설정: {args.sites}")
    
    # 데이터베이스 초기화
    db = Database(settings.database.connection_string)
    db.create_tables()
    
    # 명령 실행
    try:
        if args.command == 'crawl':
            run_crawling(settings, db, logger)
            
        elif args.command == 'analyze':
            run_analysis(settings, db, logger)
            
        elif args.command == 'report':
            generate_reports(settings, db, logger)
            
        elif args.command == 'all':
            run_all(settings, db, logger, force_analyze=args.force_analyze)
            
        elif args.command == 'schedule':
            run_scheduler(settings, db, logger)
            
        elif args.command == 'company':
            if not args.target:
                logger.error("회사 이름을 지정해주세요. 예: python main.py company '카카오'")
                sys.exit(1)
            run_company_analysis(args.target, db, logger)
            
    except KeyboardInterrupt:
        logger.info("\n사용자에 의해 중단됨")
        sys.exit(0)
    except Exception as e:
        logger.error(f"실행 중 오류 발생: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
