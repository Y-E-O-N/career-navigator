'use client';

import Link from 'next/link';
import { useState } from 'react';
import config from '@/config';

export default function Header() {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  return (
    <header className="bg-white border-b border-gray-200 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          {/* Logo */}
          <Link href="/" className="flex items-center space-x-2">
            <svg
              className="w-8 h-8 text-primary-600"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
              />
            </svg>
            <span className="font-bold text-xl text-gray-900">
              {config.site.name}
            </span>
          </Link>

          {/* Desktop Navigation */}
          <nav className="hidden md:flex items-center space-x-8">
            <Link
              href="/"
              className="text-gray-600 hover:text-primary-600 transition-colors"
            >
              대시보드
            </Link>
            <Link
              href="/jobs"
              className="text-gray-600 hover:text-primary-600 transition-colors"
            >
              채용공고
            </Link>
            <Link
              href="/companies"
              className="text-gray-600 hover:text-primary-600 transition-colors"
            >
              기업정보
            </Link>
            <Link
              href="/reports"
              className="text-gray-600 hover:text-primary-600 transition-colors"
            >
              분석 리포트
            </Link>
            <Link
              href="/trends"
              className="text-gray-600 hover:text-primary-600 transition-colors"
            >
              기술트렌드
            </Link>
            <Link
              href="/roadmap"
              className="text-gray-600 hover:text-primary-600 transition-colors"
            >
              로드맵
            </Link>
          </nav>

          {/* Mobile menu button */}
          <button
            type="button"
            className="md:hidden inline-flex items-center justify-center p-2 rounded-md text-gray-400 hover:text-gray-500 hover:bg-gray-100"
            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          >
            <span className="sr-only">메뉴 열기</span>
            {isMobileMenuOpen ? (
              <svg
                className="h-6 w-6"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            ) : (
              <svg
                className="h-6 w-6"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 6h16M4 12h16M4 18h16"
                />
              </svg>
            )}
          </button>
        </div>

        {/* Mobile menu */}
        {isMobileMenuOpen && (
          <div className="md:hidden pb-4">
            <div className="flex flex-col space-y-2">
              <Link
                href="/"
                className="px-3 py-2 rounded-md text-gray-600 hover:text-primary-600 hover:bg-gray-50"
                onClick={() => setIsMobileMenuOpen(false)}
              >
                대시보드
              </Link>
              <Link
                href="/jobs"
                className="px-3 py-2 rounded-md text-gray-600 hover:text-primary-600 hover:bg-gray-50"
                onClick={() => setIsMobileMenuOpen(false)}
              >
                채용공고
              </Link>
              <Link
                href="/companies"
                className="px-3 py-2 rounded-md text-gray-600 hover:text-primary-600 hover:bg-gray-50"
                onClick={() => setIsMobileMenuOpen(false)}
              >
                기업정보
              </Link>
              <Link
                href="/reports"
                className="px-3 py-2 rounded-md text-gray-600 hover:text-primary-600 hover:bg-gray-50"
                onClick={() => setIsMobileMenuOpen(false)}
              >
                분석 리포트
              </Link>
              <Link
                href="/trends"
                className="px-3 py-2 rounded-md text-gray-600 hover:text-primary-600 hover:bg-gray-50"
                onClick={() => setIsMobileMenuOpen(false)}
              >
                기술트렌드
              </Link>
              <Link
                href="/roadmap"
                className="px-3 py-2 rounded-md text-gray-600 hover:text-primary-600 hover:bg-gray-50"
                onClick={() => setIsMobileMenuOpen(false)}
              >
                로드맵
              </Link>
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
