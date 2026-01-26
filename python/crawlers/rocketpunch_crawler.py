#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
RocketPunch 채용공고 크롤러

로켓펀치 채용 페이지 크롤링
API와 HTML 파싱 방식 모두 지원
"""

import re
import json
import time
from typing import List, Dict, Optional
from urllib.parse import urlencode, quote

from .base_crawler import BaseCrawler
from utils.helpers import clean_text, extract_skills_from_text, categorize_job_level


class RocketPunchCrawler(BaseCrawler):
    """RocketPunch 채용공고 크롤러"""
    
    def __init__(self):
        super().__init__()
        self.site_name = 'rocketpunch'
        self.base_url = 'https://www.rocketpunch.com'
        self.api_url = 'https://www.rocketpunch.com/api/jobs'
        self.search_url = 'https://www.rocketpunch.com/jobs'
        
        # 추가 헤더
        self.session.headers.update({
            'Accept': 'application/json, text/html, */*',
            'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8',
            'Referer': 'https://www.rocketpunch.com/jobs',
        })
    
    def search_jobs(self, keyword: str, max_pages: int = 10) -> List[Dict]:
        """
        RocketPunch 채용공고 검색
        
        Args:
            keyword: 검색 키워드
            max_pages: 최대 페이지 수
            
        Returns:
            채용공고 목록
        """
        jobs = []
        
        for page in range(1, max_pages + 1):
            try:
                # API 방식 시도
                api_jobs = self._search_via_api(keyword, page)
                
                if api_jobs:
                    jobs.extend(api_jobs)
                    self.logger.info(f"페이지 {page}: {len(api_jobs)}개 수집 (API)")
                    
                    if len(api_jobs) < 20:  # 페이지당 20개 미만이면 마지막
                        break
                else:
                    # HTML 파싱 방식 fallback
                    html_jobs = self._search_via_html(keyword, page)
                    
                    if html_jobs:
                        jobs.extend(html_jobs)
                        self.logger.info(f"페이지 {page}: {len(html_jobs)}개 수집 (HTML)")
                        
                        if len(html_jobs) < 20:
                            break
                    else:
                        self.logger.info(f"페이지 {page}: 더 이상 결과 없음")
                        break
                        
            except Exception as e:
                self.logger.error(f"검색 실패 (페이지 {page}): {e}")
                break
        
        return jobs
    
    def _search_via_api(self, keyword: str, page: int) -> Optional[List[Dict]]:
        """API를 통한 검색"""
        
        params = {
            'keywords': keyword,
            'page': page,
            'job_type': '',  # 전체
            'hiring': 1,     # 채용중만
        }
        
        try:
            data = self.get_json(self.api_url, params)
            
            if not data:
                return None
            
            jobs = []
            job_list = data.get('data', {}).get('jobs', [])
            
            if not job_list:
                job_list = data.get('jobs', [])
            
            for item in job_list:
                job = self._parse_api_job(item)
                if job:
                    jobs.append(job)
            
            return jobs
            
        except Exception as e:
            self.logger.debug(f"API 검색 실패: {e}")
            return None
    
    def _parse_api_job(self, item: Dict) -> Optional[Dict]:
        """API 응답 파싱"""
        
        job_id = str(item.get('id', ''))
        if not job_id:
            return None
        
        # 회사 정보
        company = item.get('company', {})
        if isinstance(company, dict):
            company_name = company.get('name', '')
        else:
            company_name = str(company) if company else ''
        
        # 기술 스택
        tech_stacks = item.get('tech_stacks', [])
        if isinstance(tech_stacks, list):
            skills = [t.get('name', t) if isinstance(t, dict) else str(t) for t in tech_stacks]
        else:
            skills = []
        
        return {
            'source_site': self.site_name,
            'job_id': job_id,
            'title': item.get('title', ''),
            'company_name': company_name,
            'job_category': item.get('job_category', ''),
            'location': item.get('location', item.get('address', '')),
            'career_min': item.get('career_min', 0),
            'career_max': item.get('career_max', 0),
            'salary_min': item.get('salary_min'),
            'salary_max': item.get('salary_max'),
            'employment_type': item.get('employment_type', ''),
            'required_skills': skills,
            'url': f"{self.base_url}/jobs/{job_id}"
        }
    
    def _search_via_html(self, keyword: str, page: int) -> Optional[List[Dict]]:
        """HTML 파싱을 통한 검색"""
        
        url = f"{self.search_url}?keywords={quote(keyword)}&page={page}"
        
        try:
            soup = self.get_page(url)
            
            if not soup:
                return None
            
            jobs = []
            
            # 채용공고 카드 선택
            job_cards = soup.select('.job-item, .company-job-item, [data-job-id]')
            
            if not job_cards:
                # 대체 셀렉터
                job_cards = soup.select('.job-card, .job-list-item')
            
            for card in job_cards:
                job = self._parse_html_job(card)
                if job:
                    jobs.append(job)
            
            return jobs
            
        except Exception as e:
            self.logger.debug(f"HTML 검색 실패: {e}")
            return None
    
    def _parse_html_job(self, card) -> Optional[Dict]:
        """HTML 카드 파싱"""
        
        # Job ID
        job_id = card.get('data-job-id', '')
        
        if not job_id:
            link = card.select_one('a[href*="/jobs/"]')
            if link:
                href = link.get('href', '')
                match = re.search(r'/jobs/(\d+)', href)
                if match:
                    job_id = match.group(1)
        
        if not job_id:
            return None
        
        # 제목
        title_elem = card.select_one('.job-title, .title, h4, h3 a')
        title = clean_text(title_elem.get_text()) if title_elem else ''
        
        if not title:
            return None
        
        # 회사명
        company_elem = card.select_one('.company-name, .company, .job-company a')
        company_name = clean_text(company_elem.get_text()) if company_elem else ''
        
        # 위치
        location_elem = card.select_one('.location, .job-location')
        location = clean_text(location_elem.get_text()) if location_elem else ''
        
        # 기술 스택
        tech_elems = card.select('.tech-stack, .skill-tag, .tag')
        skills = [clean_text(t.get_text()) for t in tech_elems if t.get_text().strip()]
        
        # 경력
        career_elem = card.select_one('.career, .experience')
        career_text = clean_text(career_elem.get_text()) if career_elem else ''
        
        return {
            'source_site': self.site_name,
            'job_id': job_id,
            'title': title,
            'company_name': company_name,
            'location': location,
            'career_text': career_text,
            'required_skills': skills,
            'url': f"{self.base_url}/jobs/{job_id}"
        }
    
    def get_job_detail(self, job_id: str) -> Optional[Dict]:
        """채용공고 상세 정보 조회"""
        
        url = f"{self.base_url}/jobs/{job_id}"
        
        try:
            soup = self.get_page(url)
            
            if not soup:
                return None
            
            detail = {
                'job_id': job_id,
                'url': url
            }
            
            # 제목
            title_elem = soup.select_one('h1.title, .job-title, h1')
            if title_elem:
                detail['title'] = clean_text(title_elem.get_text())
            
            # 회사명
            company_elem = soup.select_one('.company-name a, .company-info .name')
            if company_elem:
                detail['company_name'] = clean_text(company_elem.get_text())
            
            # 상세 설명
            desc_elem = soup.select_one('.job-description, .description, .content')
            if desc_elem:
                detail['description'] = clean_text(desc_elem.get_text())
            
            # 자격요건
            req_elem = soup.select_one('.job-requirement, .requirement')
            if req_elem:
                detail['requirements'] = clean_text(req_elem.get_text())
            
            # 우대사항
            pref_elem = soup.select_one('.job-preference, .preferred')
            if pref_elem:
                detail['preferred'] = clean_text(pref_elem.get_text())
            
            # 복리후생
            benefit_elem = soup.select_one('.job-benefit, .benefit, .welfare')
            if benefit_elem:
                detail['benefits'] = clean_text(benefit_elem.get_text())
            
            # 기술 스택
            tech_elems = soup.select('.tech-stack .tag, .skill-tags .tag, .tech-stacks span')
            if tech_elems:
                detail['tech_stacks'] = [clean_text(t.get_text()) for t in tech_elems]
            
            # 정보 테이블 파싱
            info_items = soup.select('.job-info-item, .info-row, tr')
            for item in info_items:
                label_elem = item.select_one('.label, th, dt')
                value_elem = item.select_one('.value, td, dd')
                
                if label_elem and value_elem:
                    label = clean_text(label_elem.get_text())
                    value = clean_text(value_elem.get_text())
                    
                    if '경력' in label:
                        detail['career'] = value
                    elif '학력' in label:
                        detail['education'] = value
                    elif '고용' in label or '근무' in label:
                        detail['employment_type'] = value
                    elif '연봉' in label or '급여' in label:
                        detail['salary'] = value
                    elif '위치' in label or '근무지' in label:
                        detail['location'] = value
            
            # 스킬 추출
            text_content = f"{detail.get('description', '')} {detail.get('requirements', '')}"
            if text_content.strip():
                extracted = extract_skills_from_text(text_content)
                detail['required_skills'] = extracted.get('hard_skills', [])
                detail['soft_skills'] = extracted.get('soft_skills', [])
            
            return detail
            
        except Exception as e:
            self.logger.error(f"상세 조회 실패 ({job_id}): {e}")
            return None
    
    def crawl_keyword(self, keyword: str, max_pages: int = None) -> List[Dict]:
        """키워드로 전체 크롤링 실행"""
        
        if max_pages is None:
            max_pages = self.config.max_pages_per_keyword
        
        self.logger.info(f"RocketPunch 크롤링 시작: {keyword}")
        
        # 검색 결과 수집
        jobs = self.search_jobs(keyword, max_pages)
        
        # 상세 정보 수집 (선택적)
        detailed_jobs = []
        
        for i, job in enumerate(jobs):
            try:
                # 상세 정보가 없는 경우에만 조회
                if not job.get('description'):
                    detail = self.get_job_detail(job['job_id'])
                    
                    if detail:
                        # 기존 정보와 병합
                        job.update({k: v for k, v in detail.items() if v})
                
                # 경력 수준 분류
                job['position_level'] = categorize_job_level(
                    job.get('title', ''),
                    job.get('career_text', '')
                )
                
                detailed_jobs.append(job)
                
                # 진행 상황 로깅
                if (i + 1) % 10 == 0:
                    self.logger.info(f"상세 수집 진행: {i + 1}/{len(jobs)}")
                    
            except Exception as e:
                self.logger.debug(f"상세 수집 실패 ({job.get('job_id')}): {e}")
                detailed_jobs.append(job)
        
        self.logger.info(f"RocketPunch 크롤링 완료: {len(detailed_jobs)}개 수집")
        
        return detailed_jobs
