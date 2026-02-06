import { createServerClient } from '@/lib/supabase/server';
import { notFound } from 'next/navigation';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import Link from 'next/link';
import type { Company, CompanyReport, JobPosting } from '@/lib/supabase/types';

// ISR 재검증 주기 (초)
export const revalidate = 3600;

interface PageProps {
  params: Promise<{ id: string }>;
}

async function getCompany(id: number): Promise<Company | null> {
  const supabase = await createServerClient();

  const { data, error } = await supabase
    .from('companies')
    .select('*')
    .eq('id', id)
    .single();

  if (error) {
    console.error('Error fetching company:', error);
    return null;
  }

  return data;
}

async function getCompanyReports(companyId: number): Promise<CompanyReport[]> {
  const supabase = await createServerClient();

  const { data, error } = await supabase
    .from('company_reports')
    .select('*')
    .eq('company_id', companyId)
    .order('generated_at', { ascending: false })
    .limit(5);

  if (error) {
    console.error('Error fetching reports:', error);
    return [];
  }

  return data || [];
}

async function getCompanyJobs(companyId: number): Promise<JobPosting[]> {
  const supabase = await createServerClient();

  const { data, error } = await supabase
    .from('job_postings')
    .select('*')
    .eq('company_id', companyId)
    .eq('is_active', true)
    .order('crawled_at', { ascending: false })
    .limit(10);

  if (error) {
    console.error('Error fetching jobs:', error);
    return [];
  }

  return data || [];
}

function getVerdictStyle(verdict: string | null) {
  if (!verdict) return { bg: 'bg-gray-100', text: 'text-gray-700' };

  if (verdict.toLowerCase().includes('no-go') || verdict.toLowerCase().includes('nogo')) {
    return { bg: 'bg-red-100', text: 'text-red-700' };
  }
  if (verdict.toLowerCase().includes('conditional')) {
    return { bg: 'bg-yellow-100', text: 'text-yellow-700' };
  }
  if (verdict.toLowerCase() === 'go') {
    return { bg: 'bg-green-100', text: 'text-green-700' };
  }
  return { bg: 'bg-gray-100', text: 'text-gray-700' };
}

function formatDate(dateStr: string) {
  const date = new Date(dateStr);
  return date.toLocaleDateString('ko-KR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

export default async function CompanyDetailPage({ params }: PageProps) {
  const { id } = await params;
  const companyId = parseInt(id, 10);

  if (isNaN(companyId)) {
    notFound();
  }

  const [company, reports, jobs] = await Promise.all([
    getCompany(companyId),
    getCompanyReports(companyId),
    getCompanyJobs(companyId),
  ]);

  if (!company) {
    notFound();
  }

  return (
    <div className="lg:ml-64 space-y-6">
      {/* Breadcrumb */}
      <nav className="flex" aria-label="Breadcrumb">
        <ol className="flex items-center space-x-2 text-sm text-gray-500">
          <li>
            <Link href="/companies" className="hover:text-primary-600">
              기업정보
            </Link>
          </li>
          <li>/</li>
          <li className="text-gray-900 font-medium">{company.name}</li>
        </ol>
      </nav>

      {/* Company Header */}
      <Card>
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{company.name}</h1>
            <div className="flex flex-wrap gap-2 mt-2">
              {company.industry && (
                <Badge variant="primary">{company.industry}</Badge>
              )}
              {company.company_size && (
                <Badge variant="default">{company.company_size}</Badge>
              )}
            </div>
          </div>

          {company.jobplanet_rating && (
            <div className="flex items-center gap-2 bg-yellow-50 px-4 py-2 rounded-lg">
              <svg className="w-6 h-6 text-yellow-500" fill="currentColor" viewBox="0 0 20 20">
                <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
              </svg>
              <div>
                <div className="text-2xl font-bold text-yellow-600">
                  {company.jobplanet_rating.toFixed(1)}
                </div>
                <div className="text-xs text-gray-500">잡플래닛</div>
              </div>
            </div>
          )}
        </div>

        {/* Company Info Grid */}
        <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
          {company.address && (
            <div>
              <span className="text-gray-500">위치:</span>
              <span className="ml-2 text-gray-900">{company.address}</span>
            </div>
          )}
          {company.employee_count && (
            <div>
              <span className="text-gray-500">직원 수:</span>
              <span className="ml-2 text-gray-900">{company.employee_count.toLocaleString()}명</span>
            </div>
          )}
          {company.founded_year && (
            <div>
              <span className="text-gray-500">설립연도:</span>
              <span className="ml-2 text-gray-900">{company.founded_year}년</span>
            </div>
          )}
          {company.revenue && (
            <div>
              <span className="text-gray-500">매출:</span>
              <span className="ml-2 text-gray-900">{company.revenue}</span>
            </div>
          )}
          {company.website && (
            <div>
              <span className="text-gray-500">웹사이트:</span>
              <a
                href={company.website}
                target="_blank"
                rel="noopener noreferrer"
                className="ml-2 text-primary-600 hover:underline"
              >
                {company.website}
              </a>
            </div>
          )}
        </div>

        {company.description && (
          <div className="mt-4 pt-4 border-t">
            <p className="text-gray-600">{company.description}</p>
          </div>
        )}
      </Card>

      {/* Analysis Reports Section */}
      <div>
        <h2 className="text-xl font-bold text-gray-900 mb-4">기업 분석 보고서</h2>

        {reports.length > 0 ? (
          <div className="space-y-4">
            {reports.map((report) => {
              const verdictStyle = getVerdictStyle(report.verdict);

              return (
                <Card key={report.id} className="hover:shadow-lg transition-shadow">
                  <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-3">
                        <span className={`px-3 py-1 rounded-full text-sm font-semibold ${verdictStyle.bg} ${verdictStyle.text}`}>
                          {report.verdict || '미정'}
                        </span>
                        {report.total_score && (
                          <span className="text-lg font-bold text-gray-900">
                            {report.total_score.toFixed(1)}/5.0
                          </span>
                        )}
                        {report.quality_passed && (
                          <Badge variant="success" size="sm">Quality 통과</Badge>
                        )}
                      </div>

                      <div className="mt-2 text-sm text-gray-500">
                        <span>{formatDate(report.generated_at)}</span>
                        {report.llm_model && (
                          <span className="ml-3">
                            모델: {report.llm_model}
                          </span>
                        )}
                      </div>

                      {/* Key Points */}
                      <div className="mt-3 flex flex-wrap gap-4">
                        {report.key_attractions && report.key_attractions.length > 0 && (
                          <div className="text-sm">
                            <span className="text-green-600 font-medium">매력 포인트:</span>
                            <span className="ml-1 text-gray-600">
                              {report.key_attractions.slice(0, 2).join(', ')}
                            </span>
                          </div>
                        )}
                        {report.key_risks && report.key_risks.length > 0 && (
                          <div className="text-sm">
                            <span className="text-red-600 font-medium">리스크:</span>
                            <span className="ml-1 text-gray-600">
                              {report.key_risks.slice(0, 2).join(', ')}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>

                    <Link
                      href={`/companies/${companyId}/reports/${report.id}`}
                      className="inline-flex items-center px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
                    >
                      상세 보기
                      <svg className="ml-2 w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    </Link>
                  </div>
                </Card>
              );
            })}
          </div>
        ) : (
          <Card>
            <div className="text-center py-8">
              <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <p className="mt-4 text-gray-500">아직 생성된 분석 보고서가 없습니다.</p>
              <p className="mt-1 text-sm text-gray-400">
                CLI에서 <code className="bg-gray-100 px-2 py-1 rounded">python main.py analyze-report "{company.name}"</code> 명령으로 생성할 수 있습니다.
              </p>
            </div>
          </Card>
        )}
      </div>

      {/* Job Postings Section */}
      <div>
        <h2 className="text-xl font-bold text-gray-900 mb-4">
          채용공고 ({jobs.length}건)
        </h2>

        {jobs.length > 0 ? (
          <div className="grid gap-4">
            {jobs.map((job) => (
              <Link key={job.id} href={`/jobs/${job.id}`}>
                <Card className="card-hover">
                  <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2">
                    <div>
                      <h3 className="font-semibold text-gray-900">{job.title}</h3>
                      <div className="flex flex-wrap gap-2 mt-1">
                        {job.job_category && (
                          <Badge variant="primary" size="sm">{job.job_category}</Badge>
                        )}
                        {job.location && (
                          <Badge variant="default" size="sm">{job.location}</Badge>
                        )}
                        {job.position_level && (
                          <Badge variant="default" size="sm">{job.position_level}</Badge>
                        )}
                      </div>
                    </div>
                    <div className="text-sm text-gray-500">
                      {formatDate(job.crawled_at)}
                    </div>
                  </div>
                </Card>
              </Link>
            ))}
          </div>
        ) : (
          <Card>
            <p className="text-center text-gray-500 py-8">
              현재 진행 중인 채용공고가 없습니다.
            </p>
          </Card>
        )}
      </div>
    </div>
  );
}
