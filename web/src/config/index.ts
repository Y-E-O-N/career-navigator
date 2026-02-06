/**
 * Career Navigator - 중앙 집중식 설정 관리
 * 모든 설정값은 이 파일에서 관리합니다.
 */

// =============================================================================
// 사이트 기본 설정
// =============================================================================
export const siteConfig = {
  name: 'Career Navigator',
  description: '한국 채용 시장 트렌드 분석 및 커리어 로드맵 생성 서비스',
  url: process.env.NEXT_PUBLIC_SITE_URL || 'https://career-navigator.pages.dev',
  locale: 'ko-KR',
  timezone: 'Asia/Seoul',
} as const;

// =============================================================================
// Supabase 설정
// =============================================================================
export const supabaseConfig = {
  url: process.env.NEXT_PUBLIC_SUPABASE_URL || '',
  anonKey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || '',
} as const;

// =============================================================================
// 페이지네이션 설정
// =============================================================================
export const paginationConfig = {
  /** 채용공고 목록 페이지당 항목 수 */
  jobsPerPage: 20,
  /** 기업 목록 페이지당 항목 수 */
  companiesPerPage: 30,
  /** 대시보드 최근 채용공고 수 */
  recentJobsCount: 5,
  /** 대시보드 최근 분석 수 */
  recentAnalysisCount: 5,
  /** 인기 스킬 표시 수 */
  topSkillsCount: 10,
  /** 상세 페이지 스킬 표시 수 */
  detailSkillsCount: 20,
} as const;

// =============================================================================
// 캐시/재검증 설정 (초 단위)
// =============================================================================
export const cacheConfig = {
  /** 대시보드 재검증 주기 */
  dashboard: 3600, // 1시간
  /** 채용공고 목록 재검증 주기 */
  jobList: 1800, // 30분
  /** 채용공고 상세 재검증 주기 */
  jobDetail: 3600, // 1시간
  /** 기업 목록 재검증 주기 */
  companies: 3600, // 1시간
  /** 트렌드 페이지 재검증 주기 */
  trends: 1800, // 30분
  /** 로드맵 페이지 재검증 주기 */
  roadmap: 3600, // 1시간
} as const;

// =============================================================================
// 채용 사이트 설정
// =============================================================================
export const jobSites = [
  { id: 'wanted', name: 'Wanted', enabled: true },
  { id: 'saramin', name: '사람인', enabled: true },
  { id: 'jobkorea', name: '잡코리아', enabled: true },
  { id: 'linkedin', name: 'LinkedIn', enabled: true },
  { id: 'rocketpunch', name: '로켓펀치', enabled: true },
  { id: 'programmers', name: '프로그래머스', enabled: true },
] as const;

export type JobSiteId = (typeof jobSites)[number]['id'];

// =============================================================================
// 검색 키워드 설정 (기본값)
// =============================================================================
export const defaultKeywords = [
  '데이터 분석가',
  '데이터 엔지니어',
  '머신러닝 엔지니어',
  '백엔드 개발자',
  '프론트엔드 개발자',
  '풀스택 개발자',
  'DevOps',
  '클라우드 엔지니어',
  'AI 엔지니어',
  '데이터 사이언티스트',
] as const;

// =============================================================================
// 스킬 카테고리 설정
// =============================================================================
export const skillCategories = {
  programming_languages: {
    name: '프로그래밍 언어',
    color: 'blue',
  },
  frameworks: {
    name: '프레임워크',
    color: 'green',
  },
  databases: {
    name: '데이터베이스',
    color: 'purple',
  },
  cloud: {
    name: '클라우드/DevOps',
    color: 'orange',
  },
  data_tools: {
    name: '데이터 도구',
    color: 'pink',
  },
  soft_skills: {
    name: '소프트스킬',
    color: 'gray',
  },
} as const;

// =============================================================================
// 경력 수준 설정
// =============================================================================
export const experienceLevels = [
  { id: 'entry', name: '신입', color: 'green' },
  { id: 'junior', name: '주니어 (1-3년)', color: 'blue' },
  { id: 'mid', name: '미드레벨 (3-5년)', color: 'yellow' },
  { id: 'senior', name: '시니어 (5년+)', color: 'orange' },
  { id: 'lead', name: '리드/매니저', color: 'red' },
  { id: 'any', name: '경력무관', color: 'gray' },
] as const;

// =============================================================================
// 고용 형태 설정
// =============================================================================
export const employmentTypes = [
  { id: 'full_time', name: '정규직', color: 'green' },
  { id: 'contract', name: '계약직', color: 'yellow' },
  { id: 'intern', name: '인턴', color: 'blue' },
  { id: 'part_time', name: '파트타임', color: 'purple' },
  { id: 'freelance', name: '프리랜서', color: 'orange' },
] as const;

// =============================================================================
// UI 설정
// =============================================================================
export const uiConfig = {
  /** 스킬 뱃지 최대 표시 수 (목록 페이지) */
  maxSkillBadges: 5,
  /** 설명 텍스트 최대 길이 (잘림) */
  maxDescriptionLength: 200,
  /** 테이블 행 hover 효과 */
  tableHoverEnabled: true,
  /** 다크모드 지원 */
  darkModeEnabled: false,
  /** 애니메이션 활성화 */
  animationsEnabled: true,
} as const;

// =============================================================================
// 네비게이션 설정
// =============================================================================
export const navigationConfig = {
  main: [
    { name: '대시보드', href: '/', icon: 'home' },
    { name: '채용공고', href: '/jobs', icon: 'briefcase' },
    { name: '기업정보', href: '/companies', icon: 'building' },
    { name: '분석 리포트', href: '/reports', icon: 'document' },
    { name: '기술트렌드', href: '/trends', icon: 'trending-up' },
    { name: '커리어 로드맵', href: '/roadmap', icon: 'map' },
  ],
} as const;

// =============================================================================
// API 설정
// =============================================================================
export const apiConfig = {
  /** 재검증 시크릿 */
  revalidateSecret: process.env.REVALIDATE_SECRET || '',
  /** 요청 타임아웃 (ms) */
  timeout: 30000,
  /** 재시도 횟수 */
  retryCount: 3,
} as const;

// =============================================================================
// 차트/시각화 설정
// =============================================================================
export const chartConfig = {
  /** 기본 색상 팔레트 */
  colors: [
    '#3b82f6', // blue-500
    '#10b981', // emerald-500
    '#f59e0b', // amber-500
    '#ef4444', // red-500
    '#8b5cf6', // violet-500
    '#ec4899', // pink-500
    '#06b6d4', // cyan-500
    '#84cc16', // lime-500
  ],
  /** 차트 애니메이션 지속시간 (ms) */
  animationDuration: 300,
} as const;

// =============================================================================
// 날짜/시간 포맷 설정
// =============================================================================
export const dateConfig = {
  /** 날짜 포맷 */
  dateFormat: 'yyyy-MM-dd',
  /** 날짜시간 포맷 */
  dateTimeFormat: 'yyyy-MM-dd HH:mm',
  /** 상대 시간 표시 기준 (일) - 이 기간 이내면 "N일 전" 형식 */
  relativeTimeThreshold: 7,
} as const;

// =============================================================================
// 메타데이터 설정
// =============================================================================
export const metaConfig = {
  title: {
    default: 'Career Navigator - 채용 시장 분석',
    template: '%s | Career Navigator',
  },
  description: siteConfig.description,
  keywords: ['채용', '취업', '커리어', '로드맵', '기술 트렌드', '개발자', '데이터 분석'],
  authors: [{ name: 'Career Navigator' }],
  creator: 'Career Navigator',
  openGraph: {
    type: 'website',
    locale: 'ko_KR',
    siteName: siteConfig.name,
  },
} as const;

// =============================================================================
// 전체 설정 내보내기
// =============================================================================
const config = {
  site: siteConfig,
  supabase: supabaseConfig,
  pagination: paginationConfig,
  cache: cacheConfig,
  jobSites,
  defaultKeywords,
  skillCategories,
  experienceLevels,
  employmentTypes,
  ui: uiConfig,
  navigation: navigationConfig,
  api: apiConfig,
  chart: chartConfig,
  date: dateConfig,
  meta: metaConfig,
} as const;

export default config;
