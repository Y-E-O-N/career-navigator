import { createServerClient } from '@/lib/supabase/server';
import StatsCard from '@/components/dashboard/StatsCard';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import Link from 'next/link';
import config from '@/config';
import type { JobPosting, MarketAnalysis, SkillTrend } from '@/lib/supabase/types';

// Cloudflare Pages Edge Runtime
export const runtime = 'edge';

// ISR 재검증 주기 (초) - config.cache.dashboard와 동일하게 유지
export const revalidate = 3600;

interface DashboardData {
  totalJobs: number;
  totalCompanies: number;
  latestAnalysis: MarketAnalysis[];
  recentJobs: JobPosting[];
  topSkills: SkillTrend[];
}

async function getDashboardData(): Promise<DashboardData> {
  const supabase = await createServerClient();

  // 총 채용공고 수
  const { count: totalJobs } = await supabase
    .from('job_postings')
    .select('*', { count: 'exact', head: true })
    .eq('is_active', true);

  // 총 기업 수
  const { count: totalCompanies } = await supabase
    .from('companies')
    .select('*', { count: 'exact', head: true });

  // 최근 분석 결과
  const { data: latestAnalysis } = await supabase
    .from('market_analysis')
    .select('*')
    .order('analysis_date', { ascending: false })
    .limit(config.pagination.recentAnalysisCount);

  // 최근 채용공고
  const { data: recentJobs } = await supabase
    .from('job_postings')
    .select('*')
    .eq('is_active', true)
    .order('crawled_at', { ascending: false })
    .limit(config.pagination.recentJobsCount);

  // 인기 스킬
  const { data: topSkills } = await supabase
    .from('skill_trends')
    .select('*')
    .order('mention_count', { ascending: false })
    .limit(config.pagination.topSkillsCount);

  return {
    totalJobs: totalJobs || 0,
    totalCompanies: totalCompanies || 0,
    latestAnalysis: latestAnalysis || [],
    recentJobs: recentJobs || [],
    topSkills: topSkills || [],
  };
}

export default async function DashboardPage() {
  const data = await getDashboardData();

  return (
    <div className="lg:ml-64 space-y-8">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">대시보드</h1>
        <p className="mt-1 text-sm text-gray-500">
          채용 시장 현황을 한눈에 확인하세요
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatsCard
          title="총 채용공고"
          value={data.totalJobs}
          change="지난 주 대비"
          changeType="positive"
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
          }
        />
        <StatsCard
          title="등록된 기업"
          value={data.totalCompanies}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
            </svg>
          }
        />
        <StatsCard
          title="분석 키워드"
          value={data.latestAnalysis.length}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
          }
        />
        <StatsCard
          title="트래킹 스킬"
          value={data.topSkills.length}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
          }
        />
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Recent Jobs */}
        <Card
          title="최근 채용공고"
          className="lg:col-span-2"
          action={
            <Link
              href="/jobs"
              className="text-sm text-primary-600 hover:text-primary-700"
            >
              전체보기 &rarr;
            </Link>
          }
        >
          <div className="space-y-4">
            {data.recentJobs.length > 0 ? (
              data.recentJobs.map((job) => (
                <div
                  key={job.id}
                  className="flex items-center justify-between p-4 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <Link
                      href={`/jobs/${job.id}`}
                      className="text-sm font-medium text-gray-900 hover:text-primary-600 truncate block"
                    >
                      {job.title}
                    </Link>
                    <p className="text-sm text-gray-500 truncate">
                      {job.company_name} &middot; {job.location || '위치 미정'}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 ml-4">
                    <Badge variant="primary">{job.source_site}</Badge>
                  </div>
                </div>
              ))
            ) : (
              <p className="text-center text-gray-500 py-8">
                채용공고가 없습니다. 크롤러를 실행해주세요.
              </p>
            )}
          </div>
        </Card>

        {/* Top Skills */}
        <Card
          title="인기 기술 스택"
          action={
            <Link
              href="/trends"
              className="text-sm text-primary-600 hover:text-primary-700"
            >
              전체보기 &rarr;
            </Link>
          }
        >
          <div className="space-y-3">
            {data.topSkills.length > 0 ? (
              data.topSkills.map((skill, index) => (
                <div key={skill.id} className="flex items-center justify-between">
                  <div className="flex items-center">
                    <span className="w-6 text-sm font-medium text-gray-400">
                      {index + 1}
                    </span>
                    <span className="text-sm font-medium text-gray-900">
                      {skill.skill_name}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-gray-500">
                      {skill.mention_count.toLocaleString()}건
                    </span>
                    {skill.trend_direction === 'increasing' && (
                      <span className="text-green-500">↑</span>
                    )}
                    {skill.trend_direction === 'decreasing' && (
                      <span className="text-red-500">↓</span>
                    )}
                  </div>
                </div>
              ))
            ) : (
              <p className="text-center text-gray-500 py-8">
                스킬 데이터가 없습니다.
              </p>
            )}
          </div>
        </Card>
      </div>

      {/* Latest Analysis */}
      <Card
        title="최근 시장 분석"
        action={
          <Link
            href="/trends"
            className="text-sm text-primary-600 hover:text-primary-700"
          >
            전체보기 &rarr;
          </Link>
        }
      >
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {data.latestAnalysis.length > 0 ? (
            data.latestAnalysis.map((analysis) => (
              <Link
                key={analysis.id}
                href={`/trends/${encodeURIComponent(analysis.keyword)}`}
                className="p-4 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
              >
                <h4 className="font-medium text-gray-900">{analysis.keyword}</h4>
                <p className="text-sm text-gray-500 mt-1">
                  {analysis.total_postings?.toLocaleString() || 0}개 채용공고
                </p>
                <p className="text-xs text-gray-400 mt-2">
                  {new Date(analysis.analysis_date).toLocaleDateString('ko-KR')}
                </p>
              </Link>
            ))
          ) : (
            <p className="col-span-full text-center text-gray-500 py-8">
              분석 데이터가 없습니다. 크롤러를 실행해주세요.
            </p>
          )}
        </div>
      </Card>
    </div>
  );
}
