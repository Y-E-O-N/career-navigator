import { createServerClient } from '@/lib/supabase/server';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import Link from 'next/link';
import config from '@/config';
import type { MarketAnalysis, SkillTrend } from '@/lib/supabase/types';

// ISR 재검증 주기 (초)
export const revalidate = 3600;

async function getTrendsData(): Promise<{ analyses: MarketAnalysis[]; skillTrends: SkillTrend[] }> {
  const supabase = await createServerClient();

  // 최신 시장 분석 결과
  const { data: analyses } = await supabase
    .from('market_analysis')
    .select('*')
    .order('analysis_date', { ascending: false });

  // 키워드별 최신 분석만 필터링
  const latestByKeyword = new Map<string, MarketAnalysis>();
  ((analyses || []) as MarketAnalysis[]).forEach((analysis) => {
    if (!latestByKeyword.has(analysis.keyword)) {
      latestByKeyword.set(analysis.keyword, analysis);
    }
  });

  // 스킬 트렌드
  const { data: skillTrends } = await supabase
    .from('skill_trends')
    .select('*')
    .order('mention_count', { ascending: false })
    .limit(config.pagination.detailSkillsCount);

  return {
    analyses: Array.from(latestByKeyword.values()),
    skillTrends: (skillTrends || []) as SkillTrend[],
  };
}

export default async function TrendsPage() {
  const { analyses, skillTrends } = await getTrendsData();

  return (
    <div className="lg:ml-64 space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">기술 트렌드</h1>
        <p className="mt-1 text-sm text-gray-500">
          채용 시장의 기술 트렌드를 분석합니다
        </p>
      </div>

      {/* Market Analysis Cards */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 mb-4">시장 분석 결과</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {analyses.length > 0 ? (
            analyses.map((analysis) => (
              <Link
                key={analysis.id}
                href={`/trends/${encodeURIComponent(analysis.keyword)}`}
              >
                <Card className="h-full card-hover">
                  <h3 className="font-semibold text-gray-900 hover:text-primary-600">
                    {analysis.keyword}
                  </h3>
                  <div className="mt-4 space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-500">총 채용공고</span>
                      <span className="font-medium">
                        {analysis.total_postings?.toLocaleString() || 0}개
                      </span>
                    </div>
                    {analysis.top_skills && (
                      <div className="flex flex-wrap gap-1 mt-3">
                        {((analysis.top_skills as Array<{ skill: string }>) || [])
                          .slice(0, 3)
                          .map((skill, idx) => (
                            <Badge key={idx} variant="primary" size="sm">
                              {typeof skill === 'string' ? skill : skill.skill}
                            </Badge>
                          ))}
                      </div>
                    )}
                  </div>
                  <p className="text-xs text-gray-400 mt-4">
                    {new Date(analysis.analysis_date).toLocaleDateString('ko-KR')}
                  </p>
                </Card>
              </Link>
            ))
          ) : (
            <Card className="col-span-full">
              <p className="text-center text-gray-500 py-12">
                분석 데이터가 없습니다. 크롤러를 실행해주세요.
              </p>
            </Card>
          )}
        </div>
      </div>

      {/* Skill Trends */}
      <Card title="인기 기술 순위">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {skillTrends.length > 0 ? (
            skillTrends.map((skill, index) => (
              <div
                key={skill.id}
                className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
              >
                <div className="flex items-center">
                  <span
                    className={`w-8 h-8 flex items-center justify-center rounded-full text-sm font-bold ${
                      index < 3
                        ? 'bg-primary-100 text-primary-700'
                        : 'bg-gray-200 text-gray-600'
                    }`}
                  >
                    {index + 1}
                  </span>
                  <div className="ml-3">
                    <span className="font-medium text-gray-900">
                      {skill.skill_name}
                    </span>
                    {skill.category && (
                      <span className="ml-2 text-xs text-gray-500">
                        {skill.category}
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-gray-600">
                    {skill.mention_count.toLocaleString()}건
                  </span>
                  {skill.trend_direction === 'increasing' && (
                    <Badge variant="success" size="sm">상승</Badge>
                  )}
                  {skill.trend_direction === 'decreasing' && (
                    <Badge variant="danger" size="sm">하락</Badge>
                  )}
                  {skill.trend_direction === 'stable' && (
                    <Badge variant="default" size="sm">안정</Badge>
                  )}
                </div>
              </div>
            ))
          ) : (
            <p className="col-span-full text-center text-gray-500 py-8">
              스킬 데이터가 없습니다.
            </p>
          )}
        </div>
      </Card>
    </div>
  );
}
