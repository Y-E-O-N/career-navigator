"""
기업 분석 보고서 변환 모듈 (Phase 4)

마크다운 보고서를 HTML/PDF로 변환합니다.
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from utils.database import get_kst_now

logger = logging.getLogger(__name__)

# markdown 라이브러리 (선택적)
try:
    import markdown
    from markdown.extensions import tables, fenced_code, toc
    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False
    logger.warning("markdown 라이브러리가 설치되지 않았습니다. pip install markdown")

# PDF 변환 라이브러리 (선택적)
try:
    from weasyprint import HTML as WeasyHTML
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False


class ReportExporter:
    """보고서 HTML/PDF 변환"""

    # 기본 CSS 스타일
    DEFAULT_CSS = """
    :root {
        --primary-color: #2563eb;
        --success-color: #16a34a;
        --warning-color: #d97706;
        --danger-color: #dc2626;
        --text-color: #1f2937;
        --bg-color: #ffffff;
        --border-color: #e5e7eb;
    }

    * {
        box-sizing: border-box;
    }

    body {
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        line-height: 1.7;
        color: var(--text-color);
        background-color: var(--bg-color);
        max-width: 900px;
        margin: 0 auto;
        padding: 40px 20px;
    }

    h1 {
        font-size: 2rem;
        font-weight: 700;
        color: var(--primary-color);
        border-bottom: 3px solid var(--primary-color);
        padding-bottom: 10px;
        margin-top: 40px;
    }

    h2 {
        font-size: 1.5rem;
        font-weight: 600;
        color: #374151;
        margin-top: 30px;
        padding-left: 10px;
        border-left: 4px solid var(--primary-color);
    }

    h3 {
        font-size: 1.25rem;
        font-weight: 600;
        color: #4b5563;
        margin-top: 20px;
    }

    p {
        margin: 10px 0;
    }

    ul, ol {
        padding-left: 25px;
    }

    li {
        margin: 5px 0;
    }

    strong {
        font-weight: 600;
    }

    /* 판정 배지 */
    .verdict-go {
        display: inline-block;
        background-color: var(--success-color);
        color: white;
        padding: 5px 15px;
        border-radius: 20px;
        font-weight: 600;
    }

    .verdict-conditional {
        display: inline-block;
        background-color: var(--warning-color);
        color: white;
        padding: 5px 15px;
        border-radius: 20px;
        font-weight: 600;
    }

    .verdict-nogo {
        display: inline-block;
        background-color: var(--danger-color);
        color: white;
        padding: 5px 15px;
        border-radius: 20px;
        font-weight: 600;
    }

    /* 점수 테이블 */
    table {
        width: 100%;
        border-collapse: collapse;
        margin: 20px 0;
    }

    th, td {
        padding: 12px;
        text-align: left;
        border-bottom: 1px solid var(--border-color);
    }

    th {
        background-color: #f9fafb;
        font-weight: 600;
    }

    tr:hover {
        background-color: #f3f4f6;
    }

    /* 태그 스타일 */
    .tag-fact {
        display: inline-block;
        background-color: #dbeafe;
        color: #1e40af;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.85rem;
        font-weight: 500;
    }

    .tag-interpretation {
        display: inline-block;
        background-color: #fef3c7;
        color: #92400e;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.85rem;
        font-weight: 500;
    }

    .tag-judgment {
        display: inline-block;
        background-color: #fce7f3;
        color: #9d174d;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.85rem;
        font-weight: 500;
    }

    /* 소스 라벨 */
    .source-label {
        display: inline-block;
        background-color: #f3f4f6;
        color: #374151;
        padding: 2px 6px;
        border-radius: 3px;
        font-size: 0.8rem;
        font-weight: 600;
    }

    /* 확인 필요 항목 */
    .verify-item {
        background-color: #fef2f2;
        border-left: 4px solid var(--danger-color);
        padding: 10px 15px;
        margin: 10px 0;
    }

    /* 메타데이터 헤더 */
    .report-header {
        background-color: #f8fafc;
        padding: 20px;
        border-radius: 8px;
        margin-bottom: 30px;
    }

    .report-header h1 {
        margin-top: 0;
        border-bottom: none;
    }

    .meta-info {
        display: flex;
        flex-wrap: wrap;
        gap: 20px;
        font-size: 0.9rem;
        color: #6b7280;
    }

    .meta-item {
        display: flex;
        align-items: center;
        gap: 5px;
    }

    /* 스코어카드 */
    .scorecard {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 15px;
        margin: 20px 0;
    }

    .score-item {
        background-color: #f9fafb;
        padding: 15px;
        border-radius: 8px;
        text-align: center;
    }

    .score-label {
        font-size: 0.85rem;
        color: #6b7280;
        margin-bottom: 5px;
    }

    .score-value {
        font-size: 1.5rem;
        font-weight: 700;
        color: var(--primary-color);
    }

    /* 프린트 스타일 */
    @media print {
        body {
            max-width: none;
            padding: 20px;
        }

        h1, h2 {
            page-break-after: avoid;
        }

        table {
            page-break-inside: avoid;
        }
    }
    """

    def __init__(self, custom_css: Optional[str] = None):
        self.css = custom_css or self.DEFAULT_CSS

    def markdown_to_html(
        self,
        markdown_content: str,
        include_css: bool = True,
        include_header: bool = True,
        company_name: Optional[str] = None,
        generated_at: Optional[datetime] = None,
        verdict: Optional[str] = None,
        total_score: Optional[float] = None
    ) -> str:
        """
        마크다운을 HTML로 변환

        Args:
            markdown_content: 마크다운 보고서 내용
            include_css: CSS 포함 여부
            include_header: 메타데이터 헤더 포함 여부
            company_name: 회사명 (헤더용)
            generated_at: 생성 시간 (헤더용)
            verdict: 판정 결과 (헤더용)
            total_score: 총점 (헤더용)

        Returns:
            HTML 문자열
        """
        if not MARKDOWN_AVAILABLE:
            # 기본 변환 (라이브러리 없을 때)
            html_body = self._basic_markdown_to_html(markdown_content)
        else:
            # markdown 라이브러리 사용
            md = markdown.Markdown(
                extensions=['tables', 'fenced_code', 'toc', 'nl2br']
            )
            html_body = md.convert(markdown_content)

        # 태그 스타일링 적용
        html_body = self._apply_tag_styles(html_body)

        # 판정 배지 스타일 적용
        html_body = self._apply_verdict_badge(html_body)

        # 전체 HTML 구성
        header_html = ""
        if include_header and company_name:
            header_html = self._build_header(
                company_name, generated_at, verdict, total_score
            )

        css_html = f"<style>{self.css}</style>" if include_css else ""

        html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{company_name or '기업 분석 보고서'} - 분석 보고서</title>
    {css_html}
</head>
<body>
    {header_html}
    <main>
        {html_body}
    </main>
    <footer style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #9ca3af; font-size: 0.85rem;">
        Generated by Career Navigator AI Analysis System
    </footer>
</body>
</html>"""

        return html

    def _basic_markdown_to_html(self, md_content: str) -> str:
        """기본 마크다운 변환 (라이브러리 없을 때)"""
        html = md_content

        # 헤더 변환
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)

        # 볼드/이탤릭
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)

        # 리스트
        html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
        html = re.sub(r'(<li>.*</li>)', r'<ul>\1</ul>', html, flags=re.DOTALL)

        # 줄바꿈
        html = re.sub(r'\n\n', '</p><p>', html)
        html = f'<p>{html}</p>'

        return html

    def _apply_tag_styles(self, html: str) -> str:
        """[사실], [해석], [판단] 태그 스타일 적용"""
        html = re.sub(
            r'\[사실\]',
            '<span class="tag-fact">[사실]</span>',
            html
        )
        html = re.sub(
            r'\[해석\]',
            '<span class="tag-interpretation">[해석]</span>',
            html
        )
        html = re.sub(
            r'\[판단\]',
            '<span class="tag-judgment">[판단]</span>',
            html
        )

        # 소스 라벨 [A], [B], ..., [I]
        html = re.sub(
            r'\[([A-I])\]',
            r'<span class="source-label">[\1]</span>',
            html
        )

        # [확인 필요] 항목
        html = re.sub(
            r'\[확인\s*필요\]([^<\n]+)',
            r'<div class="verify-item"><strong>[확인 필요]</strong>\1</div>',
            html
        )

        return html

    def _apply_verdict_badge(self, html: str) -> str:
        """판정 배지 스타일 적용"""
        html = re.sub(
            r'(No-Go)',
            r'<span class="verdict-nogo">\1</span>',
            html
        )
        html = re.sub(
            r'(Conditional\s*Go)',
            r'<span class="verdict-conditional">\1</span>',
            html
        )
        # Go만 있는 경우 (No-Go, Conditional Go가 아닌)
        html = re.sub(
            r'(?<!No-)(?<!Conditional\s)(Go)(?!\s*</span>)',
            r'<span class="verdict-go">\1</span>',
            html
        )

        return html

    def _build_header(
        self,
        company_name: str,
        generated_at: Optional[datetime],
        verdict: Optional[str],
        total_score: Optional[float]
    ) -> str:
        """보고서 헤더 HTML 생성"""
        date_str = generated_at.strftime("%Y년 %m월 %d일") if generated_at else ""

        verdict_badge = ""
        if verdict:
            if verdict == "No-Go":
                verdict_badge = '<span class="verdict-nogo">No-Go</span>'
            elif "Conditional" in verdict:
                verdict_badge = '<span class="verdict-conditional">Conditional Go</span>'
            else:
                verdict_badge = '<span class="verdict-go">Go</span>'

        score_str = f"{total_score:.1f}/5.0" if total_score else ""

        return f"""
<div class="report-header">
    <h1>{company_name} 기업 분석 보고서</h1>
    <div class="meta-info">
        <div class="meta-item">
            <span>생성일:</span>
            <strong>{date_str}</strong>
        </div>
        <div class="meta-item">
            <span>판정:</span>
            {verdict_badge}
        </div>
        <div class="meta-item">
            <span>총점:</span>
            <strong>{score_str}</strong>
        </div>
    </div>
</div>
"""

    def save_html(
        self,
        html_content: str,
        output_path: str
    ) -> Path:
        """HTML 파일 저장"""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html_content, encoding='utf-8')
        logger.info(f"HTML 저장: {path}")
        return path

    def html_to_pdf(
        self,
        html_content: str,
        output_path: str
    ) -> Optional[Path]:
        """HTML을 PDF로 변환"""
        if not WEASYPRINT_AVAILABLE:
            logger.warning("weasyprint가 설치되지 않았습니다. PDF 변환을 건너뜁니다.")
            return None

        try:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            WeasyHTML(string=html_content).write_pdf(str(path))
            logger.info(f"PDF 저장: {path}")
            return path

        except Exception as e:
            logger.error(f"PDF 변환 실패: {e}")
            return None

    def export_report(
        self,
        markdown_content: str,
        output_dir: str,
        company_name: str,
        generated_at: Optional[datetime] = None,
        verdict: Optional[str] = None,
        total_score: Optional[float] = None,
        export_html: bool = True,
        export_pdf: bool = False
    ) -> Dict[str, Optional[Path]]:
        """
        보고서 내보내기

        Args:
            markdown_content: 마크다운 보고서
            output_dir: 출력 디렉토리
            company_name: 회사명
            generated_at: 생성 시간
            verdict: 판정
            total_score: 총점
            export_html: HTML 내보내기 여부
            export_pdf: PDF 내보내기 여부

        Returns:
            생성된 파일 경로 딕셔너리
        """
        results = {"html": None, "pdf": None}

        # 파일명 생성 (KST 기준)
        timestamp = get_kst_now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c for c in company_name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_name = safe_name.replace(' ', '_')
        base_name = f"{safe_name}_{timestamp}"

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # HTML 변환
        html_content = self.markdown_to_html(
            markdown_content,
            include_css=True,
            include_header=True,
            company_name=company_name,
            generated_at=generated_at,
            verdict=verdict,
            total_score=total_score
        )

        # HTML 저장
        if export_html:
            html_path = output_path / f"{base_name}.html"
            results["html"] = self.save_html(html_content, str(html_path))

        # PDF 저장
        if export_pdf:
            pdf_path = output_path / f"{base_name}.pdf"
            results["pdf"] = self.html_to_pdf(html_content, str(pdf_path))

        return results
