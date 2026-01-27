-- Add LLM analysis fields to market_analysis table
ALTER TABLE market_analysis
ADD COLUMN IF NOT EXISTS llm_analysis TEXT,
ADD COLUMN IF NOT EXISTS project_ideas TEXT;

-- Update the view if it exists
DROP VIEW IF EXISTS latest_market_analysis;

CREATE VIEW latest_market_analysis AS
SELECT DISTINCT ON (keyword)
    id,
    analysis_date,
    keyword,
    total_postings,
    avg_salary_info,
    top_companies,
    top_skills,
    market_summary,
    trend_analysis,
    recommendations,
    llm_analysis,
    project_ideas,
    roadmap_3months,
    roadmap_6months,
    analysis_date as created_at
FROM market_analysis
ORDER BY keyword, analysis_date DESC;
