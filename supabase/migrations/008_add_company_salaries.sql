-- 008: company_salaries 테이블 추가
-- 잡플래닛 연봉 정보를 별도 테이블로 관리

-- 1. company_salaries 테이블 생성
CREATE TABLE IF NOT EXISTS company_salaries (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    company_name VARCHAR(200) NOT NULL,

    -- 연봉 식별
    source_site VARCHAR(50) DEFAULT 'jobplanet',

    -- 년차/직급 정보
    experience_year VARCHAR(50),  -- '1년차', '3년차', '5년차' 등
    position VARCHAR(100),        -- 직급/직군

    -- 연봉 정보
    salary_amount INTEGER,        -- 연봉 (만원 단위)
    salary_text VARCHAR(100),     -- '4,500만원' 형태
    increase_rate VARCHAR(50),    -- 연봉 인상률 '5.2%'

    -- 통계 정보 (전체 평균일 경우)
    is_overall_avg BOOLEAN DEFAULT FALSE,  -- 전체 평균 여부
    industry_avg INTEGER,         -- 업계 평균 (만원)
    industry_rank VARCHAR(50),    -- 업계 내 순위 '상위 2%'
    response_rate VARCHAR(20),    -- 응답률 '45%'

    -- 연봉 분포 (전체 평균일 경우)
    salary_min INTEGER,           -- 최소
    salary_lower INTEGER,         -- 하위 25%
    salary_upper INTEGER,         -- 상위 25%
    salary_max INTEGER,           -- 최대

    -- 메타
    crawled_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_company_salaries_company_id ON company_salaries(company_id);
CREATE INDEX IF NOT EXISTS idx_company_salaries_company_name ON company_salaries(company_name);
CREATE INDEX IF NOT EXISTS idx_company_salaries_experience ON company_salaries(experience_year);

-- 3. RLS 정책 (Supabase)
ALTER TABLE company_salaries ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'company_salaries' AND policyname = 'Allow public read access on company_salaries'
    ) THEN
        CREATE POLICY "Allow public read access on company_salaries"
        ON company_salaries FOR SELECT USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'company_salaries' AND policyname = 'Allow service role full access on company_salaries'
    ) THEN
        CREATE POLICY "Allow service role full access on company_salaries"
        ON company_salaries FOR ALL USING (true) WITH CHECK (true);
    END IF;
END $$;

-- 4. 코멘트
COMMENT ON TABLE company_salaries IS '회사별 연봉 정보 (잡플래닛)';
COMMENT ON COLUMN company_salaries.experience_year IS '년차 (1년차, 3년차 등)';
COMMENT ON COLUMN company_salaries.is_overall_avg IS 'TRUE면 전체 평균 데이터';
COMMENT ON COLUMN company_salaries.salary_amount IS '연봉 금액 (만원 단위 숫자)';
