"""
Job Market Analyzer - Analyzers 모듈

시장 분석, 회사 분석, LLM 기반 분석 기능 제공
"""

from .market_analyzer import MarketAnalyzer
from .company_analyzer import CompanyAnalyzer
from .llm_analyzer import LLMAnalyzer, FallbackAnalyzer

# Phase 1: 기업 분석 보고서 생성 모듈
from .models import (
    AnalysisDataBundle,
    ProcessedReviews,
    ProcessedInterviews,
    ProcessedSalaries,
    ProcessedBenefits,
    ProcessedNews,
    SkillAnalysis,
    GeneratedReport,
    ApplicantProfile,
    PriorityWeights,
)
from .data_collector import CompanyDataCollector
from .data_processor import DataProcessor
from .prompt_builder import PromptBuilder
from .report_generator import ReportGenerator
from .report_orchestrator import CompanyReportOrchestrator

# Phase 4: 저장 및 출력
from .report_storage import ReportStorage
from .report_exporter import ReportExporter

__all__ = [
    # 기존 모듈
    'MarketAnalyzer',
    'CompanyAnalyzer',
    'LLMAnalyzer',
    'FallbackAnalyzer',
    # Phase 1: 기업 분석 보고서 생성
    'AnalysisDataBundle',
    'ProcessedReviews',
    'ProcessedInterviews',
    'ProcessedSalaries',
    'ProcessedBenefits',
    'ProcessedNews',
    'SkillAnalysis',
    'GeneratedReport',
    'ApplicantProfile',
    'PriorityWeights',
    'CompanyDataCollector',
    'DataProcessor',
    'PromptBuilder',
    'ReportGenerator',
    'CompanyReportOrchestrator',
    # Phase 4: 저장 및 출력
    'ReportStorage',
    'ReportExporter',
]
