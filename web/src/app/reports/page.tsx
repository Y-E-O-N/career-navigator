import { createServerClient } from '@/lib/supabase/server';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import Link from 'next/link';
import type { CompanyReport } from '@/lib/supabase/types';

// ISR 재검증 주기 (초)
export const revalidate = 600; // 10분

interface ReportsPageProps {
  searchParams: Promise<{
    page?: string;
  }>;
}

async function getReports(params: {
  page?: string;
}): Promise<{ reports: CompanyReport[]; count: number }> {
  const supabase = await createServerClient();

  const page = Number(params.page) || 1;
  const limit = 20;
  const offset = (page - 1) * limit;

  const { data: reports, count, error } = await supabase
    .from('company_reports')
    .select('*', { count: 'exact' })
    .order('generated_at', { ascending: false })
    .range(offset, offset + limit - 1);

  if (error) {
    console.error('Error fetching reports:', error);
    return { reports: [], count: 0 };
  }

  return { reports: reports || [], count: count || 0 };
}

// verdict를 한글로 변환
function getVerdictLabel(verdict: string | null): { label: string; variant: 'success' | 'warning' | 'danger' | 'default' } {
  switch (verdict) {
    case 'STRONG_YES':
      return { label: '강력 추천', variant: 'success' };
    case 'YES':
      return { label: '추천', variant: 'success' };
    case 'CONDITIONAL':
      return { label: '조건부 추천', variant: 'warning' };
    case 'NO':
      return { label: '비추천', variant: 'danger' };
    case 'STRONG_NO':
      return { label: '강력 비추천', variant: 'danger' };
    default:
      return { label: '분석중', variant: 'default' };
  }
}

export default async function ReportsPage({ searchParams }: ReportsPageProps) {
  const params = await searchParams;
  const { reports, count } = await getReports(params);
  const currentPage = Number(params.page) || 1;
  const totalPages = Math.ceil(count / 20);

  return (
    <div className="lg:ml-64 space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">분석 리포트</h1>
        <p className="mt-1 text-sm text-gray-500">
          총 {count.toLocaleString()}개의 기업 분석 리포트
        </p>
      </div>

      {/* Report List */}
      <div className="space-y-4">
        {reports.length > 0 ? (
          reports.map((report) => {
            const verdict = getVerdictLabel(report.verdict);
            return (
              <Card key={report.id} className="card-hover relative">
                <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <Link
                        href={report.company_id ? `/companies/${report.company_id}` : '#'}
                        className="text-lg font-semibold text-gray-900 hover:text-primary-600"
                      >
                        {report.company_name}
                      </Link>
                      <Badge variant={verdict.variant} size="sm">
                        {verdict.label}
                      </Badge>
                    </div>

                    {report.total_score !== null && (
                      <div className="flex items-center gap-2 mt-2">
                        <span className="text-sm text-gray-500">종합 점수:</span>
                        <span className={`text-lg font-bold ${
                          report.total_score >= 70 ? 'text-green-600' :
                          report.total_score >= 50 ? 'text-yellow-600' : 'text-red-600'
                        }`}>
                          {report.total_score}점
                        </span>
                      </div>
                    )}

                    {report.key_attractions && report.key_attractions.length > 0 && (
                      <div className="mt-3">
                        <span className="text-xs text-gray-500 block mb-1">주요 매력 포인트</span>
                        <div className="flex flex-wrap gap-1">
                          {report.key_attractions.slice(0, 3).map((attraction, idx) => (
                            <Badge key={idx} variant="success" size="sm">
                              {attraction}
                            </Badge>
                          ))}
                          {report.key_attractions.length > 3 && (
                            <Badge variant="default" size="sm">
                              +{report.key_attractions.length - 3}
                            </Badge>
                          )}
                        </div>
                      </div>
                    )}

                    {report.key_risks && report.key_risks.length > 0 && (
                      <div className="mt-2">
                        <span className="text-xs text-gray-500 block mb-1">주의 사항</span>
                        <div className="flex flex-wrap gap-1">
                          {report.key_risks.slice(0, 3).map((risk, idx) => (
                            <Badge key={idx} variant="danger" size="sm">
                              {risk}
                            </Badge>
                          ))}
                          {report.key_risks.length > 3 && (
                            <Badge variant="default" size="sm">
                              +{report.key_risks.length - 3}
                            </Badge>
                          )}
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="flex flex-col items-end gap-2">
                    <span className="text-xs text-gray-400">
                      {new Date(report.generated_at).toLocaleDateString('ko-KR')}
                    </span>
                    {report.llm_model && (
                      <Badge variant="default" size="sm">
                        {report.llm_model}
                      </Badge>
                    )}
                    {report.company_id && (
                      <Link
                        href={`/companies/${report.company_id}`}
                        className="text-sm text-primary-600 hover:text-primary-700"
                      >
                        상세 보기 &rarr;
                      </Link>
                    )}
                  </div>
                </div>
              </Card>
            );
          })
        ) : (
          <Card>
            <p className="text-center text-gray-500 py-12">
              아직 생성된 분석 리포트가 없습니다.
            </p>
          </Card>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-center gap-2">
          {currentPage > 1 && (
            <Link
              href={`/reports?page=${currentPage - 1}`}
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
              href={`/reports?page=${currentPage + 1}`}
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
