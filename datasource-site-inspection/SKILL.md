---
name: datasource-site-inspection
description: >-
  Inspect a datasource's live website, API, and download endpoints to verify
  ingestion suitability for BioThings. Use after a relevancy evaluation
  (datasource-relevancy-analysis) has been completed, or standalone when a user
  provides a datasource URL and asks to verify its data access, API schema, and
  download feasibility. Produces a structured VERIFIED / PARTIALLY_VERIFIED /
  BLOCKED report with concrete technical findings.
---

# Datasource Site Inspection

## When to Use
- After a `datasource-relevancy-analysis` evaluation to ground-truth claims from a paper
- When a user provides a datasource URL and asks "can we actually ingest this?"
- When building a BioThings data plugin and you need to document the API contract

## Prerequisites
- Check `agent_outputs/` for a prior relevancy evaluation for this datasource
- If one exists, load it to know what claims to verify (entity counts, license, formats, identifiers)
- If none exists, proceed with raw inspection and note the absence

## Instructions

### 1. Identify Endpoints to Probe
Extract from the prior evaluation, paper, or user input:
- Homepage URL
- API root URL (REST, GraphQL, SPARQL, etc.)
- Download/bulk-export URL
- License/terms-of-use page URL
- Documentation URL (if separate from the above)

### 2. Probe the Homepage
Fetch the homepage and extract:
- Current entity counts (compare with paper claims if available)
- License statement (as displayed on the site)
- Last-updated or latest-data-deposit date
- Any login/registration prompts or access gates

### 3. Probe the API (if available)
For REST APIs, perform these checks in order:

#### 3a. Root Discovery
- Fetch the API root to enumerate available endpoints
- Record the base URL and all top-level resources

#### 3b. List Endpoint Inspection
For each top-level resource (e.g., `/api/compounds/`):
- Fetch with `?limit=1` or default pagination
- Record: total count, pagination mechanism (offset/limit, cursor, page), default page size
- Record: response format (JSON, XML, etc.)
- Record: top-level fields returned in the list view (summary schema)

#### 3c. Detail Endpoint Inspection
For at least one entity:
- Fetch the detail view (e.g., `/api/compounds/EOS1/` or `/api/compounds/1/`)
- Record: full schema of the detail response
- Identify: which fields contain identifiers mappable to BioThings (InChIKey, UniProt, SMILES, etc.)
- Identify: which fields contain bioactivity data, annotations, or cross-references
- Note: any nested objects, their depth, and whether they'd need flattening for BioThings

#### 3d. Pagination & Bulk Feasibility
- Calculate: total records ÷ page size = number of API calls needed for full crawl
- Check: is there a rate limit header (X-RateLimit, Retry-After, etc.)?
- Check: does the API support large page sizes (e.g., `?limit=1000`)?
- Estimate: time to crawl entire dataset at observed response times

#### 3e. Authentication Check
- Confirm all above requests succeeded without auth headers
- If any endpoint returned 401/403, record which ones and what auth is required

### 4. Probe the Download Page (if available)
- Fetch the download page
- Record: available file formats (CSV, JSON, SDF, TSV, SQL dump, etc.)
- Record: whether downloads are per-entity-type, per-library, or full-database
- Check: can files be downloaded via direct URL (curl-able) without session/cookie?
- If possible, download a small sample file and inspect its structure (headers, delimiter, encoding)

### 5. Verify License
- Fetch the license page or look for license metadata in API responses
- Record: exact license name and version
- Record: URL to the license text
- Compare: does the live site license match the paper's stated license?

### 6. Compare Paper Claims vs Reality
If a prior evaluation exists, check each claim:
- Entity counts: paper says X, site shows Y
- Formats: paper says CSV/JSON/SDF, site actually offers...
- API: paper says REST API, site actually provides...
- License: paper says CC-BY 4.0, site actually shows...
- Identifiers: paper says InChIKey/UniProt, API actually returns...

Flag any discrepancies as MISMATCH.

### 7. Assess Ingestion Path
Based on findings, recommend the best ingestion strategy:
- **Bulk download**: If a dump file (JSON, CSV, SQL) is available and complete — simplest path
- **API crawl**: If the API is well-paginated and returns rich detail per entity but no bulk download exists
- **Hybrid**: If bulk download gets the base data but API is needed for detail/updates
- Record the recommended primary key field for BioThings (e.g., InChIKey for MyChem)

**If recommending API crawl, document the following for the plugin generator:**
- **Base URL**: exact API root (e.g., `https://pgx-db.org/api/v1`)
- **Key endpoints**: which endpoints to crawl and in what order
- **Pagination**: mechanism (offset/limit, cursor, page), max page size observed
- **Total records per endpoint**: so the dumper knows when to stop
- **Rate limits**: observed or stated (requests/sec, daily caps)
- **Auth**: none, API key (env var), or token
- **Response shape**: top-level key containing records (e.g., `{"results": [...]}` vs bare array)
- **Estimated crawl time**: (total records ÷ page size) × avg response time
- **Sample curl command**: a working `curl` one-liner that returns data, for the plugin developer to test

This section feeds directly into the `biothings-plugin-generator` skill's Section 1c (API vs Bulk Download Strategy) and the custom `dumper.py` template.

### 8. Save Output
Write the completed inspection to:
`agent_outputs/<DATASOURCE_NAME>_site_inspection_<DATETIME>.md`
where `<DATETIME>` is `YYYYMMDD` format. Use lowercase, underscore-separated datasource name.

## Required Output Format

```
## <Datasource Name> — Site Inspection Report
**Status**: VERIFIED | PARTIALLY_VERIFIED | BLOCKED
**Inspection Date**: YYYY-MM-DD
**Prior Evaluation**: <filename or "none">

### Endpoints Probed
- Homepage: <URL> — <status code>
- API Root: <URL> — <status code>
- Download: <URL> — <status code>
- License: <URL> — <status code>

### API Schema
- **Root endpoints**: <list>
- **Pagination**: <mechanism, page size, total pages for full crawl>
- **Auth required**: yes/no
- **Rate limits**: <observed or "none detected">

#### List View Fields (<entity type>)
- <field>: <type> — <description>
- ...

#### Detail View Fields (<entity type>)
- <field>: <type> — <description>
- ...

#### BioThings-Mappable Identifiers Found
- <identifier type>: <field path> (e.g., InChIKey: `_label` contains SMILES)
- ...

### Download Options
- <format>: <URL pattern> — <scope (full DB, per-library, etc.)>
- ...

### License Verification
- **Stated (paper)**: <license>
- **Observed (site)**: <license>
- **Match**: yes/no

### Paper vs Reality
- Entity counts: paper=<X>, live=<Y> — MATCH/MISMATCH
- Formats: MATCH/MISMATCH — <details>
- API: MATCH/MISMATCH — <details>
- License: MATCH/MISMATCH — <details>
- Identifiers: MATCH/MISMATCH — <details>

### Recommended Ingestion Path
- **Strategy**: API crawl | Bulk download | Hybrid
- **Primary key**: <identifier>
- **Estimated crawl effort**: <N requests, ~M minutes>
- **Recommended format**: <format>

#### API Crawl Details (include only if Strategy = API crawl or Hybrid)
- **Base URL**: <exact API root>
- **Endpoints to crawl**: <list with record counts>
- **Pagination**: <mechanism, max page size>
- **Rate limits**: <observed or stated>
- **Auth**: none | API key | token
- **Response shape**: <top-level key containing records>
- **Sample curl**: `curl -s "<url>?limit=1" | python3 -m json.tool | head -30`

### Blockers / Risks
- <bullet list, or "None identified">
```

## Decision Rules
- **VERIFIED**: All endpoints accessible, schema confirmed, license matches, no auth barriers
- **PARTIALLY_VERIFIED**: Most checks pass but some endpoints unavailable, schema incomplete, or minor discrepancies found
- **BLOCKED**: Auth required for data access, license mismatch or restrictive, critical endpoints down, or data not actually available

## Interaction with Other Skills
- This skill is designed to run AFTER `datasource-relevancy-analysis`
- If invoked standalone (no prior evaluation), skip the "Paper vs Reality" comparison section
- The output of this skill feeds directly into `biothings-plugin-generator`:
  - If **Bulk download**: plugin generator uses `dumper.data_url` with the verified download URLs
  - If **API crawl**: plugin generator uses the API Crawl Details section to build a custom `dumper.py` (see plugin generator Section 1c)
  - If **Hybrid**: plugin generator combines both approaches
