import { createServerClient } from '@/lib/supabase/server';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import Link from 'next/link';
import config from '@/config';
import type { MarketAnalysis } from '@/lib/supabase/types';

// ISR 재검증 주기 (초)
export const revalidate = 3600;

async function getRoadmapData(): Promise<MarketAnalysis[]> {
  const supabase = await createServerClient();

  // 로드맵이 있는 최신 분석 결과만 가져오기
  const { data: analyses } = await supabase
    .from('market_analysis')
    .select('*')
    .not('roadmap_3months', 'is', null)
    .order('analysis_date', { ascending: false });

  // 키워드별 최신 분석만 필터링
  const latestByKeyword = new Map<string, MarketAnalysis>();
  ((analyses || []) as MarketAnalysis[]).forEach((analysis) => {
    if (!latestByKeyword.has(analysis.keyword)) {
      latestByKeyword.set(analysis.keyword, analysis);
    }
  });

  return Array.from(latestByKeyword.values());
}

export default async function RoadmapPage() {
  const roadmaps = await getRoadmapData();

  return (
    <div className="lg:ml-64 space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">커리어 로드맵</h1>
        <p className="mt-1 text-sm text-gray-500">
          직무별 맞춤 커리어 로드맵을 확인하세요
        </p>
      </div>

      {/* Info Banner */}
      <Card className="bg-primary-50 border-primary-200">
        <div className="flex items-start gap-4">
          <div className="p-2 bg-primary-100 rounded-lg">
            <svg className="w-6 h-6 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div>
            <h3 className="font-medium text-primary-900">AI 기반 맞춤 로드맵</h3>
            <p className="text-sm text-primary-700 mt-1">
              채용 시장 분석 데이터를 바탕으로 Claude AI가 생성한 커리어 로드맵입니다.
              실제 채용공고의 요구사항을 분석하여 현실적인 학습 계획을 제안합니다.
            </p>
          </div>
        </div>
      </Card>

      {/* Roadmap Cards */}
      <div className="grid grid-cols-1 gap-6">
        {roadmaps.length > 0 ? (
          roadmaps.map((analysis) => (
            <Card key={analysis.id}>
              <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4 mb-6">
                <div>
                  <h2 className="text-xl font-bold text-gray-900">
                    {analysis.keyword}
                  </h2>
                  <div className="flex items-center gap-4 mt-2 text-sm text-gray-500">
                    <span>채용공고 {analysis.total_postings?.toLocaleString() || 0}개 분석</span>
                    <span>&middot;</span>
                    <span>{new Date(analysis.analysis_date).toLocaleDateString('ko-KR')}</span>
                  </div>
                </div>
                <Link
                  href={`/trends/${encodeURIComponent(analysis.keyword)}`}
                  className="text-sm text-primary-600 hover:text-primary-700"
                >
                  상세 분석 보기 &rarr;
                </Link>
              </div>

              {/* Top Skills */}
              {analysis.top_skills && (
                <div className="mb-6">
                  <h4 className="text-sm font-medium text-gray-700 mb-2">주요 요구 기술</h4>
                  <div className="flex flex-wrap gap-2">
                    {((analysis.top_skills as Array<{ skill: string }>) || [])
                      .slice(0, 8)
                      .map((item, idx) => (
                        <Badge key={idx} variant="primary" size="md">
                          {typeof item === 'string' ? item : item.skill}
                        </Badge>
                      ))}
                  </div>
                </div>
              )}

              {/* Roadmaps Grid */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {analysis.roadmap_3months && (
                  <div className="p-4 bg-gray-50 rounded-lg">
                    <div className="flex items-center gap-2 mb-3">
                      <Badge variant="success">3개월</Badge>
                      <h4 className="font-medium text-gray-900">단기 로드맵</h4>
                    </div>
                    <div className="text-sm text-gray-700 whitespace-pre-wrap max-h-64 overflow-y-auto">
                      {analysis.roadmap_3months}
                    </div>
                  </div>
                )}
                {analysis.roadmap_6months && (
                  <div className="p-4 bg-gray-50 rounded-lg">
                    <div className="flex items-center gap-2 mb-3">
                      <Badge variant="warning">6개월</Badge>
                      <h4 className="font-medium text-gray-900">중기 로드맵</h4>
                    </div>
                    <div className="text-sm text-gray-700 whitespace-pre-wrap max-h-64 overflow-y-auto">
                      {analysis.roadmap_6months}
                    </div>
                  </div>
                )}
              </div>

              {/* Recommendations */}
              {analysis.recommendations && (
                <div className="mt-6 p-4 bg-blue-50 rounded-lg">
                  <h4 className="font-medium text-blue-900 mb-2">추천 사항</h4>
                  <p className="text-sm text-blue-700 whitespace-pre-wrap">
                    {analysis.recommendations}
                  </p>
                </div>
              )}
            </Card>
          ))
        ) : (
          <Card>
            <div className="text-center py-12">
              <svg className="w-12 h-12 mx-auto text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
              </svg>
              <h3 className="mt-4 text-lg font-medium text-gray-900">로드맵이 없습니다</h3>
              <p className="mt-2 text-sm text-gray-500">
                크롤러를 실행하여 채용 데이터를 수집하면 AI가 맞춤 로드맵을 생성합니다.
              </p>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
