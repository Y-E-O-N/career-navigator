-- Add new company fields for jobplanet extended info
ALTER TABLE companies
ADD COLUMN IF NOT EXISTS location VARCHAR(100),
ADD COLUMN IF NOT EXISTS jobplanet_url VARCHAR(500),
ADD COLUMN IF NOT EXISTS additional_info TEXT;

-- Add comment
COMMENT ON COLUMN companies.location IS '지역 (서울, 경기 등)';
COMMENT ON COLUMN companies.jobplanet_url IS '잡플래닛 회사 페이지 URL';
COMMENT ON COLUMN companies.additional_info IS '잡플래닛 추가 정보 (연봉, 면접, 복지 등) JSON';
