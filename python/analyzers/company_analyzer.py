"""
회사 분석 모듈
채용공고 기반 회사 정보 분석 + 잡플래닛 평판 조회
"""

from typing import Dict, Any, Optional, List
from collections import Counter
import re
import json
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.database import db, Company, JobPosting
from utils.helpers import setup_logger, clean_text, RateLimiter
from config.settings import settings

# Playwright 사용 가능 여부
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Playwright Stealth (Cloudflare 우회)
try:
    from playwright_stealth import Stealth
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False

# nodriver (Cloudflare 우회 - 더 효과적)
try:
    import nodriver
    import asyncio
    NODRIVER_AVAILABLE = True
except ImportError:
    NODRIVER_AVAILABLE = False


class CompanyAnalyzer:
    """회사 분석기 - 채용공고 DB + 잡플래닛 기반"""

    def __init__(self, database=None):
        self.logger = setup_logger("analyzer.company")
        self.db = database if database else db
        self.rate_limiter = RateLimiter(5)  # 잡플래닛 차단 방지용 5초 딜레이
        self._browser = None  # 브라우저 인스턴스 재사용 (오류 시에만 재시작)
        self._logged_in = False  # 로그인 상태

        # 잡플래닛 로그인 정보 (환경변수에서)
        import os
        self._jobplanet_email = os.getenv('JOBPLANET_EMAIL')
        self._jobplanet_password = os.getenv('JOBPLANET_PASSWORD')

    def close(self):
        """브라우저 종료"""
        if self._browser:
            try:
                self._browser.stop()
                self.logger.info("브라우저 종료됨")
            except:
                pass
            self._browser = None
            self._logged_in = False

    async def _login_jobplanet(self, page):
        """잡플래닛 로그인"""
        if not self._jobplanet_email or not self._jobplanet_password:
            self.logger.warning("  → 잡플래닛 로그인 정보 없음 (.env 파일 확인)")
            return False

        if self._jobplanet_email == 'your_email@example.com':
            self.logger.warning("  → 잡플래닛 로그인 정보 미설정 (.env 파일에서 수정 필요)")
            return False

        try:
            self.logger.info("  → 잡플래닛 로그인 시도...")

            # 로그인 페이지로 이동
            await page.get('https://www.jobplanet.co.kr/users/sign_in')
            await asyncio.sleep(3)  # 초기 로드 대기

            # 로그인 폼이 나타날 때까지 대기 (최대 45초)
            form_loaded = False
            for wait_attempt in range(45):
                page_state_js = r'''
                    JSON.stringify({
                        url: window.location.href,
                        title: document.title,
                        hasEmailInput: !!document.querySelector('input[type="email"], input[name="user[email]"], #user_email, input[placeholder*="이메일"], input[placeholder*="email"]'),
                        hasPasswordInput: !!document.querySelector('input[type="password"]'),
                        hasSubmitBtn: !!document.querySelector('button[type="submit"]'),
                        hasCaptcha: !!document.querySelector('[class*="captcha"], [id*="captcha"], iframe[src*="captcha"], iframe[src*="recaptcha"], .g-recaptcha'),
                        hasCloudflare: !!document.querySelector('#challenge-form, .cf-browser-verification, [class*="cloudflare"]'),
                        bodyText: document.body?.innerText?.substring(0, 500) || ''
                    })
                '''
                page_state = await page.evaluate(page_state_js)

                # nodriver는 JSON을 자동 파싱할 수 있음 - 둘 다 처리
                state_data = None
                if isinstance(page_state, str):
                    try:
                        state_data = json.loads(page_state)
                    except Exception as e:
                        if wait_attempt == 0:
                            self.logger.warning(f"  → JSON 파싱 오류: {e}")
                elif isinstance(page_state, dict):
                    state_data = page_state

                # 디버깅: 10초마다 현재 상태 출력
                if wait_attempt % 10 == 9:
                    self.logger.info(f"  → 폼 상태 (attempt {wait_attempt+1}): type={type(page_state).__name__}, hasEmail={state_data.get('hasEmailInput') if state_data else 'N/A'}")

                if isinstance(state_data, dict):
                    if state_data.get('hasEmailInput') and state_data.get('hasPasswordInput'):
                        self.logger.info(f"  → 로그인 폼 로드됨 ({wait_attempt+1}초 대기)")
                        form_loaded = True
                        break
                    # Cloudflare나 캡챠 감지
                    if state_data.get('hasCaptcha'):
                        self.logger.warning("  → 캡챠 감지됨!")
                        try:
                            await page.save_screenshot('python/debug_login_captcha.png')
                        except:
                            pass
                        return False
                    if state_data.get('hasCloudflare'):
                        self.logger.warning("  → Cloudflare 차단 감지됨!")
                        return False

                if wait_attempt % 5 == 4:
                    self.logger.info(f"  → 로그인 폼 대기 중... ({wait_attempt+1}초)")
                await asyncio.sleep(1)

            # 디버깅용 스크린샷 저장
            try:
                await page.save_screenshot('python/debug_login_page.png')
                self.logger.info("  → 로그인 페이지 스크린샷 저장: python/debug_login_page.png")
            except Exception as ss_err:
                self.logger.warning(f"  → 스크린샷 저장 실패: {ss_err}")

            if not form_loaded:
                self.logger.warning("  → 로그인 폼이 45초 내에 로드되지 않음")
                self.logger.info(f"  → 최종 페이지 상태: {page_state}")
                # 마지막 시도: 폼이 로드되었을 수 있으므로 한번 더 확인
                if isinstance(page_state, str):
                    try:
                        final_state = json.loads(page_state)
                        if isinstance(final_state, dict) and final_state.get('hasEmailInput') and final_state.get('hasPasswordInput'):
                            self.logger.info("  → 마지막 확인에서 로그인 폼 발견됨, 계속 진행")
                            form_loaded = True
                    except:
                        pass

            if not form_loaded:
                return False

            # 이메일 입력 필드 찾기 (여러 번 시도)
            email_input = None
            for _ in range(5):
                email_input = await page.select('input[type="email"], input[name="user[email]"], #user_email')
                if email_input:
                    break
                await asyncio.sleep(1)

            if not email_input:
                self.logger.warning("  → 이메일 입력 필드를 찾을 수 없음")
                return False

            await email_input.clear_input()
            await email_input.send_keys(self._jobplanet_email)
            await asyncio.sleep(1)  # 입력 후 대기 (0.5초 → 1초)

            # 비밀번호 입력
            password_input = await page.select('input[type="password"], input[name="user[password]"], #user_password')
            if not password_input:
                self.logger.warning("  → 비밀번호 입력 필드를 찾을 수 없음")
                return False

            await password_input.clear_input()
            await password_input.send_keys(self._jobplanet_password)
            await asyncio.sleep(1)  # 입력 후 대기 (0.5초 → 1초)

            # 로그인 버튼 클릭 ("이메일로 로그인" 버튼)
            login_btn_js = r'''
                (() => {
                    // "이메일로 로그인" 버튼 찾기
                    const buttons = document.querySelectorAll('button[type="submit"]');
                    for (const btn of buttons) {
                        if (btn.innerText.includes('이메일로 로그인') || btn.className.includes('bg-green-500')) {
                            btn.click();
                            return 'clicked';
                        }
                    }
                    // fallback: 첫 번째 submit 버튼
                    const submitBtn = document.querySelector('button[type="submit"]');
                    if (submitBtn) {
                        submitBtn.click();
                        return 'clicked fallback';
                    }
                    return 'not found';
                })()
            '''
            click_result = await page.evaluate(login_btn_js)
            self.logger.info(f"  → 로그인 버튼: {click_result}")

            if click_result == 'not found':
                self.logger.warning("  → 로그인 버튼을 찾을 수 없음")
                # 디버깅용 스크린샷
                try:
                    await page.save_screenshot('python/debug_login_no_btn.png')
                except:
                    pass
                return False

            await asyncio.sleep(settings.jobplanet.login_delay)  # 로그인 처리 대기

            # 디버깅: 로그인 버튼 클릭 후 스크린샷
            try:
                await page.save_screenshot('python/debug_login_after_click.png')
                self.logger.info("  → 로그인 후 스크린샷 저장: python/debug_login_after_click.png")
            except Exception as ss_err:
                self.logger.warning(f"  → 스크린샷 저장 실패: {ss_err}")

            # 로그인 성공 여부 종합 확인
            login_check_js = r'''
                JSON.stringify((() => {
                    const result = {
                        url: window.location.href,
                        title: document.title,
                        hasSignIn: window.location.href.includes('sign_in'),
                        hasLoginError: false,
                        hasUserMenu: false,
                        hasLogoutBtn: false,
                        hasCaptcha: false,
                        hasCloudflare: false,
                        errorText: ''
                    };

                    // 캡챠 확인
                    if (document.querySelector('[class*="captcha"], [id*="captcha"], iframe[src*="captcha"], iframe[src*="recaptcha"], .g-recaptcha, #recaptcha')) {
                        result.hasCaptcha = true;
                    }

                    // Cloudflare 확인
                    if (document.querySelector('#challenge-form, .cf-browser-verification, [class*="cloudflare"]') ||
                        document.body?.innerText?.includes('Checking your browser') ||
                        document.body?.innerText?.includes('Cloudflare')) {
                        result.hasCloudflare = true;
                    }

                    // 로그인 오류 메시지 확인
                    const errorMsgs = document.querySelectorAll('.error, .alert-danger, [class*="error"], [class*="invalid"], .text-red-500, [class*="warning"]');
                    errorMsgs.forEach(el => {
                        const text = el.innerText.toLowerCase();
                        if (text.includes('비밀번호') || text.includes('이메일') || text.includes('password') || text.includes('email') || text.includes('실패') || text.includes('failed') || text.includes('일치') || text.includes('확인')) {
                            result.hasLoginError = true;
                            result.errorText = el.innerText.substring(0, 200);
                        }
                    });

                    // 사용자 메뉴/프로필 확인 (로그인 성공 시 나타남)
                    const userMenu = document.querySelector('.user-menu, .profile, [class*="user"], [class*="profile"], .gnb_user, .my_menu');
                    if (userMenu) result.hasUserMenu = true;

                    // 로그아웃 버튼 확인
                    const logoutLinks = document.querySelectorAll('a[href*="sign_out"], button[onclick*="logout"], a[href*="logout"]');
                    if (logoutLinks.length > 0) result.hasLogoutBtn = true;

                    // 페이지 내 "로그인" 텍스트가 있는 버튼 확인 (있으면 아직 로그인 안 됨)
                    const loginBtns = document.querySelectorAll('a, button');
                    loginBtns.forEach(btn => {
                        const text = btn.innerText.trim();
                        if (text === '로그인' || text === '로그인하기') {
                            result.hasLoginBtn = true;
                        }
                    });

                    return result;
                })())
            '''

            check_result = await page.evaluate(login_check_js)
            if isinstance(check_result, str):
                check = json.loads(check_result)

                # dict인 경우에만 처리
                if isinstance(check, dict):
                    self.logger.info(f"  → 로그인 확인: URL에 sign_in={check.get('hasSignIn')}, 오류메시지={check.get('hasLoginError')}, 사용자메뉴={check.get('hasUserMenu')}, 로그아웃버튼={check.get('hasLogoutBtn')}")
                    self.logger.info(f"  → 추가 확인: 캡챠={check.get('hasCaptcha')}, Cloudflare={check.get('hasCloudflare')}, 로그인버튼={check.get('hasLoginBtn')}")
                    if check.get('errorText'):
                        self.logger.warning(f"  → 에러 메시지: {check.get('errorText')}")

                    # 캡챠나 Cloudflare 발견 시
                    if check.get('hasCaptcha'):
                        self.logger.warning("  → 캡챠 감지됨! 수동 로그인이 필요할 수 있습니다.")
                        return False

                    if check.get('hasCloudflare'):
                        self.logger.warning("  → Cloudflare 차단 감지됨!")
                        return False

                    # 로그인 성공 조건: sign_in 페이지가 아니고, 오류 메시지 없고, (사용자 메뉴 또는 로그아웃 버튼 있음)
                    if not check.get('hasSignIn') and not check.get('hasLoginError'):
                        if check.get('hasUserMenu') or check.get('hasLogoutBtn'):
                            self.logger.info("  → 잡플래닛 로그인 성공! (사용자 메뉴/로그아웃 버튼 확인)")
                            self._logged_in = True
                            return True
                        elif not check.get('hasLoginBtn', False):
                            # 로그인 버튼이 없으면 로그인 된 것으로 간주
                            self.logger.info("  → 잡플래닛 로그인 성공! (로그인 버튼 없음)")
                            self._logged_in = True
                            return True

                    if check.get('hasLoginError'):
                        self.logger.warning(f"  → 잡플래닛 로그인 실패 (오류 메시지 감지): {check.get('errorText', '')}")
                        return False

                    if check.get('hasSignIn'):
                        self.logger.warning("  → 잡플래닛 로그인 실패 (여전히 로그인 페이지)")
                        return False

            # 추가 확인: 메인 페이지로 이동하여 로그인 상태 재확인
            await page.get('https://www.jobplanet.co.kr/')
            await asyncio.sleep(3)

            final_check_js = r'''
                (() => {
                    // 로그아웃 링크나 마이페이지 링크 있는지 확인
                    const links = document.querySelectorAll('a');
                    for (const link of links) {
                        const href = link.href || '';
                        const text = link.innerText || '';
                        if (href.includes('sign_out') || href.includes('logout') ||
                            text.includes('로그아웃') || text.includes('마이페이지') || text.includes('MY')) {
                            return 'logged_in';
                        }
                    }
                    // 로그인 버튼 있으면 로그인 안 됨
                    for (const link of links) {
                        const text = link.innerText.trim();
                        if (text === '로그인' || text === '로그인하기') {
                            return 'not_logged_in';
                        }
                    }
                    return 'unknown';
                })()
            '''
            final_result = await page.evaluate(final_check_js)
            self.logger.info(f"  → 최종 로그인 상태 확인: {final_result}")

            if final_result == 'logged_in':
                self.logger.info("  → 잡플래닛 로그인 성공! (최종 확인)")
                self._logged_in = True
                return True
            else:
                self.logger.warning(f"  → 잡플래닛 로그인 실패 (최종 상태: {final_result})")
                return False

        except Exception as e:
            self.logger.warning(f"  → 잡플래닛 로그인 오류: {e}")
            return False

    async def _scroll_to_bottom_incrementally(self, page, scroll_min=500, scroll_max=700, delay_min=0.3, delay_max=0.6):
        """페이지를 500~700px씩 점진적으로 스크롤하여 하단까지 이동"""
        import random

        max_iterations = 100  # 무한 루프 방지
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            # 현재 스크롤 위치와 전체 높이 확인
            scroll_info = await page.evaluate('''
                JSON.stringify({
                    scrollY: window.scrollY,
                    innerHeight: window.innerHeight,
                    scrollHeight: document.body.scrollHeight
                })
            ''')

            # scroll_info가 문자열이 아닌 경우 (ExceptionDetails 등) 종료
            if not isinstance(scroll_info, str):
                break

            try:
                scroll_data = json.loads(scroll_info)
                if not isinstance(scroll_data, dict):
                    break
            except:
                break

            current_y = scroll_data.get('scrollY', 0)
            inner_height = scroll_data.get('innerHeight', 0)
            scroll_height = scroll_data.get('scrollHeight', 0)

            # 하단 도달 확인 (여유 10px)
            if current_y + inner_height >= scroll_height - 10:
                break

            # 500~700px 사이 랜덤 스크롤
            scroll_amount = random.randint(scroll_min, scroll_max)
            new_y = current_y + scroll_amount

            await page.evaluate(f'window.scrollTo(0, {new_y})')

            # 0.3~0.6초 랜덤 대기
            delay = random.uniform(delay_min, delay_max)
            await asyncio.sleep(delay)

        # 최종 하단 도달 후 잠시 대기 (콘텐츠 로드)
        await asyncio.sleep(1)

    def analyze_company(self, company_name: str) -> Dict[str, Any]:
        """
        회사 종합 분석

        Args:
            company_name: 회사명

        Returns:
            회사 분석 결과
        """
        self.logger.info(f"Analyzing company: {company_name}")

        result = {
            'company_name': company_name,
            'analysis_date': datetime.now().isoformat(),
        }

        # 1. 채용공고 DB에서 회사 정보 집계
        job_based_info = self._analyze_from_job_postings(company_name)
        result['job_stats'] = job_based_info.get('job_stats', {})

        # 2. 잡플래닛에서 회사 정보 조회 (Playwright 사용)
        jobplanet_info = self._get_jobplanet_info(company_name)

        # 3. 기본 정보 병합 (잡플래닛 정보 우선, 없으면 채용공고 DB 정보 사용)
        db_basic = job_based_info.get('basic_info', {})
        result['basic_info'] = {
            'name': company_name,
            'industry': jobplanet_info.get('industry') or db_basic.get('industry'),
            'company_type': jobplanet_info.get('company_type'),
            'employee_count': jobplanet_info.get('employee_count'),
            'founded_date': jobplanet_info.get('founded_date'),
            'ceo': jobplanet_info.get('ceo'),
            'revenue': jobplanet_info.get('revenue'),
            'location': jobplanet_info.get('location') or db_basic.get('location'),
            'address': jobplanet_info.get('address'),
            'website': jobplanet_info.get('website'),
        }

        # 4. 평판 정보
        result['reputation'] = {
            'jobplanet_rating': jobplanet_info.get('jobplanet_rating'),
            'jobplanet_url': jobplanet_info.get('jobplanet_url'),
            'overall_sentiment': jobplanet_info.get('overall_sentiment', 'unknown'),
            'review_count': jobplanet_info.get('review_count'),
            'pros_keywords': jobplanet_info.get('pros_keywords', []),
            'cons_keywords': jobplanet_info.get('cons_keywords', []),
        }

        # 5. 연봉 정보
        result['salary_info'] = {
            'average': jobplanet_info.get('salary_info'),
            'by_position': jobplanet_info.get('salary_by_position', []),
        }

        # 6. 면접 정보
        result['interview_info'] = {
            'count': jobplanet_info.get('interview_count'),
            'difficulty': jobplanet_info.get('interview_difficulty'),
            'experience': jobplanet_info.get('interview_experience'),
            'success_rate': jobplanet_info.get('interview_success_rate'),
        }

        # 7. 복지 정보
        result['benefits'] = jobplanet_info.get('benefits', [])

        # 8. 잡플래닛 채용공고 수
        result['jobplanet_job_count'] = jobplanet_info.get('active_job_count')

        # 9. 수집된 리뷰 목록
        result['reviews'] = jobplanet_info.get('reviews', [])
        result['reviews_collected'] = jobplanet_info.get('reviews_collected', 0)

        # 9-1. 수집된 면접 후기 목록
        result['interviews'] = jobplanet_info.get('interviews', [])
        result['interviews_collected'] = jobplanet_info.get('interviews_collected', 0)

        # 9-2. 수집된 복지 후기 목록
        result['welfare_reviews'] = jobplanet_info.get('welfare_reviews', [])
        result['welfare_reviews_collected'] = jobplanet_info.get('welfare_reviews_count', 0)

        # 10. 만족도 점수
        result['satisfaction_scores'] = jobplanet_info.get('satisfaction_scores', {})

        # 11. raw_data (디버깅용 HTML/텍스트)
        result['raw_data'] = jobplanet_info.get('raw_data', {})

        # 12. 종합 평가
        result['summary'] = self._generate_summary(result)

        # DB에 저장
        self._save_to_db(result)

        return result

    def _analyze_from_job_postings(self, company_name: str) -> Dict[str, Any]:
        """채용공고 DB에서 회사 정보 분석"""
        session = self.db.get_session()

        try:
            # 해당 회사의 채용공고 조회
            jobs = session.query(JobPosting).filter(
                JobPosting.company_name.ilike(f"%{company_name}%")
            ).all()

            if not jobs:
                return {
                    'basic_info': {'name': company_name},
                    'job_stats': {'total_postings': 0}
                }

            # 기본 정보 추출 (첫 번째 공고에서)
            first_job = jobs[0]
            basic_info = {
                'name': company_name,
                'industry': getattr(first_job, 'company_industry', None),
                'location': None,
                'website': None,
            }

            # 지역 정보 집계
            locations = [job.location for job in jobs if job.location]
            if locations:
                location_counts = Counter(locations)
                basic_info['location'] = location_counts.most_common(1)[0][0]

            # 채용 통계
            skills = []
            job_categories = []
            experience_levels = []

            for job in jobs:
                if job.required_skills:
                    if isinstance(job.required_skills, list):
                        for skill in job.required_skills:
                            # skill이 dict인 경우 (예: {"name": "Python"}) 이름만 추출
                            if isinstance(skill, dict):
                                skill_name = skill.get('name') or skill.get('skill') or str(skill)
                                skills.append(skill_name)
                            elif isinstance(skill, str):
                                skills.append(skill)
                            # 그 외의 경우 문자열로 변환
                            else:
                                skills.append(str(skill))
                    elif isinstance(job.required_skills, str):
                        skills.append(job.required_skills)
                if job.job_category:
                    job_categories.append(job.job_category)
                if job.position_level:
                    experience_levels.append(job.position_level)

            job_stats = {
                'total_postings': len(jobs),
                'top_skills': [{'skill': s, 'count': c} for s, c in Counter(skills).most_common(10)],
                'job_categories': [{'category': c, 'count': cnt} for c, cnt in Counter(job_categories).most_common(5)],
                'experience_levels': [{'level': l, 'count': c} for l, c in Counter(experience_levels).most_common()],
                'sources': [{'site': s, 'count': c} for s, c in Counter(job.source_site for job in jobs).most_common()],
            }

            return {
                'basic_info': basic_info,
                'job_stats': job_stats
            }

        finally:
            session.close()

    def _normalize_company_name(self, name: str) -> str:
        """회사명 정규화 (띄어쓰기, 특수문자 제거)"""
        if not name:
            return ""
        # (주), (유), 주식회사 등 제거
        normalized = re.sub(r'\(주\)|\(유\)|주식회사|㈜|\s+', '', name)
        # 소문자로 변환
        return normalized.lower().strip()

    def _extract_core_name(self, name: str) -> str:
        """회사명에서 핵심 이름만 추출 (법인 표시, 접미사 제거)"""
        if not name:
            return ""

        # 1. 법인 표시 제거
        core = re.sub(r'\(주\)|\(유\)|㈜|주식회사|\s+', '', name)

        # 2. 일반적인 접미사 제거
        suffixes = ['그룹', '홀딩스', '코리아', '인터내셔널', '글로벌',
                    '엔터프라이즈', '테크놀로지', '테크', '솔루션', '솔루션즈',
                    '네트웍스', '네트워크', '시스템', '시스템즈', '소프트',
                    '컴퍼니', '파트너스', '벤처스', '랩', '랩스', '스튜디오']

        for suffix in suffixes:
            if core.endswith(suffix):
                core = core[:-len(suffix)]

        return core.strip()

    def _extract_korean_name(self, name: str) -> str:
        """회사명에서 한글 부분만 추출 (검색용)"""
        if not name:
            return ""

        # 1. 괄호 안의 영문/영어 이름 제거: "라프텔(Laftel)" -> "라프텔"
        #    또는 "(주)회사명" 형태에서 회사명만 추출
        cleaned = re.sub(r'\([A-Za-z0-9\s\.\-\_]+\)', '', name)  # 영문 괄호 제거
        cleaned = re.sub(r'\(주\)|\(유\)|㈜|주식회사', '', cleaned)  # 법인 표시 제거

        # 2. 영문만 있는 경우 원본 사용
        if not cleaned.strip():
            cleaned = name

        # 3. 앞뒤 공백 및 특수문자 정리
        cleaned = cleaned.strip()

        return cleaned

    def _get_jobplanet_info(self, company_name: str) -> Dict[str, Any]:
        """잡플래닛에서 회사 정보 조회 (nodriver 사용) - Cloudflare 우회"""
        info = {
            # 기본 정보
            'jobplanet_rating': None,
            'jobplanet_url': None,
            'industry': None,
            'company_type': None,
            'employee_count': None,
            'founded_date': None,
            'location': None,
            'ceo': None,
            'revenue': None,
            'address': None,
            'website': None,
            'overall_sentiment': 'unknown',
            # 리뷰 정보
            'review_count': None,
            'review_summary': None,
            'pros_keywords': [],
            'cons_keywords': [],
            # 연봉 정보
            'salary_info': None,
            'salary_by_position': [],
            # 면접 정보
            'interview_count': None,
            'interview_difficulty': None,
            'interview_experience': None,
            'interview_success_rate': None,
            # 복지 정보
            'benefits': [],
            # 채용공고 정보
            'active_job_count': None,
        }

        if not NODRIVER_AVAILABLE:
            self.logger.warning("nodriver not available, skipping Jobplanet")
            return info

        try:
            self.rate_limiter.wait()
            # async 함수 실행
            result = asyncio.run(self._get_jobplanet_info_async(company_name, info))
            return result
        except Exception as e:
            self.logger.error(f"Jobplanet search failed: {e}")
            return info

    async def _get_jobplanet_info_async(self, company_name: str, info: Dict[str, Any]) -> Dict[str, Any]:
        """잡플래닛에서 회사 정보 조회 (async - nodriver 사용)"""
        import time as sync_time
        import json
        from urllib.parse import quote

        # 한글 회사명만 추출하여 검색
        search_name = self._extract_korean_name(company_name)
        # 기업 전용 검색 URL 사용
        encoded_name = quote(search_name)
        search_url = f"https://www.jobplanet.co.kr/search/companies?query={encoded_name}"
        normalized_search = self._normalize_company_name(company_name)

        try:
            # 브라우저 재사용 (없거나 오류로 닫힌 경우에만 새로 시작)
            if not self._browser:
                self._browser = await nodriver.start(headless=False)
                self.logger.info("  → 새 브라우저 시작")
                self._logged_in = False

                # 잡플래닛 로그인
                temp_page = await self._browser.get('about:blank')
                await self._login_jobplanet(temp_page)
                await asyncio.sleep(1)

            # 1. 검색 페이지로 이동
            self.logger.info(f"  → 잡플래닛 검색: {search_name}" + (f" (원본: {company_name})" if search_name != company_name else ""))
            page = await self._browser.get(search_url)

            # 페이지 로드 대기
            await asyncio.sleep(3)

            # 페이지 타이틀 확인 (Cloudflare 차단 여부)
            title = await page.evaluate('document.title')
            if 'blocked' in title.lower() or 'cloudflare' in title.lower() or 'attention' in title.lower():
                self.logger.warning(f"Cloudflare 차단됨: {title}")
                return info

            # 스크롤하여 검색 결과 로드
            await page.evaluate('window.scrollTo(0, 600)')
            await asyncio.sleep(2)

            # 2. 검색 결과에서 회사 찾기
            # h4 태그에서 회사명 추출 (JSON.stringify로 직렬화)
            js_code = r'''
                JSON.stringify((() => {
                    const results = [];

                    // h4 태그들 찾기 - 회사명이 여기에 있음
                    const h4Elements = document.querySelectorAll('h4');

                    for (const h4 of h4Elements) {
                        const name = h4.innerText.trim();
                        if (!name || name.length < 2) continue;

                        // 가장 가까운 a[href*="/companies/"] 링크 찾기
                        let parent = h4.parentElement;
                        let link = null;
                        for (let i = 0; i < 10 && parent; i++) {
                            link = parent.querySelector('a[href*="/companies/"]') ||
                                   parent.closest('a[href*="/companies/"]');
                            if (link) break;
                            parent = parent.parentElement;
                        }

                        if (!link) {
                            const grandParent = h4.closest('div.relative');
                            if (grandParent) {
                                const parentA = grandParent.closest('a[href*="/companies/"]');
                                if (parentA) link = parentA;
                            }
                        }

                        if (!link) continue;

                        const href = link.getAttribute('href') || '';
                        const match = href.match(/\/companies\/(\d+)/);
                        if (!match) continue;

                        // 회사 정보가 담긴 컨테이너 찾기
                        let container = h4.closest('div.relative') || h4.parentElement?.parentElement?.parentElement;
                        const cardText = container ? container.innerText : '';

                        // 평점
                        let rating = null;
                        const ratingMatch = cardText.match(/(\d\.\d)/);
                        if (ratingMatch) rating = parseFloat(ratingMatch[1]);

                        // 산업/지역
                        let industry = null;
                        let location = null;
                        const infoMatch = cardText.match(/([A-Za-z가-힣\/]+)\s*[∙·]\s*([가-힣]+)/);
                        if (infoMatch) {
                            industry = infoMatch[1];
                            location = infoMatch[2];
                        }

                        // 설립연도
                        const yearMatch = cardText.match(/\((\d{4})\)/);
                        const foundedYear = yearMatch ? yearMatch[1] : null;

                        // 사원수
                        const empMatch = cardText.match(/([\d,]+)명/);
                        const employeeCount = empMatch ? empMatch[1] : null;

                        results.push({
                            id: match[1],
                            name: name,
                            rating: rating,
                            industry: industry,
                            location: location,
                            foundedYear: foundedYear,
                            employeeCount: employeeCount
                        });
                    }

                    // 중복 제거
                    const seen = new Set();
                    return results.filter(r => {
                        if (seen.has(r.id)) return false;
                        seen.add(r.id);
                        return true;
                    });
                })())
            '''
            result_str = await page.evaluate(js_code)

            # JSON 파싱
            company_data = []
            if isinstance(result_str, str):
                try:
                    parsed = json.loads(result_str)
                    # list인 경우에만 할당
                    if isinstance(parsed, list):
                        company_data = parsed
                except:
                    pass

            # 3. 검색 결과에서 회사 매칭 (정확도 순)
            matched_company = None
            search_core = self._extract_core_name(company_name)
            candidates = []

            for company in company_data:
                if not company.get('id'):
                    continue
                card_name = company.get('name', '')
                card_core = self._extract_core_name(card_name)

                # 매칭 점수 계산
                score = 0
                if search_core == card_core:
                    score = 100  # 정확히 일치
                elif card_core == search_core:
                    score = 100
                elif len(search_core) >= 2 and card_core.startswith(search_core):
                    score = 80  # 검색어로 시작 (카카오 → 카카오뱅크)
                elif len(search_core) >= 2 and search_core in card_core:
                    score = 50  # 검색어 포함
                elif len(card_core) >= 2 and card_core in search_core:
                    score = 30  # 역방향 포함

                if score > 0:
                    # 이름 길이가 짧을수록 보너스 (원본에 가까움)
                    length_bonus = max(0, 20 - len(card_core))
                    score += length_bonus
                    candidates.append((score, company, card_name, card_core))

            # 점수 높은 순으로 정렬, 동점이면 이름 짧은 것 우선
            if candidates:
                candidates.sort(key=lambda x: (-x[0], len(x[3])))
                best = candidates[0]
                matched_company = best[1]
                self.logger.info(f"  → 회사 발견: {best[2]} (핵심명: {best[3]}, 점수: {best[0]}, ID: {best[1]['id']})")
                if len(candidates) > 1:
                    self.logger.info(f"    → 다른 후보: {[(c[2], c[0]) for c in candidates[1:3]]}")

            if not matched_company:
                self.logger.warning(f"  → 잡플래닛에서 찾을 수 없음: {company_name} (핵심명: {search_core})")
                return info

            # 4. 검색 결과에서 기본 정보 추출
            company_id = matched_company['id']
            info['jobplanet_rating'] = matched_company.get('rating')
            info['industry'] = matched_company.get('industry')
            info['location'] = matched_company.get('location')
            info['founded_date'] = matched_company.get('foundedYear')
            info['employee_count'] = matched_company.get('employeeCount')

            base_url = f"https://www.jobplanet.co.kr/companies/{company_id}"
            info['jobplanet_url'] = base_url

            # 4-1. 기본 정보 즉시 저장 (companies 테이블) → db_company_id 획득
            try:
                basic_company_data = {
                    'name': company_name,
                    'industry': info.get('industry'),
                    'location': info.get('location'),
                    'jobplanet_rating': info.get('jobplanet_rating'),
                    'jobplanet_url': info.get('jobplanet_url'),
                }
                self.db.add_company(basic_company_data)
                db_company_id = self.db.get_company_id_by_name(company_name)
                info['db_company_id'] = db_company_id
                self.logger.info(f"  → 기본 정보 DB 저장 완료 (company_id: {db_company_id})")
            except Exception as e:
                self.logger.warning(f"  → 기본 정보 DB 저장 실패: {e}")
                info['db_company_id'] = None

            # 5. 회사 상세 페이지 방문하여 추가 정보 수집
            await asyncio.sleep(1)
            company_name_encoded = matched_company.get('name', '')
            await page.get(f"{base_url}/reviews/{company_name_encoded}")
            await asyncio.sleep(3)

            # 팝업 닫기 (여러 방법 시도)
            try:
                close_popup_js = r'''
                    (() => {
                        // 1. i.jp-x 클래스 버튼
                        let closeBtn = document.querySelector('i.jp-x');
                        if (closeBtn) {
                            closeBtn.click();
                            return 'clicked jp-x icon';
                        }

                        // 2. SVG X 버튼 또는 부모 버튼
                        const xIcons = document.querySelectorAll('svg, i');
                        for (const icon of xIcons) {
                            const parent = icon.closest('button') || icon.parentElement;
                            if (parent && (
                                icon.className.includes('x') ||
                                icon.className.includes('close') ||
                                parent.className.includes('close') ||
                                parent.getAttribute('aria-label')?.includes('닫기')
                            )) {
                                parent.click();
                                return 'clicked parent of icon';
                            }
                        }

                        // 3. 모달 외부 영역 클릭 (backdrop)
                        const backdrop = document.querySelector('[class*="backdrop"], [class*="overlay"], [class*="modal-bg"]');
                        if (backdrop) {
                            backdrop.click();
                            return 'clicked backdrop';
                        }

                        // 4. ESC 키 시뮬레이션
                        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', keyCode: 27 }));

                        // 5. 모달 내 X 문자가 있는 버튼
                        const buttons = document.querySelectorAll('button, [role="button"]');
                        for (const btn of buttons) {
                            const text = btn.innerText.trim();
                            if (text === '×' || text === 'X' || text === '✕') {
                                btn.click();
                                return 'clicked X button';
                            }
                        }

                        return 'no popup found';
                    })()
                '''
                result = await page.evaluate(close_popup_js)
                self.logger.info(f"  → 팝업 처리: {result}")
                await asyncio.sleep(2)

                # 추가로 팝업이 여전히 있는지 확인하고 다시 시도
                check_popup_js = r'''
                    (() => {
                        const modal = document.querySelector('[class*="modal"]:not([style*="display: none"]), [class*="popup"]:not([style*="display: none"])');
                        return modal ? 'popup still exists' : 'no popup';
                    })()
                '''
                check_result = await page.evaluate(check_popup_js)
                if 'exists' in check_result:
                    # 한번 더 ESC 시도
                    await page.evaluate('document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", keyCode: 27 }))')
                    await asyncio.sleep(1)

            except Exception as e:
                self.logger.debug(f"Popup close error: {e}")

            # 각 탭 URL로 직접 이동하여 정보 수집
            # URL 패턴: /companies/{id}/reviews, /salaries, /interviews, /benefits, /job_postings, /landing, /premium_reviews
            tabs_to_crawl = [
                ('리뷰', 'reviews', self._extract_reviews_data),
                ('연봉', 'salaries', self._extract_salary_data),
                ('면접', 'interviews', self._extract_interview_data),
                ('복지', 'benefits', self._extract_benefits_data),
                ('채용', 'job_postings', self._extract_jobs_data),
                ('기업정보', 'landing', self._extract_landing_data),
                ('프리미엄리뷰', 'premium_reviews', self._extract_premium_reviews_data),
            ]

            for tab_name, tab_path, extractor in tabs_to_crawl:
                try:
                    # URL로 직접 이동 (페이지 로드 완료까지 대기)
                    tab_url = f"{base_url}/{tab_path}"
                    self.logger.info(f"  → {tab_name} 페이지 이동: {tab_url}")
                    await page.get(tab_url)
                    await asyncio.sleep(3)  # 페이지 로드 후 동적 콘텐츠 대기 (3초)

                    # 팝업 닫기 (모든 페이지에서 항상 실행)
                    await self._close_popup(page)

                    # 스크롤하여 콘텐츠 로드
                    await page.evaluate('window.scrollTo(0, 400)')
                    await asyncio.sleep(2)  # 스크롤 후 추가 대기 (2초)

                    # 추가 스크롤로 더 많은 콘텐츠 로드
                    await page.evaluate('window.scrollTo(0, 800)')
                    await asyncio.sleep(1)

                    # 탭별 HTML 전문 및 텍스트 수집 (디버깅용)
                    try:
                        tab_html = await page.evaluate('document.documentElement.outerHTML')
                        tab_text = await page.evaluate('document.body.innerText')

                        # raw_data 딕셔너리 초기화
                        if 'raw_data' not in info:
                            info['raw_data'] = {}

                        # 문자열인 경우에만 저장 (ExceptionDetails 등 오류 객체 제외)
                        if isinstance(tab_html, str):
                            info['raw_data'][f'{tab_name}_html'] = tab_html
                        if isinstance(tab_text, str):
                            info['raw_data'][f'{tab_name}_text'] = tab_text
                            self.logger.info(f"  → {tab_name} 페이지 수집: HTML {len(tab_html) if isinstance(tab_html, str) else 0}자, 텍스트 {len(tab_text)}자")
                        else:
                            self.logger.warning(f"  → {tab_name} 텍스트 수집 실패: {type(tab_text).__name__}")
                    except Exception as e:
                        self.logger.debug(f"Raw data collection error for {tab_name}: {e}")

                    # 탭별 데이터 추출
                    await extractor(page, info)

                    # 탭별 데이터 즉시 DB 저장
                    db_company_id = info.get('db_company_id')
                    try:
                        if tab_name == '리뷰' and info.get('reviews'):
                            count = self.db.add_company_reviews(
                                company_name, info['reviews'], db_company_id
                            )
                            self.logger.info(f"  → 리뷰 DB 저장: {count}개")

                        elif tab_name == '면접' and info.get('interviews'):
                            count = self.db.add_company_interviews(
                                company_name, info['interviews'], db_company_id
                            )
                            self.logger.info(f"  → 면접 후기 DB 저장: {count}개")

                        elif tab_name == '복지' and info.get('welfare_reviews'):
                            count = self.db.add_company_benefits(
                                company_name, info['welfare_reviews'], db_company_id
                            )
                            self.logger.info(f"  → 복지 후기 DB 저장: {count}개")

                    except Exception as save_err:
                        self.logger.warning(f"  → {tab_name} DB 저장 실패: {save_err}")

                except Exception as e:
                    self.logger.warning(f"Tab {tab_name} crawl error: {e}")

            # 6. 평점 기반 sentiment 설정
            if info['jobplanet_rating']:
                rating = info['jobplanet_rating']
                if rating >= 4.0:
                    info['overall_sentiment'] = 'very_positive'
                elif rating >= 3.5:
                    info['overall_sentiment'] = 'positive'
                elif rating >= 3.0:
                    info['overall_sentiment'] = 'neutral'
                elif rating >= 2.5:
                    info['overall_sentiment'] = 'negative'
                else:
                    info['overall_sentiment'] = 'very_negative'

            self.logger.info(f"  → 잡플래닛 정보 수집 완료: 평점 {info.get('jobplanet_rating')}, 리뷰 {info.get('review_count')}건")

        except Exception as e:
            self.logger.warning(f"Jobplanet crawl failed: {e}")
            # 오류 시 브라우저 재시작 필요할 수 있음
            if self._browser:
                try:
                    self._browser.stop()
                except:
                    pass
                self._browser = None

        return info

    async def _close_popup(self, page):
        """팝업 닫기 (괜찮아요 버튼 또는 X 버튼)"""
        popup_js = r'''
            (() => {
                // 1. "괜찮아요" 버튼 (팔로우 팝업)
                const noThanksBtn = document.querySelector('#btn-no-thanks, button[onclick*="noThanks"]');
                if (noThanksBtn) { noThanksBtn.click(); return 'clicked noThanks'; }

                // 2. jp-x 아이콘
                const jpX = document.querySelector('i.jp-x');
                if (jpX) { jpX.click(); return 'clicked jp-x'; }

                // 3. 모달 닫기 버튼
                const closeBtn = document.querySelector('.modal button[class*="close"], [class*="modal"] [class*="close"]');
                if (closeBtn) { closeBtn.click(); return 'clicked modal close'; }

                // 4. ESC 키
                document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', keyCode: 27 }));
                return 'sent ESC';
            })()
        '''
        try:
            result = await page.evaluate(popup_js)
            if 'clicked' in result:
                await asyncio.sleep(1)
                return True
        except:
            pass
        return False

    async def _extract_reviews_data(self, page, info: Dict[str, Any]):
        """리뷰 탭에서 데이터 추출 (가이드 기반)"""
        try:
            # 즉시 리뷰 섹션 존재 확인 (디버깅)
            immediate_check_js = '''
                JSON.stringify({
                    viewReviewsList: !!document.getElementById('viewReviewsList'),
                    viewReviewsListChildren: document.getElementById('viewReviewsList')?.children?.length || 0,
                    reviewSections: document.querySelectorAll('section[id^="review_"]').length,
                    firstReviewId: document.querySelector('section[id^="review_"]')?.id || 'none'
                })
            '''
            immediate_result = await page.evaluate(immediate_check_js)
            self.logger.info(f"    → 리뷰 탭 진입 시 상태: {immediate_result}")

            reviews_data = {
                'review_count': None,
                'recommend_rate': None,     # 기업 추천율 (%)
                'ceo_support_rate': None,   # CEO 지지율 (%)
                'growth_potential': None,   # 성장 가능성 (%)
                'yearly_trends': {},  # 연도별 트렌드
                'pros_keywords': [],  # 장점 키워드
                'cons_keywords': [],  # 단점 키워드
                'satisfaction_scores': {},  # 만족도 점수
                'job_satisfaction': {},  # 직군별 만족도
                'reviews': [],  # 개별 리뷰 목록
            }

            # 팝업 닫기
            await self._close_popup(page)

            # 1. 리뷰 수 및 평점 추출
            stats_js = r'''
                JSON.stringify((() => {
                    const data = {
                        review_count: null,
                        rating: null,
                        recommend_rate: null,    // 기업 추천율
                        ceo_support_rate: null,  // CEO 지지율
                        growth_potential: null   // 성장 가능성
                    };
                    const bodyText = document.body.innerText;

                    // 리뷰 수: "전체 리뷰 통계 (1300명)"
                    const countMatch = bodyText.match(/리뷰[^\d]*통계[^\d]*\((\d+)/);
                    if (countMatch) data.review_count = parseInt(countMatch[1]);

                    // 평점
                    const ratingMatch = bodyText.match(/(\d\.\d)\s*\/\s*5\.0|평점[^\d]*(\d\.\d)/);
                    if (ratingMatch) data.rating = parseFloat(ratingMatch[1] || ratingMatch[2]);

                    // 기업 추천율, CEO 지지율, 성장 가능성 (파이 차트에서 추출)
                    const pieSets = document.querySelectorAll('.rate_pie_set');
                    pieSets.forEach(set => {
                        const labelEl = set.querySelector('.rate_label');
                        const valueEl = set.querySelector('.txt_point');
                        if (labelEl && valueEl) {
                            const label = labelEl.innerText.trim();
                            const value = valueEl.innerText.trim().replace('%', '');
                            if (label.includes('추천')) data.recommend_rate = parseInt(value);
                            else if (label.includes('CEO') || label.includes('지지')) data.ceo_support_rate = parseInt(value);
                            else if (label.includes('성장')) data.growth_potential = parseInt(value);
                        }
                    });

                    return data;
                })())
            '''
            stats_str = await page.evaluate(stats_js)
            if isinstance(stats_str, str):
                stats = json.loads(stats_str)
                # dict인 경우에만 처리 (list나 다른 타입은 건너뜀)
                if isinstance(stats, dict):
                    if stats.get('review_count'):
                        reviews_data['review_count'] = stats['review_count']
                        info['review_count'] = stats['review_count']
                    if stats.get('recommend_rate') is not None:
                        reviews_data['recommend_rate'] = stats['recommend_rate']
                        info['recommend_rate'] = stats['recommend_rate']
                    if stats.get('ceo_support_rate') is not None:
                        reviews_data['ceo_support_rate'] = stats['ceo_support_rate']
                        info['ceo_support_rate'] = stats['ceo_support_rate']
                    if stats.get('growth_potential') is not None:
                        reviews_data['growth_potential'] = stats['growth_potential']
                        info['growth_potential'] = stats['growth_potential']
                    self.logger.info(f"    → 기업 추천율: {stats.get('recommend_rate')}%, CEO 지지율: {stats.get('ceo_support_rate')}%, 성장 가능성: {stats.get('growth_potential')}%")
                else:
                    self.logger.debug(f"    → 리뷰 stats가 dict가 아님: {type(stats).__name__}")

            # 2. "연도별 트렌드 보기" 버튼 클릭
            trend_btn_js = r'''
                (() => {
                    const buttons = document.querySelectorAll('button');
                    for (const b of buttons) {
                        if (b.innerText.includes('연도별 트렌드')) {
                            b.click();
                            return true;
                        }
                    }
                    return false;
                })()
            '''
            clicked = await page.evaluate(trend_btn_js)
            if clicked:
                await asyncio.sleep(2)
                self.logger.info("    → 연도별 트렌드 버튼 클릭")

            # 3. 연도별 통계 수집 (전체, 2026, 2025, ...)
            # 먼저 연도 목록 가져오기
            years_list_js = r'''
                JSON.stringify((() => {
                    const years = [];
                    const yearLinks = document.querySelectorAll('a[href*="reviews"]');
                    for (const a of yearLinks) {
                        const text = a.innerText.trim();
                        if (text === '전체' || /^20\d{2}$/.test(text)) {
                            years.push(text);
                        }
                    }
                    return years;
                })())
            '''
            try:
                years_str = await page.evaluate(years_list_js)
                parsed_years = json.loads(years_str) if isinstance(years_str, str) else []
                # list인 경우에만 사용
                years_list = parsed_years if isinstance(parsed_years, list) else []

                if years_list:
                    self.logger.info(f"    → 연도 목록: {years_list[:6]}")

                    # 각 연도별로 클릭하여 만족도 통계 수집
                    for year_text in years_list[:10]:  # 최대 10개 연도
                        try:
                            # 해당 연도 링크 클릭
                            click_year_js = f'''
                                (() => {{
                                    const yearLinks = document.querySelectorAll('a[href*="reviews"]');
                                    for (const a of yearLinks) {{
                                        if (a.innerText.trim() === '{year_text}') {{
                                            a.click();
                                            return true;
                                        }}
                                    }}
                                    return false;
                                }})()
                            '''
                            clicked = await page.evaluate(click_year_js)
                            if not clicked:
                                continue

                            await asyncio.sleep(1.5)  # 데이터 로드 대기

                            # 현재 연도의 만족도 통계 추출 (점수 + 비율)
                            stats_js = r'''
                                JSON.stringify((() => {
                                    const stats = {};

                                    // 1. 만족도 점수 (5점 만점)
                                    const categories = ['총 만족도', '승진 기회', '복지 및 급여', '워라밸', '사내문화', '경영진'];
                                    const bodyText = document.body.innerText;
                                    for (const cat of categories) {
                                        const regex = new RegExp(cat + '[\\s\\S]{0,30}?(\\d\\.\\d)');
                                        const match = bodyText.match(regex);
                                        if (match) stats[cat] = parseFloat(match[1]);
                                    }

                                    // 2. 파이 차트 비율 (기업 추천율, CEO 지지율, 성장 가능성)
                                    const pieSets = document.querySelectorAll('.rate_pie_set');
                                    pieSets.forEach(set => {
                                        const labelEl = set.querySelector('.rate_label');
                                        const valueEl = set.querySelector('.txt_point');
                                        if (labelEl && valueEl) {
                                            const label = labelEl.innerText.trim();
                                            const value = valueEl.innerText.trim().replace('%', '');
                                            if (label.includes('추천')) stats['기업 추천율'] = parseInt(value);
                                            else if (label.includes('CEO') || label.includes('지지')) stats['CEO 지지율'] = parseInt(value);
                                            else if (label.includes('성장')) stats['성장 가능성'] = parseInt(value);
                                        }
                                    });

                                    return stats;
                                })())
                            '''
                            stats_str = await page.evaluate(stats_js)
                            if isinstance(stats_str, str):
                                year_stats = json.loads(stats_str)
                                # dict인 경우에만 처리
                                if isinstance(year_stats, dict) and year_stats:
                                    reviews_data['yearly_trends'][year_text] = year_stats
                                    self.logger.info(f"      → {year_text}: 총 만족도 {year_stats.get('총 만족도', '-')}")
                        except Exception as e:
                            self.logger.debug(f"Year {year_text} stats error: {e}")
                            continue

                    # 전체 만족도를 기본 satisfaction_scores로 설정
                    if '전체' in reviews_data['yearly_trends']:
                        reviews_data['satisfaction_scores'] = reviews_data['yearly_trends']['전체']
                        info['satisfaction_scores'] = reviews_data['yearly_trends']['전체']
                    elif reviews_data['yearly_trends']:
                        # 전체가 없으면 첫 번째 연도 데이터 사용
                        first_year = list(reviews_data['yearly_trends'].keys())[0]
                        reviews_data['satisfaction_scores'] = reviews_data['yearly_trends'][first_year]
                        info['satisfaction_scores'] = reviews_data['yearly_trends'][first_year]

                    info['yearly_trends'] = reviews_data['yearly_trends']
                    self.logger.info(f"    → 연도별 트렌드: {len(reviews_data['yearly_trends'])}개 연도 수집")
            except Exception as e:
                self.logger.debug(f"Yearly trends error: {e}")

            # 4. 스크롤하여 키워드 섹션 로드
            await page.evaluate('window.scrollTo(0, 1000)')
            await asyncio.sleep(2)

            # 5. 장점 키워드 수집 (페이지네이션 포함)
            pros_keywords = await self._collect_keywords(page, 'pros')
            reviews_data['pros_keywords'] = pros_keywords
            info['pros_keywords'] = pros_keywords
            self.logger.info(f"    → 장점 키워드: {len(pros_keywords)}개")

            # 6. 단점 키워드 수집 (탭 전환 후)
            cons_tab_js = r'''
                (() => {
                    const label = document.querySelector('label[for="reviewKeywordOption2"]');
                    if (label) { label.click(); return true; }
                    return false;
                })()
            '''
            await page.evaluate(cons_tab_js)
            await asyncio.sleep(1)

            cons_keywords = await self._collect_keywords(page, 'cons')
            reviews_data['cons_keywords'] = cons_keywords
            info['cons_keywords'] = cons_keywords
            self.logger.info(f"    → 단점 키워드: {len(cons_keywords)}개")

            # 7. 직군별 만족도 수집
            job_satisfaction_js = r'''
                JSON.stringify((() => {
                    const data = [];
                    // highcharts x축 라벨과 데이터 라벨 매칭
                    const xLabels = document.querySelectorAll('.highcharts-xaxis-labels text');
                    const dataLabels = document.querySelectorAll('.highcharts-data-labels text');

                    xLabels.forEach((label, i) => {
                        const job = label.textContent.trim();
                        const scoreEl = dataLabels[i];
                        if (job && scoreEl) {
                            const score = parseFloat(scoreEl.textContent);
                            if (!isNaN(score)) {
                                data.push({ job: job, score: score });
                            }
                        }
                    });
                    return data;
                })())
            '''
            try:
                job_sat_str = await page.evaluate(job_satisfaction_js)
                if isinstance(job_sat_str, str):
                    job_sat = json.loads(job_sat_str)
                    # dict인 경우에만 처리
                    if isinstance(job_sat, dict) and job_sat:
                        reviews_data['job_satisfaction'] = job_sat
                        info['job_satisfaction'] = job_sat
                        self.logger.info(f"    → 직군별 만족도: {len(job_sat)}개 직군")
            except:
                pass

            # 8. 맞춤 기업 찾기 (차트 스크린샷 저장)
            await self._capture_company_comparison_charts(page, info)

            # 9. 리뷰 페이지로 다시 이동 (다른 탭 클릭으로 인해 상태 변경될 수 있음)
            try:
                current_url_result = await page.evaluate('window.location.href')
                current_url = current_url_result if isinstance(current_url_result, str) else ''
                if '/reviews' not in current_url:
                    # 리뷰 페이지가 아니면 다시 이동
                    review_url = info.get('jobplanet_url', '').replace('/landing', '/reviews').split('?')[0]
                    if review_url:
                        self.logger.info(f"    → 리뷰 페이지로 재이동: {review_url}")
                        await page.get(review_url)
                        await asyncio.sleep(3)
                        await self._close_popup(page)
            except:
                pass

            # 리뷰 영역까지 천천히 스크롤 (lazy-loading 트리거)
            self.logger.info(f"    → 리뷰 영역까지 스크롤 시작")
            for scroll_y in range(0, 3000, 300):
                await page.evaluate(f'window.scrollTo(0, {scroll_y})')
                await asyncio.sleep(0.3)
            await asyncio.sleep(2)

            # 리뷰 상태 다시 확인
            pre_extract_check_js = '''
                JSON.stringify({
                    url: window.location.href,
                    viewReviewsList: !!document.getElementById('viewReviewsList'),
                    reviewCount: document.querySelectorAll('section[id^="review_"]').length,
                    firstReviewId: document.querySelector('section[id^="review_"]')?.id || 'none'
                })
            '''
            pre_check = await page.evaluate(pre_extract_check_js)
            self.logger.info(f"    → 리뷰 추출 전 상태: {pre_check}")

            # 9. 개별 리뷰 추출 (설정에서 페이지 수 가져옴)
            max_pages = settings.jobplanet.review_max_pages
            max_reviews = settings.jobplanet.review_max_count
            all_reviews = []
            try:
                base_url_result = await page.evaluate('window.location.href.split("?")[0]')
                base_url = base_url_result if isinstance(base_url_result, str) else await page.evaluate('window.location.href')
                if not isinstance(base_url, str):
                    base_url = info.get('jobplanet_url', '').split('?')[0]
            except:
                base_url = info.get('jobplanet_url', '').split('?')[0]

            for page_num in range(1, max_pages + 1):
                # 페이지 렌더링 대기
                await asyncio.sleep(2)

                # 리뷰 목록 컨테이너(#viewReviewsList) 내부에 리뷰가 로드될 때까지 대기
                # 최대 10초간 폴링하며 대기
                review_loaded = False
                for wait_attempt in range(10):
                    check_reviews_js = '''
                        JSON.stringify((() => {
                            const container = document.getElementById('viewReviewsList');
                            if (!container) return { containerExists: false, reviewCount: 0, html: '' };
                            const reviews = container.querySelectorAll('section[id^="review_"]');
                            // 다른 셀렉터도 시도
                            const altReviews = document.querySelectorAll('section[id^="review_"]');
                            return {
                                containerExists: true,
                                reviewCount: reviews.length,
                                altReviewCount: altReviews.length,
                                containerChildCount: container.children.length
                            };
                        })())
                    '''
                    try:
                        result = await page.evaluate(check_reviews_js)
                        # nodriver는 str 또는 dict 반환 가능
                        result_data = None
                        if isinstance(result, str):
                            result_data = json.loads(result)
                        elif isinstance(result, dict):
                            result_data = result

                        if isinstance(result_data, dict):
                            container_exists = result_data.get('containerExists', False)
                            review_count = result_data.get('reviewCount', 0)
                            alt_count = result_data.get('altReviewCount', 0)

                            # 컨테이너 내부 또는 전역에서 리뷰 발견
                            if container_exists and (review_count > 0 or alt_count > 0):
                                actual_count = review_count if review_count > 0 else alt_count
                                self.logger.info(f"    → 페이지 {page_num}: 리뷰 {actual_count}개 로드됨 ({wait_attempt+1}초 대기)")
                                review_loaded = True
                                break
                            elif wait_attempt == 0:
                                self.logger.debug(f"    → 리뷰 대기 중... (컨테이너: {container_exists}, 내부: {review_count}, 전역: {alt_count})")
                    except Exception as e:
                        self.logger.debug(f"    → 리뷰 확인 중 오류: {e}")

                    await asyncio.sleep(1)

                if not review_loaded:
                    if page_num == 1:
                        self.logger.info(f"    → 첫 페이지에 리뷰 로드 실패 (10초 대기 후에도 없음)")
                        # 페이지 상태 디버깅
                        debug_js = '''
                            JSON.stringify({
                                url: window.location.href,
                                hasViewReviewsList: !!document.getElementById('viewReviewsList'),
                                viewReviewsListHTML: document.getElementById('viewReviewsList')?.innerHTML?.substring(0, 500) || 'N/A',
                                allSections: document.querySelectorAll('section').length,
                                reviewSections: document.querySelectorAll('section[id^="review_"]').length
                            })
                        '''
                        debug_result = await page.evaluate(debug_js)
                        self.logger.debug(f"    → 디버그 정보: {debug_result}")
                        break
                    continue

                reviews_js = r'''
                    JSON.stringify((() => {
                        const reviews = [];
                        // 전역에서 section[id^="review_"] 찾기 (컨테이너 내부가 아닐 수도 있음)
                        const reviewSections = document.querySelectorAll('section[id^="review_"]');

                        for (const section of reviewSections) {
                            try {
                                const reviewId = section.id.replace('review_', '');

                                // 프로필 정보 추출 (직군, 현/전직원, 지역, 작성일)
                                // 모두 span.text-body2.text-gray-400 클래스
                                const profileSpans = section.querySelectorAll('span.text-body2.text-gray-400');
                                let job = '', employmentStatus = '', location = '', writeDate = '';
                                profileSpans.forEach((span) => {
                                    const text = span.innerText.trim();
                                    if (text.includes('직원')) {
                                        employmentStatus = text;
                                    } else if (text.match(/\d{4}\.\s*\d{2}/)) {
                                        writeDate = text.replace('작성', '').trim();
                                    } else if (text.match(/^(서울|경기|인천|부산|대구|광주|대전|울산|세종|강원|충북|충남|전북|전남|경북|경남|제주)/)) {
                                        location = text;
                                    } else if (!job && text.length > 0) {
                                        job = text;
                                    }
                                });

                                // 총 평점 (span.text-h5.text-gray-800)
                                const ratingEl = section.querySelector('span.text-h5.text-gray-800');
                                const totalRating = ratingEl ? parseFloat(ratingEl.innerText.trim()) : null;

                                // 항목별 평점 (승진 기회, 복지/급여, 워라밸, 사내문화, 경영진)
                                const categoryScores = {};
                                const scoreItems = section.querySelectorAll('#ReviewCardSide li');
                                scoreItems.forEach(item => {
                                    const labelEl = item.querySelector('p.text-small1');
                                    if (labelEl) {
                                        const label = labelEl.innerText.trim();
                                        // 바 그래프에서 점수 계산 (width: 100%인 span 개수)
                                        const bars = item.querySelectorAll('span[style*="width"]');
                                        let score = 0;
                                        bars.forEach(bar => {
                                            if (bar.style.width === '100%') score += 1;
                                        });
                                        if (label) categoryScores[label] = score;
                                    }
                                });

                                // 제목 (h2)
                                const h2 = section.querySelector('h2');
                                const title = h2 ? h2.innerText.trim() : '';

                                // 장점/단점/경영진 의견 추출 (div.whitespace-pre-wrap 내부)
                                let pros = '', cons = '', advice = '';
                                const contentDivs = section.querySelectorAll('div.whitespace-pre-wrap');

                                contentDivs.forEach(div => {
                                    const hasBlueLabel = div.querySelector('.bg-blue-50');
                                    const hasRedLabel = div.querySelector('.bg-red-50');
                                    const hasGrayLabel = div.querySelector('.bg-gray-50');

                                    // 라벨 텍스트 제거하고 내용만 추출
                                    let text = div.innerText.trim();
                                    text = text.replace(/^(장점|단점|경영진에 바라는 점)\s*/, '').trim();

                                    if (hasBlueLabel) pros = text.substring(0, 500);
                                    else if (hasRedLabel) cons = text.substring(0, 500);
                                    else if (hasGrayLabel) advice = text.substring(0, 300);
                                });

                                // 1년 후 예상 및 기업 추천 여부 (.ReviewCardTag)
                                let futureOutlook = '', recommendation = '';
                                const tagSection = section.querySelector('.ReviewCardTag');
                                if (tagSection) {
                                    const tagText = tagSection.innerText;
                                    // "1년 후~" 텍스트 추출
                                    const futureMatch = tagText.match(/(1년 후[^\n]+)/);
                                    if (futureMatch) futureOutlook = futureMatch[1].trim();
                                    // 추천 여부
                                    if (tagText.includes('추천해요') && !tagText.includes('비추천')) {
                                        recommendation = '기업을 추천해요';
                                    } else if (tagText.includes('비추천')) {
                                        recommendation = '기업을 비추천해요';
                                    }
                                }

                                if (title || pros || cons) {
                                    reviews.push({
                                        id: reviewId,
                                        job: job,
                                        employment_status: employmentStatus,
                                        location: location,
                                        write_date: writeDate,
                                        total_rating: totalRating,
                                        category_scores: categoryScores,
                                        title: title.substring(0, 150),
                                        pros: pros,
                                        cons: cons,
                                        advice: advice,
                                        future_outlook: futureOutlook,
                                        recommendation: recommendation
                                    });
                                }
                            } catch (e) {
                                // 개별 리뷰 파싱 오류 무시
                            }
                        }
                        return reviews;
                    })())
                '''

                try:
                    reviews_result = await page.evaluate(reviews_js)
                    # nodriver는 str 또는 list 반환 가능
                    page_reviews = None
                    if isinstance(reviews_result, str):
                        page_reviews = json.loads(reviews_result)
                    elif isinstance(reviews_result, list):
                        page_reviews = reviews_result

                    # list인 경우에만 처리
                    if isinstance(page_reviews, list) and page_reviews:
                        all_reviews.extend(page_reviews)
                        self.logger.info(f"    → 페이지 {page_num}: {len(page_reviews)}개 리뷰 수집")
                    elif page_reviews is not None and not page_reviews:
                        self.logger.info(f"    → 페이지 {page_num}: 리뷰 없음, 수집 종료")
                        break
                    else:
                        # ExceptionDetails 등 오류 객체인 경우
                        self.logger.debug(f"Page {page_num} review: JS 결과 타입 {type(reviews_result).__name__}")
                        if page_num == 1:
                            break  # 첫 페이지부터 실패하면 중단
                        continue  # 이후 페이지면 다음으로 시도
                except Exception as e:
                    self.logger.debug(f"Page {page_num} review extraction error: {e}")
                    if page_num == 1:
                        break  # 첫 페이지부터 실패하면 중단
                    continue

                # 다음 페이지로 이동
                if page_num < max_pages:
                    next_url = f"{base_url}?page={page_num + 1}"
                    try:
                        await page.get(next_url)
                        await asyncio.sleep(3)
                        await self._close_popup(page)
                        await self._scroll_to_bottom_incrementally(page)
                    except:
                        break

                if len(all_reviews) >= max_reviews:
                    self.logger.info(f"    → {max_reviews}개 리뷰 도달, 수집 종료")
                    break

            reviews_data['reviews'] = all_reviews
            info['reviews'] = all_reviews
            info['reviews_collected'] = len(all_reviews)

            self.logger.info(f"  → 리뷰 추출 완료: {reviews_data.get('review_count')}건 중 {len(all_reviews)}개 수집")

        except Exception as e:
            self.logger.warning(f"Review extraction error: {e}")

    async def _collect_keywords(self, page, keyword_type: str) -> list:
        """장점/단점 키워드 수집 (페이지네이션 포함)"""
        all_keywords = []
        max_pages = 10  # 키워드 페이지 최대 10페이지

        for _ in range(max_pages):
            # 현재 페이지 키워드 수집
            keywords_js = r'''
                JSON.stringify((() => {
                    const keywords = [];
                    // 키워드 그리드 내 항목들
                    const items = document.querySelectorAll('.grid .rounded-\\[8px\\], .row-span-1 > div');
                    items.forEach(item => {
                        const text = item.innerText.trim().split('\n')[0];  // 첫 줄만
                        if (text && text.length > 1 && text.length < 50) {
                            keywords.push(text);
                        }
                    });
                    return keywords;
                })())
            '''
            try:
                kw_str = await page.evaluate(keywords_js)
                if isinstance(kw_str, str):
                    kws = json.loads(kw_str)
                    # list인 경우에만 처리
                    if isinstance(kws, list) and kws:
                        all_keywords.extend(kws)
            except:
                break

            # 다음 페이지 버튼 클릭
            next_btn_js = r'''
                (() => {
                    const nextBtns = document.querySelectorAll('i.jp-chevron-right');
                    for (const btn of nextBtns) {
                        const parent = btn.closest('button') || btn.parentElement;
                        if (parent && !parent.disabled) {
                            parent.click();
                            return true;
                        }
                    }
                    return false;
                })()
            '''
            clicked = await page.evaluate(next_btn_js)
            if not clicked:
                break
            await asyncio.sleep(0.5)

        # 중복 제거
        return list(dict.fromkeys(all_keywords))

    async def _capture_company_comparison_charts(self, page, info: Dict[str, Any]):
        """맞춤 기업 찾기 차트 스크린샷 저장 (모든 축 조합)"""
        try:
            # 스크린샷 저장 디렉토리
            company_name = info.get('company_name', 'unknown')
            safe_name = re.sub(r'[\\/:*?"<>|]', '_', company_name)
            screenshots_dir = Path(__file__).parent.parent / 'data' / 'charts' / safe_name
            screenshots_dir.mkdir(parents=True, exist_ok=True)

            # 1. "맞춤 기업 찾기" 탭 클릭
            click_tab_js = r'''
                (() => {
                    const tabs = document.querySelectorAll('.graph_tab, a[class*="graph_tab"]');
                    for (const tab of tabs) {
                        if (tab.innerText.includes('맞춤 기업 찾기')) {
                            tab.click();
                            return true;
                        }
                    }
                    return false;
                })()
            '''
            clicked = await page.evaluate(click_tab_js)
            if not clicked:
                self.logger.info("    → 맞춤 기업 찾기 탭 없음, 스킵")
                return

            await asyncio.sleep(2)
            self.logger.info("    → 맞춤 기업 찾기 탭 클릭")

            # 축 옵션 목록
            axis_options = [
                ('review_avg_cache', '총만족도'),
                ('review_advancement_cache', '승진기회'),
                ('review_compensation_cache', '복지급여'),
                ('review_worklife_cache', '워라밸'),
                ('review_culture_cache', '사내문화'),
                ('review_management_cache', '경영진')
            ]

            screenshots_saved = []
            total_combinations = len(axis_options) ** 3  # 6^3 = 216
            current = 0

            # 2. 모든 조합에 대해 스크린샷 저장
            for x_val, x_name in axis_options:
                for y_val, y_name in axis_options:
                    for size_val, size_name in axis_options:
                        current += 1

                        try:
                            # select 값 변경
                            change_selects_js = f'''
                                (() => {{
                                    const xSelect = document.querySelector('#xaxis-select');
                                    const ySelect = document.querySelector('#yaxis-select');
                                    const sizeSelect = document.querySelector('#size-select');

                                    if (xSelect) {{ xSelect.value = '{x_val}'; xSelect.dispatchEvent(new Event('change')); }}
                                    if (ySelect) {{ ySelect.value = '{y_val}'; ySelect.dispatchEvent(new Event('change')); }}
                                    if (sizeSelect) {{ sizeSelect.value = '{size_val}'; sizeSelect.dispatchEvent(new Event('change')); }}

                                    return xSelect && ySelect && sizeSelect;
                                }})()
                            '''
                            await page.evaluate(change_selects_js)
                            await asyncio.sleep(0.5)  # 차트 업데이트 대기

                            # 스크린샷 파일명
                            filename = f"chart_x{x_name}_y{y_name}_s{size_name}.png"
                            filepath = screenshots_dir / filename

                            # 차트 영역 스크린샷 (전체 페이지 스크린샷 후 크롭은 복잡하므로 전체 저장)
                            await page.save_screenshot(str(filepath))
                            screenshots_saved.append(str(filepath))

                            # 진행상황 (10개마다 로그)
                            if current % 10 == 0:
                                self.logger.info(f"    → 차트 스크린샷 진행: {current}/{total_combinations}")

                        except Exception as e:
                            self.logger.debug(f"Chart screenshot error ({x_name},{y_name},{size_name}): {e}")
                            continue

            info['chart_screenshots'] = screenshots_saved
            info['chart_screenshots_dir'] = str(screenshots_dir)
            self.logger.info(f"    → 맞춤 기업 찾기 차트: {len(screenshots_saved)}개 스크린샷 저장")

        except Exception as e:
            self.logger.debug(f"Company comparison charts error: {e}")

    async def _extract_salary_data(self, page, info: Dict[str, Any]):
        """연봉 탭에서 데이터 추출 (가이드 기반)"""
        try:
            await self._close_popup(page)
            await asyncio.sleep(1)

            # 1. 전체 직종 평균 연봉 추출
            overall_salary_js = r'''
                JSON.stringify((() => {
                    const data = {
                        avgSalary: null,
                        salaryCount: null,
                        jobType: '전체 직종'
                    };

                    // "전체 직종 평균 연봉" 섹션에서 금액 추출
                    // <em class="text-h9 text-green-600">전체 직종</em>평균 연봉
                    // <em class="mt-[4px] inline-block text-h2">5,537</em> 만원
                    const salarySection = document.querySelector('.border-t.border-gray-100');
                    if (salarySection) {
                        const amountEl = salarySection.querySelector('em.text-h2, em[class*="text-h2"]');
                        if (amountEl) {
                            data.avgSalary = amountEl.innerText.trim().replace(/,/g, '');
                        }
                    }

                    // 연봉 정보 수
                    const bodyText = document.body.innerText;
                    const countMatch = bodyText.match(/연봉\s*(\d{1,5})/);
                    if (countMatch) data.salaryCount = parseInt(countMatch[1]);

                    return data;
                })())
            '''
            overall_str = await page.evaluate(overall_salary_js)
            salary_data = {
                'overall_avg': None,
                'salary_count': None,
                'industry_avg': None,  # 업계 평균 연봉
                'industry_rank': None,  # 업계 내 순위 (상위 x%)
                'by_year': [],  # 년차별 연봉
                'by_position': [],  # 직급별 연봉
                'response_rate': None,  # 응답 비율 (전체 응답 중 x%가 응답)
                'salary_distribution': {  # 연봉 분포
                    'min': None,  # 최소
                    'low': None,  # 하위
                    'high': None,  # 상위
                    'max': None   # 최대
                }
            }

            if isinstance(overall_str, str):
                overall = json.loads(overall_str)
                # dict인 경우에만 처리
                if isinstance(overall, dict):
                    if overall.get('avgSalary'):
                        salary_data['overall_avg'] = overall['avgSalary'] + '만원'
                        info['salary_info'] = salary_data['overall_avg']
                    if overall.get('salaryCount'):
                        salary_data['salary_count'] = overall['salaryCount']
                        info['salary_count'] = overall['salaryCount']

            # 1-1. 업계 평균 연봉 및 순위 추출
            industry_compare_js = r'''
                JSON.stringify((() => {
                    const data = {
                        industryAvg: null,
                        industryRank: null
                    };

                    // 업계 비교 섹션: .bg-green-50 내 .border-green-500
                    const compareSection = document.querySelector('.bg-green-50 .border-green-500, .rounded-\\[8px\\].bg-green-50 .border-green-500');
                    if (compareSection) {
                        const text = compareSection.innerText;

                        // 업계 평균 연봉: "선택한 직종의 업계 평균 연봉은 4,224만원입니다"
                        const avgMatch = text.match(/업계\s*평균\s*연봉은?\s*([\d,]+)\s*만원/);
                        if (avgMatch) data.industryAvg = avgMatch[1].replace(/,/g, '') + '만원';

                        // 업계 내 순위: "해당 업계에서 상위2%에 해당하는 연봉"
                        const rankMatch = text.match(/상위\s*(\d+)\s*%/);
                        if (rankMatch) data.industryRank = '상위 ' + rankMatch[1] + '%';
                    }

                    return data;
                })())
            '''
            try:
                industry_str = await page.evaluate(industry_compare_js)
                if isinstance(industry_str, str):
                    industry_data = json.loads(industry_str)
                    # dict인 경우에만 처리
                    if isinstance(industry_data, dict):
                        if industry_data.get('industryAvg'):
                            salary_data['industry_avg'] = industry_data['industryAvg']
                            info['industry_avg_salary'] = industry_data['industryAvg']
                        if industry_data.get('industryRank'):
                            salary_data['industry_rank'] = industry_data['industryRank']
                            info['industry_salary_rank'] = industry_data['industryRank']
                            self.logger.info(f"    → 업계 비교: 평균 {industry_data.get('industryAvg')}, {industry_data.get('industryRank')}")
            except:
                pass

            # 1-2. 연봉 분포 추출 (전체 응답 중 x%가 응답, 최소/하위/상위/최대)
            salary_dist_js = r'''
                JSON.stringify((() => {
                    const data = {
                        responseRate: null,
                        min: null,
                        low: null,
                        high: null,
                        max: null
                    };

                    // "전체 응답 중 88%가 응답" 텍스트 추출
                    const bodyText = document.body.innerText;
                    const responseMatch = bodyText.match(/전체\s*응답\s*중\s*(\d+)%가\s*응답/);
                    if (responseMatch) {
                        data.responseRate = parseInt(responseMatch[1]);
                    }

                    // 연봉 분포 차트에서 4개의 값 추출 (최소, 하위, 상위, 최대)
                    // <span>2,404</span><span>3,591</span><span>8,978</span><span>12,037</span>
                    const salaryChart = document.querySelector('.salary-chart, [class*="salary"], [class*="range"]');
                    if (salaryChart) {
                        const spans = salaryChart.querySelectorAll('span');
                        const values = [];
                        spans.forEach(span => {
                            const text = span.innerText.trim();
                            if (/^[\d,]+$/.test(text)) {
                                values.push(parseInt(text.replace(/,/g, '')));
                            }
                        });
                        if (values.length >= 4) {
                            data.min = values[0];
                            data.low = values[1];
                            data.high = values[2];
                            data.max = values[3];
                        }
                    }

                    // 대안: 연봉 분포 영역 내 모든 숫자 추출
                    if (!data.min) {
                        const distMatch = bodyText.match(/(\d{1,2},?\d{3})\s*[\s\S]*?(\d{1,2},?\d{3})\s*[\s\S]*?(\d{1,2},?\d{3})\s*[\s\S]*?(\d{1,2},?\d{3})\s*만원/);
                        if (distMatch) {
                            data.min = parseInt(distMatch[1].replace(/,/g, ''));
                            data.low = parseInt(distMatch[2].replace(/,/g, ''));
                            data.high = parseInt(distMatch[3].replace(/,/g, ''));
                            data.max = parseInt(distMatch[4].replace(/,/g, ''));
                        }
                    }

                    return data;
                })())
            '''
            try:
                dist_str = await page.evaluate(salary_dist_js)
                if isinstance(dist_str, str):
                    dist_data = json.loads(dist_str)
                    # dict인 경우에만 처리
                    if isinstance(dist_data, dict):
                        if dist_data.get('responseRate'):
                            salary_data['response_rate'] = f"{dist_data['responseRate']}%"
                        if dist_data.get('min'):
                            salary_data['salary_distribution'] = {
                                'min': f"{dist_data['min']}만원",
                                'low': f"{dist_data['low']}만원",
                                'high': f"{dist_data['high']}만원",
                                'max': f"{dist_data['max']}만원"
                            }
                            self.logger.info(f"    → 연봉 분포: {dist_data['min']}~{dist_data['max']}만원 (응답률: {dist_data.get('responseRate')}%)")
            except:
                pass

            # 2. 년차 선택 드롭다운 열기 및 년차 목록 가져오기
            years_js = r'''
                JSON.stringify((() => {
                    const years = [];
                    // 년차 선택 버튼 클릭
                    const yearBtn = document.querySelector('button span.truncate');
                    if (yearBtn && yearBtn.innerText.includes('년차')) {
                        yearBtn.closest('button').click();
                    }

                    // 잠시 후 드롭다운 항목 수집
                    setTimeout(() => {}, 500);

                    const yearOptions = document.querySelectorAll('button[type="button"]');
                    yearOptions.forEach(btn => {
                        const text = btn.innerText.trim();
                        if (/^\d+년차$/.test(text)) {
                            years.push(text);
                        }
                    });
                    return years;
                })())
            '''
            try:
                # 드롭다운 열기
                open_dropdown_js = r'''
                    (() => {
                        const buttons = document.querySelectorAll('button');
                        for (const btn of buttons) {
                            const span = btn.querySelector('span.truncate');
                            if (span && span.innerText.includes('년차')) {
                                btn.click();
                                return true;
                            }
                        }
                        return false;
                    })()
                '''
                await page.evaluate(open_dropdown_js)
                await asyncio.sleep(0.5)

                # 년차 목록 가져오기
                get_years_js = r'''
                    JSON.stringify((() => {
                        const years = [];
                        const buttons = document.querySelectorAll('.overflow-y-scroll button, [class*="shadow"] button');
                        buttons.forEach(btn => {
                            const text = btn.innerText.trim();
                            if (/^\d+년차$/.test(text)) {
                                years.push(text);
                            }
                        });
                        return years;
                    })())
                '''
                years_str = await page.evaluate(get_years_js)
                parsed_salary_years = json.loads(years_str) if isinstance(years_str, str) else []
                # list인 경우에만 사용
                years = parsed_salary_years if isinstance(parsed_salary_years, list) else []

                # 드롭다운 닫기 (ESC)
                await page.evaluate('document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }))')
                await asyncio.sleep(0.3)

                # 3. 각 년차별 연봉 정보 수집
                for year in years[:15]:  # 최대 15년차까지
                    try:
                        # 해당 년차 선택
                        select_year_js = f'''
                            (() => {{
                                // 드롭다운 열기
                                const buttons = document.querySelectorAll('button');
                                for (const btn of buttons) {{
                                    const span = btn.querySelector('span.truncate');
                                    if (span && span.innerText.includes('년차')) {{
                                        btn.click();
                                        break;
                                    }}
                                }}
                                return true;
                            }})()
                        '''
                        await page.evaluate(select_year_js)
                        await asyncio.sleep(0.3)

                        click_year_js = f'''
                            (() => {{
                                const buttons = document.querySelectorAll('.overflow-y-scroll button, [class*="shadow"] button');
                                for (const btn of buttons) {{
                                    if (btn.innerText.trim() === '{year}') {{
                                        btn.click();
                                        return true;
                                    }}
                                }}
                                return false;
                            }})()
                        '''
                        await page.evaluate(click_year_js)
                        await asyncio.sleep(0.5)

                        # 연봉 정보 추출
                        year_salary_js = r'''
                            JSON.stringify((() => {
                                const data = { salary: null, increaseRate: null };

                                // 평균 연봉 금액: em.text-green-600 안의 숫자
                                const salaryBox = document.querySelector('.border-green-500, [class*="border-green"]');
                                if (salaryBox) {
                                    const salaryEl = salaryBox.querySelector('em.text-green-600, em[class*="text-green"]');
                                    if (salaryEl) {
                                        data.salary = salaryEl.innerText.trim().replace(/,/g, '');
                                    }

                                    // 예상 연봉 인상률
                                    const rateEl = salaryBox.querySelectorAll('em.text-green-600, em[class*="text-green"]')[1];
                                    if (rateEl) {
                                        const rateText = rateEl.innerText.trim();
                                        if (rateText.includes('%') || /[\d.]+/.test(rateText)) {
                                            data.increaseRate = rateText;
                                        }
                                    }
                                }
                                return data;
                            })())
                        '''
                        salary_str = await page.evaluate(year_salary_js)
                        if isinstance(salary_str, str):
                            year_data = json.loads(salary_str)
                            # dict인 경우에만 처리
                            if isinstance(year_data, dict) and year_data.get('salary'):
                                salary_data['by_year'].append({
                                    'year': year,
                                    'salary': year_data['salary'] + '만원',
                                    'increase_rate': year_data.get('increaseRate')
                                })
                    except:
                        continue

                if salary_data['by_year']:
                    info['salary_by_year'] = salary_data['by_year']
                    info['salary_by_position'] = salary_data['by_year']  # 호환성
                    self.logger.info(f"  → 연봉 추출: 전체 {salary_data.get('overall_avg') or '없음'}, {len(salary_data['by_year'])}개 년차")
                else:
                    self.logger.info(f"  → 연봉 추출: 전체 {salary_data.get('overall_avg') or '없음'}")

            except Exception as e:
                self.logger.debug(f"Year-by-year salary error: {e}")

        except Exception as e:
            self.logger.debug(f"Salary extraction error: {e}")

    async def _extract_interview_data(self, page, info: Dict[str, Any]):
        """면접 탭에서 데이터 추출 (가이드 기반)"""
        try:
            await self._close_popup(page)
            await asyncio.sleep(1)

            # 1. 면접 통계 요약 추출 (난이도, 경로, 경험, 결과)
            stats_js = r'''
                JSON.stringify((() => {
                    const data = {
                        count: null,
                        difficulty: { score: null, level: null },
                        routes: [],  // 면접 경로 (인맥, 헤드헌터 등)
                        experiences: [],  // 면접 경험 (긍정적, 부정적, 보통)
                        results: []  // 면접 결과 (합격, 불합격, 대기중)
                    };

                    // 면접 후기 수
                    const bodyText = document.body.innerText;
                    const countMatch = bodyText.match(/면접\s*(\d{1,5})/);
                    if (countMatch) data.count = parseInt(countMatch[1]);

                    // 면접 난이도 섹션 (.vib_sec)
                    const diffSection = document.querySelector('.vib_sec');
                    if (diffSection) {
                        const scoreEl = diffSection.querySelector('.vib_num');
                        const levelEl = diffSection.querySelector('.vib_txt');
                        if (scoreEl) data.difficulty.score = parseFloat(scoreEl.innerText);
                        if (levelEl) data.difficulty.level = levelEl.innerText.trim();
                    }

                    // 면접 경로 테이블 (각 행에 2개씩 있음)
                    const routeTable = document.querySelector('table[summary="면접경로"]');
                    if (routeTable) {
                        const rows = routeTable.querySelectorAll('tr');
                        rows.forEach(row => {
                            const ths = row.querySelectorAll('th');
                            const tds = row.querySelectorAll('td:not(.empty)');
                            ths.forEach((th, idx) => {
                                const td = tds[idx];
                                if (th && td) {
                                    data.routes.push({
                                        route: th.innerText.trim(),
                                        percent: td.innerText.trim()
                                    });
                                }
                            });
                        });
                    }

                    // 면접 경험 테이블
                    const expTable = document.querySelector('table[summary="면접경험"]');
                    if (expTable) {
                        const rows = expTable.querySelectorAll('tr');
                        rows.forEach(row => {
                            const th = row.querySelector('th');
                            const td = row.querySelector('td');
                            if (th && td) {
                                data.experiences.push({
                                    type: th.innerText.trim(),
                                    percent: td.innerText.trim()
                                });
                            }
                        });
                    }

                    // 면접 결과 테이블
                    const resultTable = document.querySelector('table[summary="면접결과"]');
                    if (resultTable) {
                        const rows = resultTable.querySelectorAll('tr');
                        rows.forEach(row => {
                            const th = row.querySelector('th');
                            const td = row.querySelector('td');
                            if (th && td) {
                                data.results.push({
                                    result: th.innerText.trim(),
                                    percent: td.innerText.trim()
                                });
                            }
                        });
                    }

                    return data;
                })())
            '''
            stats_str = await page.evaluate(stats_js)
            interview_data = {
                'count': None,
                'difficulty': None,
                'difficulty_score': None,
                'routes': [],
                'experiences': [],
                'results': [],
                'interviews': []
            }

            if isinstance(stats_str, str):
                stats = json.loads(stats_str)
                # dict인 경우에만 처리
                if isinstance(stats, dict):
                    interview_data['count'] = stats.get('count')
                    info['interview_count'] = stats.get('count')

                    if stats.get('difficulty', {}).get('level'):
                        interview_data['difficulty'] = stats['difficulty']['level']
                        interview_data['difficulty_score'] = stats['difficulty'].get('score')
                        info['interview_difficulty'] = stats['difficulty']['level']

                    if stats.get('routes'):
                        interview_data['routes'] = stats['routes']
                    if stats.get('experiences'):
                        interview_data['experiences'] = stats['experiences']
                        # 가장 높은 비율의 경험 타입
                        for exp in stats['experiences']:
                            if isinstance(exp, dict) and '긍정' in exp.get('type', ''):
                                info['interview_experience'] = '긍정적'
                                break
                    if stats.get('results'):
                        interview_data['results'] = stats['results']
                        # 합격률 추출
                        for res in stats['results']:
                            if isinstance(res, dict) and '합격' in res.get('result', '') and '불' not in res.get('result', ''):
                                info['interview_success_rate'] = res.get('percent')
                                break
                else:
                    self.logger.debug(f"    → 면접 stats가 dict가 아님: {type(stats).__name__}")

            # 2. 스크롤하여 개별 면접 후기 로드
            await self._scroll_to_bottom_incrementally(page)

            # 3. 개별 면접 후기 수집 (설정에서 페이지 수 가져옴)
            max_pages = settings.jobplanet.interview_max_pages
            max_interviews = settings.jobplanet.interview_max_count
            all_interviews = []
            try:
                base_url_result = await page.evaluate('window.location.href.split("?")[0]')
                base_url = base_url_result if isinstance(base_url_result, str) else info.get('jobplanet_url', '').replace('/reviews', '/interviews').split('?')[0]
            except:
                base_url = info.get('jobplanet_url', '').replace('/reviews', '/interviews').split('?')[0]

            for page_num in range(1, max_pages + 1):
                interviews_js = r'''
                    JSON.stringify((() => {
                        const interviews = [];
                        // section[data-content_type="interview"] 형식
                        const sections = document.querySelectorAll('section[data-content_type="interview"], .content_ty4[data-content_type="interview"]');

                        sections.forEach(section => {
                            const interview = {
                                id: section.dataset.content_id,
                                job: '',
                                position: '',
                                date: '',
                                difficulty: '',
                                route: '',
                                title: '',
                                question: '',
                                answer: '',
                                announcement_timing: '',  // 발표시기
                                result: '',
                                experience: ''
                            };

                            // 직군/직급
                            const infoSpan = section.querySelector('.txt1');
                            if (infoSpan) {
                                const parts = infoSpan.innerText.split('/');
                                if (parts[0]) interview.job = parts[0].trim();
                                if (parts[1]) {
                                    const posAndDate = parts[1].split('|');
                                    interview.position = posAndDate[0].trim();
                                    if (posAndDate[1]) interview.date = posAndDate[1].trim();
                                }
                            }

                            // 면접 난이도
                            const diffEl = section.querySelector('.blo_txt2, .us_txt_mr');
                            if (diffEl) interview.difficulty = diffEl.innerText.trim();

                            // 면접 경로
                            const routeEl = section.querySelector('.ctbody_lft .txt2');
                            if (routeEl) interview.route = routeEl.innerText.trim();

                            // 면접 제목/요약
                            const titleEl = section.querySelector('.us_label h2, .us_label');
                            if (titleEl) interview.title = titleEl.innerText.trim().replace(/^"|"$/g, '').substring(0, 200);

                            // 면접 질문
                            const questionDt = section.querySelector('dt.df_tit');
                            if (questionDt && questionDt.innerText.includes('면접질문')) {
                                const questionDd = questionDt.nextElementSibling;
                                if (questionDd) interview.question = questionDd.innerText.trim().substring(0, 500);
                            }

                            // 면접 답변/느낌
                            const answerEl = section.querySelector('.answer, [id*="interview_answer"]');
                            if (answerEl) interview.answer = answerEl.innerText.trim().substring(0, 500);

                            // 발표시기
                            const allDts = section.querySelectorAll('dt.df_tit');
                            allDts.forEach(dt => {
                                if (dt.innerText.includes('발표시기')) {
                                    const dd = dt.nextElementSibling;
                                    if (dd) interview.announcement_timing = dd.innerText.trim();
                                }
                            });

                            // 면접 결과
                            const resultEl = section.querySelector('.rt_pass, .rt_fail, .rt_waiting');
                            if (resultEl) {
                                const resultText = resultEl.parentElement?.innerText || resultEl.innerText;
                                interview.result = resultText.trim();
                            }

                            // 면접 경험
                            const expEl = section.querySelector('.ex_psv, .ex_ngt, .ex_nor');
                            if (expEl) {
                                const expText = expEl.parentElement?.innerText || expEl.innerText;
                                interview.experience = expText.trim();
                            }

                            if (interview.title || interview.question) {
                                interviews.push(interview);
                            }
                        });

                        return interviews;
                    })())
                '''

                try:
                    interviews_str = await page.evaluate(interviews_js)
                    if isinstance(interviews_str, str):
                        page_interviews = json.loads(interviews_str)
                        # list인 경우에만 처리
                        if isinstance(page_interviews, list) and page_interviews:
                            all_interviews.extend(page_interviews)
                            self.logger.info(f"    → 페이지 {page_num}: {len(page_interviews)}개 면접 후기 수집")
                        elif not page_interviews:
                            self.logger.info(f"    → 페이지 {page_num}: 면접 후기 없음, 수집 종료")
                            break
                    else:
                        # ExceptionDetails 등 오류 객체인 경우
                        self.logger.debug(f"Page {page_num} interview: JS 실행 결과가 문자열이 아님 (type: {type(interviews_str).__name__})")
                        if page_num == 1:
                            break  # 첫 페이지부터 실패하면 중단
                        continue  # 이후 페이지면 다음으로 시도
                except Exception as e:
                    self.logger.debug(f"Page {page_num} interview extraction error: {e}")
                    if page_num == 1:
                        break  # 첫 페이지부터 실패하면 중단
                    continue

                # 다음 페이지로 이동
                if page_num < max_pages:
                    next_url = f"{base_url}?page={page_num + 1}"
                    try:
                        await page.get(next_url)
                        await asyncio.sleep(3)
                        await self._close_popup(page)
                        await self._scroll_to_bottom_incrementally(page)
                    except:
                        break

                if len(all_interviews) >= max_interviews:
                    self.logger.info(f"    → {max_interviews}개 면접 후기 도달, 수집 종료")
                    break

            interview_data['interviews'] = all_interviews
            info['interviews'] = all_interviews
            info['interviews_collected'] = len(all_interviews)

            # 면접 질문 목록 추출 (상위 5개)
            questions = [i['question'] for i in all_interviews if i.get('question')][:5]
            if questions:
                info['interview_questions'] = questions

            self.logger.info(f"  → 면접 추출: {interview_data.get('count')}건 중 {len(all_interviews)}개 수집, 난이도: {interview_data.get('difficulty') or '없음'}")

        except Exception as e:
            self.logger.debug(f"Interview extraction error: {e}")

    async def _extract_benefits_data(self, page, info: Dict[str, Any]):
        """복지 탭에서 데이터 추출 (가이드 기반 - 완전 버전)"""
        try:
            await self._close_popup(page)
            await asyncio.sleep(1)

            benefits_data = {
                'overall_rating': None,
                'total_count': None,
                'welfare_count': None,  # 복지 개수
                'rating_distribution': {},  # 평점 분포도
                'top_satisfaction': [],  # 만족도가 가장 높은 복지 TOP 3
                'most_used': [],  # 가장 많이 사용한 복지 TOP 3
                'welfare_by_category': {},  # 카테고리별 복지 목록
                'welfare_list': [],  # 전체 복지 목록
                'welfare_reviews': []  # 복지 후기
            }

            # 1. 복지 요약 정보 추출 (평점, 총 건수, 복지 개수, 순위 정보)
            summary_js = r'''
                JSON.stringify((() => {
                    const data = {
                        overall_rating: null,
                        total_count: null,
                        welfare_count: null,
                        rating_distribution: {},
                        top_satisfaction: [],
                        most_used: []
                    };

                    // 전체 복지 평점: .welfare-star__point
                    const ratingEl = document.querySelector('.welfare-average .welfare-star__point');
                    if (ratingEl) {
                        data.overall_rating = parseFloat(ratingEl.innerText.trim());
                    }

                    // 총 건수: (총 270건)
                    const countEl = document.querySelector('.welfare-summary__ref');
                    if (countEl) {
                        const match = countEl.innerText.match(/(\d+)/);
                        if (match) data.total_count = parseInt(match[1]);
                    }

                    // 복지 개수: .welfare-overview__count
                    const welfareCountEl = document.querySelector('.welfare-overview__count .welfare-overview__num, .welfare-overview__num');
                    if (welfareCountEl) {
                        const countText = welfareCountEl.innerText.trim();
                        const match = countText.match(/(\d+)/);
                        if (match) data.welfare_count = parseInt(match[1]);
                    }

                    // 평점 분포도: .welfare-overview__bar
                    const bars = document.querySelectorAll('.welfare-overview__bar');
                    bars.forEach(bar => {
                        const scoreEl = bar.querySelector('.welfare-overview__txt');
                        const percentEl = bar.querySelector('.welfare-overview__val .job_tooltip_inner');
                        if (scoreEl && percentEl) {
                            const score = scoreEl.innerText.trim();
                            const percent = percentEl.innerText.trim();
                            data.rating_distribution[score] = percent;
                        }
                    });

                    // 만족도가 가장 높은 복지 TOP 3: .welfare-summary__ranking 첫 번째
                    const rankingSections = document.querySelectorAll('.welfare-summary__ranking');
                    if (rankingSections.length >= 1) {
                        const topSatSection = rankingSections[0];
                        const items = topSatSection.querySelectorAll('.welfare-rank');
                        items.forEach(item => {
                            const rank = item.querySelector('.welfare-rank__num')?.innerText.trim();
                            const name = item.querySelector('.welfare-rank__tit')?.innerText.trim();
                            const count = item.querySelector('.welfare-rank__cnt')?.innerText.trim();
                            const scoreEl = item.querySelector('.welfare-section__score p');
                            const score = scoreEl ? parseFloat(scoreEl.innerText) : null;
                            if (name) {
                                data.top_satisfaction.push({ rank, name, count, score });
                            }
                        });
                    }

                    // 가장 많이 사용한 복지 TOP 3: .welfare-summary__ranking 두 번째
                    if (rankingSections.length >= 2) {
                        const mostUsedSection = rankingSections[1];
                        const items = mostUsedSection.querySelectorAll('.welfare-rank');
                        items.forEach(item => {
                            const rank = item.querySelector('.welfare-rank__num')?.innerText.trim();
                            const name = item.querySelector('.welfare-rank__tit')?.innerText.trim();
                            const count = item.querySelector('.welfare-rank__cnt')?.innerText.trim();
                            const percentEl = item.querySelector('.welfare-rank__percent');
                            const percent = percentEl ? percentEl.innerText.trim() : null;
                            if (name) {
                                data.most_used.push({ rank, name, count, percent });
                            }
                        });
                    }

                    return data;
                })())
            '''
            summary_str = await page.evaluate(summary_js)

            if isinstance(summary_str, str):
                summary = json.loads(summary_str)
                # dict인 경우에만 처리
                if isinstance(summary, dict):
                    benefits_data['overall_rating'] = summary.get('overall_rating')
                    benefits_data['total_count'] = summary.get('total_count')
                    benefits_data['welfare_count'] = summary.get('welfare_count')
                    benefits_data['rating_distribution'] = summary.get('rating_distribution', {})
                    benefits_data['top_satisfaction'] = summary.get('top_satisfaction', [])
                    benefits_data['most_used'] = summary.get('most_used', [])

                    if summary.get('overall_rating'):
                        info['benefits_rating'] = summary['overall_rating']
                    if summary.get('welfare_count'):
                        info['welfare_count'] = summary['welfare_count']
                    if summary.get('top_satisfaction'):
                        info['top_satisfaction_benefits'] = summary['top_satisfaction']
                    if summary.get('most_used'):
                        info['most_used_benefits'] = summary['most_used']

                    self.logger.info(f"    → 복지 요약: 평점 {summary.get('overall_rating')}, 복지 개수 {summary.get('welfare_count')}개")

            # 2. 600px 스크롤하여 복지 목록 로드
            await page.evaluate('window.scrollTo(0, 600)')
            await asyncio.sleep(1)

            # 3. 회사 복지 목록 카테고리별 수집 (.welfare-provision)
            welfare_by_category_js = r'''
                JSON.stringify((() => {
                    const categories = {};
                    const allItems = [];

                    // 카테고리별 복지 항목 (.welfare-bullet)
                    const bulletSections = document.querySelectorAll('.welfare-bullet, .welfare-provision__item .welfare-bullet');
                    bulletSections.forEach(section => {
                        const categoryEl = section.querySelector('.welfare-bullet__tit, h5.welfare-bullet__tit');
                        const category = categoryEl ? categoryEl.innerText.trim() : '기타';

                        if (!categories[category]) {
                            categories[category] = [];
                        }

                        const items = section.querySelectorAll('.welfare-bullet__item, .welfare-bullet__list li');
                        items.forEach(item => {
                            const nameEl = item.querySelector('.item-name, span.item-name');
                            const authorEl = item.querySelector('.item-author');
                            if (nameEl) {
                                const name = nameEl.innerText.trim();
                                const isEmployeeRegistered = authorEl ? authorEl.innerText.includes('직원 등록') : false;
                                categories[category].push({
                                    name: name,
                                    employee_registered: isEmployeeRegistered
                                });
                                allItems.push(name);
                            }
                        });
                    });

                    return { categories, allItems };
                })())
            '''
            category_str = await page.evaluate(welfare_by_category_js)
            if isinstance(category_str, str):
                category_data = json.loads(category_str)
                # dict인 경우에만 처리
                if isinstance(category_data, dict):
                    benefits_data['welfare_by_category'] = category_data.get('categories', {})
                    benefits_data['welfare_list'] = category_data.get('allItems', [])
                    info['benefits'] = benefits_data['welfare_list'][:30]
                    info['benefits_by_category'] = benefits_data['welfare_by_category']

                    total_items = sum(len(items) for items in benefits_data['welfare_by_category'].values())
                    self.logger.info(f"    → 복지 목록: {len(benefits_data['welfare_by_category'])}개 카테고리, {total_items}개 항목")

            # 4. 복지 후기 수집 (페이지네이션 포함) - 상세 정보 포함
            await self._scroll_to_bottom_incrementally(page)

            max_pages = settings.jobplanet.benefit_max_pages
            all_reviews = []
            base_url = await page.evaluate('window.location.href.split("?")[0]')

            for page_num in range(1, max_pages + 1):
                # 복지 후기 추출 (.welfare-content__box) - 상세 정보 포함
                reviews_js = r'''
                    JSON.stringify((() => {
                        const reviews = [];
                        const boxes = document.querySelectorAll('.welfare-content__box');

                        boxes.forEach(box => {
                            // 직장 생활 치트키 섹션 제외
                            if (box.closest('.jply_section')) return;

                            const review = {
                                category: '',
                                category_rating: null,
                                profile: {
                                    job: '',
                                    employment_status: '',
                                    location: '',
                                    employment_type: ''
                                },
                                content: '',
                                item_scores: []
                            };

                            // 카테고리 (의료/건강 등)
                            const catEl = box.querySelector('.welfare-content__star .category');
                            if (catEl) review.category = catEl.innerText.trim();

                            // 카테고리별 평점
                            const catRatingEl = box.querySelector('.welfare-content__star .welfare-star__point');
                            if (catRatingEl) review.category_rating = parseFloat(catRatingEl.innerText.trim());

                            // 작성자 프로필 (.welfare-profile)
                            const profileEl = box.querySelector('.welfare-profile');
                            if (profileEl) {
                                const profileTexts = profileEl.querySelectorAll('.welfare-profile__txt');
                                profileTexts.forEach((txt, idx) => {
                                    const text = txt.innerText.trim();
                                    if (idx === 0) review.profile.job = text;  // 직군 (개발, 영업 등)
                                    else if (idx === 1) review.profile.employment_status = text;  // 현직원/전직원
                                    else if (idx === 2) review.profile.location = text;  // 지역
                                    else if (idx === 3) review.profile.employment_type = text;  // 정규직/계약직
                                });
                            }

                            // 후기 내용 (.welfare-content__comment)
                            const commentEl = box.querySelector('.welfare-content__comment');
                            if (commentEl) review.content = commentEl.innerText.trim().substring(0, 500);

                            // 개별 복지 항목별 평점 (.welfare-content__score)
                            const scoreItems = box.querySelectorAll('.welfare-content__item, .welfare-content__list li');
                            scoreItems.forEach(item => {
                                const nameEl = item.querySelector('.welfare-content__wrap span:first-child, span:not(.welfare-section__score)');
                                const scoreEl = item.querySelector('.welfare-section__score p');
                                if (nameEl && scoreEl) {
                                    const name = nameEl.innerText.trim();
                                    const score = parseFloat(scoreEl.innerText.trim());
                                    if (name && !isNaN(score)) {
                                        review.item_scores.push({ name, score });
                                    }
                                }
                            });

                            if (review.category || review.content) {
                                reviews.push(review);
                            }
                        });

                        return reviews;
                    })())
                '''

                try:
                    reviews_str = await page.evaluate(reviews_js)
                    if isinstance(reviews_str, str):
                        page_reviews = json.loads(reviews_str)
                        # list인 경우에만 처리
                        if isinstance(page_reviews, list) and page_reviews:
                            all_reviews.extend(page_reviews)
                            self.logger.info(f"    → 복지 후기 페이지 {page_num}: {len(page_reviews)}개")
                        elif not page_reviews:
                            break
                except:
                    break

                # 다음 페이지로 이동 (pagination 버튼)
                if page_num < max_pages:
                    next_page_js = f'''
                        (() => {{
                            const buttons = document.querySelectorAll('.jply_pagination_ty1 button');
                            for (const btn of buttons) {{
                                if (btn.innerText.trim() === '{page_num + 1}') {{
                                    btn.click();
                                    return true;
                                }}
                            }}
                            // 다음 버튼
                            const nextBtn = document.querySelector('.jply_pagination_ty1 .btn_next');
                            if (nextBtn && !nextBtn.disabled) {{
                                nextBtn.click();
                                return true;
                            }}
                            return false;
                        }})()
                    '''
                    clicked = await page.evaluate(next_page_js)
                    if not clicked:
                        break
                    await asyncio.sleep(3)
                    await self._close_popup(page)
                    await self._scroll_to_bottom_incrementally(page)

            benefits_data['welfare_reviews'] = all_reviews
            info['welfare_reviews'] = all_reviews
            info['welfare_reviews_count'] = len(all_reviews)

            self.logger.info(f"  → 복지 추출 완료: 평점 {benefits_data.get('overall_rating')}, "
                           f"복지 {benefits_data.get('welfare_count')}개, "
                           f"{len(benefits_data.get('welfare_by_category', {}))}개 카테고리, "
                           f"{len(all_reviews)}개 후기")

        except Exception as e:
            self.logger.debug(f"Benefits extraction error: {e}")

    async def _extract_jobs_data(self, page, info: Dict[str, Any]):
        """채용 탭에서 데이터 추출"""
        try:
            await self._close_popup(page)
            await asyncio.sleep(1)

            # 스크롤하여 채용공고 로드
            await self._scroll_to_bottom_incrementally(page)

            jobs_js = r'''
                JSON.stringify((() => {
                    const data = { count: 0, jobs: [] };
                    const bodyText = document.body.innerText;

                    // 채용 공고 수 (탭에서 "채용 0" 또는 "채용 15" 형식)
                    const countMatch = bodyText.match(/채용\s*(\d+)/);
                    if (countMatch) data.count = parseInt(countMatch[1]);

                    // 채용공고 상세 정보 추출
                    const jobCards = document.querySelectorAll(
                        '[class*="job"], [class*="position"], [class*="posting"], ' +
                        'article, .rounded-\\[12px\\], section'
                    );
                    const seen = new Set();

                    jobCards.forEach(card => {
                        const cardText = card.innerText || '';

                        // 채용공고 특성 있는지 확인 (직무명, 경력, 지역 등)
                        if (cardText.length < 20 || cardText.length > 1000) return;

                        const title = card.querySelector('h3, h4, h2, [class*="title"], strong');
                        if (!title) return;

                        const titleText = title.innerText.trim();
                        if (!titleText || titleText.length < 3 || titleText.length > 100 || seen.has(titleText)) return;

                        seen.add(titleText);

                        const job = {
                            title: titleText,
                            location: '',
                            experience: '',
                            deadline: ''
                        };

                        // 지역 추출
                        const locMatch = cardText.match(/(서울|경기|인천|부산|대구|광주|대전|울산|세종|강원|충북|충남|전북|전남|경북|경남|제주)[^\s]*/);
                        if (locMatch) job.location = locMatch[0];

                        // 경력 추출
                        const expMatch = cardText.match(/(신입|경력|경력\s*\d+년|신입\/경력|\d+년\s*이상)/);
                        if (expMatch) job.experience = expMatch[0];

                        // 마감일 추출
                        const deadlineMatch = cardText.match(/~\s*(\d{1,2}\/\d{1,2}|\d{4}\.\d{2}\.\d{2}|상시)/);
                        if (deadlineMatch) job.deadline = deadlineMatch[0];

                        data.jobs.push(job);
                    });

                    return data;
                })())
            '''
            result_str = await page.evaluate(jobs_js)
            if isinstance(result_str, str):
                data = json.loads(result_str)
                # dict인 경우에만 처리
                if isinstance(data, dict):
                    if data.get('count') is not None:
                        info['active_job_count'] = data['count']
                    if data.get('jobs'):
                        info['active_jobs'] = data['jobs'][:20]
                        info['active_job_titles'] = [j['title'] for j in data['jobs'][:10]]
                    self.logger.info(f"  → 채용 추출: {data.get('count')}개 공고, {len(data.get('jobs', []))}개 상세")
        except Exception as e:
            self.logger.debug(f"Jobs extraction error: {e}")

    async def _extract_landing_data(self, page, info: Dict[str, Any]):
        """랜딩 페이지에서 기업 정보 추출"""
        try:
            await self._close_popup(page)
            await asyncio.sleep(1)

            # 기업 정보 섹션 (#profile)
            profile_js = r'''
                JSON.stringify((() => {
                    const data = {
                        industry: null,
                        company_type: null,
                        employee_count: null,
                        founded_year: null,
                        ceo: null,
                        revenue: null,
                        address: null,
                        website: null,
                        history: null  // 연혁
                    };

                    const profileSection = document.querySelector('#profile, section[id="profile"]');
                    if (!profileSection) return data;

                    const items = profileSection.querySelectorAll('li');
                    items.forEach(li => {
                        const text = li.innerText.trim();
                        const imgAlt = li.querySelector('img')?.alt || '';

                        // 산업
                        if (imgAlt.includes('산업') || text.includes('산업')) {
                            const match = text.match(/산업[^\n]*\n?([^\n]+)/);
                            if (match) data.industry = match[1].trim();
                        }
                        // 기업형태
                        if (imgAlt.includes('기업') || text.includes('기업형태')) {
                            const match = text.match(/기업형태[^\n]*\n?([^\n]+)/);
                            if (match) data.company_type = match[1].trim();
                        }
                        // 사원수
                        if (imgAlt.includes('사원') || text.includes('사원수')) {
                            const match = text.match(/사원수[^\n]*\n?([^\n]+)/);
                            if (match) data.employee_count = match[1].trim();
                        }
                        // 설립
                        if (imgAlt.includes('설립') || text.includes('설립')) {
                            const match = text.match(/설립[^\n]*\n?([^\n]+)/);
                            if (match) data.founded_year = match[1].trim();
                        }
                        // 대표자
                        if (imgAlt.includes('대표') || text.includes('대표')) {
                            const match = text.match(/대표[^\n]*\n?([^\n]+)/);
                            if (match) data.ceo = match[1].trim();
                        }
                        // 매출액
                        if (imgAlt.includes('매출') || text.includes('매출')) {
                            const match = text.match(/매출[^\n]*\n?([^\n]+)/);
                            if (match) data.revenue = match[1].trim();
                        }
                        // 주소
                        if (imgAlt.includes('주소') || text.includes('주소')) {
                            const match = text.match(/주소[^\n]*\n?([^\n]+)/);
                            if (match) data.address = match[1].trim();
                        }
                        // 홈페이지/웹사이트
                        if (imgAlt.includes('홈페이지') || imgAlt.includes('웹사이트') ||
                            text.includes('홈페이지') || text.includes('웹사이트')) {
                            const link = li.querySelector('a');
                            if (link) data.website = link.href;
                        }
                        // 연혁
                        if (imgAlt.includes('연혁') || text.includes('연혁')) {
                            const match = text.match(/연혁[^\n]*\n?([^\n]+)/);
                            if (match) data.history = match[1].trim();
                        }
                    });

                    return data;
                })())
            '''
            result_str = await page.evaluate(profile_js)
            if isinstance(result_str, str):
                data = json.loads(result_str)
                # dict인 경우에만 처리
                if isinstance(data, dict):
                    # 기존 정보 보완 (없는 경우에만 업데이트)
                    if data.get('industry') and not info.get('industry'):
                        info['industry'] = data['industry']
                    if data.get('company_type') and not info.get('company_type'):
                        info['company_type'] = data['company_type']
                    if data.get('employee_count') and not info.get('employee_count'):
                        info['employee_count'] = data['employee_count']
                    if data.get('founded_date') and not info.get('founded_date'):
                        info['founded_date'] = data['founded_year']
                    if data.get('ceo'):
                        info['ceo'] = data['ceo']
                    if data.get('revenue'):
                        info['revenue'] = data['revenue']
                    if data.get('address') and not info.get('address'):
                        info['address'] = data['address']
                    if data.get('website') and not info.get('website'):
                        info['website'] = data['website']
                    if data.get('history'):
                        info['history'] = data['history']

                    self.logger.info(f"  → 기업정보 추출: 산업 {data.get('industry')}, 사원수 {data.get('employee_count')}")

        except Exception as e:
            self.logger.debug(f"Landing extraction error: {e}")

    async def _extract_premium_reviews_data(self, page, info: Dict[str, Any]):
        """프리미엄 리뷰 페이지에서 Q&A 추출"""
        try:
            await self._close_popup(page)
            await asyncio.sleep(3)

            premium_data = {
                'categories': {},
                'category_counts': {},  # 카테고리별 총 문항 수
                'total_qna': []
            }

            # 카테고리 목록: 직무와 커리어, 업무 방식, 일과 삶의 균형, 복지 및 급여, 기업 만족도, 기업 문화 (6개)
            categories = ['직무와 커리어', '업무 방식', '일과 삶의 균형', '복지 및 급여', '기업 만족도', '기업 문화']

            for category in categories:
                try:
                    # 카테고리 버튼 클릭
                    click_cat_js = f'''
                        (() => {{
                            const buttons = document.querySelectorAll('button');
                            for (const btn of buttons) {{
                                if (btn.innerText.includes('{category}')) {{
                                    btn.click();
                                    return true;
                                }}
                            }}
                            return false;
                        }})()
                    '''
                    clicked = await page.evaluate(click_cat_js)
                    if not clicked:
                        continue

                    await asyncio.sleep(1)
                    await self._close_popup(page)

                    # 카테고리별 총 문항 수 추출: "OO의 프리미엄 리뷰 (총 10문항)"
                    count_js = f'''
                        (() => {{
                            const titleEl = document.querySelector('span[role="title"]');
                            if (titleEl) {{
                                const text = titleEl.innerText;
                                const match = text.match(/총\\s*(\\d+)\\s*문항/);
                                if (match) return parseInt(match[1]);
                            }}
                            return null;
                        }})()
                    '''
                    question_count = await page.evaluate(count_js)
                    if question_count:
                        premium_data['category_counts'][category] = question_count
                        self.logger.info(f"    → {category}: 총 {question_count}문항")

                    # "답변 더 보기" 버튼 모두 클릭 (최대 30번)
                    for _ in range(30):
                        more_btn_js = r'''
                            (() => {
                                const btns = document.querySelectorAll('button');
                                for (const btn of btns) {
                                    if (btn.innerText.includes('답변 더 보기')) {
                                        btn.click();
                                        return true;
                                    }
                                }
                                return false;
                            })()
                        '''
                        clicked = await page.evaluate(more_btn_js)
                        if not clicked:
                            break
                        await asyncio.sleep(0.3)

                    # Q&A 수집 (답변 선택지 비율, 연차별 데이터, 기타 의견 포함)
                    qna_js = r'''
                        JSON.stringify((() => {
                            const qnas = [];
                            const containers = document.querySelectorAll('.border-t.border-t-gray-50[class*="py-"], div[class*="border-t"][class*="py-[28px]"]');

                            containers.forEach(container => {
                                const qna = {
                                    category: '',
                                    question: '',
                                    answer_choices: [],  // 답변 선택지와 비율
                                    year_breakdown: {},  // 연차별 응답 결과
                                    other_opinions: []   // 기타 의견 (프로필 포함)
                                };

                                // 카테고리
                                const catEl = container.querySelector('[class*="bg-gray-50"][class*="text-gray-500"]');
                                if (catEl) qna.category = catEl.innerText.trim();

                                // 질문 (Q.)
                                const qEl = container.querySelector('.text-h7, [class*="text-h7"]');
                                if (qEl) {
                                    qna.question = qEl.innerText.replace(/^Q\.\s*/, '').trim();
                                }

                                // 답변 선택지와 비율 (A. 43%, B. 40% 등)
                                const choiceEls = container.querySelectorAll('li[class*="rounded-"][class*="border"]');
                                choiceEls.forEach(li => {
                                    const spans = li.querySelectorAll('span.relative');
                                    if (spans.length >= 2) {
                                        const text = spans[0].innerText.trim();
                                        const percent = spans[1].innerText.trim().replace('%', '');
                                        const labelMatch = text.match(/^([A-Z])\.\s*/);
                                        if (labelMatch) {
                                            qna.answer_choices.push({
                                                label: labelMatch[1],
                                                text: text.replace(/^[A-Z]\.\s*/, ''),
                                                percent: parseInt(percent) || 0
                                            });
                                        }
                                    }
                                });

                                // 연차별 응답 결과 탭
                                const yearTabs = container.querySelectorAll('ul.flex.border-b li button');
                                const currentYear = container.querySelector('ul.flex.border-b li.border-gray-700 button, ul.flex.border-b li[class*="border-b-[2px]"]:not([class*="border-transparent"]) button');
                                if (currentYear) {
                                    const yearLabel = currentYear.innerText.trim();
                                    const yearData = {};
                                    const bars = container.querySelectorAll('.group[class*="orange"], .group[class*="green"], .group[class*="blue"], .group[class*="purple"]');
                                    bars.forEach(bar => {
                                        const percentEl = bar.querySelector('[class*="w-[38px]"]');
                                        const labelEl = bar.querySelector('.item_index_text');
                                        if (percentEl && labelEl) {
                                            const label = labelEl.innerText.trim();
                                            const percent = percentEl.innerText.trim().replace('%', '');
                                            yearData[label] = parseInt(percent) || 0;
                                        }
                                    });
                                    if (Object.keys(yearData).length > 0) {
                                        qna.year_breakdown[yearLabel] = yearData;
                                    }
                                }

                                // 기타 의견 (프로필 정보 포함)
                                const opinionHeader = Array.from(container.querySelectorAll('div')).find(d => d.innerText.includes('기타 의견'));
                                if (opinionHeader) {
                                    const opinionItems = container.querySelectorAll('.py-\\[20px\\], div[class*="py-[20px]"]');
                                    opinionItems.forEach(item => {
                                        const profileEl = item.querySelector('.text-gray-400, [class*="text-gray-400"]');
                                        const contentEl = item.querySelector('.text-gray-800, [class*="text-gray-800"]');
                                        if (profileEl && contentEl) {
                                            qna.other_opinions.push({
                                                profile: profileEl.innerText.trim(),  // "영업/제휴 · 전직원 · 2024. 08."
                                                content: contentEl.innerText.trim().substring(0, 500)
                                            });
                                        }
                                    });
                                }

                                if (qna.question) {
                                    qnas.push(qna);
                                }
                            });

                            return qnas;
                        })())
                    '''
                    qna_str = await page.evaluate(qna_js)
                    if isinstance(qna_str, str):
                        qnas = json.loads(qna_str)
                        # list인 경우에만 처리
                        if isinstance(qnas, list) and qnas:
                            premium_data['categories'][category] = qnas
                            premium_data['total_qna'].extend(qnas)
                            self.logger.info(f"    → {category}: {len(qnas)}개 Q&A")

                except Exception as e:
                    self.logger.debug(f"Premium review category {category} error: {e}")
                    continue

            info['premium_reviews'] = premium_data
            info['premium_qna_count'] = len(premium_data['total_qna'])
            info['premium_category_counts'] = premium_data['category_counts']
            total_questions = sum(premium_data['category_counts'].values()) if premium_data['category_counts'] else 0
            self.logger.info(f"  → 프리미엄 리뷰 추출: {len(premium_data['total_qna'])}개 Q&A, {len(premium_data['categories'])}개 카테고리, 총 {total_questions}문항")

        except Exception as e:
            self.logger.debug(f"Premium reviews extraction error: {e}")

    def _extract_from_search_card(self, card, info: Dict[str, Any]):
        """검색 결과 카드에서 기본 정보 추출"""
        try:
            # 평점: <span class="ml-[2px] text-gray-800 ...">3.9</span>
            rating_elem = card.query_selector('span.text-gray-800')
            if rating_elem:
                rating_text = rating_elem.text_content().strip()
                rating_match = re.search(r'^(\d+\.?\d*)$', rating_text)
                if rating_match:
                    info['jobplanet_rating'] = float(rating_match.group(1))

            # 산업/지역: <div class="ml-[16px] text-gray-400 ...">제조/화학∙서울</div>
            industry_loc_elem = card.query_selector('div.text-gray-400')
            if industry_loc_elem:
                industry_loc_text = industry_loc_elem.text_content().strip()
                if '∙' in industry_loc_text:
                    parts = industry_loc_text.split('∙')
                    info['industry'] = parts[0].strip()
                    if len(parts) > 1:
                        info['location'] = parts[1].strip()
                else:
                    info['industry'] = industry_loc_text

            # 설립연도, 사원수
            info_spans = card.query_selector_all('span')
            for span in info_spans:
                span_text = span.text_content().strip()
                # 설립연도: "57년차 (1969)" 패턴
                founded_match = re.search(r'\((\d{4})\)', span_text)
                if founded_match:
                    info['founded_date'] = founded_match.group(1)
                # 사원수: "71666명" 패턴
                employee_match = re.match(r'^([\d,]+)명$', span_text)
                if employee_match:
                    info['employee_count'] = span_text

        except Exception as e:
            self.logger.debug(f"Error extracting card info: {e}")

    def _extract_reviews(self, page, base_url: str, info: Dict[str, Any]):
        """리뷰 페이지에서 정보 추출"""
        try:
            import time
            self.rate_limiter.wait()
            page.goto(f"{base_url}/reviews", wait_until='domcontentloaded', timeout=20000)
            time.sleep(2)

            # 리뷰 수 추출
            review_count_elem = page.query_selector('[class*="review"] [class*="count"], .review_count, h2:has-text("리뷰")')
            if review_count_elem:
                count_text = review_count_elem.text_content()
                count_match = re.search(r'([\d,]+)', count_text)
                if count_match:
                    info['review_count'] = int(count_match.group(1).replace(',', ''))

            # 장점/단점 키워드 추출
            pros_elems = page.query_selector_all('[class*="pros"], [class*="merit"], .good_point')
            for elem in pros_elems[:5]:
                text = elem.text_content().strip()
                if text and len(text) < 50:
                    info['pros_keywords'].append(text)

            cons_elems = page.query_selector_all('[class*="cons"], [class*="demerit"], .bad_point')
            for elem in cons_elems[:5]:
                text = elem.text_content().strip()
                if text and len(text) < 50:
                    info['cons_keywords'].append(text)

            self.logger.info(f"  → 리뷰 수집 완료: {info.get('review_count', 0)}건")

        except Exception as e:
            self.logger.debug(f"Error extracting reviews: {e}")

    def _extract_salaries(self, page, base_url: str, info: Dict[str, Any]):
        """연봉 페이지에서 정보 추출"""
        try:
            import time
            self.rate_limiter.wait()
            page.goto(f"{base_url}/salaries", wait_until='domcontentloaded', timeout=20000)
            time.sleep(2)

            # 평균 연봉 추출
            salary_elem = page.query_selector('[class*="salary"] [class*="average"], .average_salary, [class*="avg"]')
            if salary_elem:
                salary_text = salary_elem.text_content().strip()
                info['salary_info'] = salary_text

            # 직급별/직군별 연봉 테이블
            salary_rows = page.query_selector_all('table tr, [class*="salary_item"], [class*="salary-row"]')
            for row in salary_rows[:10]:
                try:
                    cells = row.query_selector_all('td, [class*="cell"]')
                    if len(cells) >= 2:
                        position = cells[0].text_content().strip()
                        salary = cells[1].text_content().strip()
                        if position and salary and '만원' in salary:
                            info['salary_by_position'].append({
                                'position': position,
                                'salary': salary
                            })
                except:
                    continue

            self.logger.info(f"  → 연봉 정보 수집 완료")

        except Exception as e:
            self.logger.debug(f"Error extracting salaries: {e}")

    def _extract_interviews(self, page, base_url: str, info: Dict[str, Any]):
        """면접 페이지에서 정보 추출"""
        try:
            import time
            self.rate_limiter.wait()
            page.goto(f"{base_url}/interviews", wait_until='domcontentloaded', timeout=20000)
            time.sleep(2)

            # 면접 후기 수
            interview_count_elem = page.query_selector('[class*="interview"] [class*="count"], .interview_count')
            if interview_count_elem:
                count_text = interview_count_elem.text_content()
                count_match = re.search(r'([\d,]+)', count_text)
                if count_match:
                    info['interview_count'] = int(count_match.group(1).replace(',', ''))

            # 면접 난이도
            difficulty_elem = page.query_selector('[class*="difficulty"], [class*="level"]')
            if difficulty_elem:
                info['interview_difficulty'] = difficulty_elem.text_content().strip()

            # 면접 경험 (긍정/부정/보통)
            experience_elem = page.query_selector('[class*="experience"], [class*="feeling"]')
            if experience_elem:
                info['interview_experience'] = experience_elem.text_content().strip()

            # 합격률
            success_elem = page.query_selector('[class*="success"], [class*="pass_rate"], [class*="result"]')
            if success_elem:
                success_text = success_elem.text_content()
                rate_match = re.search(r'(\d+)%', success_text)
                if rate_match:
                    info['interview_success_rate'] = f"{rate_match.group(1)}%"

            self.logger.info(f"  → 면접 정보 수집 완료: {info.get('interview_count', 0)}건")

        except Exception as e:
            self.logger.debug(f"Error extracting interviews: {e}")

    def _extract_benefits(self, page, base_url: str, info: Dict[str, Any]):
        """복지 페이지에서 정보 추출"""
        try:
            import time
            self.rate_limiter.wait()
            page.goto(f"{base_url}/benefits", wait_until='domcontentloaded', timeout=20000)
            time.sleep(2)

            # 복지 항목 추출
            benefit_elems = page.query_selector_all('[class*="benefit"], [class*="welfare"], .benefit_item, li')
            seen = set()
            for elem in benefit_elems[:30]:
                try:
                    text = elem.text_content().strip()
                    # 복지 관련 키워드가 포함된 항목만
                    if text and len(text) < 100 and text not in seen:
                        # 일반적인 복지 키워드 체크
                        welfare_keywords = ['식', '보험', '휴가', '지원', '수당', '복지', '건강',
                                          '교육', '포인트', '카페', '헬스', '통근', '주차']
                        if any(kw in text for kw in welfare_keywords):
                            info['benefits'].append(text)
                            seen.add(text)
                except:
                    continue

            self.logger.info(f"  → 복지 정보 수집 완료: {len(info['benefits'])}개")

        except Exception as e:
            self.logger.debug(f"Error extracting benefits: {e}")

    def _extract_job_postings(self, page, base_url: str, info: Dict[str, Any]):
        """채용공고 페이지에서 정보 추출"""
        try:
            import time
            self.rate_limiter.wait()
            page.goto(f"{base_url}/job_postings", wait_until='domcontentloaded', timeout=20000)
            time.sleep(2)

            # 채용공고 수
            job_count_elem = page.query_selector('[class*="job"] [class*="count"], .job_count, [class*="total"]')
            if job_count_elem:
                count_text = job_count_elem.text_content()
                count_match = re.search(r'([\d,]+)', count_text)
                if count_match:
                    info['active_job_count'] = int(count_match.group(1).replace(',', ''))

            # 채용공고 카드 수로 대체
            if not info['active_job_count']:
                job_cards = page.query_selector_all('[class*="job_card"], [class*="job-item"], .posting_item')
                if job_cards:
                    info['active_job_count'] = len(job_cards)

            self.logger.info(f"  → 채용공고 수집 완료: {info.get('active_job_count', 0)}건")

        except Exception as e:
            self.logger.debug(f"Error extracting job postings: {e}")
    
    def _generate_summary(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """분석 결과 요약 생성"""
        basic_info = analysis.get('basic_info', {})
        job_stats = analysis.get('job_stats', {})
        reputation = analysis.get('reputation', {})
        salary_info = analysis.get('salary_info', {})
        interview_info = analysis.get('interview_info', {})
        benefits = analysis.get('benefits', [])

        # 기본 정보 요약
        info_parts = []
        if basic_info.get('industry'):
            info_parts.append(f"산업: {basic_info['industry']}")
        if basic_info.get('location'):
            info_parts.append(f"지역: {basic_info['location']}")
        if basic_info.get('company_type'):
            info_parts.append(f"형태: {basic_info['company_type']}")
        if basic_info.get('employee_count'):
            info_parts.append(f"사원수: {basic_info['employee_count']}")
        if basic_info.get('founded_date'):
            info_parts.append(f"설립: {basic_info['founded_date']}")
        if basic_info.get('revenue'):
            info_parts.append(f"매출: {basic_info['revenue']}")

        basic_summary = ' | '.join(info_parts) if info_parts else "기본 정보 없음"

        # 채용 현황 요약
        job_summary_parts = []
        total = job_stats.get('total_postings', 0)
        if total > 0:
            job_summary_parts.append(f"DB 채용공고 {total}건")
            top_skills = job_stats.get('top_skills', [])[:3]
            if top_skills:
                skills_str = ', '.join([s['skill'] for s in top_skills])
                job_summary_parts.append(f"주요 스킬: {skills_str}")
        jp_jobs = analysis.get('jobplanet_job_count')
        if jp_jobs:
            job_summary_parts.append(f"잡플래닛 채용 중 {jp_jobs}건")

        job_summary = ' | '.join(job_summary_parts) if job_summary_parts else "채용공고 없음"

        # 평판 요약
        reputation_parts = []
        if reputation.get('jobplanet_rating'):
            reputation_parts.append(f"평점 {reputation['jobplanet_rating']}/5.0")
        if reputation.get('review_count'):
            reputation_parts.append(f"리뷰 {reputation['review_count']}건")
        if reputation.get('pros_keywords'):
            reputation_parts.append(f"장점: {', '.join(reputation['pros_keywords'][:3])}")
        if reputation.get('cons_keywords'):
            reputation_parts.append(f"단점: {', '.join(reputation['cons_keywords'][:3])}")

        reputation_summary = ' | '.join(reputation_parts) if reputation_parts else "평판 정보 없음"

        # 연봉 요약
        salary_summary = "연봉 정보 없음"
        if salary_info.get('average'):
            salary_summary = f"평균 연봉: {salary_info['average']}"
            if salary_info.get('by_position'):
                positions = [f"{p['position']}: {p['salary']}" for p in salary_info['by_position'][:3]]
                salary_summary += f" | {', '.join(positions)}"

        # 면접 요약
        interview_parts = []
        if interview_info.get('count'):
            interview_parts.append(f"면접 후기 {interview_info['count']}건")
        if interview_info.get('difficulty'):
            interview_parts.append(f"난이도: {interview_info['difficulty']}")
        if interview_info.get('success_rate'):
            interview_parts.append(f"합격률: {interview_info['success_rate']}")

        interview_summary = ' | '.join(interview_parts) if interview_parts else "면접 정보 없음"

        # 복지 요약
        benefits_summary = "복지 정보 없음"
        if benefits:
            benefits_summary = ', '.join(benefits[:5])
            if len(benefits) > 5:
                benefits_summary += f" 외 {len(benefits) - 5}개"

        # 종합 평가
        overall = "정보 부족"
        if reputation.get('jobplanet_rating'):
            rating = reputation['jobplanet_rating']
            if rating >= 4.0:
                overall = "매우 좋음"
            elif rating >= 3.5:
                overall = "좋음"
            elif rating >= 3.0:
                overall = "보통"
            elif rating >= 2.5:
                overall = "주의 필요"
            else:
                overall = "신중한 검토 필요"
        elif total > 10:
            overall = "활발한 채용 중"

        return {
            'basic': basic_summary,
            'jobs': job_summary,
            'reputation': reputation_summary,
            'salary': salary_summary,
            'interview': interview_summary,
            'benefits': benefits_summary,
            'overall': overall,
        }

    def _save_to_db(self, analysis: Dict[str, Any]):
        """분석 결과 DB 저장"""
        try:
            basic_info = analysis.get('basic_info', {})
            reputation = analysis.get('reputation', {})
            summary = analysis.get('summary', {})
            salary_info = analysis.get('salary_info', {})
            interview_info = analysis.get('interview_info', {})
            benefits = analysis.get('benefits', [])

            # raw_data가 있으면 파일로 저장
            raw_data_files = {}
            raw_data = analysis.get('raw_data', {})
            if raw_data:
                raw_data_files = self._save_raw_data_to_files(analysis['company_name'], raw_data)

            # JSON으로 저장할 추가 정보
            import json
            additional_info = {
                'salary': salary_info,
                'interview': interview_info,
                'benefits': benefits,
                'pros_keywords': reputation.get('pros_keywords', []),
                'cons_keywords': reputation.get('cons_keywords', []),
                'review_count': reputation.get('review_count'),
                'jobplanet_job_count': analysis.get('jobplanet_job_count'),
                'raw_data_files': raw_data_files,  # 저장된 파일 경로
                # 탭별 텍스트 요약 (디버깅용, 문자열만)
                'tab_texts': {k: v[:5000] for k, v in raw_data.items() if k.endswith('_text') and isinstance(v, str)},
            }

            company_data = {
                'name': analysis['company_name'],
                'industry': basic_info.get('industry'),
                'company_size': basic_info.get('company_type'),
                'location': basic_info.get('location'),
                'address': basic_info.get('address'),
                'website': basic_info.get('website'),
                'founded_year': self._extract_year(basic_info.get('founded_date')),
                'employee_count': self._extract_number(basic_info.get('employee_count')),
                'revenue': basic_info.get('revenue'),
                'jobplanet_rating': reputation.get('jobplanet_rating'),
                'jobplanet_url': reputation.get('jobplanet_url'),
                'public_sentiment': summary.get('overall'),
                'additional_info': json.dumps(additional_info, ensure_ascii=False),
            }

            self.db.add_company(company_data)
            self.logger.info(f"  → 회사 최종 정보 DB 업데이트 완료")
            # 참고: 개별 리뷰, 면접 후기, 복지 후기는 탭별로 이미 저장됨

        except Exception as e:
            self.logger.error(f"Error saving to DB: {e}")

    def _save_raw_data_to_files(self, company_name: str, raw_data: Dict[str, str]) -> Dict[str, str]:
        """raw data (HTML, 텍스트)를 파일로 저장"""
        import os
        from datetime import datetime

        # 저장 디렉토리 생성
        base_dir = Path(__file__).parent.parent / 'data' / 'raw_html'
        base_dir.mkdir(parents=True, exist_ok=True)

        # 회사명 정규화 (파일명에 사용 가능하도록)
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', company_name)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        saved_files = {}

        for key, content in raw_data.items():
            # 문자열이 아니거나 빈 내용은 건너뛰기
            if not isinstance(content, str) or not content:
                continue

            # 파일 확장자 결정
            ext = '.html' if key.endswith('_html') else '.txt'
            filename = f"{safe_name}_{key}_{timestamp}{ext}"
            filepath = base_dir / filename

            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                saved_files[key] = str(filepath)
                self.logger.info(f"  → 저장됨: {filename} ({len(content):,}자)")
            except Exception as e:
                self.logger.warning(f"파일 저장 실패 {filename}: {e}")

        return saved_files

    def _extract_year(self, date_str: str) -> Optional[int]:
        """날짜 문자열에서 연도 추출"""
        if not date_str:
            return None
        match = re.search(r'(\d{4})', date_str)
        return int(match.group(1)) if match else None

    def _extract_number(self, num_str: str) -> Optional[int]:
        """문자열에서 숫자 추출 (예: '115명' -> 115)"""
        if not num_str:
            return None
        match = re.search(r'([\d,]+)', num_str.replace(',', ''))
        return int(match.group(1)) if match else None

    def get_top_hiring_companies(self, keyword: str = None, days: int = 30, limit: int = 20) -> List[Dict[str, Any]]:
        """채용공고가 많은 상위 회사 목록"""
        session = self.db.get_session()

        try:
            from datetime import timedelta
            from sqlalchemy import func

            query = session.query(
                JobPosting.company_name,
                func.count(JobPosting.id).label('job_count')
            )

            if keyword:
                query = query.filter(
                    (JobPosting.title.ilike(f"%{keyword}%")) |
                    (JobPosting.description.ilike(f"%{keyword}%"))
                )

            # 최근 N일
            from utils.database import get_kst_now
            cutoff = get_kst_now() - timedelta(days=days)
            query = query.filter(JobPosting.crawled_at >= cutoff)

            results = query.group_by(JobPosting.company_name)\
                .order_by(func.count(JobPosting.id).desc())\
                .limit(limit)\
                .all()

            return [
                {'company_name': r[0], 'job_count': r[1]}
                for r in results
            ]

        finally:
            session.close()

    def analyze_companies_batch(self, company_names: List[str]) -> List[Dict[str, Any]]:
        """여러 회사 일괄 분석"""
        results = []

        for company_name in company_names:
            try:
                result = self.analyze_company(company_name)
                results.append(result)
            except Exception as e:
                self.logger.error(f"Error analyzing {company_name}: {e}")
                results.append({
                    'company_name': company_name,
                    'error': str(e)
                })

        return results


# 테스트용
if __name__ == "__main__":
    analyzer = CompanyAnalyzer()

    # 채용 많은 회사 조회
    top_companies = analyzer.get_top_hiring_companies(keyword="백엔드", limit=10)
    print("채용 많은 회사:")
    for c in top_companies:
        print(f"  {c['company_name']}: {c['job_count']}건")

    # 특정 회사 분석
    if top_companies:
        result = analyzer.analyze_company(top_companies[0]['company_name'])
        print(f"\n회사 분석: {result['company_name']}")
        print(f"요약: {result.get('summary', {})}")
