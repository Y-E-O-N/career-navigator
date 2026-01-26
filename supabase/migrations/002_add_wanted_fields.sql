-- Career Navigator - Supabase PostgreSQL Schema
-- Migration: 002_add_wanted_fields.sql
-- Wanted 크롤링을 위한 추가 필드

-- =============================================================================
-- job_postings 테이블에 새 필드 추가
-- =============================================================================

-- 경력 요구사항 (예: "경력 1년 이상", "신입", "경력 3~5년")
ALTER TABLE job_postings ADD COLUMN IF NOT EXISTS experience_level VARCHAR(100);

-- 합격 보상금 (예: "합격보상금 100만원")
ALTER TABLE job_postings ADD COLUMN IF NOT EXISTS reward_info VARCHAR(200);

-- 주요 업무 (상세 설명과 별도로 저장)
ALTER TABLE job_postings ADD COLUMN IF NOT EXISTS main_tasks TEXT;

-- 회사 태그 (복지, 규모, 설립연도 등의 태그들)
ALTER TABLE job_postings ADD COLUMN IF NOT EXISTS company_tags JSONB DEFAULT '[]'::jsonb;

-- 마감일 (예: "상시채용", "2024-12-31")
ALTER TABLE job_postings ADD COLUMN IF NOT EXISTS deadline VARCHAR(100);

-- 상세 근무지 주소
ALTER TABLE job_postings ADD COLUMN IF NOT EXISTS work_address VARCHAR(500);

-- 회사 산업분야 (채용공고에서 추출)
ALTER TABLE job_postings ADD COLUMN IF NOT EXISTS company_industry VARCHAR(200);

-- =============================================================================
-- 인덱스 추가
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_job_postings_experience_level ON job_postings(experience_level);
CREATE INDEX IF NOT EXISTS idx_job_postings_deadline ON job_postings(deadline);
CREATE INDEX IF NOT EXISTS idx_job_postings_company_tags ON job_postings USING gin(company_tags);
