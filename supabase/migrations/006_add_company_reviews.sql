-- Career Navigator - Supabase PostgreSQL Schema
-- Migration: 006_add_company_reviews.sql
-- 잡플래닛 개별 리뷰, 면접 후기, 복지 후기 테이블

-- =============================================================================
-- 회사 리뷰 테이블 (잡플래닛)
-- =============================================================================
CREATE TABLE IF NOT EXISTS company_reviews (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    company_name VARCHAR(200) NOT NULL,

    -- 리뷰 식별
    source_site VARCHAR(50) DEFAULT 'jobplanet',
    review_id VARCHAR(100),  -- 잡플래닛 리뷰 ID

    -- 작성자 정보
    job_category VARCHAR(100),  -- 직군 (개발, 마케팅 등)
    employment_status VARCHAR(50),  -- 현직원/전직원
    location VARCHAR(100),  -- 지역
    write_date VARCHAR(50),  -- 작성일

    -- 평점
    total_rating DECIMAL(2,1),  -- 총 평점 (5점 만점)
    category_scores JSONB DEFAULT '{}'::jsonb,  -- 항목별 점수 (승진기회, 복지/급여, 워라밸, 사내문화, 경영진)

    -- 리뷰 내용
    title VARCHAR(300),
    pros TEXT,  -- 장점
    cons TEXT,  -- 단점
    advice TEXT,  -- 경영진에 바라는 점

    -- 추가 정보
    future_outlook VARCHAR(200),  -- 1년 후 전망
    recommendation VARCHAR(100),  -- 추천 여부

    -- 메타
    crawled_at TIMESTAMPTZ DEFAULT NOW(),

    -- 유니크 제약 (같은 사이트의 같은 리뷰 중복 방지)
    UNIQUE(source_site, review_id)
);

-- =============================================================================
-- 면접 후기 테이블 (잡플래닛)
-- =============================================================================
CREATE TABLE IF NOT EXISTS company_interviews (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    company_name VARCHAR(200) NOT NULL,

    -- 면접 식별
    source_site VARCHAR(50) DEFAULT 'jobplanet',
    interview_id VARCHAR(100),

    -- 면접 정보
    job_category VARCHAR(100),  -- 직군
    position VARCHAR(100),  -- 직급
    interview_date VARCHAR(50),  -- 면접 날짜

    -- 면접 상세
    difficulty VARCHAR(50),  -- 난이도
    route VARCHAR(200),  -- 면접 경로 (공채, 헤드헌팅 등)
    title VARCHAR(300),  -- 면접 제목/요약
    question TEXT,  -- 면접 질문
    answer TEXT,  -- 답변/느낌

    -- 결과
    announcement_timing VARCHAR(100),  -- 발표 시기
    result VARCHAR(100),  -- 합격/불합격/대기
    experience VARCHAR(100),  -- 면접 경험 (긍정/부정)

    -- 메타
    crawled_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(source_site, interview_id)
);

-- =============================================================================
-- 복지 후기 테이블 (잡플래닛)
-- =============================================================================
CREATE TABLE IF NOT EXISTS company_benefits (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    company_name VARCHAR(200) NOT NULL,

    -- 복지 식별
    source_site VARCHAR(50) DEFAULT 'jobplanet',
    benefit_id VARCHAR(100),

    -- 카테고리 정보
    category VARCHAR(100),  -- 의료/건강, 휴가/휴직 등
    category_rating DECIMAL(2,1),  -- 카테고리별 평점

    -- 작성자 정보
    job_category VARCHAR(100),
    employment_status VARCHAR(50),
    location VARCHAR(100),
    employment_type VARCHAR(50),  -- 정규직/계약직

    -- 후기 내용
    content TEXT,
    item_scores JSONB DEFAULT '[]'::jsonb,  -- 개별 복지 항목별 점수

    -- 메타
    crawled_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- 인덱스 생성
-- =============================================================================

-- company_reviews 인덱스
CREATE INDEX IF NOT EXISTS idx_company_reviews_company_id ON company_reviews(company_id);
CREATE INDEX IF NOT EXISTS idx_company_reviews_company_name ON company_reviews(company_name);
CREATE INDEX IF NOT EXISTS idx_company_reviews_rating ON company_reviews(total_rating DESC);
CREATE INDEX IF NOT EXISTS idx_company_reviews_crawled_at ON company_reviews(crawled_at DESC);

-- company_interviews 인덱스
CREATE INDEX IF NOT EXISTS idx_company_interviews_company_id ON company_interviews(company_id);
CREATE INDEX IF NOT EXISTS idx_company_interviews_company_name ON company_interviews(company_name);
CREATE INDEX IF NOT EXISTS idx_company_interviews_crawled_at ON company_interviews(crawled_at DESC);

-- company_benefits 인덱스
CREATE INDEX IF NOT EXISTS idx_company_benefits_company_id ON company_benefits(company_id);
CREATE INDEX IF NOT EXISTS idx_company_benefits_company_name ON company_benefits(company_name);
CREATE INDEX IF NOT EXISTS idx_company_benefits_category ON company_benefits(category);

-- =============================================================================
-- Row Level Security (RLS)
-- =============================================================================

ALTER TABLE company_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE company_interviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE company_benefits ENABLE ROW LEVEL SECURITY;

-- 읽기 전용 공개 접근
CREATE POLICY "Public read access for company_reviews"
    ON company_reviews FOR SELECT USING (true);

CREATE POLICY "Public read access for company_interviews"
    ON company_interviews FOR SELECT USING (true);

CREATE POLICY "Public read access for company_benefits"
    ON company_benefits FOR SELECT USING (true);

-- 서비스 롤용 쓰기 권한
CREATE POLICY "Service role write access for company_reviews"
    ON company_reviews FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role write access for company_interviews"
    ON company_interviews FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role write access for company_benefits"
    ON company_benefits FOR ALL USING (auth.role() = 'service_role');

-- =============================================================================
-- 뷰 생성
-- =============================================================================

-- 회사별 리뷰 요약 뷰
CREATE OR REPLACE VIEW company_review_summary AS
SELECT
    company_name,
    COUNT(*) as review_count,
    ROUND(AVG(total_rating), 2) as avg_rating,
    COUNT(CASE WHEN recommendation LIKE '%추천%' AND recommendation NOT LIKE '%비추천%' THEN 1 END) as recommend_count,
    COUNT(CASE WHEN recommendation LIKE '%비추천%' THEN 1 END) as not_recommend_count,
    MAX(crawled_at) as last_crawled
FROM company_reviews
GROUP BY company_name;

-- 회사별 면접 요약 뷰
CREATE OR REPLACE VIEW company_interview_summary AS
SELECT
    company_name,
    COUNT(*) as interview_count,
    MODE() WITHIN GROUP (ORDER BY difficulty) as common_difficulty,
    COUNT(CASE WHEN result LIKE '%합격%' THEN 1 END) as pass_count,
    COUNT(CASE WHEN result LIKE '%불합격%' THEN 1 END) as fail_count,
    MAX(crawled_at) as last_crawled
FROM company_interviews
GROUP BY company_name;
