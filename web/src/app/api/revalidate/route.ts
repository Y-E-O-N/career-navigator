import { revalidatePath } from 'next/cache';
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

    // 경로 재검증
    revalidatePath(path);

    // 추가로 관련 경로들도 재검증
    if (path === '/') {
      revalidatePath('/jobs');
      revalidatePath('/companies');
      revalidatePath('/trends');
      revalidatePath('/roadmap');
    }

    return NextResponse.json({
      revalidated: true,
      path,
      timestamp: new Date().toISOString(),
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
    usage: {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-revalidate-secret': 'your-secret',
      },
      body: {
        path: '/',
      },
    },
  });
}
