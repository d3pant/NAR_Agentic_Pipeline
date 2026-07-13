# PRIME Plugin — Design Rationale

## Quick Stats

| Metric | Value |
|---|---|
| Source samples | 53,449 |
| Source taxa (SILVA species-level columns) | 4,593 |
| Source phenotype base terms | 102 (multi-value combos yield ~1,148 unique strings) |
| Expected taxon documents | ~tens of millions (53,449 samples × resolved taxa × non-zero abundance) |
| Expected phenotype documents | ~tens of thousands (per sample × per resolved phenotype) |
| Skip rate (subject core fields missing) | High — ~40–60% estimated (PRIME has sparse demographics) |
| Skip reason (zero abundance) | Most sample×taxon pairs are zero; non-zero pairs are the meaningful signal |
| Target API | pending.api |
| Data format | Multi-file CSV (Zenodo bulk download) |
| Total source file size | ~1.65 GB (samples_metadata 38MB + silva_abs 496MB + silva_rel 581MB + projects 108KB) |
| Version strategy | Zenodo API `metadata.publication_date` → YYYYMMDD |

---

## Why These Dump Files Were Chosen

### Selected files
| File | Reason |
|---|---|
| `samples_metadata.csv` | Primary spine — 80+ columns of per-sample host metadata (demographics, phenotype, body site, SRA identifiers, QC scores) |
| `silva_species_absolute.csv` | Species-level absolute read counts (SILVA 138.2); the most granular taxonomic resolution; rows = SRA runs, columns = SILVA lineage strings |
| `silva_species_relative.csv` | Companion relative abundance (proportions) for the same samples × taxa matrix |
| `projects_metadata.csv` | Downloaded as reference; not parsed in v1.0 (study-level metadata already embedded in samples_metadata) |

### Rejected files
| File | Reason |
|---|---|
| `gg_species_absolute.csv` / `gg_species_relative.csv` (1.6GB + 1.8GB) | Greengenes2 reference; targeted for v2.0. SILVA 138.2 is more widely cited in the literature and has fewer taxa (12K vs 25K GG2), making v1.0 more tractable. |
| `silva_genus_*.csv`, `silva_family_*.csv`, etc. | Coarser taxonomic ranks; species-level is the most informative for KG integration. Coarser ranks targeted for v2.0. |
| `gg_genus_*.csv`, `gg_class_*.csv`, etc. | Same reasoning — coarser ranks + GG2 deferred to v2.0. |
| `silva-138-99-nb-classifier.qza` / `gg_2024_09_backbone_full_length.nb.qza` | QIIME2 classifier artifacts; not data files — excluded from ingestion. |
| `primeDB_0.1.0.tar.gz` | R package source; not a data file. |

### Why Zenodo (not canonical PRIME homepage)
The PRIME homepage (`primedb.sjtu.edu.cn`) is a JavaScript-rendered React application — direct HTTP fetching returns an empty shell. The Zenodo deposit (`doi:10.5281/zenodo.15711237`) is the only viable automated download source. The `?download=1` URL pattern was verified as returning `content-type: text/plain` (the actual CSV file) without authentication. The Zenodo API `/content` endpoint returns 403 without a Bearer token.

---

## Why the Parser Works the Way It Does

### Three-phase structure
Required by `parser-processing-order.md`: all OLS4 and biothings_client API calls happen in Phase 1 before any documents are yielded. This avoids one API call per row (which would be ~53,449 × 4,593 = ~245M calls).

### `_terminal_rank()` implementation
SILVA lineage strings use the format `d__Domain;p__Phylum;...;s__` where the species-level suffix is empty (`s__`) for any taxon without a formal species name. A naïve "last segment" approach returns empty string for all 4,593 columns. The fixed implementation walks backwards through the semicolon-split parts to find the last non-empty rank label — this captures the deepest classified rank for each taxon (e.g., `Lachnospiraceae` for an unresolved Lachnospiraceae species-level column).

### Multi-value `Phenotype` field
The `Phenotype` column in `samples_metadata.csv` is comma-separated and multi-value (e.g., `"ADHD,ASD,IBD"`). There are only 102 base phenotype terms but ~1,148 unique multi-value combinations. The parser splits on `,` and emits one phenotype association document per resolved base term per BioSample, deduplicating by `(biosample, curie)` pair.

### `_id` strategy
- **Taxon docs**: `{BioSample}_{SRARunID}_has_taxon_{taxid_int}` — unique per (sample, run, taxon) triple. Multiple SRA runs from the same BioSample get separate documents.
- **Phenotype docs**: `{BioSample}_has_phenotype_{curie_local_id}` — unique per (sample, phenotype CURIE). Multi-value phenotype fields produce multiple phenotype documents per sample, each with a distinct CURIE-derived suffix.

### Subject core field check
Per `output_json_structure.md`: a sample is skipped (both taxon and phenotype records) if `Host_Age`, `Host_Sex`, or `Host_BMI` is missing/NaN, AND if both `Race_or_Ethnicity` and `Country` are missing. PRIME has sparse demographic coverage — many samples (especially control samples from early studies) have no structured demographics. Expected skip rate is high (~40–60%).

### Zero-abundance filtering
Taxon documents are only emitted for non-zero absolute read counts. Most (sample × taxon) pairs are zero-abundance — the sparse matrix is the norm in microbiome data. Only non-zero entries carry biological signal.

### `on_duplicates: error`
Each `(BioSample, Run, taxid)` triple is globally unique by construction — no two rows in the abundance CSV produce the same `_id`. Phenotype docs are deduplicated in-parser via `yielded_phenotype_pairs` set.

---

## Sample Output Documents

### Taxon association document (example)
```json
{
  "_id": "SAMD00518188_DRR396974_has_taxon_816",
  "association": {
    "category": "biolink:MaterialSampleToOrganismTaxonAssociation",
    "predicate": "biolink:has_taxon",
    "BioProject": "PRJDB13875",
    "SRA Run ID": "DRR396974",
    "project_name": "MUSC-JP-2024",
    "relative_abundance": 0.0234,
    "absolute_abundance": 142.0,
    "instrument": "Illumina MiSeq",
    "primary_knowledge_source": ["infores:PRIMEDB"],
    "agent_type": "biolink:automated_agent",
    "anatomical_entity": {
      "id": "UBERON:0001988",
      "original_name": "Stool/feces",
      "category": "biolink:AnatomicalEntity"
    }
  },
  "object": {
    "id": "taxid:816",
    "taxid": 816,
    "name": "Bacteroides",
    "original_name": "s__",
    "parent_taxid": 815,
    "lineage": [816, 815, 171549, 976, 68336, 2, 131567, 1],
    "rank": "genus",
    "category": "biolink:OrganismTaxon"
  },
  "subject": {
    "BioSample ID": "SAMD00518188",
    "age": 35.0,
    "gender": "Male",
    "BMI": 22.4,
    "country": "Japan",
    "continent": "Asia",
    "category": "biolink:MaterialSample"
  }
}
```
Source cross-reference: https://primedb.sjtu.edu.cn/api/v1/samples/DRR396974/stats

### Phenotype association document (example)
```json
{
  "_id": "SAMD01234567_has_phenotype_0005015",
  "association": {
    "category": "biolink:MaterialSampleToDiseaseOrPhenotypicFeatureAssociation",
    "predicate": "biolink:has_phenotype",
    "BioProject": "PRJNA123456",
    "project_name": "T2D-US-2023",
    "primary_knowledge_source": ["infores:PRIMEDB"],
    "agent_type": "biolink:automated_agent"
  },
  "object": {
    "id": "MONDO:0005015",
    "original_name": "Type II diabetes (T2D)",
    "category": "biolink:Disease"
  },
  "subject": {
    "BioSample ID": "SAMD01234567",
    "age": 52.0,
    "gender": "Female",
    "BMI": 31.2,
    "ethnicity": "Asian",
    "country": "Japan",
    "continent": "Asia",
    "category": "biolink:MaterialSample"
  }
}
```
Source cross-reference: https://primedb.sjtu.edu.cn/api/v1/samples/

---

## Field Coverage

Demographic field coverage is expected to be sparse (many samples have no structured host metadata). Estimated coverage based on PRIME paper and sample inspection:

- `subject.age`: ~20–30% (sparsely populated — most control samples lack age)
- `subject.gender`: ~30–40%
- `subject.BMI`: ~15–25%
- `subject.ethnicity` (Race_or_Ethnicity): <10% (very sparse)
- `subject.country`: ~95% (present for most samples via metadata standardization)
- `subject.continent`: ~95%
- `subject.smoke_status`: <5%
- `subject.drinking_status`: <5%
- `subject.diet_type`: <5%
- `association.anatomical_entity`: ~60–80% (depends on UBERON resolution success rate)
- `association.publication.doi`: <15% (many studies don't have DOI in PRIME metadata)

> **Note:** Because all three core fields (Host_Age, Host_Sex, Host_BMI) must be present to emit a document, the effective skip rate is high. Actual coverage will be confirmed in the inspect step after upload completes.

---

## Test Results Summary

| Step | Status | Notes |
|---|---|---|
| validate | PASS | manifest.json valid; all required fields present |
| dump | PASS | All 4 files downloaded to `.biothings_hub/archive/prime_plugin/20250718/` |
| upload | pending | OLS4 + biothings_client resolution running; large dataset |
| list | pending | |
| inspect | pending | |

> Upload and subsequent steps pending completion of OLS4 resolution (~4,593 taxa + 94 body sites + 102 phenotypes) and streaming of 53,449 sample × 4,593 taxon pairs.
