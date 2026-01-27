export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[];

export interface Database {
  public: {
    Tables: {
      job_postings: {
        Row: {
          id: number;
          source_site: string;
          job_id: string;
          title: string;
          company_name: string;
          company_id: number | null;
          job_category: string | null;
          position_level: string | null;
          employment_type: string | null;
          description: string | null;
          requirements: string | null;
          preferred: string | null;
          required_skills: string[];
          preferred_skills: string[];
          salary_info: string | null;
          location: string | null;
          url: string | null;
          crawled_at: string;
          posted_at: string | null;
          expires_at: string | null;
          is_active: boolean;
        };
        Insert: {
          id?: number;
          source_site: string;
          job_id: string;
          title: string;
          company_name: string;
          company_id?: number | null;
          job_category?: string | null;
          position_level?: string | null;
          employment_type?: string | null;
          description?: string | null;
          requirements?: string | null;
          preferred?: string | null;
          required_skills?: string[];
          preferred_skills?: string[];
          salary_info?: string | null;
          location?: string | null;
          url?: string | null;
          crawled_at?: string;
          posted_at?: string | null;
          expires_at?: string | null;
          is_active?: boolean;
        };
        Update: {
          id?: number;
          source_site?: string;
          job_id?: string;
          title?: string;
          company_name?: string;
          company_id?: number | null;
          job_category?: string | null;
          position_level?: string | null;
          employment_type?: string | null;
          description?: string | null;
          requirements?: string | null;
          preferred?: string | null;
          required_skills?: string[];
          preferred_skills?: string[];
          salary_info?: string | null;
          location?: string | null;
          url?: string | null;
          crawled_at?: string;
          posted_at?: string | null;
          expires_at?: string | null;
          is_active?: boolean;
        };
      };
      companies: {
        Row: {
          id: number;
          name: string;
          business_number: string | null;
          industry: string | null;
          company_size: string | null;
          founded_year: number | null;
          description: string | null;
          website: string | null;
          address: string | null;
          glassdoor_rating: number | null;
          jobplanet_rating: number | null;
          blind_summary: string | null;
          news_summary: string | null;
          public_sentiment: string | null;
          revenue: string | null;
          employee_count: number | null;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: number;
          name: string;
          business_number?: string | null;
          industry?: string | null;
          company_size?: string | null;
          founded_year?: number | null;
          description?: string | null;
          website?: string | null;
          address?: string | null;
          glassdoor_rating?: number | null;
          jobplanet_rating?: number | null;
          blind_summary?: string | null;
          news_summary?: string | null;
          public_sentiment?: string | null;
          revenue?: string | null;
          employee_count?: number | null;
        };
        Update: {
          id?: number;
          name?: string;
          business_number?: string | null;
          industry?: string | null;
          company_size?: string | null;
          founded_year?: number | null;
          description?: string | null;
          website?: string | null;
          address?: string | null;
          glassdoor_rating?: number | null;
          jobplanet_rating?: number | null;
          blind_summary?: string | null;
          news_summary?: string | null;
          public_sentiment?: string | null;
          revenue?: string | null;
          employee_count?: number | null;
        };
      };
      market_analysis: {
        Row: {
          id: number;
          analysis_date: string;
          keyword: string;
          total_postings: number | null;
          avg_salary_info: string | null;
          top_companies: Json;
          top_skills: Json;
          market_summary: string | null;
          trend_analysis: string | null;
          recommendations: string | null;
          llm_analysis: string | null;
          project_ideas: string | null;
          roadmap_3months: string | null;
          roadmap_6months: string | null;
          created_at: string;
        };
        Insert: {
          id?: number;
          keyword: string;
          total_postings?: number | null;
          avg_salary_info?: string | null;
          top_companies?: Json;
          top_skills?: Json;
          market_summary?: string | null;
          trend_analysis?: string | null;
          recommendations?: string | null;
          llm_analysis?: string | null;
          project_ideas?: string | null;
          roadmap_3months?: string | null;
          roadmap_6months?: string | null;
        };
        Update: {
          id?: number;
          keyword?: string;
          total_postings?: number | null;
          avg_salary_info?: string | null;
          top_companies?: Json;
          top_skills?: Json;
          market_summary?: string | null;
          trend_analysis?: string | null;
          recommendations?: string | null;
          llm_analysis?: string | null;
          project_ideas?: string | null;
          roadmap_3months?: string | null;
          roadmap_6months?: string | null;
        };
      };
      skill_trends: {
        Row: {
          id: number;
          skill_name: string;
          category: string | null;
          mention_count: number;
          job_category: string | null;
          trend_direction: string | null;
          analysis_date: string;
          period_start: string | null;
          period_end: string | null;
        };
        Insert: {
          id?: number;
          skill_name: string;
          category?: string | null;
          mention_count?: number;
          job_category?: string | null;
          trend_direction?: string | null;
          period_start?: string | null;
          period_end?: string | null;
        };
        Update: {
          id?: number;
          skill_name?: string;
          category?: string | null;
          mention_count?: number;
          job_category?: string | null;
          trend_direction?: string | null;
          period_start?: string | null;
          period_end?: string | null;
        };
      };
    };
    Views: {
      active_job_postings: {
        Row: {
          id: number;
          source_site: string;
          job_id: string;
          title: string;
          company_name: string;
          company_id: number | null;
          job_category: string | null;
          position_level: string | null;
          employment_type: string | null;
          description: string | null;
          requirements: string | null;
          preferred: string | null;
          required_skills: string[];
          preferred_skills: string[];
          salary_info: string | null;
          location: string | null;
          url: string | null;
          crawled_at: string;
          posted_at: string | null;
          expires_at: string | null;
          is_active: boolean;
          company_industry: string | null;
          company_size: string | null;
          jobplanet_rating: number | null;
        };
      };
      latest_market_analysis: {
        Row: {
          id: number;
          analysis_date: string;
          keyword: string;
          total_postings: number | null;
          avg_salary_info: string | null;
          top_companies: Json;
          top_skills: Json;
          market_summary: string | null;
          trend_analysis: string | null;
          recommendations: string | null;
          llm_analysis: string | null;
          project_ideas: string | null;
          roadmap_3months: string | null;
          roadmap_6months: string | null;
          created_at: string;
        };
      };
    };
  };
}

// Helper types
export type JobPosting = Database['public']['Tables']['job_postings']['Row'];
export type Company = Database['public']['Tables']['companies']['Row'];
export type MarketAnalysis = Database['public']['Tables']['market_analysis']['Row'];
export type SkillTrend = Database['public']['Tables']['skill_trends']['Row'];
