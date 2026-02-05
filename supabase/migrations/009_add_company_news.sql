-- 009: company_news 테이블 추가
-- 3차 크롤링: 기업별 뉴스 기사 수집 (연합뉴스)

-- 1. company_news 테이블 생성
CREATE TABLE IF NOT EXISTS company_news (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    company_name VARCHAR(200) NOT NULL,

    -- 뉴스 식별
    source_site VARCHAR(50) DEFAULT 'yna',  -- 연합뉴스
    news_url VARCHAR(500) NOT NULL,
    news_id VARCHAR(100),  -- URL에서 추출한 기사 ID

    -- 기사 기본 정보 (목록에서 수집)
    title VARCHAR(500),
    published_at VARCHAR(50),  -- '2026-01-29 17:16'

    -- 기사 상세 정보 (상세 페이지에서 수집)
    subtitle VARCHAR(500),
    reporter_name VARCHAR(100),
    content TEXT,

    -- 메타
    crawled_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- 중복 방지
    UNIQUE(source_site, news_url)
);

-- 2. 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_company_news_company_id ON company_news(company_id);
CREATE INDEX IF NOT EXISTS idx_company_news_company_name ON company_news(company_name);
CREATE INDEX IF NOT EXISTS idx_company_news_published_at ON company_news(published_at);
CREATE INDEX IF NOT EXISTS idx_company_news_source ON company_news(source_site);

-- 3. RLS 정책 (Supabase)
ALTER TABLE company_news ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'company_news' AND policyname = 'Allow public read access on company_news'
    ) THEN
        CREATE POLICY "Allow public read access on company_news"
        ON company_news FOR SELECT USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'company_news' AND policyname = 'Allow service role full access on company_news'
    ) THEN
        CREATE POLICY "Allow service role full access on company_news"
        ON company_news FOR ALL USING (true) WITH CHECK (true);
    END IF;
END $$;

-- 4. 코멘트
COMMENT ON TABLE company_news IS '회사별 뉴스 기사 (연합뉴스 등)';
COMMENT ON COLUMN company_news.news_id IS 'URL에서 추출한 기사 고유 ID';
COMMENT ON COLUMN company_news.content IS '기사 본문 (p 태그 내용)';
