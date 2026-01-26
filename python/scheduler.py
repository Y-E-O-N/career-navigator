#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Job Market Analyzer - 스케줄러

APScheduler를 사용한 자동 실행 스케줄러
매일 지정된 시간에 크롤링 → 분석 → 리포트 생성 파이프라인 실행
"""

import os
import sys
import signal
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
    HAS_APSCHEDULER = True
except ImportError:
    HAS_APSCHEDULER = False

sys.path.insert(0, str(Path(__file__).parent))

from config.settings import Settings
from utils.database import Database
from utils.helpers import setup_logger


class JobScheduler:
    """채용 시장 분석 스케줄러"""
    
    def __init__(self, settings: Settings = None, db: Database = None):
        if not HAS_APSCHEDULER:
            raise ImportError(
                "APScheduler가 설치되지 않았습니다. "
                "pip install apscheduler 로 설치해주세요."
            )
        
        self.settings = settings or Settings()
        self.db = db
        self.logger = setup_logger('scheduler', log_level='INFO')
        self.scheduler = BlockingScheduler(timezone=self.settings.scheduler.timezone)
        
        # 시그널 핸들러 등록
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # 이벤트 리스너 등록
        self.scheduler.add_listener(self._job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    
    def _signal_handler(self, signum, frame):
        """시그널 핸들러"""
        self.logger.info("종료 신호 수신, 스케줄러 중지 중...")
        self.stop()
    
    def _job_listener(self, event):
        """작업 이벤트 리스너"""
        if event.exception:
            self.logger.error(f"작업 실행 실패: {event.job_id}")
            self.logger.error(f"에러: {event.exception}")
        else:
            self.logger.info(f"작업 완료: {event.job_id}")
    
    def _ensure_db(self):
        """데이터베이스 연결 확인"""
        if self.db is None:
            self.db = Database(self.settings.database.connection_string)
            self.db.create_tables()
    
    def run_daily_job(self):
        """매일 실행되는 메인 작업"""
        self.logger.info("=" * 60)
        self.logger.info(f"일일 작업 시작: {datetime.now()}")
        self.logger.info("=" * 60)
        
        self._ensure_db()
        
        try:
            from main import run_crawling, run_analysis, generate_reports
            
            # 1. 크롤링
            self.logger.info("1단계: 크롤링")
            total_jobs = run_crawling(self.settings, self.db, self.logger)
            
            # 2. 분석
            if total_jobs > 0:
                self.logger.info("2단계: 시장 분석")
                results = run_analysis(self.settings, self.db, self.logger)
                
                # 3. 리포트 생성
                if results:
                    self.logger.info("3단계: 리포트 생성")
                    generate_reports(self.settings, self.db, self.logger)
            else:
                self.logger.warning("수집된 데이터 없음 - 분석 건너뜀")
            
            self.logger.info("일일 작업 완료")
            
        except Exception as e:
            self.logger.error(f"일일 작업 실패: {e}")
            import traceback
            traceback.print_exc()
    
    def run_crawling_only(self):
        """크롤링만 실행"""
        self.logger.info(f"크롤링 작업 시작: {datetime.now()}")
        self._ensure_db()
        
        try:
            from main import run_crawling
            run_crawling(self.settings, self.db, self.logger)
        except Exception as e:
            self.logger.error(f"크롤링 실패: {e}")
    
    def run_analysis_only(self):
        """분석만 실행"""
        self.logger.info(f"분석 작업 시작: {datetime.now()}")
        self._ensure_db()
        
        try:
            from main import run_analysis
            run_analysis(self.settings, self.db, self.logger)
        except Exception as e:
            self.logger.error(f"분석 실패: {e}")
    
    def add_daily_job(self, hour: int = None, minute: int = None):
        """매일 실행 작업 추가"""
        schedule_time = self.settings.scheduler.schedule_time
        
        if hour is None:
            hour = int(schedule_time.split(':')[0])
        if minute is None:
            minute = int(schedule_time.split(':')[1]) if ':' in schedule_time else 0
        
        trigger = CronTrigger(hour=hour, minute=minute)
        
        self.scheduler.add_job(
            self.run_daily_job,
            trigger=trigger,
            id='daily_job',
            name='일일 크롤링 및 분석',
            replace_existing=True,
            max_instances=1
        )
        
        self.logger.info(f"일일 작업 등록: 매일 {hour:02d}:{minute:02d}")
    
    def add_interval_job(self, hours: int = None, minutes: int = None, 
                         job_type: str = 'crawl'):
        """주기적 실행 작업 추가"""
        if hours is None and minutes is None:
            hours = 6  # 기본 6시간 간격
        
        trigger = IntervalTrigger(hours=hours or 0, minutes=minutes or 0)
        
        job_func = {
            'crawl': self.run_crawling_only,
            'analyze': self.run_analysis_only,
            'all': self.run_daily_job
        }.get(job_type, self.run_crawling_only)
        
        self.scheduler.add_job(
            job_func,
            trigger=trigger,
            id=f'interval_{job_type}',
            name=f'주기적 {job_type}',
            replace_existing=True,
            max_instances=1
        )
        
        interval_str = f"{hours}시간" if hours else f"{minutes}분"
        self.logger.info(f"주기적 작업 등록: {interval_str}마다 {job_type}")
    
    def add_weekday_job(self, hour: int = 9, minute: int = 0):
        """평일만 실행 작업 추가"""
        trigger = CronTrigger(
            day_of_week='mon-fri',
            hour=hour,
            minute=minute
        )
        
        self.scheduler.add_job(
            self.run_daily_job,
            trigger=trigger,
            id='weekday_job',
            name='평일 크롤링 및 분석',
            replace_existing=True,
            max_instances=1
        )
        
        self.logger.info(f"평일 작업 등록: 월-금 {hour:02d}:{minute:02d}")
    
    def list_jobs(self):
        """등록된 작업 목록"""
        jobs = self.scheduler.get_jobs()
        
        self.logger.info("=" * 40)
        self.logger.info("등록된 작업 목록")
        self.logger.info("=" * 40)
        
        if not jobs:
            self.logger.info("등록된 작업 없음")
            return
        
        for job in jobs:
            self.logger.info(f"  ID: {job.id}")
            self.logger.info(f"  이름: {job.name}")
            self.logger.info(f"  다음 실행: {job.next_run_time}")
            self.logger.info("-" * 40)
    
    def remove_job(self, job_id: str):
        """작업 제거"""
        try:
            self.scheduler.remove_job(job_id)
            self.logger.info(f"작업 제거됨: {job_id}")
        except Exception as e:
            self.logger.error(f"작업 제거 실패: {e}")
    
    def start(self, run_now: bool = False):
        """스케줄러 시작"""
        self.logger.info("=" * 60)
        self.logger.info("스케줄러 시작")
        self.logger.info(f"타임존: {self.settings.scheduler.timezone}")
        self.logger.info("=" * 60)
        
        # 기본 일일 작업 등록
        self.add_daily_job()
        
        # 등록된 작업 목록 출력
        self.list_jobs()
        
        # 즉시 실행 옵션
        if run_now:
            self.logger.info("즉시 실행 시작...")
            self.run_daily_job()
        
        try:
            self.logger.info("스케줄러 실행 중... (Ctrl+C로 종료)")
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            self.logger.info("스케줄러 종료됨")
    
    def stop(self):
        """스케줄러 중지"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            self.logger.info("스케줄러 중지됨")


def main():
    """스케줄러 CLI"""
    import argparse
    
    parser = argparse.ArgumentParser(description='채용 시장 분석 스케줄러')
    
    parser.add_argument(
        '--mode',
        choices=['daily', 'interval', 'weekday', 'once'],
        default='daily',
        help='실행 모드'
    )
    
    parser.add_argument(
        '--hour',
        type=int,
        default=None,
        help='실행 시간 (시)'
    )
    
    parser.add_argument(
        '--minute',
        type=int,
        default=0,
        help='실행 시간 (분)'
    )
    
    parser.add_argument(
        '--interval-hours',
        type=int,
        default=None,
        help='실행 간격 (시간)'
    )
    
    parser.add_argument(
        '--run-now',
        action='store_true',
        help='시작 시 즉시 실행'
    )
    
    parser.add_argument(
        '--config',
        default=None,
        help='설정 파일 경로'
    )
    
    args = parser.parse_args()
    
    # 설정 로드
    settings = Settings()
    if args.config:
        settings.load_from_file(args.config)
    
    # 스케줄러 초기화
    scheduler = JobScheduler(settings)
    
    if args.mode == 'once':
        # 즉시 한 번만 실행
        scheduler.run_daily_job()
    elif args.mode == 'interval':
        # 주기적 실행
        scheduler.add_interval_job(hours=args.interval_hours or 6)
        scheduler.start()
    elif args.mode == 'weekday':
        # 평일만 실행
        scheduler.add_weekday_job(hour=args.hour or 9, minute=args.minute)
        scheduler.start()
    else:
        # 매일 실행 (기본)
        if args.hour is not None:
            scheduler.add_daily_job(hour=args.hour, minute=args.minute)
        scheduler.start(run_now=args.run_now)


if __name__ == '__main__':
    main()
