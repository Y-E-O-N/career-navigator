"""
크롤러 매니저 - 모든 크롤러 통합 관리
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Type, Optional
from collections import defaultdict

from .base import BaseCrawler, JobPosting
from .wanted import WantedCrawler
from .saramin import SaraminCrawler
from .other_sites import JobKoreaCrawler, JumpitCrawler, ProgrammersCrawler

import sys
sys.path.append(str(__file__).rsplit('/', 2)[0])
from config import crawler_config, DATA_DIR


# 사용 가능한 크롤러 등록
AVAILABLE_CRAWLERS: Dict[str, Type[BaseCrawler]] = {
    "wanted": WantedCrawler,
    "saramin": SaraminCrawler,
    "jobkorea": JobKoreaCrawler,
    "jumpit": JumpitCrawler,
    "programmers": ProgrammersCrawler,
}


class CrawlerManager:
    """크롤러 통합 관리자"""
    
    def __init__(self, enabled_sites: List[str] = None):
        self.logger = logging.getLogger("crawler.manager")
        self.enabled_sites = enabled_sites or crawler_config.enabled_sites
        self.crawlers: Dict[str, BaseCrawler] = {}
        
        self._initialize_crawlers()
    
    def _initialize_crawlers(self):
        """크롤러 초기화"""
        for site in self.enabled_sites:
            if site in AVAILABLE_CRAWLERS:
                self.crawlers[site] = AVAILABLE_CRAWLERS[site]()
                self.logger.info(f"크롤러 초기화: {site}")
            else:
                self.logger.warning(f"알 수 없는 사이트: {site}")
    
    def crawl_all(self) -> List[JobPosting]:
        """모든 사이트 크롤링"""
        all_jobs = []
        seen_hashes = set()
        
        for site_name, crawler in self.crawlers.items():
            self.logger.info(f"=== {site_name} 크롤링 시작 ===")
            
            try:
                jobs = crawler.crawl_all_keywords()
                
                # 중복 제거
                new_jobs = []
                for job in jobs:
                    if job.content_hash not in seen_hashes:
                        seen_hashes.add(job.content_hash)
                        new_jobs.append(job)
                
                all_jobs.extend(new_jobs)
                self.logger.info(f"{site_name}: {len(new_jobs)}개 수집")
                
            except Exception as e:
                self.logger.error(f"{site_name} 크롤링 실패: {e}")
        
        self.logger.info(f"총 {len(all_jobs)}개 채용 공고 수집 완료")
        
        # 데이터 저장
        self._save_jobs(all_jobs)
        
        return all_jobs
    
    def crawl_site(self, site_name: str) -> List[JobPosting]:
        """특정 사이트만 크롤링"""
        if site_name not in self.crawlers:
            self.logger.error(f"크롤러 없음: {site_name}")
            return []
        
        crawler = self.crawlers[site_name]
        return crawler.crawl_all_keywords()
    
    def _save_jobs(self, jobs: List[JobPosting], filename: str = None):
        """크롤링 데이터 저장"""
        if not filename:
            date_str = datetime.now().strftime("%Y%m%d")
            filename = f"jobs_{date_str}.json"
        
        filepath = DATA_DIR / filename
        
        data = {
            "crawled_at": datetime.now().isoformat(),
            "total_count": len(jobs),
            "jobs": [job.to_dict() for job in jobs]
        }
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"데이터 저장: {filepath}")
        
        # 마스터 데이터 업데이트
        self._update_master_data(jobs)
    
    def _update_master_data(self, new_jobs: List[JobPosting]):
        """마스터 데이터 업데이트 (기존 데이터와 병합)"""
        master_file = DATA_DIR / "master_jobs.json"
        
        existing_jobs = []
        existing_hashes = set()
        
        if master_file.exists():
            with open(master_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for job_dict in data.get("jobs", []):
                    existing_jobs.append(JobPosting.from_dict(job_dict))
                    existing_hashes.add(job_dict.get("content_hash", ""))
        
        # 새 데이터 추가
        added_count = 0
        for job in new_jobs:
            if job.content_hash not in existing_hashes:
                existing_jobs.append(job)
                existing_hashes.add(job.content_hash)
                added_count += 1
        
        # 저장
        data = {
            "updated_at": datetime.now().isoformat(),
            "total_count": len(existing_jobs),
            "jobs": [job.to_dict() for job in existing_jobs]
        }
        
        with open(master_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"마스터 데이터 업데이트: +{added_count}개 (총 {len(existing_jobs)}개)")
    
    def load_data(self, date: str = None, source: str = None) -> List[JobPosting]:
        """저장된 데이터 로드"""
        if date:
            filename = f"jobs_{date.replace('-', '')}.json"
            filepath = DATA_DIR / filename
        else:
            filepath = DATA_DIR / "master_jobs.json"
        
        if not filepath.exists():
            self.logger.warning(f"데이터 파일 없음: {filepath}")
            return []
        
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        jobs = [JobPosting.from_dict(j) for j in data.get("jobs", [])]
        
        # 소스 필터링
        if source:
            jobs = [j for j in jobs if j.source == source]
        
        return jobs
    
    def get_statistics(self, jobs: List[JobPosting] = None) -> Dict:
        """데이터 통계"""
        if jobs is None:
            jobs = self.load_data()
        
        if not jobs:
            return {}
        
        stats = {
            "total_count": len(jobs),
            "by_source": defaultdict(int),
            "by_company": defaultdict(int),
            "crawled_dates": set(),
        }
        
        for job in jobs:
            stats["by_source"][job.source] += 1
            stats["by_company"][job.company] += 1
            if job.crawled_at:
                date = job.crawled_at[:10]
                stats["crawled_dates"].add(date)
        
        # set을 list로 변환
        stats["crawled_dates"] = sorted(list(stats["crawled_dates"]))
        stats["by_source"] = dict(stats["by_source"])
        stats["by_company"] = dict(sorted(
            stats["by_company"].items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:20])
        
        return stats
