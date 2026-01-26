import { createServerClient } from '@/lib/supabase/server';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import Link from 'next/link';
import config from '@/config';
import type { Company } from '@/lib/supabase/types';

// Cloudflare Pages Edge Runtime
export const runtime = 'edge';

// ISR 재검증 주기 (초) - config.cache.companies와 동일하게 유지
export const revalidate = 3600;

async function getCompanies(): Promise<Company[]> {
  const supabase = await createServerClient();

  const { data: companies, error } = await supabase
    .from('companies')
    .select('*')
    .order('name');

  if (error) {
    console.error('Error fetching companies:', error);
    return [];
  }

  return companies || [];
}

export default async function CompaniesPage() {
  const companies = await getCompanies();

  return (
    <div className="lg:ml-64 space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">기업정보</h1>
        <p className="mt-1 text-sm text-gray-500">
          총 {companies.length.toLocaleString()}개의 기업
        </p>
      </div>

      {/* Company Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {companies.length > 0 ? (
          companies.map((company) => (
            <Link key={company.id} href={`/companies/${company.id}`}>
              <Card className="h-full card-hover">
                <div className="flex flex-col h-full">
                  <div className="flex items-start justify-between">
                    <h3 className="font-semibold text-gray-900 hover:text-primary-600">
                      {company.name}
                    </h3>
                    {company.jobplanet_rating && (
                      <div className="flex items-center text-yellow-500">
                        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                          <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                        </svg>
                        <span className="ml-1 text-sm font-medium">
                          {company.jobplanet_rating.toFixed(1)}
                        </span>
                      </div>
                    )}
                  </div>

                  <div className="flex flex-wrap gap-2 mt-3">
                    {company.industry && (
                      <Badge variant="primary" size="sm">
                        {company.industry}
                      </Badge>
                    )}
                    {company.company_size && (
                      <Badge variant="default" size="sm">
                        {company.company_size}
                      </Badge>
                    )}
                  </div>

                  <div className="mt-auto pt-4 text-sm text-gray-500">
                    {company.address && (
                      <p className="truncate">{company.address}</p>
                    )}
                    {company.employee_count && (
                      <p className="mt-1">직원 수: {company.employee_count.toLocaleString()}명</p>
                    )}
                  </div>
                </div>
              </Card>
            </Link>
          ))
        ) : (
          <Card className="col-span-full">
            <p className="text-center text-gray-500 py-12">
              등록된 기업이 없습니다.
            </p>
          </Card>
        )}
      </div>
    </div>
  );
}
