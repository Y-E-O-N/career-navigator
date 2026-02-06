-- 기업 분석 보고서 테이블
-- Phase 4: Storage and Output

CREATE TABLE IF NOT EXISTS company_reports (
    id SERIAL PRIMARY KEY,

    -- 회사 및 채용공고 연결
    company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
    company_name VARCHAR(200) NOT NULL,
    job_posting_id INTEGER,  -- FK 제거 (job_postings.id에 unique constraint 없음)

    -- 보고서 메타데이터
    report_version VARCHAR(20) DEFAULT 'v4',
    llm_provider VARCHAR(50),  -- openai, anthropic, gemini
    llm_model VARCHAR(100),    -- gpt-4o, claude-sonnet-4-20250514, etc.

    -- 분석 결과
    verdict VARCHAR(50),           -- Go, Conditional Go, No-Go
    total_score DECIMAL(3,2),      -- 0.00 ~ 5.00
    scores JSONB,                  -- 개별 평가축 점수 {직무적합성: 4.0, ...}

    -- 핵심 요약
    key_attractions TEXT[],        -- 핵심 매력 포인트
    key_risks TEXT[],              -- 핵심 리스크
    verification_items TEXT[],     -- [확인 필요] 항목

    -- 보고서 본문
    full_markdown TEXT,            -- 전체 마크다운 보고서
    full_html TEXT,                -- HTML 변환 버전

    -- Quality Gate 결과
    quality_passed BOOLEAN DEFAULT FALSE,
    quality_details JSONB,         -- 상세 검증 결과

    -- 데이터 소스 정보
    data_sources JSONB,            -- 사용된 데이터 소스 및 건수

    -- 지원자 컨텍스트 (선택)
    applicant_profile JSONB,       -- 지원자 프로필
    priority_weights JSONB,        -- 우선순위 가중치

    -- 캐시 관리
    cache_key VARCHAR(255) UNIQUE, -- 캐시 키 (company_name + job_id + weights hash)
    cache_expires_at TIMESTAMP WITH TIME ZONE,

    -- 타임스탬프
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_company_reports_company_id ON company_reports(company_id);
CREATE INDEX IF NOT EXISTS idx_company_reports_company_name ON company_reports(company_name);
CREATE INDEX IF NOT EXISTS idx_company_reports_cache_key ON company_reports(cache_key);
CREATE INDEX IF NOT EXISTS idx_company_reports_generated_at ON company_reports(generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_company_reports_verdict ON company_reports(verdict);

-- 캐시 만료 확인용 인덱스
CREATE INDEX IF NOT EXISTS idx_company_reports_cache_expires ON company_reports(cache_expires_at)
    WHERE cache_expires_at IS NOT NULL;

-- 트리거: updated_at 자동 업데이트
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

-- 코멘트
COMMENT ON TABLE company_reports IS '기업 분석 보고서 저장 테이블';
COMMENT ON COLUMN company_reports.verdict IS '종합 판정 (Go, Conditional Go, No-Go)';
COMMENT ON COLUMN company_reports.total_score IS '가중 총점 (0.00 ~ 5.00)';
COMMENT ON COLUMN company_reports.cache_key IS '캐시 키 (중복 생성 방지)';
COMMENT ON COLUMN company_reports.cache_expires_at IS '캐시 만료 시간';
