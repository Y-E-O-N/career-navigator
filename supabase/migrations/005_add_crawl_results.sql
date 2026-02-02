-- 005: 크롤링 결과 추적 테이블 추가
-- 1차 크롤링(채용공고)과 2차 크롤링(회사정보)의 결과를 추적

CREATE TABLE IF NOT EXISTS crawl_results (
    id SERIAL PRIMARY KEY,
    crawl_date TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    crawl_type VARCHAR(50) NOT NULL,  -- 'jobs' or 'companies'
    source_site VARCHAR(50),  -- wanted, saramin, jobkorea, jobplanet 등
    keyword VARCHAR(200),  -- 검색 키워드 또는 회사명

    -- 크롤링 통계
    total_found INTEGER DEFAULT 0,  -- 검색 결과 총 개수
    new_count INTEGER DEFAULT 0,  -- 새로 추가된 공고/회사
    existing_count INTEGER DEFAULT 0,  -- 기존 공고/회사 (업데이트)
    deleted_count INTEGER DEFAULT 0,  -- 삭제된 공고 (이전 대비)

    -- 상세 정보 (JSON)
    new_job_ids JSONB,  -- 새로 추가된 job_id 목록
    deleted_job_ids JSONB,  -- 삭제된 job_id 목록

    -- 상태
    status VARCHAR(50) DEFAULT 'completed',  -- completed, failed
    error_message TEXT,
    duration_seconds FLOAT  -- 크롤링 소요 시간
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_crawl_results_date ON crawl_results(crawl_date DESC);
CREATE INDEX IF NOT EXISTS idx_crawl_results_type ON crawl_results(crawl_type);
CREATE INDEX IF NOT EXISTS idx_crawl_results_site ON crawl_results(source_site);

-- job_postings 테이블에 is_active 컬럼이 없으면 추가
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'job_postings' AND column_name = 'is_active'
    ) THEN
        ALTER TABLE job_postings ADD COLUMN is_active BOOLEAN DEFAULT TRUE;
    END IF;
END $$;

-- is_active 인덱스 추가
CREATE INDEX IF NOT EXISTS idx_job_postings_active ON job_postings(is_active);
