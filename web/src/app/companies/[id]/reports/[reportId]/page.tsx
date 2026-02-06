import { createServerClient } from '@/lib/supabase/server';
import { notFound } from 'next/navigation';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import Link from 'next/link';
import type { CompanyReport, Company } from '@/lib/supabase/types';

// ISR 재검증 주기 (초)
export const revalidate = 3600;

interface PageProps {
  params: Promise<{ id: string; reportId: string }>;
}

async function getReport(reportId: number): Promise<CompanyReport | null> {
  const supabase = await createServerClient();

  const { data, error } = await supabase
    .from('company_reports')
    .select('*')
    .eq('id', reportId)
    .single();

  if (error) {
    console.error('Error fetching report:', error);
    return null;
  }

  return data;
}

async function getCompany(id: number): Promise<Company | null> {
  const supabase = await createServerClient();

  const { data, error } = await supabase
    .from('companies')
    .select('*')
    .eq('id', id)
    .single();

  if (error) {
    return null;
  }

  return data;
}

function getVerdictStyle(verdict: string | null) {
  if (!verdict) return { bg: 'bg-gray-100', text: 'text-gray-700', border: 'border-gray-300' };

  if (verdict.toLowerCase().includes('no-go') || verdict.toLowerCase().includes('nogo')) {
    return { bg: 'bg-red-100', text: 'text-red-700', border: 'border-red-300' };
  }
  if (verdict.toLowerCase().includes('conditional')) {
    return { bg: 'bg-yellow-100', text: 'text-yellow-700', border: 'border-yellow-300' };
  }
  if (verdict.toLowerCase() === 'go') {
    return { bg: 'bg-green-100', text: 'text-green-700', border: 'border-green-300' };
  }
  return { bg: 'bg-gray-100', text: 'text-gray-700', border: 'border-gray-300' };
}

function formatDate(dateStr: string) {
  const date = new Date(dateStr);
  return date.toLocaleDateString('ko-KR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default async function ReportDetailPage({ params }: PageProps) {
  const { id, reportId } = await params;
  const companyId = parseInt(id, 10);
  const reportIdNum = parseInt(reportId, 10);

  if (isNaN(companyId) || isNaN(reportIdNum)) {
    notFound();
  }

  const [report, company] = await Promise.all([
    getReport(reportIdNum),
    getCompany(companyId),
  ]);

  if (!report) {
    notFound();
  }

  const verdictStyle = getVerdictStyle(report.verdict);
  const scores = report.scores as Record<string, number> | null;

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
          <li>
            <Link href={`/companies/${companyId}`} className="hover:text-primary-600">
              {company?.name || report.company_name}
            </Link>
          </li>
          <li>/</li>
          <li className="text-gray-900 font-medium">분석 보고서</li>
        </ol>
      </nav>

      {/* Report Header */}
      <Card>
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {report.company_name} 기업 분석 보고서
            </h1>
            <p className="mt-1 text-sm text-gray-500">
              생성일: {formatDate(report.generated_at)}
            </p>
          </div>

          {/* Verdict Badge */}
          <div className={`px-6 py-4 rounded-xl border-2 ${verdictStyle.bg} ${verdictStyle.border}`}>
            <div className="text-center">
              <div className={`text-2xl font-bold ${verdictStyle.text}`}>
                {report.verdict || '미정'}
              </div>
              {report.total_score && (
                <div className="text-3xl font-bold text-gray-900 mt-1">
                  {report.total_score.toFixed(1)}<span className="text-lg text-gray-500">/5.0</span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Meta Info */}
        <div className="mt-4 pt-4 border-t flex flex-wrap gap-4 text-sm text-gray-500">
          {report.llm_provider && (
            <span>Provider: {report.llm_provider}</span>
          )}
          {report.llm_model && (
            <span>Model: {report.llm_model}</span>
          )}
          {report.report_version && (
            <span>Version: {report.report_version}</span>
          )}
          {report.quality_passed && (
            <Badge variant="success" size="sm">Quality Gate 통과</Badge>
          )}
        </div>
      </Card>

      {/* Scores Section */}
      {scores && Object.keys(scores).length > 0 && (
        <Card>
          <h2 className="text-lg font-bold text-gray-900 mb-4">평가 점수</h2>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {Object.entries(scores).map(([key, value]) => (
              <div key={key} className="text-center p-4 bg-gray-50 rounded-lg">
                <div className="text-2xl font-bold text-primary-600">
                  {typeof value === 'number' ? value.toFixed(1) : value}
                </div>
                <div className="text-sm text-gray-500 mt-1">{key}</div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Key Points */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* Attractions */}
        {report.key_attractions && report.key_attractions.length > 0 && (
          <Card>
            <h2 className="text-lg font-bold text-green-700 mb-3 flex items-center">
              <svg className="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              핵심 매력 포인트
            </h2>
            <ul className="space-y-2">
              {report.key_attractions.map((item, idx) => (
                <li key={idx} className="flex items-start">
                  <span className="text-green-500 mr-2">+</span>
                  <span className="text-gray-700">{item}</span>
                </li>
              ))}
            </ul>
          </Card>
        )}

        {/* Risks */}
        {report.key_risks && report.key_risks.length > 0 && (
          <Card>
            <h2 className="text-lg font-bold text-red-700 mb-3 flex items-center">
              <svg className="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              핵심 리스크
            </h2>
            <ul className="space-y-2">
              {report.key_risks.map((item, idx) => (
                <li key={idx} className="flex items-start">
                  <span className="text-red-500 mr-2">!</span>
                  <span className="text-gray-700">{item}</span>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>

      {/* Verification Items */}
      {report.verification_items && report.verification_items.length > 0 && (
        <Card>
          <h2 className="text-lg font-bold text-yellow-700 mb-3 flex items-center">
            <svg className="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
            </svg>
            면접에서 확인 필요
          </h2>
          <ul className="space-y-2">
            {report.verification_items.map((item, idx) => (
              <li key={idx} className="flex items-start">
                <span className="text-yellow-500 mr-2">?</span>
                <span className="text-gray-700">{item}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* Full Report Content */}
      <Card>
        <h2 className="text-lg font-bold text-gray-900 mb-4">전체 보고서</h2>

        {report.full_html ? (
          <div
            className="prose prose-sm max-w-none report-content"
            dangerouslySetInnerHTML={{ __html: report.full_html }}
          />
        ) : report.full_markdown ? (
          <div className="prose prose-sm max-w-none whitespace-pre-wrap font-mono text-sm bg-gray-50 p-4 rounded-lg overflow-auto">
            {report.full_markdown}
          </div>
        ) : (
          <p className="text-gray-500">보고서 내용이 없습니다.</p>
        )}
      </Card>

      {/* Data Sources */}
      {report.data_sources && (
        <Card>
          <h2 className="text-lg font-bold text-gray-900 mb-3">데이터 소스</h2>
          <div className="flex flex-wrap gap-2">
            {Object.entries(report.data_sources as Record<string, number | boolean>).map(([key, value]) => (
              <Badge
                key={key}
                variant={value ? 'success' : 'default'}
                size="sm"
              >
                {key}: {typeof value === 'boolean' ? (value ? 'O' : 'X') : value}
              </Badge>
            ))}
          </div>
        </Card>
      )}

      {/* Back Button */}
      <div className="flex justify-center">
        <Link
          href={`/companies/${companyId}`}
          className="inline-flex items-center px-6 py-3 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
        >
          <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          기업 페이지로 돌아가기
        </Link>
      </div>

      {/* Custom styles for report content */}
      <style jsx global>{`
        .report-content h1 { font-size: 1.5rem; font-weight: 700; margin-top: 2rem; margin-bottom: 1rem; color: #1f2937; border-bottom: 2px solid #3b82f6; padding-bottom: 0.5rem; }
        .report-content h2 { font-size: 1.25rem; font-weight: 600; margin-top: 1.5rem; margin-bottom: 0.75rem; color: #374151; padding-left: 0.75rem; border-left: 4px solid #3b82f6; }
        .report-content h3 { font-size: 1.1rem; font-weight: 600; margin-top: 1rem; margin-bottom: 0.5rem; color: #4b5563; }
        .report-content table { width: 100%; border-collapse: collapse; margin: 1rem 0; }
        .report-content th, .report-content td { padding: 0.75rem; text-align: left; border-bottom: 1px solid #e5e7eb; }
        .report-content th { background-color: #f9fafb; font-weight: 600; }
        .report-content .tag-fact { display: inline-block; background-color: #dbeafe; color: #1e40af; padding: 2px 8px; border-radius: 4px; font-size: 0.85rem; }
        .report-content .tag-interpretation { display: inline-block; background-color: #fef3c7; color: #92400e; padding: 2px 8px; border-radius: 4px; font-size: 0.85rem; }
        .report-content .tag-judgment { display: inline-block; background-color: #fce7f3; color: #9d174d; padding: 2px 8px; border-radius: 4px; font-size: 0.85rem; }
        .report-content .source-label { display: inline-block; background-color: #f3f4f6; color: #374151; padding: 2px 6px; border-radius: 3px; font-size: 0.8rem; font-weight: 600; }
        .report-content .verdict-go { display: inline-block; background-color: #16a34a; color: white; padding: 4px 12px; border-radius: 20px; font-weight: 600; }
        .report-content .verdict-conditional { display: inline-block; background-color: #d97706; color: white; padding: 4px 12px; border-radius: 20px; font-weight: 600; }
        .report-content .verdict-nogo { display: inline-block; background-color: #dc2626; color: white; padding: 4px 12px; border-radius: 20px; font-weight: 600; }
      `}</style>
    </div>
  );
}
