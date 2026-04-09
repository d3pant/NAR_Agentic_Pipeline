---
name: datasource-relevancy-analysis
description: >-
  Evaluate a biomedical datasource for BioThings ingestion fit. Use when a user
  provides a datasource name/URL and asks whether it is (1) relevant to the
  BioThings sphere (MyChem, MyGene, MyDisease, MyVariant, pending.api, etc.),
  (2) novel vs already-included BioThings data, and (3) openly downloadable
  without login, paywall, or restrictive license. Produces a structured
  RECOMMEND_INGEST / NEEDS_REVIEW / DO_NOT_INGEST verdict with scored evidence.
---

# Datasource Relevancy Analysis

## Instructions

1. Parse input and extract:
   - datasource name
   - homepage / documentation URL
   - download or API URL(s)
   - stated license / terms of use

2. Assess **BioThings sphere relevance** (score 0–5):
   - 5: Directly aligned — covers core BioThings entities/relations (drug, chemical, gene, variant, disease, pathway, target, adverse event, clinical evidence).
   - 3: Biomedical-adjacent but weakly structured for BioThings entity types.
   - 1: Mostly out of scope.

3. Assess **novelty to BioThings APIs** (score 0–5):
   - Compare against known BioThings data sources and endpoints.
   - 5: Clearly new entities, relations, or annotations not already represented.
   - 3: Partial overlap with meaningful new fields or better provenance/freshness.
   - 1: Largely redundant with existing sources.
   - See [references/evaluation-checklist.md](references/evaluation-checklist.md) for the known-source comparison list.

4. Assess **open download / access** (PASS / FAIL + score 0–5):
   - PASS requires **all** of:
     - downloadable via public URL or open API
     - no account / login / API key required for basic acquisition
     - no paywall or click-through-only access gate
     - license permits reuse for integration and redistribution
   - FAIL if any blocker exists.
   - Score reflects degree of openness (5 = fully open CC0/public-domain; 3 = open with attribution; 1 = restricted).

5. Produce a final **verdict**:
   - **RECOMMEND_INGEST**: relevance ≥ 4, novelty ≥ 3, openness PASS
   - **NEEDS_REVIEW**: mixed scores or uncertainty in any dimension
   - **DO_NOT_INGEST**: relevance < 3, OR openness FAIL, OR clearly redundant

6. If evidence is missing, explicitly list unknowns — do not guess.

7. **Save output**: Write the completed evaluation to `agent_outputs/<DATASOURCE_NAME>_relevancy_evaluation_<DATETIME>.md` (relative to the working directory), where `<DATETIME>` is the current date in `YYYYMMDD` format (e.g., `20260330`). Create the `agent_outputs/` directory if it does not exist. Use a lowercase, underscore-separated datasource name (e.g., `ecbd_relevancy_evaluation_20260330.md`). Also move the TTD evaluation if found in the parent directory.

## Required Output Format

```
## <Datasource Name>
**Verdict**: RECOMMEND_INGEST | NEEDS_REVIEW | DO_NOT_INGEST

### Scores
- Relevance: X/5 — <one-line justification>
- Novelty:   X/5 — <one-line justification>
- Openness:  PASS|FAIL (X/5) — <one-line justification>

### Evidence
- **Scope**: <what entities/relations it covers>
- **Overlap**: <what it shares with existing BioThings sources>
- **License/Access**: <license name, URL, any restrictions>

### Risks / Unknowns
- <bullet list>

### Recommended Next Actions
- <bullet list>
```

## Decision Rules
- Openness FAIL is a hard blocker unless user explicitly requests restricted-source tracking.
- If novelty is uncertain, default to NEEDS_REVIEW, not RECOMMEND_INGEST.
- Always cite concrete evidence (URL, license text, docs page) — not assumptions.

## Examples
- `/datasource-relevancy-analysis SIGNOR pathway database`
- `/datasource-relevancy-analysis DrugMap drug-target interactions`
- "Evaluate the STRING protein-protein interaction database for BioThings ingestion"
