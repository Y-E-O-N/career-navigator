import { createServerClient } from '@/lib/supabase/server';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import Link from 'next/link';
import config from '@/config';
import type { JobPosting } from '@/lib/supabase/types';
import AnalyzeCompanyButton from '@/components/AnalyzeCompanyButton';

// ISR 재검증 주기 (초) - 새 공고 빠르게 반영
export const revalidate = 600; // 10분

interface JobsPageProps {
  searchParams: Promise<{
    keyword?: string;
    site?: string;
    page?: string;
    status?: string; // active, closed, today
  }>;
}

async function getJobs(params: {
  keyword?: string;
  site?: string;
  page?: string;
  status?: string;
}): Promise<{ jobs: JobPosting[]; count: number }> {
  const supabase = await createServerClient();

  const page = Number(params.page) || 1;
  const limit = config.pagination.jobsPerPage;
  const offset = (page - 1) * limit;
  const status = params.status || 'active';

  let query = supabase
    .from('job_postings')
    .select('*', { count: 'exact' });

  // 상태별 필터
  if (status === 'active') {
    query = query.eq('is_active', true);
  } else if (status === 'closed') {
    query = query.eq('is_active', false);
  } else if (status === 'today') {
    // 오늘 추가된 공고 (KST 기준)
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    query = query.gte('crawled_at', today.toISOString());
  }

  // 정렬 및 페이지네이션
  query = query
    .order('crawled_at', { ascending: false })
    .range(offset, offset + limit - 1);

  if (params.keyword) {
    query = query.ilike('title', `%${params.keyword}%`);
  }

  if (params.site) {
    query = query.eq('source_site', params.site);
  }

  const { data: jobs, count, error } = await query;

  if (error) {
    console.error('Error fetching jobs:', error);
    return { jobs: [], count: 0 };
  }

  return { jobs: jobs || [], count: count || 0 };
}

export default async function JobsPage({ searchParams }: JobsPageProps) {
  const params = await searchParams;
  const { jobs, count } = await getJobs(params);
  const currentPage = Number(params.page) || 1;
  const totalPages = Math.ceil(count / config.pagination.jobsPerPage);
  const currentStatus = params.status || 'active';

  const sites = config.jobSites.filter(s => s.enabled).map(s => s.id);

  // 탭 정의
  const tabs = [
    { id: 'active', label: '모집중', icon: '🟢' },
    { id: 'today', label: '오늘 추가', icon: '🆕' },
    { id: 'closed', label: '마감', icon: '⏹️' },
  ];

  // 현재 필터 유지하면서 URL 생성
  const buildUrl = (newParams: Record<string, string | undefined>) => {
    const searchParams = new URLSearchParams();
    const merged = { ...params, ...newParams, page: undefined }; // 탭 변경 시 페이지 리셋

    Object.entries(merged).forEach(([key, value]) => {
      if (value) searchParams.set(key, value);
    });

    return `/jobs?${searchParams.toString()}`;
  };

  return (
    <div className="lg:ml-64 space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">채용공고</h1>
        <p className="mt-1 text-sm text-gray-500">
          총 {count.toLocaleString()}개의 채용공고
        </p>
      </div>

      {/* Status Tabs */}
      <div className="flex gap-2 border-b border-gray-200">
        {tabs.map((tab) => (
          <Link
            key={tab.id}
            href={buildUrl({ status: tab.id })}
            className={`
              px-4 py-3 text-sm font-medium border-b-2 transition-colors
              ${currentStatus === tab.id
                ? 'border-primary-600 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }
            `}
          >
            <span className="mr-1.5">{tab.icon}</span>
            {tab.label}
          </Link>
        ))}
      </div>

      {/* Filters */}
      <Card>
        <form className="flex flex-wrap gap-4">
          <input type="hidden" name="status" value={currentStatus} />
          <div className="flex-1 min-w-[200px]">
            <input
              type="text"
              name="keyword"
              placeholder="키워드로 검색..."
              defaultValue={params.keyword || ''}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-gray-700 placeholder-gray-400"
            />
          </div>
          <div>
            <select
              name="site"
              defaultValue={params.site || ''}
              className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-gray-700"
            >
              <option value="">모든 사이트</option>
              {sites.map((site) => (
                <option key={site} value={site}>
                  {site.charAt(0).toUpperCase() + site.slice(1)}
                </option>
              ))}
            </select>
          </div>
          <button
            type="submit"
            className="px-6 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
          >
            검색
          </button>
        </form>
      </Card>

      {/* Job List */}
      <div className="space-y-4">
        {jobs.length > 0 ? (
          jobs.map((job) => (
            <Card key={job.id} className="card-hover relative">
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <Link
                      href={`/jobs/${job.id}`}
                      className="text-lg font-semibold text-gray-900 hover:text-primary-600 after:absolute after:inset-0 after:content-['']"
                    >
                      {job.title}
                    </Link>
                    {!job.is_active && (
                      <Badge variant="danger" size="sm">마감</Badge>
                    )}
                  </div>
                  <p className="text-gray-600 mt-1">
                    {job.company_name}
                  </p>
                  <div className="flex flex-wrap items-center gap-2 mt-2 text-sm text-gray-500">
                    <span>{job.location || '위치 미정'}</span>
                    {job.position_level && (
                      <>
                        <span>&middot;</span>
                        <span>{job.position_level}</span>
                      </>
                    )}
                    {job.salary_info && (
                      <>
                        <span>&middot;</span>
                        <span>{job.salary_info}</span>
                      </>
                    )}
                  </div>
                  {job.required_skills && job.required_skills.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-3">
                      {(job.required_skills as string[]).slice(0, config.ui.maxSkillBadges).map((skill, idx) => (
                        <Badge key={idx} variant="primary" size="sm">
                          {skill}
                        </Badge>
                      ))}
                      {(job.required_skills as string[]).length > config.ui.maxSkillBadges && (
                        <Badge variant="default" size="sm">
                          +{(job.required_skills as string[]).length - config.ui.maxSkillBadges}
                        </Badge>
                      )}
                    </div>
                  )}
                </div>
                <div className="flex flex-col items-end gap-2">
                  <Badge variant="primary">{job.source_site}</Badge>
                  <span className="text-xs text-gray-400">
                    {new Date(job.crawled_at).toLocaleDateString('ko-KR')}
                  </span>
                  <AnalyzeCompanyButton
                    companyName={job.company_name}
                    companyId={job.company_id}
                  />
                  {job.url && (
                    <a
                      href={job.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="relative z-10 text-sm text-primary-600 hover:text-primary-700"
                    >
                      원문 보기 &rarr;
                    </a>
                  )}
                </div>
              </div>
            </Card>
          ))
        ) : (
          <Card>
            <p className="text-center text-gray-500 py-12">
              {currentStatus === 'today'
                ? '오늘 추가된 채용공고가 없습니다.'
                : currentStatus === 'closed'
                ? '마감된 채용공고가 없습니다.'
                : '검색 결과가 없습니다.'
              }
            </p>
          </Card>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-center gap-2">
          {currentPage > 1 && (
            <Link
              href={`/jobs?page=${currentPage - 1}&status=${currentStatus}${params.keyword ? `&keyword=${params.keyword}` : ''}${params.site ? `&site=${params.site}` : ''}`}
              className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
            >
              이전
            </Link>
          )}
          <span className="px-4 py-2 text-gray-600">
            {currentPage} / {totalPages}
          </span>
          {currentPage < totalPages && (
            <Link
              href={`/jobs?page=${currentPage + 1}&status=${currentStatus}${params.keyword ? `&keyword=${params.keyword}` : ''}${params.site ? `&site=${params.site}` : ''}`}
              className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
            >
              다음
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
