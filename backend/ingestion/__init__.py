"""
Phase 1 — Ingestion & Normalization

Source connectors, canonical mapping, PII scrubbing, and dedup.
See docs/implementationPlan.md Phase 1.
"""

from ingestion.service import ingest_all

__all__ = ["ingest_all"]
