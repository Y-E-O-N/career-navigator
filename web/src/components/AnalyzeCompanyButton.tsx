'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';

interface AnalyzeCompanyButtonProps {
  companyName: string;
  companyId?: number | null;
  className?: string;
}

export default function AnalyzeCompanyButton({
  companyName,
  companyId,
  className = '',
}: AnalyzeCompanyButtonProps) {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleAnalyze = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    setIsLoading(true);
    setMessage(null);
    setError(null);

    try {
      const response = await fetch('/api/analyze-company', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ companyName }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || '분석 요청에 실패했습니다.');
      }

      setMessage(data.message);

      // 3초 후 회사 페이지로 이동
      setTimeout(() => {
        if (companyId) {
          router.push(`/companies/${companyId}`);
        } else {
          router.push('/companies');
        }
      }, 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : '오류가 발생했습니다.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="relative">
      <button
        onClick={handleAnalyze}
        disabled={isLoading}
        className={`
          relative z-10 inline-flex items-center gap-1.5 px-3 py-1.5
          text-sm font-medium rounded-lg transition-all
          ${isLoading
            ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
            : 'bg-green-50 text-green-700 hover:bg-green-100 border border-green-200'
          }
          ${className}
        `}
      >
        {isLoading ? (
          <>
            <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
            분석 중...
          </>
        ) : (
          <>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            기업 분석하기
          </>
        )}
      </button>

      {/* Toast message */}
      {(message || error) && (
        <div className={`
          absolute top-full left-0 mt-2 p-3 rounded-lg shadow-lg z-20 min-w-[250px]
          ${error ? 'bg-red-50 text-red-700 border border-red-200' : 'bg-green-50 text-green-700 border border-green-200'}
        `}>
          <div className="flex items-start gap-2">
            {error ? (
              <svg className="w-5 h-5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
            ) : (
              <svg className="w-5 h-5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
            )}
            <p className="text-sm">{error || message}</p>
          </div>
        </div>
      )}
    </div>
  );
}
