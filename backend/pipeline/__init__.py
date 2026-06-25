"""
Phases 2–3 — AI Analysis Pipeline

Classification, clustering, Q&A synthesis, segmentation, and unmet-needs extraction.
See docs/implementationPlan.md Phases 2–3.
"""

from pipeline.orchestrator import AnalysisResult, run_analysis
from pipeline.stages import ALL_STAGES, StageStats, build_stages

__all__ = [
    "ALL_STAGES",
    "AnalysisResult",
    "StageStats",
    "build_stages",
    "run_analysis",
]
