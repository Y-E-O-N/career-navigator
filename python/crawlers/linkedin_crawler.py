#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LinkedIn 채용공고 크롤러

LinkedIn은 API 접근이 제한적이고 로그인이 필요하므로,
공개된 채용 검색 페이지를 크롤링합니다.

주의: LinkedIn은 크롤링에 민감하므로 적절한 딜레이와 User-Agent 설정 필요
"""

import re
import json
import time
from typing import List, Dict, Optional
from urllib.parse import quote, urlencode

from .base_crawler import BaseCrawler
from utils.helpers import clean_text, extract_skills_from_text, categorize_job_level


class LinkedInCrawler(BaseCrawler):
    """LinkedIn 채용공고 크롤러"""
    
    def __init__(self):
        super().__init__()
        self.site_name = 'linkedin'
        self.base_url = 'https://www.linkedin.com'
        self.search_url = 'https://www.linkedin.com/jobs/search'
        
        # LinkedIn은 더 긴 딜레이 필요
        self.rate_limiter.min_interval = 3.0
        
        # 추가 헤더 설정
        self.session.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
    
    def search_jobs(self, keyword: str, max_pages: int = 5) -> List[Dict]:
        """
        LinkedIn 채용공고 검색
        
        Args:
            keyword: 검색 키워드
            max_pages: 최대 페이지 수 (각 페이지 25개)
            
        Returns:
            채용공고 목록
        """
        jobs = []
        
        for page in range(max_pages):
            start = page * 25  # LinkedIn은 25개씩
            
            params = {
                'keywords': keyword,
                'location': '대한민국',
                'geoId': '105149562',  # South Korea
                'f_TPR': 'r604800',  # Last week
                'position': 1,
                'pageNum': page,
                'start': start
            }
            
            try:
                # 공개 검색 페이지 요청
                url = f"{self.search_url}?{urlencode(params)}"
                soup = self.get_page(url)
                
                if not soup:
                    self.logger.warning(f"페이지 {page + 1} 로드 실패")
                    break
                
                # 채용공고 카드 파싱
                job_cards = soup.select('.base-card, .job-search-card, .base-search-card')
                
                if not job_cards:
                    # 대체 셀렉터 시도
                    job_cards = soup.select('[data-entity-urn*="jobPosting"]')
                
                if not job_cards:
                    self.logger.info(f"페이지 {page + 1}: 더 이상 결과 없음")
                    break
                
                for card in job_cards:
                    try:
                        job = self._parse_job_card(card)
                        if job:
                            jobs.append(job)
                    except Exception as e:
                        self.logger.debug(f"카드 파싱 실패: {e}")
                        continue
                
                self.logger.info(f"페이지 {page + 1}: {len(job_cards)}개 수집")
                
                # 다음 페이지 확인
                if len(job_cards) < 25:
                    break
                    
            except Exception as e:
                self.logger.error(f"검색 실패 (페이지 {page + 1}): {e}")
                break
        
        return jobs
    
    def _parse_job_card(self, card) -> Optional[Dict]:
        """채용공고 카드 파싱"""
        
        # Job ID 추출
        job_id = None
        
        # data-entity-urn에서 추출
        entity_urn = card.get('data-entity-urn', '')
        if entity_urn:
            match = re.search(r'jobPosting:(\d+)', entity_urn)
            if match:
                job_id = match.group(1)
        
        # href에서 추출
        if not job_id:
            link = card.select_one('a[href*="/jobs/view/"]')
            if link:
                href = link.get('href', '')
                match = re.search(r'/jobs/view/(\d+)', href)
                if match:
                    job_id = match.group(1)
        
        if not job_id:
            return None
        
        # 제목
        title_elem = card.select_one('.base-search-card__title, .job-search-card__title, h3, h4')
        title = clean_text(title_elem.get_text()) if title_elem else ''
        
        if not title:
            return None
        
        # 회사명
        company_elem = card.select_one('.base-search-card__subtitle, .job-search-card__company-name, h4 a')
        company_name = clean_text(company_elem.get_text()) if company_elem else ''
        
        # 위치
        location_elem = card.select_one('.job-search-card__location, .base-search-card__metadata')
        location = clean_text(location_elem.get_text()) if location_elem else ''
        
        # 게시일
        date_elem = card.select_one('time, .job-search-card__listdate')
        posted_date = date_elem.get('datetime', '') if date_elem else ''
        
        # URL
        url = f"https://www.linkedin.com/jobs/view/{job_id}"
        
        return {
            'source_site': self.site_name,
            'job_id': job_id,
            'title': title,
            'company_name': company_name,
            'location': location,
            'posted_date': posted_date,
            'url': url
        }
    
    def get_job_detail(self, job_id: str) -> Optional[Dict]:
        """
        채용공고 상세 정보 조회
        
        LinkedIn 상세 페이지는 로그인이 필요할 수 있어 제한적
        """
        url = f"https://www.linkedin.com/jobs/view/{job_id}"
        
        try:
            soup = self.get_page(url)
            
            if not soup:
                return None
            
            detail = {
                'job_id': job_id,
                'url': url
            }
            
            # 상세 설명
            description_elem = soup.select_one('.description__text, .show-more-less-html__markup, .job-description')
            if description_elem:
                detail['description'] = clean_text(description_elem.get_text())
            
            # 회사 정보
            company_elem = soup.select_one('.topcard__org-name-link, .company-name')
            if company_elem:
                detail['company_name'] = clean_text(company_elem.get_text())
            
            # 고용 형태
            criteria = soup.select('.description__job-criteria-item, .job-criteria__item')
            for item in criteria:
                header = item.select_one('.description__job-criteria-subheader, h3')
                value = item.select_one('.description__job-criteria-text, span')
                
                if header and value:
                    header_text = clean_text(header.get_text()).lower()
                    value_text = clean_text(value.get_text())
                    
                    if '고용' in header_text or 'employment' in header_text:
                        detail['employment_type'] = value_text
                    elif '경력' in header_text or 'seniority' in header_text:
                        detail['seniority_level'] = value_text
                    elif '직무' in header_text or 'function' in header_text:
                        detail['job_function'] = value_text
                    elif '산업' in header_text or 'industry' in header_text:
                        detail['industry'] = value_text
            
            # 스킬 추출
            if detail.get('description'):
                detail['required_skills'] = extract_skills_from_text(detail['description'])
            
            return detail
            
        except Exception as e:
            self.logger.error(f"상세 조회 실패 ({job_id}): {e}")
            return None
    
    def crawl_keyword(self, keyword: str, max_pages: int = None) -> List[Dict]:
        """
        키워드로 전체 크롤링 실행
        
        LinkedIn은 상세 페이지 접근이 제한적이므로
        검색 결과만 수집하고 스킬은 제목/설명에서 추출
        """
        if max_pages is None:
            max_pages = self.config.max_pages_per_keyword
        
        self.logger.info(f"LinkedIn 크롤링 시작: {keyword}")
        
        # 검색 결과 수집
        jobs = self.search_jobs(keyword, max_pages)
        
        # 제목에서 스킬 추출
        for job in jobs:
            if job.get('title'):
                skills = extract_skills_from_text(job['title'])
                job['required_skills'] = skills.get('hard_skills', []) + skills.get('soft_skills', [])
            
            # 경력 수준 추정
            job['position_level'] = categorize_job_level(job.get('title', ''))
        
        self.logger.info(f"LinkedIn 크롤링 완료: {len(jobs)}개 수집")
        
        return jobs
