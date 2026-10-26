"""Plan import: floor-plan PDFs / images → a building.json draft (archive/hackathon/superpowers/specs/2026-10-25-plan-import-design.md).

Deterministic stages driven by the Creator agent (backend/agents/creator.py): ingest → prepare (rectify, crop, wall mask) →
cells → labels → scale / stack → assemble. Code does geometry; the model only reads and labels."""
