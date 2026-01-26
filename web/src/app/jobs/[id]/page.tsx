import { createServerClient } from '@/lib/supabase/server';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import Link from 'next/link';
import { notFound } from 'next/navigation';

interface JobDetailPageProps {
  params: Promise<{ id: string }>;
}

async function getJob(id: string) {
  const supabase = await createServerClient();

  const { data: job, error } = await supabase
    .from('job_postings')
    .select('*')
    .eq('id', id)
    .single();

  if (error || !job) {
    return null;
  }

  return job;
}

export default async function JobDetailPage({ params }: JobDetailPageProps) {
  const { id } = await params;
  const job = await getJob(id);

  if (!job) {
    notFound();
  }

  return (
    <div className="lg:ml-64 space-y-6">
      {/* Back Button */}
      <Link
        href="/jobs"
        className="inline-flex items-center text-sm text-gray-600 hover:text-gray-900"
      >
        <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
        채용공고 목록으로
      </Link>

      {/* Job Header */}
      <Card>
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Badge variant="primary">{job.source_site}</Badge>
              {job.employment_type && (
                <Badge variant="default">{job.employment_type}</Badge>
              )}
            </div>
            <h1 className="text-2xl font-bold text-gray-900">{job.title}</h1>
            <p className="text-lg text-gray-600 mt-2">{job.company_name}</p>
            <div className="flex flex-wrap items-center gap-4 mt-4 text-sm text-gray-500">
              {job.location && (
                <span className="flex items-center">
                  <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                  {job.location}
                </span>
              )}
              {job.position_level && (
                <span className="flex items-center">
                  <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                  {job.position_level}
                </span>
              )}
              {job.salary_info && (
                <span className="flex items-center">
                  <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  {job.salary_info}
                </span>
              )}
            </div>
          </div>
          <div className="flex flex-col gap-2">
            {job.url && (
              <a
                href={job.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center justify-center px-6 py-3 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
              >
                지원하기
                <svg className="w-4 h-4 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                </svg>
              </a>
            )}
            <span className="text-xs text-gray-400 text-center">
              수집일: {new Date(job.crawled_at).toLocaleDateString('ko-KR')}
            </span>
          </div>
        </div>
      </Card>

      {/* Skills */}
      {((job.required_skills as string[])?.length > 0 || (job.preferred_skills as string[])?.length > 0) && (
        <Card title="요구 기술">
          <div className="space-y-4">
            {(job.required_skills as string[])?.length > 0 && (
              <div>
                <h4 className="text-sm font-medium text-gray-700 mb-2">필수 기술</h4>
                <div className="flex flex-wrap gap-2">
                  {(job.required_skills as string[]).map((skill, idx) => (
                    <Badge key={idx} variant="primary" size="md">
                      {skill}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
            {(job.preferred_skills as string[])?.length > 0 && (
              <div>
                <h4 className="text-sm font-medium text-gray-700 mb-2">우대 기술</h4>
                <div className="flex flex-wrap gap-2">
                  {(job.preferred_skills as string[]).map((skill, idx) => (
                    <Badge key={idx} variant="default" size="md">
                      {skill}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Description */}
      {job.description && (
        <Card title="상세 내용">
          <div className="prose max-w-none">
            <p className="whitespace-pre-wrap text-gray-700">{job.description}</p>
          </div>
        </Card>
      )}

      {/* Requirements */}
      {job.requirements && (
        <Card title="자격요건">
          <div className="prose max-w-none">
            <p className="whitespace-pre-wrap text-gray-700">{job.requirements}</p>
          </div>
        </Card>
      )}

      {/* Preferred */}
      {job.preferred && (
        <Card title="우대사항">
          <div className="prose max-w-none">
            <p className="whitespace-pre-wrap text-gray-700">{job.preferred}</p>
          </div>
        </Card>
      )}
    </div>
  );
}
