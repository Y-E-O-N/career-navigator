-- Career Navigator - Supabase PostgreSQL Schema
-- Migration: 001_initial_schema.sql

-- =============================================================================
-- 회사 정보 테이블
-- =============================================================================
CREATE TABLE IF NOT EXISTS companies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL UNIQUE,

    -- 기본 정보
    business_number VARCHAR(50),
    industry VARCHAR(200),
    company_size VARCHAR(100),
    founded_year INTEGER,

    -- 상세 정보
    description TEXT,
    website VARCHAR(300),
    address VARCHAR(500),

    -- 평판 정보
    glassdoor_rating DECIMAL(3,2),
    jobplanet_rating DECIMAL(3,2),
    blind_summary TEXT,
    news_summary TEXT,
    public_sentiment TEXT,

    -- 재무 정보
    revenue VARCHAR(100),
    employee_count INTEGER,

    -- 메타
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- 채용공고 테이블
-- =============================================================================
CREATE TABLE IF NOT EXISTS job_postings (
    id SERIAL PRIMARY KEY,
    source_site VARCHAR(50) NOT NULL,
    job_id VARCHAR(100) NOT NULL,
    title VARCHAR(500) NOT NULL,
    company_name VARCHAR(200) NOT NULL,
    company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,

    -- 직무 정보
    job_category VARCHAR(200),
    position_level VARCHAR(100),
    employment_type VARCHAR(100),

    -- 상세 정보
    description TEXT,
    requirements TEXT,
    preferred TEXT,

    -- 스킬 정보 (JSONB for better querying)
    required_skills JSONB DEFAULT '[]'::jsonb,
    preferred_skills JSONB DEFAULT '[]'::jsonb,

    -- 조건
    salary_info VARCHAR(200),
    location VARCHAR(200),

    -- URL 및 메타
    url VARCHAR(500),
    crawled_at TIMESTAMPTZ DEFAULT NOW(),
    posted_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE,

    -- 유니크 제약
    UNIQUE(source_site, job_id)
);

-- =============================================================================
-- 스킬 트렌드 테이블
-- =============================================================================
CREATE TABLE IF NOT EXISTS skill_trends (
    id SERIAL PRIMARY KEY,
    skill_name VARCHAR(200) NOT NULL,
    category VARCHAR(100),

    -- 통계
    mention_count INTEGER DEFAULT 0,
    job_category VARCHAR(200),
    trend_direction VARCHAR(50),

    -- 분석 기간
    analysis_date TIMESTAMPTZ DEFAULT NOW(),
    period_start TIMESTAMPTZ,
    period_end TIMESTAMPTZ
);

-- =============================================================================
-- 시장 분석 결과 테이블
-- =============================================================================
CREATE TABLE IF NOT EXISTS market_analysis (
    id SERIAL PRIMARY KEY,
    analysis_date TIMESTAMPTZ DEFAULT NOW(),
    keyword VARCHAR(200) NOT NULL,

    -- 분석 결과
    total_postings INTEGER,
    avg_salary_info TEXT,
    top_companies JSONB DEFAULT '[]'::jsonb,
    top_skills JSONB DEFAULT '[]'::jsonb,

    -- AI 분석 결과
    market_summary TEXT,
    trend_analysis TEXT,
    recommendations TEXT,

    -- 로드맵
    roadmap_3months TEXT,
    roadmap_6months TEXT,

    -- 메타
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- 인덱스 생성
-- =============================================================================

-- job_postings 인덱스
CREATE INDEX IF NOT EXISTS idx_job_postings_source_site ON job_postings(source_site);
CREATE INDEX IF NOT EXISTS idx_job_postings_company_name ON job_postings(company_name);
CREATE INDEX IF NOT EXISTS idx_job_postings_company_id ON job_postings(company_id);
CREATE INDEX IF NOT EXISTS idx_job_postings_crawled_at ON job_postings(crawled_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_postings_is_active ON job_postings(is_active);
CREATE INDEX IF NOT EXISTS idx_job_postings_location ON job_postings(location);

-- Full-text search index for job title and description
CREATE INDEX IF NOT EXISTS idx_job_postings_title_search ON job_postings USING gin(to_tsvector('simple', title));

-- JSONB 인덱스 for skills
CREATE INDEX IF NOT EXISTS idx_job_postings_required_skills ON job_postings USING gin(required_skills);
CREATE INDEX IF NOT EXISTS idx_job_postings_preferred_skills ON job_postings USING gin(preferred_skills);

-- market_analysis 인덱스
CREATE INDEX IF NOT EXISTS idx_market_analysis_keyword ON market_analysis(keyword);
CREATE INDEX IF NOT EXISTS idx_market_analysis_date ON market_analysis(analysis_date DESC);
CREATE INDEX IF NOT EXISTS idx_market_analysis_keyword_date ON market_analysis(keyword, analysis_date DESC);

-- companies 인덱스
CREATE INDEX IF NOT EXISTS idx_companies_name ON companies(name);
CREATE INDEX IF NOT EXISTS idx_companies_industry ON companies(industry);

-- skill_trends 인덱스
CREATE INDEX IF NOT EXISTS idx_skill_trends_skill_name ON skill_trends(skill_name);
CREATE INDEX IF NOT EXISTS idx_skill_trends_category ON skill_trends(category);
CREATE INDEX IF NOT EXISTS idx_skill_trends_analysis_date ON skill_trends(analysis_date DESC);

-- =============================================================================
-- Row Level Security (RLS)
-- =============================================================================

-- Enable RLS on all tables
ALTER TABLE job_postings ENABLE ROW LEVEL SECURITY;
ALTER TABLE companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE skill_trends ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_analysis ENABLE ROW LEVEL SECURITY;

-- 읽기 전용 공개 접근 (인증 없이 조회 가능)
CREATE POLICY "Public read access for job_postings"
    ON job_postings FOR SELECT
    USING (true);

CREATE POLICY "Public read access for companies"
    ON companies FOR SELECT
    USING (true);

CREATE POLICY "Public read access for skill_trends"
    ON skill_trends FOR SELECT
    USING (true);

CREATE POLICY "Public read access for market_analysis"
    ON market_analysis FOR SELECT
    USING (true);

-- 서비스 롤용 쓰기 권한 (크롤러에서 사용)
CREATE POLICY "Service role write access for job_postings"
    ON job_postings FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service role write access for companies"
    ON companies FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service role write access for skill_trends"
    ON skill_trends FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service role write access for market_analysis"
    ON market_analysis FOR ALL
    USING (auth.role() = 'service_role');

-- =============================================================================
-- 자동 updated_at 트리거
-- =============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_companies_updated_at
    BEFORE UPDATE ON companies
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- 유틸리티 함수
-- =============================================================================

-- 최신 분석 결과 조회 함수
CREATE OR REPLACE FUNCTION get_latest_analysis(search_keyword VARCHAR)
RETURNS SETOF market_analysis AS $$
BEGIN
    RETURN QUERY
    SELECT *
    FROM market_analysis
    WHERE keyword = search_keyword
    ORDER BY analysis_date DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- 스킬별 채용공고 수 집계 함수
CREATE OR REPLACE FUNCTION get_skill_job_counts(skill_name VARCHAR)
RETURNS INTEGER AS $$
DECLARE
    job_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO job_count
    FROM job_postings
    WHERE required_skills ? skill_name
       OR preferred_skills ? skill_name;
    RETURN job_count;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- 뷰 생성
-- =============================================================================

-- 활성 채용공고 뷰
CREATE OR REPLACE VIEW active_job_postings AS
SELECT
    jp.*,
    c.industry as company_industry,
    c.company_size,
    c.jobplanet_rating
FROM job_postings jp
LEFT JOIN companies c ON jp.company_id = c.id
WHERE jp.is_active = true
  AND (jp.expires_at IS NULL OR jp.expires_at > NOW());

-- 최신 시장 분석 뷰 (각 키워드별 최신 1개)
CREATE OR REPLACE VIEW latest_market_analysis AS
SELECT DISTINCT ON (keyword)
    *
FROM market_analysis
ORDER BY keyword, analysis_date DESC;

-- 스킬 트렌드 요약 뷰
CREATE OR REPLACE VIEW skill_trend_summary AS
SELECT
    skill_name,
    category,
    SUM(mention_count) as total_mentions,
    MAX(analysis_date) as last_analyzed,
    MODE() WITHIN GROUP (ORDER BY trend_direction) as overall_trend
FROM skill_trends
GROUP BY skill_name, category
ORDER BY total_mentions DESC;
