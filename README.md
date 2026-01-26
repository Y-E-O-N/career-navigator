# 📊 Job Market Analyzer

채용 시장 분석 및 커리어 로드맵 생성 시스템

매일 주요 채용 사이트를 크롤링하여 시장 트렌드를 분석하고, AI 기반 맞춤형 커리어 로드맵을 생성합니다.

## ✨ 주요 기능

- **멀티 사이트 크롤링**: LinkedIn, 원티드, 잡코리아, 사람인, 로켓펀치
- **시장 트렌드 분석**: 채용 동향, 스킬 수요, 기업별 채용 현황
- **회사 평판 조사**: 잡플래닛 평점, 뉴스, 종합 평가
- **AI 커리어 로드맵**: Claude/GPT 기반 3/6개월 학습 로드맵
- **자동 스케줄링**: 매일 지정 시간 자동 실행
- **리포트 생성**: Markdown, HTML, JSON 형식

## 🚀 빠른 시작

### 1. 설치

```bash
# 저장소 클론
git clone https://github.com/your-repo/job-market-analyzer.git
cd job-market-analyzer

# 가상환경 생성 (권장)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

### 2. 환경 설정

```bash
# .env 파일 생성
cp .env.example .env

# 또는 환경변수 직접 설정
export ANTHROPIC_API_KEY=your_api_key  # LLM 분석용 (선택)
export DB_TYPE=sqlite                   # 또는 postgresql
```

### 3. 실행

```bash
# 전체 파이프라인 실행 (크롤링 → 분석 → 리포트)
python main.py all

# 크롤링만 실행
python main.py crawl

# 분석만 실행
python main.py analyze

# 리포트 생성
python main.py report

# 특정 회사 분석
python main.py company "카카오"

# 스케줄러 시작 (매일 자동 실행)
python main.py schedule
```

## 📁 프로젝트 구조

```
job_market_analyzer/
├── config/
│   └── settings.py      # 설정 관리
├── crawlers/
│   ├── base_crawler.py       # 크롤러 베이스 클래스
│   ├── linkedin_crawler.py   # LinkedIn 크롤러
│   ├── wanted_crawler.py     # 원티드 크롤러
│   ├── saramin_crawler.py    # 사람인 크롤러
│   ├── jobkorea_crawler.py   # 잡코리아 크롤러
│   └── rocketpunch_crawler.py # 로켓펀치 크롤러
├── analyzers/
│   ├── market_analyzer.py   # 시장 분석
│   ├── company_analyzer.py  # 회사 분석
│   └── llm_analyzer.py      # LLM 기반 분석
├── utils/
│   ├── database.py          # 데이터베이스 ORM
│   └── helpers.py           # 유틸리티 함수
├── main.py              # 메인 실행 스크립트
├── scheduler.py         # 자동 스케줄러
├── report_generator.py  # 리포트 생성기
├── data/                # SQLite DB 저장
├── reports/             # 생성된 리포트
└── logs/                # 로그 파일
```

## ⚙️ 설정

### 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DB_TYPE` | `sqlite` | 데이터베이스 종류 (`sqlite` 또는 `postgresql`) |
| `PG_HOST` | `localhost` | PostgreSQL 호스트 |
| `PG_PORT` | `5432` | PostgreSQL 포트 |
| `PG_DATABASE` | `job_market` | PostgreSQL 데이터베이스 |
| `PG_USER` | `postgres` | PostgreSQL 사용자 |
| `PG_PASSWORD` | - | PostgreSQL 비밀번호 |
| `ANTHROPIC_API_KEY` | - | Claude API 키 |
| `OPENAI_API_KEY` | - | OpenAI API 키 (대체) |
| `LLM_PROVIDER` | `anthropic` | LLM 제공자 |
| `SCHEDULER_TIME` | `09:00` | 스케줄러 실행 시간 |
| `SCHEDULER_TIMEZONE` | `Asia/Seoul` | 타임존 |

### 설정 파일 (config.json)

```json
{
  "keywords": ["데이터 분석가", "백엔드 개발자", "프론트엔드 개발자"],
  "sites": {
    "linkedin": true,
    "wanted": true,
    "jobkorea": true,
    "saramin": true,
    "rocketpunch": true
  },
  "crawler": {
    "request_delay": 2.0,
    "max_retries": 3,
    "max_pages_per_keyword": 10
  }
}
```

## 📊 사용 예시

### Python에서 직접 사용

```python
from config.settings import Settings
from utils.database import Database
from crawlers import get_crawler
from analyzers.market_analyzer import MarketAnalyzer
from analyzers.llm_analyzer import LLMAnalyzer

# 설정 및 DB 초기화
settings = Settings()
db = Database(settings.database.connection_string)
db.create_tables()

# 크롤링
crawler = get_crawler('wanted')
jobs = crawler.crawl_keyword('데이터 분석가')
for job in jobs:
    db.add_job_posting(job)

# 시장 분석
analyzer = MarketAnalyzer(db)
analysis = analyzer.analyze_keyword('데이터 분석가', days=30)
print(f"총 {analysis['total_postings']}개 채용공고")
print(f"상위 스킬: {[s['skill'] for s in analysis['skill_analysis']['hard_skills'][:5]]}")

# AI 로드맵 생성
llm = LLMAnalyzer()
if llm.is_available():
    roadmap = llm.generate_career_roadmap(
        '데이터 분석가',
        analysis['skill_analysis'],
        duration_months=6
    )
    print(roadmap['roadmap_3_months'])
```

### CLI 옵션

```bash
# 특정 키워드만 크롤링
python main.py crawl --keywords "데이터 분석가" "백엔드 개발자"

# 특정 사이트만 사용
python main.py crawl --sites linkedin wanted rocketpunch

# 설정 파일 지정
python main.py --config my_config.json all

# 디버그 모드
python main.py --debug all
```

### 스케줄러 옵션

```bash
# 기본: 매일 09:00 실행
python main.py schedule

# 시간 지정
python scheduler.py --hour 8 --minute 30

# 즉시 실행 후 스케줄 시작
python scheduler.py --run-now

# 평일만 실행
python scheduler.py --mode weekday

# 6시간 간격 실행
python scheduler.py --mode interval --interval-hours 6
```

## 📝 출력 예시

### 시장 분석 요약

```
## 데이터 분석가 채용 시장 분석

### 기본 통계
- 총 채용공고: 1,234개
- 고유 기업: 456개
- 분석 기간: 2025-01-01 ~ 2025-01-30

### 상위 채용 기업
1. 카카오 (45건)
2. 네이버 (38건)
3. 쿠팡 (32건)

### 상위 기술 스택
1. Python (78.5%)
2. SQL (72.3%)
3. Pandas (45.2%)
4. Tableau (38.1%)
5. AWS (35.4%)
```

### 3개월 로드맵 (AI 생성)

```
## 3개월 커리어 로드맵: 데이터 분석가

### 1주차-2주차: Python 기초
- 목표: Python 문법, 자료구조 완전 숙달
- 실습: 간단한 데이터 처리 스크립트 작성
- 추천 자료: 점프 투 파이썬, Codecademy

### 3주차-4주차: 데이터 처리
- 목표: Pandas, NumPy 기본 사용법
- 실습: 공공데이터 분석 프로젝트
...
```

## 🔧 트러블슈팅

### 크롤링 오류

```bash
# 요청 딜레이 늘리기
export CRAWLER_DELAY=3.0

# 특정 사이트 제외
python main.py crawl --sites wanted programmers
```

### DB 연결 오류

```bash
# SQLite 사용 (기본)
export DB_TYPE=sqlite

# PostgreSQL 연결 확인
psql -h localhost -U postgres -d job_market
```

### LLM API 오류

```bash
# API 키 확인
echo $ANTHROPIC_API_KEY

# Fallback 모드 사용 (API 없이)
# LLM API가 없으면 자동으로 템플릿 기반 로드맵 생성
```

## 📄 라이선스

MIT License

## 🤝 기여

이슈 및 PR 환영합니다!
