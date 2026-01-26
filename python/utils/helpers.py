"""
유틸리티 헬퍼 함수들
"""

import re
import time
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from functools import wraps
import hashlib
import json

# 로깅 설정
def setup_logger(name: str, log_file: Optional[str] = None, log_level: str = 'INFO') -> logging.Logger:
    """로거 설정"""
    logger = logging.getLogger(name)
    level = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(level)
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 콘솔 핸들러
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 파일 핸들러
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def retry_on_failure(max_retries: int = 3, delay: float = 1.0):
    """실패 시 재시도 데코레이터"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        time.sleep(delay * (attempt + 1))
            raise last_exception
        return wrapper
    return decorator


def clean_text(text: str) -> str:
    """텍스트 정리"""
    if not text:
        return ""
    
    # HTML 태그 제거
    text = re.sub(r'<[^>]+>', '', text)
    # 연속 공백 제거
    text = re.sub(r'\s+', ' ', text)
    # 앞뒤 공백 제거
    text = text.strip()
    
    return text


def extract_skills_from_text(text: str) -> Dict[str, List[str]]:
    """텍스트에서 스킬 추출"""
    
    # 하드 스킬 패턴
    hard_skills_patterns = {
        'programming_languages': [
            r'\bPython\b', r'\bJava\b', r'\bJavaScript\b', r'\bTypeScript\b',
            r'\bC\+\+\b', r'\bC#\b', r'\bGo\b', r'\bRust\b', r'\bKotlin\b',
            r'\bSwift\b', r'\bRuby\b', r'\bPHP\b', r'\bScala\b', r'\bR\b'
        ],
        'frameworks': [
            r'\bReact\b', r'\bVue\b', r'\bAngular\b', r'\bDjango\b', r'\bFlask\b',
            r'\bFastAPI\b', r'\bSpring\b', r'\bNode\.js\b', r'\bExpress\b',
            r'\bNext\.js\b', r'\bNuxt\b', r'\bNestJS\b', r'\bRails\b'
        ],
        'databases': [
            r'\bMySQL\b', r'\bPostgreSQL\b', r'\bMongoDB\b', r'\bRedis\b',
            r'\bElasticsearch\b', r'\bCassandra\b', r'\bOracle\b', r'\bSQLite\b',
            r'\bDynamoDB\b', r'\bFirebase\b', r'\bBigQuery\b', r'\bSnowflake\b'
        ],
        'cloud': [
            r'\bAWS\b', r'\bGCP\b', r'\bAzure\b', r'\bKubernetes\b', r'\bDocker\b',
            r'\bTerraform\b', r'\bAnsible\b', r'\bJenkins\b', r'\bGitHub Actions\b',
            r'\bCI/CD\b', r'\bEC2\b', r'\bS3\b', r'\bLambda\b'
        ],
        'data_tools': [
            r'\bPandas\b', r'\bNumPy\b', r'\bScikit-learn\b', r'\bTensorFlow\b',
            r'\bPyTorch\b', r'\bKeras\b', r'\bSpark\b', r'\bHadoop\b',
            r'\bAirflow\b', r'\bKafka\b', r'\bTableau\b', r'\bPower BI\b',
            r'\bLooker\b', r'\bDbt\b', r'\bMLflow\b'
        ],
        'ml_ai': [
            r'\bLLM\b', r'\bNLP\b', r'\b딥러닝\b', r'\b머신러닝\b',
            r'\bRAG\b', r'\bLangChain\b', r'\bOpenAI\b', r'\bGPT\b',
            r'\bTransformer\b', r'\bBERT\b', r'\bComputer Vision\b'
        ]
    }
    
    # 소프트 스킬 패턴 (한국어/영어)
    soft_skills_patterns = [
        r'\b커뮤니케이션\b', r'\bcommunication\b',
        r'\b문제\s*해결\b', r'\bproblem.solving\b',
        r'\b협업\b', r'\b팀워크\b', r'\bteamwork\b', r'\bcollaboration\b',
        r'\b리더십\b', r'\bleadership\b',
        r'\b자기\s*주도\b', r'\bself.driven\b', r'\bself.motivated\b',
        r'\b분석력\b', r'\banalytical\b',
        r'\b창의\b', r'\bcreativ\w*\b',
        r'\b꼼꼼\b', r'\b세심\b', r'\battention.to.detail\b',
        r'\b적응\b', r'\bflexibl\w*\b', r'\badaptab\w*\b',
        r'\b주도\s*적\b', r'\bproactive\b',
        r'\b발표\b', r'\bpresentation\b',
        r'\b기획\b', r'\bplanning\b'
    ]
    
    text_lower = text.lower()
    text_original = text
    
    extracted = {
        'hard_skills': [],
        'soft_skills': [],
        'tools': []
    }
    
    # 하드 스킬 추출
    for category, patterns in hard_skills_patterns.items():
        for pattern in patterns:
            matches = re.findall(pattern, text_original, re.IGNORECASE)
            for match in matches:
                skill = match.strip()
                if skill and skill not in extracted['hard_skills']:
                    extracted['hard_skills'].append(skill)
    
    # 소프트 스킬 추출
    for pattern in soft_skills_patterns:
        matches = re.findall(pattern, text_original, re.IGNORECASE)
        for match in matches:
            skill = match.strip()
            if skill and skill not in extracted['soft_skills']:
                extracted['soft_skills'].append(skill)
    
    return extracted


def parse_salary(salary_text: str) -> Dict[str, Any]:
    """급여 정보 파싱"""
    result = {
        'min': None,
        'max': None,
        'currency': 'KRW',
        'period': 'yearly',
        'raw': salary_text
    }
    
    if not salary_text:
        return result
    
    # 연봉 패턴 (만원 단위)
    patterns = [
        r'(\d{1,2},?\d{3})\s*[~\-]\s*(\d{1,2},?\d{3})\s*만\s*원',
        r'(\d{1,2},?\d{3})\s*만\s*원\s*이상',
        r'연봉\s*(\d{1,2},?\d{3})\s*만\s*원',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, salary_text)
        if match:
            groups = match.groups()
            if len(groups) >= 1:
                result['min'] = int(groups[0].replace(',', '')) * 10000
            if len(groups) >= 2:
                result['max'] = int(groups[1].replace(',', '')) * 10000
            break
    
    return result


def generate_hash(data: Any) -> str:
    """데이터의 해시값 생성"""
    if isinstance(data, dict):
        data = json.dumps(data, sort_keys=True)
    return hashlib.md5(str(data).encode()).hexdigest()


def format_number(num: int) -> str:
    """숫자 포맷팅 (천 단위 구분)"""
    return f"{num:,}"


def parse_date_korean(date_str: str) -> Optional[datetime]:
    """한국어 날짜 문자열 파싱"""
    if not date_str:
        return None
    
    patterns = [
        (r'(\d{4})\.(\d{1,2})\.(\d{1,2})', '%Y.%m.%d'),
        (r'(\d{4})-(\d{1,2})-(\d{1,2})', '%Y-%m-%d'),
        (r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일', None),
    ]
    
    for pattern, fmt in patterns:
        match = re.search(pattern, date_str)
        if match:
            if fmt:
                try:
                    return datetime.strptime(match.group(), fmt)
                except:
                    pass
            else:
                try:
                    year, month, day = match.groups()
                    return datetime(int(year), int(month), int(day))
                except:
                    pass
    
    return None


def categorize_job_level(text: str) -> str:
    """경력 수준 분류"""
    text_lower = text.lower()
    
    if any(word in text_lower for word in ['신입', '주니어', 'junior', '0년', '1년 미만']):
        return 'entry'
    elif any(word in text_lower for word in ['경력무관', '무관', '경력 무관']):
        return 'any'
    elif any(word in text_lower for word in ['시니어', 'senior', '10년', '15년']):
        return 'senior'
    elif any(word in text_lower for word in ['경력', '3년', '5년', '7년']):
        return 'experienced'
    else:
        return 'unknown'


def categorize_employment_type(text: str) -> str:
    """고용 형태 분류"""
    text_lower = text.lower()
    
    if any(word in text_lower for word in ['정규직', 'full-time', 'fulltime', '정규']):
        return 'full_time'
    elif any(word in text_lower for word in ['계약직', 'contract', '기간제']):
        return 'contract'
    elif any(word in text_lower for word in ['인턴', 'intern']):
        return 'intern'
    elif any(word in text_lower for word in ['파트타임', 'part-time', 'parttime', '시간제']):
        return 'part_time'
    elif any(word in text_lower for word in ['프리랜서', 'freelance']):
        return 'freelance'
    else:
        return 'unknown'


class RateLimiter:
    """요청 속도 제한기"""
    
    def __init__(self, calls_per_second: float = 1.0):
        self.min_interval = 1.0 / calls_per_second
        self.last_call_time = 0
    
    def wait(self):
        """필요한 만큼 대기"""
        current_time = time.time()
        elapsed = current_time - self.last_call_time
        
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        
        self.last_call_time = time.time()


def chunk_list(lst: List, chunk_size: int) -> List[List]:
    """리스트를 청크로 분할"""
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]
