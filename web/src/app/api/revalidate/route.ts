import { NextRequest, NextResponse } from 'next/server';
import config from '@/config';

export async function POST(request: NextRequest) {
  const secret = request.headers.get('x-revalidate-secret');

  // Secret 검증
  if (secret !== config.api.revalidateSecret) {
    return NextResponse.json(
      { error: 'Invalid secret' },
      { status: 401 }
    );
  }

  try {
    const body = await request.json();
    const path = body.path || '/';

    // Edge Runtime에서는 revalidatePath가 지원되지 않음
    // Cloudflare Pages는 자동으로 캐시를 관리함
    // 이 엔드포인트는 크롤러 완료 알림용으로만 사용

    return NextResponse.json({
      revalidated: true,
      path,
      timestamp: new Date().toISOString(),
      note: 'Edge runtime - cache managed by Cloudflare',
    });
  } catch (error) {
    console.error('Revalidation error:', error);
    return NextResponse.json(
      { error: 'Revalidation failed' },
      { status: 500 }
    );
  }
}

export async function GET() {
  return NextResponse.json({
    message: 'Use POST method to trigger revalidation',
    runtime: 'edge',
  });
}
