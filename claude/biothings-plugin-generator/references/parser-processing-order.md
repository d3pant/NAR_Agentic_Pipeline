# Parser Processing Order

Defines the required chronology of operations inside `load_data()` for any microbiome abundance plugin. Three phases must execute in order — never interleave them.

---

## Overview

```
Phase 1 — Pre-resolution
    ├── Load all source data into memory (metadata + abundance headers)
    ├── Collect all unique raw strings per entity type
    ├── Batch-resolve taxa via OLS4 → ncbitaxon
    ├── Batch-resolve body sites via OLS4 → uberon
    ├── Batch-resolve phenotypes via OLS4 → mondo/hp
    └── Batch-resolve taxon details (parent_taxid, lineage, rank) via biothings_client

Phase 2 — Document construction loop
    ├── For each (sample × taxon) pair:
    │   ├── Look up pre-resolved CURIEs from maps (no API calls here)
    │   ├── Skip record if taxon CURIE unresolved
    │   ├── Skip record if subject core fields missing
    │   ├── Build taxon association document
    │   └── Yield
    └── For each sample (phenotype association):
        ├── Look up pre-resolved phenotype CURIE from map
        ├── Skip record if phenotype CURIE unresolved
        ├── Skip record if subject core fields missing
        ├── Build phenotype association document
        └── Yield

Phase 3 — (no teardown needed; OLS4 is stateless HTTP)
```

---

## Phase 1 — Pre-resolution

Run once before any document is yielded. All API calls happen here.

### Step 1a: Load source data

Load the metadata file and all abundance files into memory structures. The exact format varies by datasource (JSON, CSV, TSV), but the output of this step must be:
- `metadata_rows` — iterable of dicts, one per sample, keyed by field name
- `abundance_col_headers` — list of raw taxon column header strings from abundance file(s)

```python
# Generic pattern — adapt column/file names per datasource
metadata_rows = [...]           # list[dict] — one dict per sample
abundance_col_headers = [...]   # list[str] — taxon column names from abundance CSV(s)
```

### Step 1b: Collect unique raw strings

```python
raw_taxa = list({
    col.split(";")[-1].split("__")[-1].strip()
    for col in abundance_col_headers
})

raw_body_sites = list({
    row[BODY_SITE_FIELD]
    for row in metadata_rows
    if row.get(BODY_SITE_FIELD)
})

raw_phenotypes = list({
    row[PHENOTYPE_FIELD]
    for row in metadata_rows
    if row.get(PHENOTYPE_FIELD)
})
```

> `BODY_SITE_FIELD` and `PHENOTYPE_FIELD` are datasource-specific column names (e.g. `"Body_Site"`, `"Systems"`, `"Phenotype"`, `"Disease"`). Identify them from the source schema before writing the parser.

### Step 1c: OLS4 batch resolution

Call in this order. Each returns a `dict[raw_string → curie]` (or tuple for phenotypes).
See [entity_resolution.md](entity_resolution.md) for the full implementation.

```python
taxon_curie_map  = batch_resolve_ols4(raw_taxa, "ncbitaxon")
body_site_map    = batch_resolve_ols4(raw_body_sites, "uberon")
phenotype_map    = {raw: resolve_phenotype(raw) for raw in raw_phenotypes}
# phenotype_map values are (curie, biolink_category) tuples
```

### Step 1d: Extract integer taxids

```python
resolved_taxids = {}
for name, curie in taxon_curie_map.items():
    if curie and ":" in curie:
        try:
            resolved_taxids[name] = int(curie.split(":")[1])
        except ValueError:
            pass
unique_taxid_ints = list(set(resolved_taxids.values()))
```

### Step 1e: biothings_client batch taxon detail lookup

```python
import biothings_client
t = biothings_client.get_client('taxon')
taxon_detail_map = {}
for r in t.gettaxa(unique_taxid_ints, fields='parent_taxid,lineage,rank'):
    if not r.get('notfound'):
        taxon_detail_map[int(r['query'])] = {
            'parent_taxid': r.get('parent_taxid'),
            'lineage':      r.get('lineage', []),
            'rank':         r.get('rank'),
        }
```

See [biothings-taxon-resolution.md](biothings-taxon-resolution.md) for full details.

---

## Phase 2 — Document construction loop

All map lookups only — zero API calls. Yields two document types per sample.

### Taxon association documents

One document per (sample × taxon) pair. Skip if either the taxon or subject core fields are unresolved.

```python
for sample in metadata_rows:
    if not _subject_core_fields_present(sample):
        continue                             # drop entire sample

    for taxon_col in abundance_col_headers:
        terminal = taxon_col.split(";")[-1].split("__")[-1].strip()
        ncbitaxon_curie = taxon_curie_map.get(terminal)
        taxid = resolved_taxids.get(terminal)
        if not ncbitaxon_curie or not taxid:
            continue                         # skip unresolved taxon

        taxon_info = taxon_detail_map.get(taxid, {})
        body_site_curie = body_site_map.get(sample.get(BODY_SITE_FIELD))

        doc = _build_taxon_doc(sample, taxon_col, taxid, taxon_info, body_site_curie)
        doc = dict_sweep(unlist(doc), [None])
        yield doc
```

### Phenotype association documents

One document per sample (not per taxon). Skip if phenotype unresolved or subject core fields missing.

```python
for sample in metadata_rows:
    if not _subject_core_fields_present(sample):
        continue

    phenotype_curie, phenotype_category = phenotype_map.get(
        sample.get(PHENOTYPE_FIELD), (None, None)
    )
    if not phenotype_curie:
        continue                             # skip unresolved or control ("Healthy")

    doc = _build_phenotype_doc(sample, phenotype_curie, phenotype_category)
    doc = dict_sweep(unlist(doc), [None])
    yield doc
```

---

## Subject Core Field Check

A sample is skipped entirely (both taxon and phenotype records) if any core field is missing.
A field is missing if its value is `None`, `""`, or case-insensitive `"nan"`.

```python
_CORE_FIELDS = {"age", "gender", "bmi"}          # adjust field names per datasource schema
_CORE_FIELDS_ALT = {"ethnicity", "country"}       # at least one of these must be present

def _subject_core_fields_present(sample: dict) -> bool:
    def _missing(v):
        return v is None or str(v).strip().lower() in ("", "nan")

    for f in _CORE_FIELDS:
        if _missing(sample.get(f)):
            return False
    if all(_missing(sample.get(f)) for f in _CORE_FIELDS_ALT):
        return False
    return True
```

---

## `_id` Construction Rules

Do not construct `_id` until both components are confirmed resolved.

| Association type | `_id` pattern | Example |
|---|---|---|
| Sample → Taxon | `{BioSample}_{SRARunID}_has_taxon_{taxid_int}` | `SAMN12345_SRR999_has_taxon_853` |
| Sample → Phenotype | `{BioSample}_has_phenotype_{curie_local_id}` | `SAMN12345_has_phenotype_0005148` |

For the phenotype `_id`, `curie_local_id` is the numeric part after the prefix (e.g. `MONDO:0005148` → `0005148`, `HP:0000252` → `0000252`).

```python
def _curie_local_id(curie: str) -> str:
    return curie.split(":")[1]
```

---

## Unresolved Handling Summary

| Situation | Action |
|---|---|
| Taxon CURIE is `None` | Skip this (sample × taxon) record |
| Subject core field missing | Skip entire sample — both taxon and phenotype records |
| Body site CURIE is `None` | Omit `anatomical_entity` block; keep taxon record |
| Phenotype CURIE is `(None, None)` | Skip phenotype association record for this sample |

Never store `None` or a raw string in any CURIE field.

---

## Phase 3

No teardown needed. OLS4 is stateless HTTP with no connections to close.
`biothings_client` handles its own session lifecycle.
