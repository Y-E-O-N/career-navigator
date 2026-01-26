import { createServerClient } from '@/lib/supabase/server';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import type { MarketAnalysis } from '@/lib/supabase/types';

// Cloudflare Pages Edge Runtime
export const runtime = 'edge';

interface TrendDetailPageProps {
  params: Promise<{ keyword: string }>;
}

async function getAnalysis(keyword: string): Promise<MarketAnalysis | null> {
  const supabase = await createServerClient();
  const decodedKeyword = decodeURIComponent(keyword);

  const { data: analysis, error } = await supabase
    .from('market_analysis')
    .select('*')
    .eq('keyword', decodedKeyword)
    .order('analysis_date', { ascending: false })
    .limit(1)
    .single();

  if (error || !analysis) {
    return null;
  }

  return analysis;
}

export default async function TrendDetailPage({ params }: TrendDetailPageProps) {
  const { keyword } = await params;
  const analysis = await getAnalysis(keyword);

  if (!analysis) {
    notFound();
  }

  const topCompanies = (analysis.top_companies as Array<{ company: string; count: number }>) || [];
  const topSkills = (analysis.top_skills as Array<{ skill: string; count: number; percentage?: number }>) || [];

  return (
    <div className="lg:ml-64 space-y-6">
      {/* Back Button */}
      <Link
        href="/trends"
        className="inline-flex items-center text-sm text-gray-600 hover:text-gray-900"
      >
        <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
        트렌드 목록으로
      </Link>

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">{analysis.keyword}</h1>
        <p className="mt-1 text-sm text-gray-500">
          분석일: {new Date(analysis.analysis_date).toLocaleDateString('ko-KR')}
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card>
          <div className="text-center">
            <p className="text-sm text-gray-500">총 채용공고</p>
            <p className="text-3xl font-bold text-gray-900 mt-2">
              {analysis.total_postings?.toLocaleString() || 0}
            </p>
          </div>
        </Card>
        <Card>
          <div className="text-center">
            <p className="text-sm text-gray-500">채용 기업 수</p>
            <p className="text-3xl font-bold text-gray-900 mt-2">
              {topCompanies.length}
            </p>
          </div>
        </Card>
        <Card>
          <div className="text-center">
            <p className="text-sm text-gray-500">주요 기술</p>
            <p className="text-3xl font-bold text-gray-900 mt-2">
              {topSkills.length}
            </p>
          </div>
        </Card>
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top Companies */}
        <Card title="상위 채용 기업">
          <div className="space-y-3">
            {topCompanies.length > 0 ? (
              topCompanies.slice(0, 10).map((item, index) => (
                <div
                  key={index}
                  className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
                >
                  <div className="flex items-center">
                    <span className="w-6 text-sm font-medium text-gray-400">
                      {index + 1}
                    </span>
                    <span className="font-medium text-gray-900">
                      {item.company}
                    </span>
                  </div>
                  <Badge variant="primary">{item.count}건</Badge>
                </div>
              ))
            ) : (
              <p className="text-center text-gray-500 py-4">데이터 없음</p>
            )}
          </div>
        </Card>

        {/* Top Skills */}
        <Card title="요구 기술 스택">
          <div className="space-y-3">
            {topSkills.length > 0 ? (
              topSkills.slice(0, 10).map((item, index) => (
                <div
                  key={index}
                  className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
                >
                  <div className="flex items-center flex-1">
                    <span className="w-6 text-sm font-medium text-gray-400">
                      {index + 1}
                    </span>
                    <span className="font-medium text-gray-900">
                      {item.skill}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    {item.percentage && (
                      <div className="w-24 bg-gray-200 rounded-full h-2">
                        <div
                          className="bg-primary-600 h-2 rounded-full"
                          style={{ width: `${Math.min(item.percentage, 100)}%` }}
                        />
                      </div>
                    )}
                    <span className="text-sm text-gray-600 w-16 text-right">
                      {item.percentage ? `${item.percentage.toFixed(1)}%` : `${item.count}건`}
                    </span>
                  </div>
                </div>
              ))
            ) : (
              <p className="text-center text-gray-500 py-4">데이터 없음</p>
            )}
          </div>
        </Card>
      </div>

      {/* Market Summary */}
      {analysis.market_summary && (
        <Card title="시장 분석 요약">
          <div className="prose max-w-none">
            <p className="whitespace-pre-wrap text-gray-700">{analysis.market_summary}</p>
          </div>
        </Card>
      )}

      {/* Trend Analysis */}
      {analysis.trend_analysis && (
        <Card title="트렌드 분석">
          <div className="prose max-w-none">
            <p className="whitespace-pre-wrap text-gray-700">{analysis.trend_analysis}</p>
          </div>
        </Card>
      )}

      {/* Recommendations */}
      {analysis.recommendations && (
        <Card title="추천 사항">
          <div className="prose max-w-none">
            <p className="whitespace-pre-wrap text-gray-700">{analysis.recommendations}</p>
          </div>
        </Card>
      )}

      {/* Roadmaps */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {analysis.roadmap_3months && (
          <Card title="3개월 로드맵">
            <div className="prose max-w-none text-sm">
              <p className="whitespace-pre-wrap text-gray-700">{analysis.roadmap_3months}</p>
            </div>
          </Card>
        )}
        {analysis.roadmap_6months && (
          <Card title="6개월 로드맵">
            <div className="prose max-w-none text-sm">
              <p className="whitespace-pre-wrap text-gray-700">{analysis.roadmap_6months}</p>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
