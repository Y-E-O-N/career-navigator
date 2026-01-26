"""
Job Market Analyzer - Crawlers 모듈

각 채용 사이트별 크롤러 제공
- LinkedIn: 글로벌 채용 플랫폼
- Wanted: 원티드
- JobKorea: 잡코리아
- Saramin: 사람인
- RocketPunch: 로켓펀치 (스타트업 중심)
"""

from .base_crawler import BaseCrawler
from .linkedin_crawler import LinkedInCrawler
from .wanted_playwright import WantedCrawler  # Playwright 기반 크롤러 사용
from .saramin_crawler import SaraminCrawler
from .jobkorea_crawler import JobKoreaCrawler
from .rocketpunch_crawler import RocketPunchCrawler


CRAWLERS = {
    'linkedin': LinkedInCrawler,
    'wanted': WantedCrawler,
    'jobkorea': JobKoreaCrawler,
    'saramin': SaraminCrawler,
    'rocketpunch': RocketPunchCrawler,
}


def get_crawler(site_name: str) -> BaseCrawler:
    """사이트 이름으로 크롤러 인스턴스 반환"""
    crawler_class = CRAWLERS.get(site_name.lower())
    if crawler_class:
        return crawler_class()
    return None


def get_all_crawlers() -> dict:
    """모든 크롤러 인스턴스 반환"""
    return {name: cls() for name, cls in CRAWLERS.items()}


__all__ = [
    'BaseCrawler',
    'LinkedInCrawler',
    'WantedCrawler',
    'SaraminCrawler',
    'JobKoreaCrawler',
    'RocketPunchCrawler',
    'get_crawler',
    'get_all_crawlers',
    'CRAWLERS'
]
