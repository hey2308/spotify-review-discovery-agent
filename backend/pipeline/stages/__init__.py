from pipeline.stages.base import PipelineStage, StageStats
from pipeline.stages.classify import ClassifyStage
from pipeline.stages.cluster import ClusterStage
from pipeline.stages.embed import EmbedStage
from pipeline.stages.evidence import EvidenceStage
from pipeline.stages.qa import QAStage
from pipeline.stages.segments import SegmentsStage
from pipeline.stages.theme_labels import ThemeLabelsStage
from pipeline.stages.unmet_needs import UnmetNeedsStage

ALL_STAGES: tuple[str, ...] = (
    "classify",
    "embed",
    "cluster",
    "theme_labels",
    "evidence",
    "qa",
    "segments",
    "unmet_needs",
)

INTELLIGENCE_STAGES: frozenset[str] = frozenset({"qa", "segments", "unmet_needs"})


def build_stages() -> dict[str, PipelineStage]:
    stages: list[PipelineStage] = [
        ClassifyStage(),
        EmbedStage(),
        ClusterStage(),
        ThemeLabelsStage(),
        EvidenceStage(),
        QAStage(),
        SegmentsStage(),
        UnmetNeedsStage(),
    ]
    return {stage.name: stage for stage in stages}


__all__ = [
    "ALL_STAGES",
    "INTELLIGENCE_STAGES",
    "ClassifyStage",
    "ClusterStage",
    "EmbedStage",
    "EvidenceStage",
    "PipelineStage",
    "QAStage",
    "SegmentsStage",
    "StageStats",
    "ThemeLabelsStage",
    "UnmetNeedsStage",
    "build_stages",
]
