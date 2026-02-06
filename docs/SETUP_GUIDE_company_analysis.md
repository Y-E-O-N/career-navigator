# 기업 분석 보고서 시스템 설정 가이드

이 문서는 `analyze-report` 명령어를 사용하여 기업 분석 보고서를 생성하기 위해 필요한 설정을 안내합니다.

---

## 목차

1. [사전 요구사항](#1-사전-요구사항)
2. [데이터베이스 마이그레이션](#2-데이터베이스-마이그레이션)
3. [환경변수 설정](#3-환경변수-설정)
4. [Python 패키지 설치](#4-python-패키지-설치)
5. [사용 방법](#5-사용-방법)
6. [문제 해결](#6-문제-해결)

---

## 1. 사전 요구사항

### 필수 조건
- Python 3.9 이상
- Supabase 프로젝트 (이미 설정되어 있음)
- 기업 데이터가 DB에 수집되어 있어야 함 (크롤링 완료 상태)

### 권장 조건
- LLM API 키 (OpenAI, Anthropic, 또는 Google Gemini 중 하나)

---

## 2. 데이터베이스 마이그레이션

보고서를 DB에 저장하려면 `company_reports` 테이블이 필요합니다.

### 방법 1: Supabase 대시보드에서 실행 (권장)

1. [Supabase 대시보드](https://supabase.com/dashboard)에 로그인
2. 프로젝트 선택
3. 왼쪽 메뉴에서 **SQL Editor** 클릭
4. **New query** 클릭
5. 아래 SQL을 붙여넣고 **Run** 클릭:

```sql
-- company_reports 테이블 생성
CREATE TABLE IF NOT EXISTS company_reports (
    id SERIAL PRIMARY KEY,

    -- 기본 정보
    company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
    company_name VARCHAR(200) NOT NULL,
    job_posting_id INTEGER,

    -- 보고서 버전 및 LLM 정보
    report_version VARCHAR(20) DEFAULT 'v4',
    llm_provider VARCHAR(50),
    llm_model VARCHAR(100),

    -- 평가 결과
    verdict VARCHAR(50),
    total_score DECIMAL(3,2),
    scores JSONB,

    -- 핵심 요약
    key_attractions JSONB,
    key_risks JSONB,
    verification_items JSONB,

    -- 전체 보고서
    full_markdown TEXT,
    full_html TEXT,

    -- Quality Gate
    quality_passed BOOLEAN DEFAULT FALSE,
    quality_details JSONB,

    -- 입력 컨텍스트
    data_sources JSONB,
    applicant_profile JSONB,
    priority_weights JSONB,

    -- 캐싱
    cache_key VARCHAR(255) UNIQUE,
    cache_expires_at TIMESTAMP,

    -- 타임스탬프
    generated_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_company_reports_company_name ON company_reports(company_name);
CREATE INDEX IF NOT EXISTS idx_company_reports_cache_key ON company_reports(cache_key);
CREATE INDEX IF NOT EXISTS idx_company_reports_generated_at ON company_reports(generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_company_reports_verdict ON company_reports(verdict);

-- updated_at 자동 갱신 트리거
CREATE OR REPLACE FUNCTION update_company_reports_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_company_reports_updated_at ON company_reports;
CREATE TRIGGER trigger_company_reports_updated_at
    BEFORE UPDATE ON company_reports
    FOR EACH ROW
    EXECUTE FUNCTION update_company_reports_updated_at();
```

6. "Success" 메시지가 나오면 완료!

### 방법 2: 마이그레이션 파일 직접 실행

프로젝트에 이미 마이그레이션 파일이 있습니다:
```
supabase/migrations/010_add_company_reports.sql
```

Supabase CLI가 설치되어 있다면:
```bash
supabase db push
```

---

## 3. 환경변수 설정

### LLM API 키 설정 (필수 - 보고서 생성 시)

`.env` 파일에 아래 중 **하나 이상**을 설정하세요:

```bash
# python/.env 파일

# 방법 1: OpenAI (권장 - 가장 안정적)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 방법 2: Anthropic Claude
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 방법 3: Google Gemini (무료 티어 있음)
LLM_PROVIDER=gemini
GEMINI_API_KEY=AIzaxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### API 키 발급 방법

#### OpenAI
1. https://platform.openai.com 접속
2. 로그인 후 API Keys 메뉴
3. "Create new secret key" 클릭
4. 키 복사하여 `.env`에 붙여넣기

#### Anthropic Claude
1. https://console.anthropic.com 접속
2. API Keys 메뉴에서 키 생성
3. 키 복사하여 `.env`에 붙여넣기

#### Google Gemini (무료 티어 있음)
1. https://aistudio.google.com/app/apikey 접속
2. "Create API Key" 클릭
3. 키 복사하여 `.env`에 붙여넣기

### GitHub Actions 사용 시 (선택)

GitHub Secrets에도 동일하게 설정:
1. GitHub 레포지토리 → Settings → Secrets and variables → Actions
2. "New repository secret" 클릭
3. 아래 값들 추가:
   - `LLM_PROVIDER`: openai 또는 anthropic 또는 gemini
   - `OPENAI_API_KEY`: (OpenAI 사용 시)
   - `ANTHROPIC_API_KEY`: (Anthropic 사용 시)
   - `GEMINI_API_KEY`: (Gemini 사용 시)

---

## 4. Python 패키지 설치

### 필수 패키지 (이미 requirements.txt에 포함)

```bash
cd python
pip install -r requirements.txt
```

### 선택적 패키지

#### HTML 변환 개선 (권장)
```bash
pip install markdown
```
- 설치하면 마크다운 → HTML 변환 품질이 향상됩니다
- 미설치 시 기본 정규식 변환 사용 (기능은 동작함)

#### PDF 내보내기 (선택)
```bash
pip install weasyprint
```
- `--export-pdf` 옵션 사용 시 필요
- Windows에서는 GTK 런타임 추가 설치 필요할 수 있음
- 복잡하면 PDF는 건너뛰고 HTML만 사용해도 충분합니다

---

## 5. 사용 방법

### 기본 사용법

```bash
cd python

# 1. 데이터 요약만 확인 (LLM 호출 없이 빠르게 확인)
python main.py analyze-report "회사이름" --data-summary

# 2. 프롬프트만 생성 (LLM 호출 없음, 비용 무료)
python main.py analyze-report "회사이름"

# 3. LLM으로 보고서 생성 (API 비용 발생)
python main.py analyze-report "회사이름" --generate-llm
```

### 전체 옵션 사용 예시

```bash
# 보고서 생성 + DB 저장 + HTML 파일 생성
python main.py analyze-report "카카오" \
    --generate-llm \
    --save-db \
    --export-html

# 특정 채용공고에 대한 분석
python main.py analyze-report "네이버" \
    --job-id 123 \
    --generate-llm \
    --export-html

# 캐시 무시하고 새로 생성
python main.py analyze-report "쿠팡" \
    --generate-llm \
    --no-cache

# 가중치 커스텀 (합계 100)
python main.py analyze-report "토스" \
    --generate-llm \
    --weights "성장성:30,안정성:20,보상:25,워라밸:10,직무적합:15"
```

### 옵션 설명

| 옵션 | 설명 |
|------|------|
| `--data-summary` | 데이터 요약만 출력 (LLM 호출 없음) |
| `--generate-llm` | LLM을 호출하여 실제 보고서 생성 |
| `--save-db` | 생성된 보고서를 DB에 저장 |
| `--export-html` | HTML 파일로 내보내기 |
| `--export-pdf` | PDF 파일로 내보내기 (weasyprint 필요) |
| `--job-id N` | 특정 채용공고 ID로 분석 |
| `--weights "..."` | 평가 가중치 커스텀 |
| `--no-cache` | 캐시 무시하고 새로 생성 |
| `--cache-days N` | 캐시 유효 기간 (기본 7일) |
| `--output-dir PATH` | 출력 디렉토리 지정 |

### 출력 파일 위치

```
python/reports/company_analysis/
├── 카카오_20240206_143052_prompt.md   # 생성된 프롬프트
├── 카카오_20240206_143052_report.md   # 마크다운 보고서
└── 카카오_20240206_143052.html        # HTML 보고서
```

---

## 6. 문제 해결

### Q1: "최소 분석 요건 미충족" 오류

```
회사 정보 또는 채용공고가 없습니다.
```

**원인**: 해당 회사의 데이터가 DB에 없음

**해결**:
1. 먼저 크롤링 실행:
   ```bash
   python main.py crawl-jobs
   python main.py crawl-companies
   ```
2. 또는 회사명 정확히 확인 (오타, 띄어쓰기 등)

### Q2: "LLM API 키가 설정되지 않았습니다" 오류

**원인**: `.env` 파일에 API 키가 없음

**해결**:
1. `python/.env` 파일 확인
2. `LLM_PROVIDER`와 해당 API 키가 설정되어 있는지 확인
3. 환경변수 재로드: 터미널 재시작

### Q3: "company_reports 테이블이 없습니다" 오류

**원인**: DB 마이그레이션이 안 됨

**해결**: [2. 데이터베이스 마이그레이션](#2-데이터베이스-마이그레이션) 섹션 참고

### Q4: Windows에서 인코딩 오류

```
'cp949' codec can't encode character...
```

**원인**: Windows 콘솔의 인코딩 문제

**해결**: 이미 코드에서 처리되어 있으나, 추가로:
```bash
# PowerShell에서 UTF-8 설정
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001
```

### Q5: HTML 변환 품질이 낮음

**원인**: `markdown` 라이브러리 미설치

**해결**:
```bash
pip install markdown
```

### Q6: 보고서 생성이 너무 느림

**원인**: LLM API 응답 시간

**해결**:
- 정상적인 현상입니다 (보통 30초~2분 소요)
- 스트리밍으로 실시간 출력되므로 기다려주세요
- 캐시 기능으로 동일 조건 재요청 시 즉시 반환됨

---

## 비용 참고

### LLM API 비용 (보고서 1건 기준, 대략적)

| Provider | 모델 | 예상 비용 |
|----------|------|----------|
| OpenAI | gpt-4o-mini | ~$0.01-0.02 |
| OpenAI | gpt-4o | ~$0.05-0.10 |
| Anthropic | claude-3-5-haiku | ~$0.01-0.02 |
| Anthropic | claude-3-5-sonnet | ~$0.05-0.10 |
| Google | gemini-2.0-flash | 무료 티어 내 가능 |

**비용 절약 팁**:
- `--data-summary`로 먼저 데이터 확인
- 캐시 활용 (`--no-cache` 사용 자제)
- Gemini 무료 티어 활용

---

## 문의

추가 질문이 있으시면 언제든 물어봐주세요!
