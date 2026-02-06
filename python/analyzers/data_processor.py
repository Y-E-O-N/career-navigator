"""
데이터 정제 모듈

수집된 원시 데이터를 분석 가능한 형태로 정제합니다:
- 리뷰: 통계 계산, 키워드 추출, 트렌드 분석
- 면접: 난이도 통계, 질문 유형 분류, 합격률 계산
- 급여: 업계 비교, 경력별 분포
- 복리후생: 카테고리별 평점, 강점/약점 분류
- 뉴스: 기사 유형 분류, 신뢰도 등급 부여
- 스킬: JD 스킬과 트렌드 매칭
"""

import re
import logging
from collections import Counter
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from statistics import mean, median

from utils.database import get_kst_now
from analyzers.models import (
    AnalysisDataBundle,
    ProcessedReviews,
    ProcessedInterviews,
    ProcessedSalaries,
    ProcessedBenefits,
    ProcessedNews,
    SkillAnalysis
)

logger = logging.getLogger(__name__)


class DataProcessor:
    """수집된 원시 데이터를 분석 가능한 형태로 정제"""

    # 리뷰 키워드 추출용 불용어
    STOPWORDS = {
        '있음', '없음', '있다', '없다', '하는', '되는', '것이', '수가', '때문',
        '정도', '하고', '있고', '되고', '같은', '통해', '위해', '대한', '하면',
        '있는', '되는', '않는', '좋은', '나쁜', '많은', '적은', '높은', '낮은',
        '회사', '직원', '업무', '일을', '하는', '있어', '없어', '해서', '하지',
        '그리고', '하지만', '그러나', '그래서', '따라서', '또한', '그냥', '매우',
        '정말', '너무', '아주', '굉장히', '상당히', '꽤', '조금', '약간'
    }

    # 면접 질문 유형 분류용 키워드
    QUESTION_TYPE_KEYWORDS = {
        '기술': [
            'python', 'java', 'sql', '알고리즘', '자료구조', '코딩', '구현',
            'api', '데이터베이스', '서버', '프론트', '백엔드', '클라우드',
            'aws', '쿠버네티스', 'docker', '머신러닝', 'ml', 'ai', '딥러닝',
            '기술', '개발', '설계', '아키텍처', '시스템', '프레임워크'
        ],
        '행동': [
            '경험', '했을 때', '어떻게 했', '해결했', '대처했', '겪었',
            '사례', '성과', '실패', '성공', '갈등', '협업', '리더십',
            '문제 상황', '어려움', '극복', '배운 점'
        ],
        '상황': [
            '만약', '가정', '상황에서', '어떻게 할', '한다면', '경우에',
            '가상', '시나리오', '상황이 주어진다면'
        ],
        '컬쳐핏': [
            '지원 동기', '왜', '회사', '비전', '가치관', '문화', '팀',
            '장단점', '강점', '약점', '목표', '계획', '이유', '관심',
            '본인', '자신', '성격', '스타일'
        ]
    }

    # 뉴스 기사 유형 분류용 키워드
    NEWS_TYPE_KEYWORDS = {
        'PR/보도자료': [
            '출시', '런칭', '오픈', '선보', '발표', '공개', '서비스 시작',
            '신제품', '업데이트', '기능 추가', '파트너십', '제휴', '협약',
            '수상', '인증', '선정'
        ],
        '실적/투자': [
            '투자', '유치', '시리즈', '라운드', '밸류에이션', '기업가치',
            '매출', '영업이익', '순이익', '흑자', '적자', '성장률',
            'ipo', '상장', '인수', '합병', 'm&a'
        ],
        '인사/조직': [
            '대표', 'ceo', '임원', '영입', '선임', '취임', '사임', '퇴임',
            '조직개편', '구조조정', '인력', '채용', '정리해고', '희망퇴직'
        ],
        '사건/이슈': [
            '논란', '의혹', '조사', '수사', '기소', '고발', '소송',
            '사고', '피해', '문제', '비판', '갈등', '파업', '분쟁'
        ],
        '산업분석': [
            '시장', '전망', '트렌드', '분석', '리포트', '보고서',
            '업계', '경쟁', '점유율', '동향', '전략', '방향'
        ],
        'CEO/임원 인터뷰': [
            '인터뷰', '대담', '간담회', '"', '밝혔다', '말했다', '강조했다'
        ]
    }

    # 뉴스 매체별 신뢰도
    NEWS_SOURCE_RELIABILITY = {
        'high': ['한국경제', '매일경제', '조선비즈', '동아비즈', '이데일리', '머니투데이'],
        'medium': ['연합뉴스', '뉴시스', '뉴스1', 'yna'],
        'low': ['블로터', '플래텀', '벤처스퀘어']  # PR 비중 높음
    }

    def process_all(self, data_bundle: AnalysisDataBundle) -> AnalysisDataBundle:
        """모든 데이터 정제 수행"""
        logger.info("데이터 정제 시작...")

        # 리뷰 정제
        if data_bundle.reviews:
            data_bundle.processed_reviews = self.process_reviews(data_bundle.reviews)
            logger.info(f"[C] 리뷰 정제 완료: {data_bundle.processed_reviews.total_count}건")

        # 면접 후기 정제
        if data_bundle.interviews:
            data_bundle.processed_interviews = self.process_interviews(data_bundle.interviews)
            logger.info(f"[D] 면접 정제 완료: {data_bundle.processed_interviews.total_count}건")

        # 급여 정제
        if data_bundle.salaries:
            data_bundle.processed_salaries = self.process_salaries(data_bundle.salaries)
            logger.info(f"[E] 급여 정제 완료: {data_bundle.processed_salaries.total_count}건")

        # 복리후생 정제
        if data_bundle.benefits:
            data_bundle.processed_benefits = self.process_benefits(data_bundle.benefits)
            logger.info(f"[F] 복리후생 정제 완료: {data_bundle.processed_benefits.total_count}건")

        # 뉴스 정제
        if data_bundle.news:
            data_bundle.processed_news = self.process_news(data_bundle.news)
            logger.info(f"[G] 뉴스 정제 완료: {data_bundle.processed_news.total_count}건")

        # 스킬 분석
        if data_bundle.job_postings:
            data_bundle.skill_analysis = self.analyze_skills(
                data_bundle.job_postings,
                data_bundle.skill_trends
            )
            logger.info(f"[B+I] 스킬 분석 완료")

        logger.info("데이터 정제 완료")
        return data_bundle

    def process_reviews(self, reviews: List[dict]) -> ProcessedReviews:
        """
        리뷰 데이터 정제

        - 평점 통계 (평균, 분포)
        - category_scores 항목별 통계
        - pros/cons 키워드 빈도 분석
        - advice 패턴 추출
        - 시기별 트렌드
        - 직군별 분석
        """
        result = ProcessedReviews(
            total_count=len(reviews),
            raw_reviews=reviews
        )

        if not reviews:
            return result

        # 1. 평점 통계
        ratings = [r.get('total_rating') for r in reviews if r.get('total_rating')]
        if ratings:
            result.avg_rating = round(mean(ratings), 2)
            result.rating_distribution = dict(Counter(int(r) for r in ratings))

        # 2. category_scores 통계
        result.category_score_stats = self._calculate_category_score_stats(reviews)

        # 3. 키워드 분석
        pros_texts = [r.get('pros', '') for r in reviews if r.get('pros')]
        cons_texts = [r.get('cons', '') for r in reviews if r.get('cons')]
        advice_texts = [r.get('advice', '') for r in reviews if r.get('advice')]

        result.pros_keywords = self._extract_keywords(pros_texts, top_n=15)
        result.cons_keywords = self._extract_keywords(cons_texts, top_n=15)
        result.advice_patterns = self._extract_advice_patterns(advice_texts)

        # 4. 시기별 트렌드 (반기별)
        result.trend_by_period = self._calculate_rating_trend(reviews)

        # 5. 직군별 분석
        result.by_job_category = self._analyze_by_job_category(reviews)

        return result

    def _calculate_category_score_stats(self, reviews: List[dict]) -> Dict[str, Dict[str, float]]:
        """category_scores 항목별 통계 계산"""
        category_scores_list: Dict[str, List[float]] = {}

        for review in reviews:
            scores = review.get('category_scores')
            if not scores or not isinstance(scores, dict):
                continue

            for category, score in scores.items():
                if score is not None:
                    if category not in category_scores_list:
                        category_scores_list[category] = []
                    category_scores_list[category].append(float(score))

        stats = {}
        for category, scores in category_scores_list.items():
            if scores:
                stats[category] = {
                    'avg': round(mean(scores), 2),
                    'median': round(median(scores), 2),
                    'min': min(scores),
                    'max': max(scores),
                    'count': len(scores)
                }

        return stats

    def _extract_keywords(self, texts: List[str], top_n: int = 10) -> List[Tuple[str, int]]:
        """텍스트에서 키워드 추출 (빈도 기반)"""
        # 한글 단어 추출 (2글자 이상)
        word_pattern = re.compile(r'[가-힣]{2,}')
        word_counter = Counter()

        for text in texts:
            if not text:
                continue
            words = word_pattern.findall(text)
            # 불용어 제거
            words = [w for w in words if w not in self.STOPWORDS and len(w) >= 2]
            word_counter.update(words)

        return word_counter.most_common(top_n)

    def _extract_advice_patterns(self, advice_texts: List[str], top_n: int = 5) -> List[str]:
        """경영진에게 바라는 점에서 주요 패턴 추출"""
        # 키워드 기반 패턴 분류
        patterns = {
            '소통/커뮤니케이션': ['소통', '커뮤니케이션', '의사소통', '피드백', '경청'],
            '급여/보상': ['급여', '연봉', '인상', '보상', '성과급', '인센티브'],
            '복지/근무환경': ['복지', '워라밸', '야근', '근무시간', '휴가', '재택'],
            '성장/발전': ['성장', '발전', '교육', '역량', '커리어', '승진'],
            '조직문화': ['문화', '분위기', '수평', '수직', '권위', '자율'],
            '비전/방향성': ['비전', '방향', '전략', '목표', '사업']
        }

        pattern_counts = {p: 0 for p in patterns}

        for text in advice_texts:
            if not text:
                continue
            text_lower = text.lower()
            for pattern, keywords in patterns.items():
                if any(kw in text_lower for kw in keywords):
                    pattern_counts[pattern] += 1

        # 상위 패턴 반환
        sorted_patterns = sorted(pattern_counts.items(), key=lambda x: x[1], reverse=True)
        return [p[0] for p in sorted_patterns[:top_n] if p[1] > 0]

    def _calculate_rating_trend(self, reviews: List[dict]) -> Dict[str, float]:
        """시기별 평점 트렌드 계산"""
        period_ratings: Dict[str, List[float]] = {}

        for review in reviews:
            write_date = review.get('write_date', '')
            rating = review.get('total_rating')

            if not write_date or not rating:
                continue

            # "2021. 05" 형태에서 년도-반기 추출
            match = re.search(r'(\d{4})\.\s*(\d{1,2})', write_date)
            if match:
                year = match.group(1)
                month = int(match.group(2))
                half = 'H1' if month <= 6 else 'H2'
                period = f"{year}-{half}"

                if period not in period_ratings:
                    period_ratings[period] = []
                period_ratings[period].append(float(rating))

        # 기간별 평균 계산
        trend = {}
        for period in sorted(period_ratings.keys()):
            ratings = period_ratings[period]
            trend[period] = round(mean(ratings), 2)

        return trend

    def _analyze_by_job_category(self, reviews: List[dict]) -> Dict[str, Dict[str, Any]]:
        """직군별 분석"""
        by_category: Dict[str, List[dict]] = {}

        for review in reviews:
            category = review.get('job_category', '기타')
            if not category:
                category = '기타'

            if category not in by_category:
                by_category[category] = []
            by_category[category].append(review)

        result = {}
        for category, cat_reviews in by_category.items():
            ratings = [r.get('total_rating') for r in cat_reviews if r.get('total_rating')]
            result[category] = {
                'count': len(cat_reviews),
                'avg_rating': round(mean(ratings), 2) if ratings else 0,
                'keywords_pros': self._extract_keywords(
                    [r.get('pros', '') for r in cat_reviews], top_n=5
                ),
                'keywords_cons': self._extract_keywords(
                    [r.get('cons', '') for r in cat_reviews], top_n=5
                )
            }

        return result

    def process_interviews(self, interviews: List[dict]) -> ProcessedInterviews:
        """
        면접 후기 정제

        - 난이도 분포
        - 질문 유형 분류
        - 합격률 계산
        - 직군별 분석
        """
        result = ProcessedInterviews(
            total_count=len(interviews),
            raw_interviews=interviews
        )

        if not interviews:
            return result

        # 1. 난이도 분포
        difficulty_map = {
            '쉬움': 1, '보통': 2, '어려움': 3, '매우 어려움': 4,
            '1': 1, '2': 2, '3': 3, '4': 4, '5': 5
        }

        difficulties = []
        for interview in interviews:
            diff = interview.get('difficulty', '')
            if diff in difficulty_map:
                difficulties.append(difficulty_map[diff])
            result.difficulty_distribution[diff] = result.difficulty_distribution.get(diff, 0) + 1

        if difficulties:
            result.avg_difficulty = round(mean(difficulties), 2)

        # 2. 질문 유형 분류
        result.question_types = self._classify_questions(interviews)

        # 3. 합격률 계산
        result.result_distribution = self._calculate_result_distribution(interviews)
        total_with_result = sum(result.result_distribution.values())
        pass_count = result.result_distribution.get('합격', 0) + result.result_distribution.get('최종합격', 0)
        if total_with_result > 0:
            result.pass_rate = round(pass_count / total_with_result * 100, 1)

        # 4. 직군별 분석
        result.by_job_category = self._analyze_interviews_by_category(interviews)

        return result

    def _classify_questions(self, interviews: List[dict]) -> Dict[str, List[str]]:
        """면접 질문을 유형별로 분류"""
        classified = {
            '기술': [],
            '행동': [],
            '상황': [],
            '컬쳐핏': [],
            '기타': []
        }

        for interview in interviews:
            question = interview.get('question', '')
            if not question:
                continue

            question_lower = question.lower()
            matched = False

            for q_type, keywords in self.QUESTION_TYPE_KEYWORDS.items():
                if any(kw in question_lower for kw in keywords):
                    # 중복 방지
                    if question not in classified[q_type]:
                        classified[q_type].append(question[:200])  # 길이 제한
                    matched = True
                    break

            if not matched and question not in classified['기타']:
                classified['기타'].append(question[:200])

        return classified

    def _calculate_result_distribution(self, interviews: List[dict]) -> Dict[str, int]:
        """면접 결과 분포 계산"""
        result_counter = Counter()

        for interview in interviews:
            result = interview.get('result', '')
            if result:
                # 정규화
                if '합격' in result:
                    if '불합격' in result:
                        result_counter['불합격'] += 1
                    elif '최종' in result:
                        result_counter['최종합격'] += 1
                    else:
                        result_counter['합격'] += 1
                elif '불합격' in result or '탈락' in result:
                    result_counter['불합격'] += 1
                elif '대기' in result or '진행' in result:
                    result_counter['진행중'] += 1
                else:
                    result_counter[result] += 1

        return dict(result_counter)

    def _analyze_interviews_by_category(self, interviews: List[dict]) -> Dict[str, Dict[str, Any]]:
        """직군별 면접 분석"""
        by_category: Dict[str, List[dict]] = {}

        for interview in interviews:
            category = interview.get('job_category', '기타')
            if not category:
                category = '기타'

            if category not in by_category:
                by_category[category] = []
            by_category[category].append(interview)

        result = {}
        for category, cat_interviews in by_category.items():
            questions = [i.get('question', '') for i in cat_interviews if i.get('question')]
            result[category] = {
                'count': len(cat_interviews),
                'sample_questions': questions[:5],  # 샘플 질문
                'difficulty_avg': self._calc_avg_difficulty(cat_interviews)
            }

        return result

    def _calc_avg_difficulty(self, interviews: List[dict]) -> float:
        """평균 난이도 계산"""
        difficulty_map = {'쉬움': 1, '보통': 2, '어려움': 3, '매우 어려움': 4}
        difficulties = []

        for i in interviews:
            diff = i.get('difficulty', '')
            if diff in difficulty_map:
                difficulties.append(difficulty_map[diff])

        return round(mean(difficulties), 2) if difficulties else 0

    def process_salaries(self, salaries: List[dict]) -> ProcessedSalaries:
        """
        급여 데이터 정제

        - 전체 평균 및 업계 비교
        - 경력별/직급별 분포
        """
        result = ProcessedSalaries(
            total_count=len(salaries),
            raw_salaries=salaries
        )

        if not salaries:
            return result

        # 전체 평균 찾기
        for s in salaries:
            if s.get('is_overall_avg'):
                result.overall_avg = s.get('salary_amount')
                result.industry_avg = s.get('industry_avg')

                if result.overall_avg and result.industry_avg:
                    diff = result.overall_avg - result.industry_avg
                    result.vs_industry_percent = round(diff / result.industry_avg * 100, 1)

                result.salary_min = s.get('salary_min')
                result.salary_max = s.get('salary_max')
                result.salary_lower = s.get('salary_lower')
                result.salary_upper = s.get('salary_upper')
                break

        # 경력별 급여
        for s in salaries:
            if not s.get('is_overall_avg') and s.get('experience_year'):
                exp = s.get('experience_year')
                amount = s.get('salary_amount')
                if amount:
                    result.by_experience[exp] = amount

        # 직급별 급여
        for s in salaries:
            if not s.get('is_overall_avg') and s.get('position'):
                pos = s.get('position')
                amount = s.get('salary_amount')
                if amount:
                    result.by_position[pos] = amount

        return result

    def process_benefits(self, benefits: List[dict]) -> ProcessedBenefits:
        """
        복리후생 데이터 정제

        - 카테고리별 평점
        - 강점/약점 분류
        """
        result = ProcessedBenefits(
            total_count=len(benefits),
            raw_benefits=benefits
        )

        if not benefits:
            return result

        # 카테고리별 그룹화
        by_category: Dict[str, List[dict]] = {}
        for b in benefits:
            cat = b.get('category', '기타')
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(b)

        # 카테고리별 평점 계산
        for cat, items in by_category.items():
            ratings = [i.get('category_rating') for i in items if i.get('category_rating')]
            if ratings:
                result.category_ratings[cat] = round(mean(ratings), 2)

            # 항목별 점수
            category_items = []
            for item in items:
                item_scores = item.get('item_scores')
                if item_scores and isinstance(item_scores, dict):
                    for item_name, score in item_scores.items():
                        category_items.append({'item': item_name, 'score': score})

            if category_items:
                result.category_items[cat] = sorted(
                    category_items, key=lambda x: x.get('score', 0), reverse=True
                )[:5]

        # 강점/약점 분류 (상위 3개 / 하위 3개)
        if result.category_ratings:
            sorted_cats = sorted(result.category_ratings.items(), key=lambda x: x[1], reverse=True)
            result.strongest_categories = [c[0] for c in sorted_cats[:3]]
            result.weakest_categories = [c[0] for c in sorted_cats[-3:]]

        return result

    def process_news(self, news: List[dict]) -> ProcessedNews:
        """
        뉴스 데이터 정제

        - 기사 유형 분류
        - 신뢰도 등급 부여
        - 시간순 정렬
        """
        result = ProcessedNews(
            total_count=len(news),
            raw_news=news
        )

        if not news:
            return result

        # 기사 유형 분류 및 신뢰도 등급 부여
        for article in news:
            # 유형 분류
            article_type = self._classify_news_type(article)
            article['_type'] = article_type

            # 신뢰도 등급 부여
            reliability = self._assess_news_reliability(article)
            article['_reliability'] = reliability

            # 유형별 그룹화
            if article_type not in result.by_type:
                result.by_type[article_type] = []
            result.by_type[article_type].append(article)

            # 신뢰도별 그룹화
            if reliability not in result.by_reliability:
                result.by_reliability[reliability] = []
            result.by_reliability[reliability].append(article)

        # 시간순 정렬 (최신순)
        result.timeline = sorted(
            news,
            key=lambda x: x.get('published_at', ''),
            reverse=True
        )

        # 최근 6개월 기사 (KST 기준)
        six_months_ago = (get_kst_now() - timedelta(days=180)).strftime('%Y-%m-%d')
        result.recent_news = [
            n for n in result.timeline
            if n.get('published_at', '') >= six_months_ago
        ]

        return result

    def _classify_news_type(self, article: dict) -> str:
        """뉴스 기사 유형 분류"""
        title = (article.get('title', '') or '').lower()
        content = (article.get('content', '') or '').lower()
        text = f"{title} {content}"

        for news_type, keywords in self.NEWS_TYPE_KEYWORDS.items():
            if any(kw.lower() in text for kw in keywords):
                return news_type

        return '일반보도'

    def _assess_news_reliability(self, article: dict) -> str:
        """뉴스 신뢰도 등급 부여"""
        source = (article.get('source_site', '') or '').lower()
        article_type = article.get('_type', '')

        # 기사 유형에 따른 기본 신뢰도
        if article_type in ['사건/이슈', '실적/투자', '인사/조직', '산업분석']:
            base_reliability = 'G+'
        elif article_type == 'PR/보도자료':
            base_reliability = 'G-'
        else:
            base_reliability = 'G'

        # 매체에 따른 조정
        for reliability, sources in self.NEWS_SOURCE_RELIABILITY.items():
            if any(s.lower() in source for s in sources):
                if reliability == 'high' and base_reliability == 'G':
                    return 'G+'
                elif reliability == 'low' and base_reliability == 'G':
                    return 'G-'
                break

        return base_reliability

    def analyze_skills(
        self,
        job_postings: List[dict],
        skill_trends: Optional[List[dict]] = None
    ) -> SkillAnalysis:
        """
        JD 스킬과 시장 트렌드 매칭 분석

        - required/preferred 스킬 추출
        - 트렌드 데이터와 매칭
        - 상승/하락 분류
        """
        result = SkillAnalysis()

        # JD에서 스킬 추출
        for jp in job_postings:
            required = jp.get('required_skills') or []
            preferred = jp.get('preferred_skills') or []

            if isinstance(required, list):
                result.required_skills.extend(required)
            if isinstance(preferred, list):
                result.preferred_skills.extend(preferred)

        # 중복 제거
        result.required_skills = list(set(result.required_skills))
        result.preferred_skills = list(set(result.preferred_skills))

        # 트렌드 매칭
        if skill_trends:
            trend_map = {t.get('skill_name'): t for t in skill_trends}

            all_skills = set(result.required_skills + result.preferred_skills)
            for skill in all_skills:
                if skill in trend_map:
                    trend = trend_map[skill]
                    result.skill_trends[skill] = {
                        'mention_count': trend.get('mention_count', 0),
                        'trend': trend.get('trend_direction', '유지'),
                        'category': trend.get('category', 'unknown')
                    }

                    # 상승/하락/유지 분류
                    direction = trend.get('trend_direction', '유지')
                    if direction == '상승':
                        result.rising_skills.append(skill)
                    elif direction == '하락':
                        result.falling_skills.append(skill)
                    else:
                        result.stable_skills.append(skill)

        return result


def process_data_bundle(data_bundle: AnalysisDataBundle) -> AnalysisDataBundle:
    """데이터 번들 정제 (편의 함수)"""
    processor = DataProcessor()
    return processor.process_all(data_bundle)
