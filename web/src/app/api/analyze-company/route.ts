import { NextRequest, NextResponse } from 'next/server';

const GITHUB_TOKEN = process.env.GITHUB_TOKEN;
const GITHUB_REPO = process.env.GITHUB_REPO || 'chiseoyeon/career-navigator';

export async function POST(request: NextRequest) {
  try {
    const { companyName } = await request.json();

    if (!companyName) {
      return NextResponse.json(
        { error: '회사 이름이 필요합니다.' },
        { status: 400 }
      );
    }

    if (!GITHUB_TOKEN) {
      return NextResponse.json(
        { error: 'GitHub 토큰이 설정되지 않았습니다.' },
        { status: 500 }
      );
    }

    // Trigger GitHub Actions workflow
    const [owner, repo] = GITHUB_REPO.split('/');
    const workflowId = 'analyze-company.yml';

    const response = await fetch(
      `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${workflowId}/dispatches`,
      {
        method: 'POST',
        headers: {
          'Accept': 'application/vnd.github.v3+json',
          'Authorization': `Bearer ${GITHUB_TOKEN}`,
          'Content-Type': 'application/json',
          'User-Agent': 'career-navigator-web',
        },
        body: JSON.stringify({
          ref: 'main',
          inputs: {
            company_name: companyName,
          },
        }),
      }
    );

    if (!response.ok) {
      const errorText = await response.text();
      console.error('GitHub API error:', response.status, errorText);
      return NextResponse.json(
        { error: '분석 요청에 실패했습니다.', details: errorText },
        { status: response.status }
      );
    }

    return NextResponse.json({
      success: true,
      message: `${companyName} 기업 분석이 요청되었습니다. 잠시 후 결과를 확인해주세요.`,
      companyName,
    });
  } catch (error) {
    console.error('Analyze company error:', error);
    return NextResponse.json(
      { error: '서버 오류가 발생했습니다.' },
      { status: 500 }
    );
  }
}
