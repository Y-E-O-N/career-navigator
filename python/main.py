#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Job Market Analyzer - 메인 실행 스크립트

사용법:
    # 크롤링 (분리된 플로우)
    python main.py crawl-jobs         # 1차 크롤링: 채용공고 수집 (신규/기존/삭제 추적)
    python main.py crawl-companies    # 2차 크롤링: 회사정보 수집 (잡플래닛)
    python main.py crawl-news         # 3차 크롤링: 뉴스 기사 수집 (연합뉴스)
    python main.py crawl              # 전체 크롤링 (1차 + 2차)

    # 분석 및 리포트
    python main.py analyze            # 시장 분석 실행
    python main.py report             # 리포트 생성
    python main.py all                # 전체 실행 (크롤링 → 분석 → 리포트)

    # 기타
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


def run_job_crawling(settings: Settings, db: Database, logger) -> dict:
    """
    1차 크롤링: 채용공고 수집

    전일 대비 새로 추가된 공고, 기존 공고, 삭제된 공고를 추적합니다.

    Returns:
        dict: 크롤링 결과 통계
        {
            'total_found': int,      # 검색에서 발견된 총 공고 수
            'new_count': int,        # 새로 추가된 공고 수
            'existing_count': int,   # 기존 공고 (업데이트)
            'deleted_count': int,    # 삭제된 공고 수
            'companies': set,        # 발견된 회사 목록
        }
    """
    import time
    from datetime import datetime

    logger.info("=" * 60)
    logger.info("1차 크롤링: 채용공고 수집 시작")
    logger.info("=" * 60)

    sites = settings.search_keywords.sites

    # 키워드 정보 로깅
    logger.info(f"직무 키워드: {settings.search_keywords.job_keywords}")
    if settings.search_keywords.combine_all:
        logger.info(f"연차 키워드: {[k for k in settings.search_keywords.experience_keywords if k]}")
        logger.info(f"지역 키워드: {[k for k in settings.search_keywords.location_keywords if k]}")

    # 전체 통계
    total_stats = {
        'total_found': 0,
        'new_count': 0,
        'existing_count': 0,
        'deleted_count': 0,
        'companies': set(),
    }

    for site_name, enabled in sites.items():
        if not enabled:
            logger.info(f"[{site_name}] 비활성화됨 - 건너뜀")
            continue

        try:
            crawler = get_crawler(site_name)
            if not crawler:
                logger.warning(f"[{site_name}] 크롤러를 찾을 수 없음")
                continue

            # 크롤링 전: 해당 사이트의 기존 활성 job_id 목록 조회
            previous_job_ids = db.get_all_active_job_ids(site_name)
            logger.info(f"[{site_name}] 기존 활성 공고: {len(previous_job_ids)}개")

            # 사이트별 최적화된 키워드 가져오기
            keywords = settings.search_keywords.get_keywords_for_site(site_name)
            logger.info(f"\n[{site_name}] 크롤링 시작 ({len(keywords)}개 키워드)")

            site_found_job_ids = set()  # 이번 크롤링에서 발견된 모든 job_id
            site_stats = {'new': 0, 'existing': 0, 'total': 0}

            for keyword in keywords:
                start_time = time.time()
                logger.info(f"  키워드: {keyword}")

                try:
                    jobs = crawler.crawl_keyword(keyword)
                    site_stats['total'] += len(jobs)

                    # 크롤러에서 발견한 모든 job_id 수집 (삭제 감지용)
                    if hasattr(crawler, 'last_found_job_ids') and crawler.last_found_job_ids:
                        site_found_job_ids.update(crawler.last_found_job_ids)

                    for job in jobs:
                        job_id = str(job.get('job_id', ''))
                        company_name = job.get('company_name', '')

                        if job_id:
                            site_found_job_ids.add(job_id)

                        if company_name:
                            total_stats['companies'].add(company_name)

                        # DB에 저장 (중복 시 업데이트)
                        is_new = job_id not in previous_job_ids
                        db.add_job_posting(job)

                        if is_new:
                            site_stats['new'] += 1
                        else:
                            site_stats['existing'] += 1

                    duration = time.time() - start_time
                    logger.info(f"    → {len(jobs)}개 수집 (신규: {site_stats['new']}, 소요: {duration:.1f}초)")

                    # 크롤링 결과 저장
                    db.save_crawl_result({
                        'crawl_type': 'jobs',
                        'source_site': site_name,
                        'keyword': keyword,
                        'total_found': len(jobs),
                        'new_count': site_stats['new'],
                        'existing_count': site_stats['existing'],
                        'duration_seconds': duration,
                        'status': 'completed'
                    })

                except Exception as e:
                    logger.error(f"    → 크롤링 실패: {e}")
                    db.save_crawl_result({
                        'crawl_type': 'jobs',
                        'source_site': site_name,
                        'keyword': keyword,
                        'status': 'failed',
                        'error_message': str(e)
                    })

            # 삭제 감지: 이전에는 있었는데 이번 크롤링에서 발견되지 않은 공고
            deleted_job_ids = previous_job_ids - site_found_job_ids

            # 마감된 공고 처리
            if deleted_job_ids:
                closed = db.mark_jobs_as_closed(site_name, list(deleted_job_ids))
                total_stats['deleted_count'] += closed
                logger.info(f"[{site_name}] {closed}개 공고 마감 처리")

            # 사이트별 통계 집계
            total_stats['total_found'] += site_stats['total']
            total_stats['new_count'] += site_stats['new']
            total_stats['existing_count'] += site_stats['existing']

            logger.info(f"\n[{site_name}] 크롤링 완료:")
            logger.info(f"  - 발견: {site_stats['total']}개")
            logger.info(f"  - 신규: {site_stats['new']}개")
            logger.info(f"  - 기존: {site_stats['existing']}개")
            logger.info(f"  - 삭제(마감): {len(deleted_job_ids)}개")

        except Exception as e:
            logger.error(f"[{site_name}] 크롤러 초기화 실패: {e}")

    logger.info("\n" + "=" * 60)
    logger.info("1차 크롤링 완료 (채용공고)")
    logger.info("=" * 60)
    logger.info(f"총 발견: {total_stats['total_found']}개")
    logger.info(f"신규 추가: {total_stats['new_count']}개")
    logger.info(f"기존 업데이트: {total_stats['existing_count']}개")
    logger.info(f"삭제 처리: {total_stats['deleted_count']}개")
    logger.info(f"발견된 회사: {len(total_stats['companies'])}개")

    return total_stats


def run_company_crawling(settings: Settings, db: Database, logger, max_companies: int = 1, resume: bool = True) -> dict:
    """
    2차 크롤링: 회사정보 수집 (잡플래닛)

    1차 크롤링에서 발견된 회사들 중 정보가 없는 회사를 잡플래닛에서 검색하여
    가능한 모든 정보를 수집합니다.

    Args:
        max_companies: 한 번에 처리할 최대 회사 수 (차단 방지, 기본 10개)
        resume: True이면 이미 jobplanet_rating이 있는 회사는 건너뛰고, 불완전한 회사는 재수집

    Returns:
        dict: 크롤링 결과 통계
    """
    import time
    import json

    logger.info("=" * 60)
    logger.info("2차 크롤링: 회사정보 수집 시작 (잡플래닛)")
    logger.info("=" * 60)

    analyzer = CompanyAnalyzer(db)

    # 정보가 없거나 불완전한 회사 목록 조회 (resume 모드에 따라)
    # DB 기준: jobplanet_url이 없거나 jobplanet_rating이 없는 회사 포함
    all_missing = db.get_companies_without_info(include_incomplete=resume)

    # 진행 상황 파일 로드 (세션 내 중복 방지)
    # 주의: DB에서 불완전하다고 판단된 회사는 진행 상황 파일에 있어도 재시도
    progress_file = Path("data/crawl_progress.json")
    processed_in_session = set()

    if resume and progress_file.exists():
        try:
            with open(progress_file, 'r', encoding='utf-8') as f:
                progress_data = json.load(f)
                all_processed = set(progress_data.get('processed', []))
                # DB에서 불완전한 회사는 진행 상황 파일에서 제외 (재시도 대상)
                processed_in_session = all_processed - set(all_missing)
                skipped_count = len(all_processed) - len(all_processed & set(all_missing))
                retry_count = len(all_processed & set(all_missing))
                if retry_count > 0:
                    logger.info(f"이전 세션: {len(all_processed)}개 중 {retry_count}개 재시도 (불완전), {skipped_count}개 건너뜀")
                elif skipped_count > 0:
                    logger.info(f"이전 세션에서 처리된 회사: {skipped_count}개 (건너뜀)")
        except Exception as e:
            logger.warning(f"진행 상황 파일 로드 실패: {e}")

    # 이미 완전히 처리된 회사만 제외 (불완전한 회사는 재시도)
    all_missing = [c for c in all_missing if c not in processed_in_session]

    # 한 번에 처리할 회사 수 제한 (차단 방지)
    missing_companies = all_missing[:max_companies]

    total_target = len(all_missing)
    batch_size = len(missing_companies)
    logger.info(f"전체 대상: {total_target}개 | 이번 배치: {batch_size}개")

    if not missing_companies:
        logger.info("모든 회사 정보가 이미 수집되어 있습니다.")
        return {'total': 0, 'success': 0, 'failed': 0, 'remaining': 0}

    stats = {'total': batch_size, 'success': 0, 'failed': 0, 'remaining': total_target - batch_size}
    failed_companies = []

    def save_progress():
        """진행 상황 저장"""
        try:
            progress_file.parent.mkdir(parents=True, exist_ok=True)
            with open(progress_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'processed': list(processed_in_session),
                    'failed': failed_companies,
                    'last_updated': datetime.now().isoformat()
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"진행 상황 저장 실패: {e}")

    try:
        for i, company_name in enumerate(missing_companies, 1):
            start_time = time.time()

            try:
                logger.info(f"\n[{i}/{batch_size}] (전체 {total_target}개 중 {i}번째) {company_name} 분석 중...")
                result = analyzer.analyze_company(company_name)

                duration = time.time() - start_time

                if result and result.get('reputation', {}).get('jobplanet_rating'):
                    rating = result['reputation']['jobplanet_rating']
                    logger.info(f"  → 잡플래닛 평점: {rating}/5.0 (소요: {duration:.1f}초)")
                    stats['success'] += 1
                    processed_in_session.add(company_name)  # 성공한 회사 기록
                elif result:
                    logger.info(f"  → 잡플래닛 정보 없음 (기본 정보 저장, 소요: {duration:.1f}초)")
                    stats['success'] += 1
                    processed_in_session.add(company_name)  # 성공한 회사 기록
                else:
                    logger.warning(f"  → 분석 실패")
                    stats['failed'] += 1
                    failed_companies.append(company_name)

                # 크롤링 결과 저장
                db.save_crawl_result({
                    'crawl_type': 'companies',
                    'source_site': 'jobplanet',
                    'keyword': company_name,
                    'total_found': 1 if result else 0,
                    'new_count': 1 if result else 0,
                    'duration_seconds': duration,
                    'status': 'completed' if result else 'failed'
                })

                # 진행 상황 저장 (매 회사 처리 후)
                save_progress()

            except Exception as e:
                logger.warning(f"  → 분석 실패: {e}")
                stats['failed'] += 1
                failed_companies.append(company_name)
                save_progress()  # 실패해도 진행 상황 저장

    finally:
        # 중단되더라도 브라우저 종료 보장
        analyzer.close()
        # 최종 진행 상황 저장
        save_progress()

    logger.info("\n" + "=" * 60)
    logger.info("2차 크롤링 완료 (회사정보)")
    logger.info("=" * 60)
    logger.info(f"이번 처리: {stats['total']}개")
    logger.info(f"성공: {stats['success']}개")
    logger.info(f"실패: {stats['failed']}개")
    logger.info(f"남은 회사: {stats['remaining']}개")

    if failed_companies:
        logger.info(f"실패한 회사: {failed_companies[:10]}{'...' if len(failed_companies) > 10 else ''}")

    return stats


def run_news_crawling(settings: Settings, db: Database, logger, max_companies: int = 10, only_no_news: bool = False, since_date: str = None) -> dict:
    """
    3차 크롤링: 뉴스 기사 수집 (연합뉴스)

    1차 크롤링(채용공고)으로 수집된 회사들의 뉴스 기사를 연합뉴스에서 검색하여 수집합니다.

    Args:
        max_companies: 한 번에 처리할 최대 회사 수
        only_no_news: True이면 뉴스가 0건인 회사만 크롤링 (재시도용)
        since_date: 특정 날짜 이후의 기사만 수집 (YYYY-MM-DD 형식)

    Returns:
        dict: 크롤링 결과 통계
    """
    import time
    from crawlers.news_crawler import NewsCrawler

    logger.info("=" * 60)
    logger.info("3차 크롤링: 뉴스 기사 수집 시작 (연합뉴스)")
    if only_no_news:
        logger.info("모드: 뉴스 0건인 회사만 재시도")
    if since_date:
        logger.info(f"날짜 필터: {since_date} 이후 기사만 수집")
    logger.info("=" * 60)

    crawler = NewsCrawler(db, since_date=since_date)

    # 뉴스 크롤링이 필요한 회사 목록 조회
    companies = db.get_companies_for_news_crawling(limit=max_companies, only_no_news=only_no_news)

    if not companies:
        logger.info("뉴스 크롤링이 필요한 회사가 없습니다.")
        return {'total': 0, 'success': 0, 'failed': 0}

    total_target = len(companies)
    logger.info(f"전체 대상: {total_target}개")

    stats = {
        'total': total_target,
        'success': 0,
        'failed': 0,
        'total_articles': 0
    }

    try:
        for i, company_name in enumerate(companies, 1):
            start_time = time.time()

            try:
                logger.info(f"\n[{i}/{total_target}] {company_name} 뉴스 수집 중...")

                # 회사 ID 조회
                company_id = db.get_company_id_by_name(company_name)

                # 뉴스 크롤링
                result = crawler.crawl_company_news_sync(company_name, company_id)

                duration = time.time() - start_time

                if result.get('total_found', 0) > 0:
                    new_count = result.get('new_count', 0)
                    dup_count = result.get('duplicate_count', 0)
                    logger.info(f"  → 완료: {result['total_found']}개 발견, 신규 {new_count}개 저장, 중복 {dup_count}개 (소요: {duration:.1f}초)")
                    stats['success'] += 1
                    stats['total_articles'] += new_count
                else:
                    logger.info(f"  → 검색된 뉴스 없음 (소요: {duration:.1f}초)")
                    stats['success'] += 1  # 뉴스 없어도 성공으로 처리

            except Exception as e:
                logger.error(f"  → 뉴스 수집 실패: {e}")
                stats['failed'] += 1

    finally:
        crawler.close()

    logger.info("\n" + "=" * 60)
    logger.info("3차 크롤링 완료 (뉴스 기사)")
    logger.info("=" * 60)
    logger.info(f"처리 회사: {stats['total']}개")
    logger.info(f"성공: {stats['success']}개")
    logger.info(f"실패: {stats['failed']}개")
    logger.info(f"신규 저장 기사: {stats['total_articles']}개")

    return stats


def run_crawling(settings: Settings, db: Database, logger):
    """전체 크롤링 실행 (1차 + 2차)"""
    logger.info("=" * 60)
    logger.info("전체 크롤링 시작 (1차 채용공고 + 2차 회사정보)")
    logger.info("=" * 60)

    # 1차: 채용공고 크롤링
    job_stats = run_job_crawling(settings, db, logger)

    # 2차: 회사정보 크롤링
    company_stats = run_company_crawling(settings, db, logger)

    logger.info("\n" + "=" * 60)
    logger.info("전체 크롤링 완료")
    logger.info("=" * 60)

    return job_stats.get('total_found', 0)


def run_analysis(settings: Settings, db: Database, logger):
    """시장 분석 실행"""
    logger.info("=" * 60)
    logger.info("시장 분석 시작")
    logger.info("=" * 60)

    keywords = settings.search_keywords.keywords

    # LLM 분석기 초기화
    llm_analyzer = LLMAnalyzer()
    use_llm = llm_analyzer.is_available()

    # MarketAnalyzer에 LLM 분석기 전달
    market_analyzer = MarketAnalyzer(db, llm_analyzer=llm_analyzer if use_llm else None)

    if use_llm:
        logger.info("LLM 분석 활성화됨 (스킬/지역/경력 분석에 LLM 사용)")
    else:
        logger.info("LLM 분석 비활성화 - 규칙 기반 분석 사용")

    results = {}

    for keyword in keywords:
        logger.info(f"\n키워드 분석: {keyword}")

        try:
            # 기본 시장 분석 (LLM 사용 여부 전달)
            analysis = market_analyzer.analyze_keyword(keyword, days=30, use_llm=use_llm)

            # 데이터 없음 체크 (에러 반환 또는 total_postings가 0인 경우)
            if analysis.get('error') or analysis.get('total_postings', 0) == 0:
                logger.warning(f"  → 데이터 없음: {analysis.get('error', '채용공고 0건')}")
                continue
            
            logger.info(f"  → 총 {analysis['total_postings']}개 공고 분석")
            logger.info(f"  → 고유 기업 {analysis['unique_companies']}개")
            
            # 트렌드 분석
            trends = market_analyzer.get_trend_comparison(keyword)
            analysis['trends'] = trends
            
            # LLM 분석 (사용 가능한 경우)
            llm_roadmap_success = False
            if use_llm:
                try:
                    logger.info("  → LLM 트렌드 분석 중...")
                    llm_result = llm_analyzer.analyze_market_trends(analysis)
                    analysis['llm_analysis'] = llm_result.get('llm_analysis', '') if llm_result else ''

                    logger.info("  → 커리어 로드맵 생성 중...")
                    roadmap = llm_analyzer.generate_career_roadmap(
                        keyword,
                        analysis['skill_analysis'],
                        duration_months=6
                    )
                    # LLM은 'roadmap' 키에 전체 텍스트 반환
                    roadmap_text = roadmap.get('roadmap', '') if roadmap else ''

                    # 로드맵이 유효한지 확인 (실패 메시지가 아닌 경우만)
                    if roadmap_text and '실패' not in roadmap_text and len(roadmap_text) > 100:
                        analysis['roadmap_3_months'] = roadmap_text
                        analysis['roadmap_6_months'] = roadmap_text
                        analysis['project_ideas'] = roadmap_text
                        llm_roadmap_success = True
                        logger.info(f"  → LLM 로드맵 생성 성공: {len(roadmap_text)} chars")
                    else:
                        logger.warning(f"  → LLM 로드맵 응답이 유효하지 않음, Fallback 사용")

                except Exception as e:
                    logger.error(f"  → LLM 분석 실패: {e}")
                    import traceback
                    traceback.print_exc()

            # LLM 실패 시 또는 LLM 미사용 시 Fallback 로드맵 사용
            if not llm_roadmap_success:
                logger.info("  → Fallback 로드맵 생성 중...")
                fallback = FallbackAnalyzer()
                top_skills = [s['skill'] for s in analysis['skill_analysis'].get('hard_skills', [])[:10]]
                roadmap = fallback.generate_basic_roadmap(keyword, top_skills)
                # Fallback은 리스트 반환하므로 JSON 문자열로 변환
                import json as json_module
                analysis['roadmap_3_months'] = json_module.dumps(roadmap.get('roadmap_3_months', []), ensure_ascii=False)
                analysis['roadmap_6_months'] = json_module.dumps(roadmap.get('roadmap_6_months', []), ensure_ascii=False)
            
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
                'llm_analysis': analysis.get('llm_analysis', ''),
                'project_ideas': analysis.get('project_ideas', ''),
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
    try:
        result = analyzer.analyze_company(company_name)
    finally:
        analyzer.close()
    
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


def run_top_companies_analysis(settings: Settings, db: Database, logger):
    """DB에 정보가 없는 모든 회사 분석 (레거시 - run_company_crawling으로 대체)"""
    # run_company_crawling 함수로 위임
    return run_company_crawling(settings, db, logger)


def run_company_report(
    company_name: str,
    db: Database,
    logger,
    job_posting_id: int = None,
    output_dir: str = './reports/company_analysis',
    profile_path: str = None,
    weights_str: str = None,
    generate_llm: bool = False,
    data_summary_only: bool = False,
    # Phase 4 옵션
    save_to_db: bool = False,
    export_html: bool = False,
    export_pdf: bool = False,
    use_cache: bool = True,
    cache_days: int = 7
):
    """
    기업 분석 보고서 생성

    Args:
        company_name: 분석할 회사명
        db: 데이터베이스 인스턴스
        logger: 로거
        job_posting_id: 특정 채용공고 ID (선택)
        output_dir: 출력 디렉토리
        profile_path: 지원자 프로필 JSON 파일 경로
        weights_str: 가중치 문자열
        generate_llm: LLM 호출 여부
        data_summary_only: 데이터 요약만 출력
        save_to_db: DB 저장 여부
        export_html: HTML 내보내기 여부
        export_pdf: PDF 내보내기 여부
        use_cache: 캐시 사용 여부
        cache_days: 캐시 유효 기간
    """
    from analyzers.report_orchestrator import (
        CompanyReportOrchestrator,
        parse_weights_string,
        load_applicant_profile
    )

    logger.info("=" * 60)
    logger.info(f"기업 분석 보고서 생성: {company_name}")
    logger.info("=" * 60)

    # 오케스트레이터 초기화
    orchestrator = CompanyReportOrchestrator(db=db, output_dir=output_dir)

    # 데이터 요약만 출력하는 경우
    if data_summary_only:
        logger.info("데이터 요약 모드")
        summary = orchestrator.get_company_data_summary(company_name)

        logger.info(f"\n회사명: {summary['company_name']}")
        logger.info(f"회사 ID: {summary['company_id']}")
        logger.info(f"최소 데이터 충족: {'예' if summary['has_minimum_data'] else '아니오'}")
        logger.info(f"\n데이터 가용성:")

        for source, count in summary['data_availability'].items():
            status = "✓" if count else "✗"
            logger.info(f"  {status} {source}: {count}")

        if summary['job_titles']:
            logger.info(f"\n채용공고 ({summary['job_postings_count']}건):")
            for title in summary['job_titles']:
                logger.info(f"  - {title}")

        return summary

    # 지원자 프로필 로드
    applicant_profile = None
    if profile_path:
        applicant_profile = load_applicant_profile(profile_path)
        if applicant_profile:
            logger.info(f"지원자 프로필 로드: {profile_path}")

    # 가중치 파싱
    priority_weights = None
    if weights_str:
        priority_weights = parse_weights_string(weights_str)
        if priority_weights:
            logger.info(f"가중치 설정: {priority_weights.to_dict()}")

    # 분석 실행
    result = orchestrator.analyze_company(
        company_name=company_name,
        job_posting_id=job_posting_id,
        applicant_profile=applicant_profile,
        priority_weights=priority_weights,
        save_prompt=True,
        generate_report=generate_llm,
        # Phase 4 옵션
        save_to_db=save_to_db,
        export_html=export_html,
        export_pdf=export_pdf,
        use_cache=use_cache,
        cache_max_days=cache_days
    )

    # 결과 출력
    logger.info("\n" + "=" * 60)
    logger.info("분석 결과")
    logger.info("=" * 60)
    logger.info(f"상태: {result['status']}")

    logger.info("\n데이터 가용성:")
    for source, count in result['data_availability'].items():
        status = "✓" if count else "✗"
        logger.info(f"  {status} {source}: {count}")

    if result.get('prompt_file'):
        logger.info(f"\n프롬프트 파일: {result['prompt_file']}")

    if result.get('report_file'):
        logger.info(f"보고서 파일: {result['report_file']}")

    # Phase 4 결과
    if result.get('from_cache'):
        logger.info(f"\n[캐시에서 로드됨]")

    if result.get('html_file'):
        logger.info(f"HTML 파일: {result['html_file']}")

    if result.get('pdf_file'):
        logger.info(f"PDF 파일: {result['pdf_file']}")

    if result.get('db_report_id'):
        logger.info(f"DB 저장 ID: {result['db_report_id']}")

    if result.get('error'):
        logger.error(f"오류: {result['error']}")

    return result


def run_check_expired(settings: Settings, db: Database, logger, days: int = 7) -> dict:
    """
    만료/삭제된 채용공고 확인

    DB에 있는 활성 공고들의 URL에 접근하여 실제로 아직 유효한지 확인합니다.
    만료되거나 삭제된 공고는 status='마감'으로 처리합니다.

    Args:
        days: 최근 N일 이내에 크롤링된 공고만 확인 (기본 7일)

    Returns:
        dict: 확인 결과 통계
    """
    import time
    from datetime import timedelta
    from utils.database import JobPosting, get_kst_now

    logger.info("=" * 60)
    logger.info("만료/삭제 공고 확인 시작")
    logger.info("=" * 60)

    stats = {
        'total_checked': 0,
        'active': 0,
        'expired': 0,
        'deleted': 0,
        'error': 0
    }

    session = db.get_session()

    try:
        # 확인할 공고 조회 (최근 N일 내 크롤링된 활성 공고)
        cutoff = get_kst_now() - timedelta(days=days)
        active_jobs = session.query(JobPosting).filter(
            JobPosting.status == '모집중',
            JobPosting.crawled_at >= cutoff
        ).all()

        # 사이트별로 그룹핑
        jobs_by_site = {}
        for job in active_jobs:
            site = job.source_site
            if site not in jobs_by_site:
                jobs_by_site[site] = []
            jobs_by_site[site].append(job)

        logger.info(f"확인 대상: {len(active_jobs)}개 공고 (최근 {days}일)")
        for site, jobs in jobs_by_site.items():
            logger.info(f"  - {site}: {len(jobs)}개")

        # 사이트별 처리
        for site_name, jobs in jobs_by_site.items():
            if site_name != 'wanted':
                logger.info(f"[{site_name}] 만료 확인 미지원 - 건너뜀")
                continue

            logger.info(f"\n[{site_name}] 만료 확인 시작 ({len(jobs)}개)")

            try:
                crawler = get_crawler(site_name)
                if not crawler or not hasattr(crawler, 'check_jobs_active_batch'):
                    logger.warning(f"[{site_name}] 만료 확인 기능 없음")
                    continue

                job_ids = [job.job_id for job in jobs]

                # 일괄 확인
                start_time = time.time()
                results = crawler.check_jobs_active_batch(job_ids)
                duration = time.time() - start_time

                # 결과 처리
                expired_ids = []
                deleted_ids = []

                for result in results:
                    stats['total_checked'] += 1
                    status = result.get('status', 'error')
                    job_id = result.get('job_id')

                    if status == 'active':
                        stats['active'] += 1
                    elif status == 'expired':
                        stats['expired'] += 1
                        expired_ids.append(job_id)
                        logger.info(f"  만료: {job_id} - {result.get('reason', '')}")
                    elif status == 'deleted':
                        stats['deleted'] += 1
                        deleted_ids.append(job_id)
                        logger.info(f"  삭제: {job_id} - {result.get('reason', '')}")
                    else:
                        stats['error'] += 1
                        logger.warning(f"  오류: {job_id} - {result.get('reason', '')}")

                # 만료/삭제된 공고 비활성화
                all_inactive_ids = expired_ids + deleted_ids
                if all_inactive_ids:
                    closed = db.mark_jobs_as_closed(site_name, all_inactive_ids)
                    logger.info(f"[{site_name}] {closed}개 공고 마감 처리")

                # 크롤링 결과 저장
                db.save_crawl_result({
                    'crawl_type': 'check_expired',
                    'source_site': site_name,
                    'total_found': len(jobs),
                    'existing_count': stats['active'],
                    'deleted_count': len(all_inactive_ids),
                    'duration_seconds': duration,
                    'status': 'completed',
                    'deleted_job_ids': all_inactive_ids[:100] if all_inactive_ids else None  # 최대 100개만 저장
                })

                logger.info(f"[{site_name}] 확인 완료 (소요: {duration:.1f}초)")

            except Exception as e:
                logger.error(f"[{site_name}] 만료 확인 실패: {e}")
                import traceback
                traceback.print_exc()

    finally:
        session.close()

    logger.info("\n" + "=" * 60)
    logger.info("만료/삭제 공고 확인 완료")
    logger.info("=" * 60)
    logger.info(f"총 확인: {stats['total_checked']}개")
    logger.info(f"활성: {stats['active']}개")
    logger.info(f"만료: {stats['expired']}개")
    logger.info(f"삭제: {stats['deleted']}개")
    logger.info(f"오류: {stats['error']}개")

    return stats


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
    """전체 크롤링 실행 (1차 채용공고 + 2차 회사정보)

    분석(analyze)과 리포트(report)는 별도 명령으로 실행해야 합니다.
    """
    logger.info("=" * 60)
    logger.info("전체 크롤링 시작 (1차 + 2차)")
    logger.info(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    start_time = datetime.now()

    # 1차 크롤링: 채용공고 수집
    run_job_crawling(settings, db, logger)

    # 2차 크롤링: 회사정보 수집
    run_company_crawling(settings, db, logger)

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    logger.info("=" * 60)
    logger.info("전체 크롤링 완료")
    logger.info(f"소요 시간: {duration:.1f}초")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description='채용 시장 분석 및 커리어 로드맵 생성 시스템',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
    python main.py crawl-jobs         # 1차 크롤링: 채용공고 수집
    python main.py crawl-companies    # 2차 크롤링: 회사정보 수집 (잡플래닛)
    python main.py crawl-news         # 3차 크롤링: 뉴스 기사 수집 (연합뉴스)
    python main.py crawl              # 전체 크롤링 (1차 + 2차)
    python main.py check-expired      # 만료/삭제 공고 확인
    python main.py analyze            # 분석만 실행
    python main.py report             # 리포트 생성
    python main.py all                # 전체 실행
    python main.py schedule           # 스케줄러 시작
    python main.py company "카카오"    # 특정 회사 분석 (레거시)

    # 기업 분석 보고서 (기본: LLM 호출 + DB 저장 + HTML)
    python main.py analyze-report "카카오"              # 전체 실행
    python main.py analyze-report "카카오" --prompt-only  # 프롬프트만 생성
    python main.py analyze-report "카카오" --data-summary # 데이터 요약만
    python main.py analyze-report "카카오" --no-save-db   # DB 저장 안 함
        """
    )

    parser.add_argument(
        'command',
        choices=['crawl', 'crawl-jobs', 'crawl-companies', 'crawl-news', 'check-expired', 'analyze', 'report', 'all', 'schedule', 'company', 'analyze-report'],
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

    parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='check-expired 명령에서 확인할 공고의 최근 일수 (기본: 7)'
    )

    parser.add_argument(
        '--max-companies',
        type=int,
        default=None,
        help='처리할 최대 회사 수 (기본: crawl-companies=1, crawl-news=전체)'
    )

    parser.add_argument(
        '--reset-progress',
        action='store_true',
        help='진행 상황 초기화 (이전 세션에서 처리된 회사도 다시 크롤링)'
    )

    parser.add_argument(
        '--no-resume',
        action='store_true',
        help='이미 수집된 회사 건너뛰기 비활성화 (불완전한 회사도 재수집하지 않음)'
    )

    parser.add_argument(
        '--only-no-news',
        action='store_true',
        help='뉴스가 0건인 회사만 크롤링 (괄호 등으로 검색 실패했던 회사 재시도)'
    )

    parser.add_argument(
        '--since-date',
        type=str,
        default=None,
        help='특정 날짜 이후의 기사만 수집 (형식: YYYY-MM-DD, 예: 2024-01-01)'
    )

    # analyze-report 명령 전용 옵션
    parser.add_argument(
        '--job-id',
        type=int,
        default=None,
        help='analyze-report: 특정 채용공고 ID (미지정 시 전체 공고 분석)'
    )

    parser.add_argument(
        '--output-dir',
        type=str,
        default='./reports/company_analysis',
        help='analyze-report: 보고서 저장 디렉토리'
    )

    parser.add_argument(
        '--profile',
        type=str,
        default=None,
        help='analyze-report: 지원자 프로필 JSON 파일 경로'
    )

    parser.add_argument(
        '--weights',
        type=str,
        default=None,
        help='analyze-report: 우선순위 가중치 (예: "성장성:30,안정성:20,보상:20,워라밸:15,직무적합:15")'
    )

    parser.add_argument(
        '--prompt-only',
        action='store_true',
        help='analyze-report: 프롬프트만 생성 (LLM 호출 안 함)'
    )

    parser.add_argument(
        '--data-summary',
        action='store_true',
        help='analyze-report: 데이터 요약만 출력 (프롬프트 생성 없이)'
    )

    # Phase 4: 저장 및 내보내기 옵션 (기본값: 모두 활성화)
    parser.add_argument(
        '--no-save-db',
        action='store_true',
        help='analyze-report: DB 저장 안 함 (기본: 저장함)'
    )

    parser.add_argument(
        '--no-html',
        action='store_true',
        help='analyze-report: HTML 내보내기 안 함 (기본: 내보냄)'
    )

    parser.add_argument(
        '--export-pdf',
        action='store_true',
        help='analyze-report: PDF 파일로 내보내기 (weasyprint 필요)'
    )

    parser.add_argument(
        '--no-cache',
        action='store_true',
        help='analyze-report: 캐시 사용 안 함 (항상 새로 생성)'
    )

    parser.add_argument(
        '--cache-days',
        type=int,
        default=7,
        help='analyze-report: 캐시 유효 기간 (일, 기본: 7)'
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
        if args.command == 'crawl-jobs':
            # 1차 크롤링: 채용공고만
            run_job_crawling(settings, db, logger)

        elif args.command == 'crawl-companies':
            # 2차 크롤링: 회사정보만
            # --reset-progress: 진행 상황 파일 삭제
            if args.reset_progress:
                progress_file = Path("data/crawl_progress.json")
                if progress_file.exists():
                    progress_file.unlink()
                    logger.info("진행 상황 초기화됨")

            # --no-resume: 불완전한 회사도 재수집하지 않음
            resume = not args.no_resume
            # 2차 크롤링 기본값: 1000 (전체)
            max_companies = args.max_companies if args.max_companies is not None else 1000
            run_company_crawling(settings, db, logger, max_companies=max_companies, resume=resume)

        elif args.command == 'crawl-news':
            # 3차 크롤링: 뉴스 기사 수집
            # 3차 크롤링 기본값: 전체 (1000개 제한)
            max_companies = args.max_companies if args.max_companies is not None else 1000
            only_no_news = args.only_no_news if hasattr(args, 'only_no_news') else False
            since_date = args.since_date if hasattr(args, 'since_date') else None
            run_news_crawling(settings, db, logger, max_companies=max_companies, only_no_news=only_no_news, since_date=since_date)

        elif args.command == 'crawl':
            # 전체 크롤링 (1차 + 2차)
            run_crawling(settings, db, logger)

        elif args.command == 'check-expired':
            # 만료/삭제 공고 확인
            run_check_expired(settings, db, logger, days=args.days)

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

        elif args.command == 'analyze-report':
            # 기업 분석 보고서 생성
            # 기본 동작: LLM 호출 + DB 저장 + HTML 내보내기
            if not args.target:
                logger.error("회사 이름을 지정해주세요. 예: python main.py analyze-report '카카오'")
                sys.exit(1)
            run_company_report(
                company_name=args.target,
                db=db,
                logger=logger,
                job_posting_id=args.job_id,
                output_dir=args.output_dir,
                profile_path=args.profile,
                weights_str=args.weights,
                generate_llm=not args.prompt_only,  # 기본: LLM 호출
                data_summary_only=args.data_summary,
                # Phase 4 옵션 (기본: 모두 활성화)
                save_to_db=not args.no_save_db,     # 기본: DB 저장
                export_html=not args.no_html,       # 기본: HTML 내보내기
                export_pdf=args.export_pdf,
                use_cache=not args.no_cache,
                cache_days=args.cache_days
            )

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
