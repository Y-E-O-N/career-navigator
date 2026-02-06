-- 007: companies 테이블에 jobplanet_id 컬럼 추가
-- 잡플래닛 URL의 회사 ID (예: /companies/471429 → "471429")

-- 1. jobplanet_id 컬럼 추가
ALTER TABLE companies ADD COLUMN IF NOT EXISTS jobplanet_id VARCHAR(50);

-- 2. 기존 데이터에서 URL로부터 ID 추출하여 업데이트
UPDATE companies
SET jobplanet_id = SUBSTRING(jobplanet_url FROM '/companies/(\d+)')
WHERE jobplanet_url IS NOT NULL AND jobplanet_id IS NULL;

-- 3. 인덱스 추가 (검색 성능)
CREATE INDEX IF NOT EXISTS idx_companies_jobplanet_id ON companies(jobplanet_id);

-- 4. 코멘트 추가
COMMENT ON COLUMN companies.jobplanet_id IS '잡플래닛 회사 고유 ID (URL에서 추출)';
