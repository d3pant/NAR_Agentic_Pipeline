---
name: biothings-plugin-generator
description: >-
  Generate a BioThings data plugin (manifest.json + parser.py) for a given
  datasource. Use when a user wants to create the scaffolding to ingest a
  biomedical datasource into a BioThings API (MyChem, MyGene, MyDisease,
  MyVariant, pending.api, etc.). Works standalone — does not require prior
  evaluation/inspection skills, but will use their outputs if available in
  agent_outputs/. Reference production plugins at
  https://github.com/biothings/pending.api/tree/master/plugins and
  https://github.com/biothings/mydisease.info/tree/master/src/plugins
---

# BioThings Plugin Generator

## When to Use
- User asks to create a BioThings data plugin for a datasource
- User provides a datasource name, download URL, and data format
- After a datasource evaluation/inspection when the user wants to proceed to implementation

## Plugin File Structure
A minimal BioThings data plugin requires only two files:
```
<plugin_name>/
├── manifest.json    # Required — defines data URLs, parser reference, metadata
└── parser.py        # Required — parses data, yields documents
```

Optional files (only add when explicitly requested):
- `mapping.py` — Elasticsearch field mappings (for production Hub deployment)
- `version.py` — Data release version tracking (for scheduled re-dumps)

## Instructions

### 1. Gather Required Information
Collect the following (prompt the user if missing):
- **Datasource name**: lowercase, underscore-separated (e.g., `ecbd`)
- **Download URL(s)**: direct URLs to the **specific files** needed — NOT every file the datasource offers. Ask the user which files are relevant. If a prior site inspection exists, use its recommended files.
- **Data format**: CSV, TSV, JSON, NDJSON, SDF, or other
- **Primary key field**: the field to use as `_id` (e.g., InChIKey for MyChem, gene symbol for MyGene)
- **Target BioThings API**: MyChem.info, MyGene.info, MyDisease.info, MyVariant.info, pending.api, or custom
- **Key data fields**: which fields from the source should be included in the output documents

If a prior site inspection report exists in `agent_outputs/`, load it to extract download URLs, CSV column headers, API schema, recommended ingestion path, and file relationship classifications.

### 1b. File Selection Strategy
Most datasources offer multiple download files. Classify each before choosing which to include:

**File relationship types:**
- **Superset**: Contains all records from other files (e.g., `ecbd_all.csv` = everything)
- **Independent**: Contains unique data NOT found in the superset (e.g., curated bioactives, fragment library)
- **Subset**: A filtered view of the superset (e.g., "representative diverse set")
- **Composite**: Combination of other files (e.g., pilot library = representative + bioactives + nuisance)

**Decision tree:**
- User wants comprehensive coverage → single superset file, `on_duplicates: "error"`
- User wants only novel/specialized data → independent files only, skip subsets/composites, `on_duplicates: "ignore"`
- Unclear → ask user, or default to independent files with novel content

**How to classify files (when no prior inspection exists):**
1. Fetch the download page and list all available files with their descriptions
2. Compare record counts: if file A has 100K rows and file B has 2K, B is likely a subset or independent set
3. Check if file descriptions say "subset of", "representative", "selected from" → subset
4. Check if files are described as separately curated/designed → independent
5. Download CSV headers from each file (just the first line) to confirm schema compatibility

**How to use prior inspection reports:**
If `agent_outputs/` contains a prior inspection report (from a site-inspector or datasource-evaluator skill), it should include:
- A catalog of all available download files with URLs, sizes, and descriptions
- File relationship classifications (superset/independent/subset/composite)
- Recommended files for ingestion
- CSV column headers for each file

Load and use these classifications directly instead of re-discovering them.

**Multi-file manifest pattern:**
When using multiple files, set `data_url` as a list. All files land in the same `data_folder`, so the parser must iterate all matching files:
```json
{
    "dumper": {
        "data_url": [
            "https://example.org/data/bioactives.csv",
            "https://example.org/data/fragments.csv"
        ]
    },
    "uploader": {
        "parser": "parser:load_data",
        "on_duplicates": "ignore"
    }
}
```

### 1c. API vs Bulk Download Strategy
Many datasources offer both bulk downloads and REST APIs. Choose the right approach:

**Decision tree:**
- Bulk CSV/TSV/JSON download available and complete → use `dumper.data_url` (simplest, preferred)
- Bulk download incomplete but API returns all records → write a custom `dumper.py` that crawls the API and saves JSON to `data_folder`
- API-only, no bulk download → custom `dumper.py` is required
- Hybrid: bulk for base data, API for detail enrichment → two-phase approach

**When to use the datasource's API:**
- No bulk download exists (PGxDB, IGVF Catalog)
- Bulk download is stale but API has live data
- You need specific fields not in the bulk export
- The API supports pagination and returns structured JSON

**Custom dumper pattern for API-based plugins:**
Add a `dumper.py` alongside `parser.py` and reference it in the manifest:
```json
{
    "version": "1.0",
    "requires": ["requests"],
    "dumper": {
        "data_url": "__REPLACE__"
    },
    "uploader": {
        "parser": "parser:load_data",
        "on_duplicates": "error"
    }
}
```
For API-only sources, the `dumper.py` module handles fetching. The simplest approach: dump API responses as JSON files into `data_folder`, then have the parser read those files normally.

```python
# dumper.py — crawl a paginated REST API and save results as JSON
import os, json, logging, requests

logger = logging.getLogger(__name__)
API_BASE = "https://example-api.org/api/v1"

def fetch_all(data_folder, endpoint, params=None):
    """Paginate through an API endpoint and save results to a JSON file."""
    all_records = []
    page = 1
    while True:
        resp = requests.get(f"{API_BASE}/{endpoint}",
                            params={**(params or {}), "page": page, "limit": 1000},
                            timeout=60)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", data)  # adapt to API shape
        if not results:
            break
        all_records.extend(results)
        logger.info("Fetched page %d (%d records so far)", page, len(all_records))
        page += 1
    outfile = os.path.join(data_folder, f"{endpoint}.json")
    with open(outfile, "w") as f:
        json.dump(all_records, f)
    logger.info("Saved %d records to %s", len(all_records), outfile)
    return outfile
```

**API crawl best practices:**
- Always respect rate limits — add `time.sleep()` between pages if needed
- Set reasonable timeouts on requests (30-60s)
- Save raw API responses as JSON files in `data_folder` so the parser reads files (not live API)
- Log progress: page number, record count, errors
- Handle pagination correctly: offset/limit, cursor-based, or page-based
- For large APIs (>100K records), use streaming/chunked writes instead of accumulating in memory
- Never hardcode API keys in the plugin — use environment variables if auth is needed

### 2. Generate manifest.json
Always use version `"1.0"` and always include `__metadata__`.

**Standard manifest template:**
```json
{
    "version": "1.0",
    "requires": ["pandas"],
    "__metadata__": {
        "license": "CC BY 4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "url": "https://datasource-homepage.org"
    },
    "dumper": {
        "data_url": ["<only_the_specific_files_needed>"],
        "uncompress": false
    },
    "uploader": {
        "parser": "parser:load_data",
        "on_duplicates": "error"
    }
}
```

Rules for manifest.json:
- `version`: Always `"1.0"`. This is the manifest spec version, not the datasource version.
- `__metadata__`: **Always include.** Must have `license`, `license_url`, and `url` (datasource homepage). Optional `author` object with `name` and `url`.
- `requires`: List Python packages the parser needs (e.g., `["pandas"]`). Omit the key entirely if only stdlib + biothings SDK are needed.
- `dumper.data_url`: Single string URL or list of URLs. **Only include the specific files the parser needs** — not every file the datasource offers. Must be direct-download links.
- `dumper.uncompress`: Set `true` only for `.zip` files. For `.gz` files that pandas reads natively via `compression='gzip'`, set `false`.
- `uploader` (singular): Standard form. Contains `parser`, `on_duplicates`, and optionally `mapping`.
- `uploaders` (plural, list): Only when multiple parsers process different entity types. Each needs a `name` field.
- `on_duplicates`: Use `"error"` for most plugins. Use `"ignore"` only when the same `_id` legitimately appears from multiple source IDs.
- `parser`: Format is `"module:function"`. Standard is `"parser:load_data"`. Can reference shared parsers like `"hub.dataload.data_parsers:load_obo"`.
- `parser_kwargs`: Optional dict passed to parser function. Used with shared parsers (e.g., `{"obofile": "doid.obo", "prefix": "DOID"}`)

**Reference:** https://github.com/biothings/mydisease.info/blob/master/src/plugins/disgenet/manifest.json

### 3. Generate parser.py
Create a parser module following BioThings conventions:

```python
import os
import csv
from biothings.utils.dataload import dict_sweep, unlist

def load_data(data_folder):
    """Parse <datasource> data and yield BioThings-compatible documents."""
    infile = os.path.join(data_folder, "<filename>")
    assert os.path.exists(infile), f"Expected file not found: {infile}"

    with open(infile, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            _id = row.get("<primary_key_field>")
            if not _id:
                continue
            doc = {
                "_id": str(_id),
                "<datasource_name>": {
                    # Map source fields to output fields here
                }
            }
            doc = dict_sweep(unlist(doc), [None])
            yield doc
```

Rules for parser.py:
- The main parse function MUST accept `data_folder` as its only argument (unless `parser_kwargs` is used)
- The function MUST be a generator (use `yield`, not `return`)
- Every yielded document MUST have an `_id` key (string, unique, max 512 chars)
- All field keys MUST be lowercase with underscores. Clean keys: `key.lower().replace(" ", "_").replace("/", "_")`
- Nest all datasource-specific fields under a top-level key matching the datasource name
- Use SDK helpers: `dict_sweep(doc, [None])` removes None/empty values; `unlist(doc)` flattens single-item lists
- Also available: `value_convert_to_number()`, `merge_duplicate_rows()`, `to_boolean()`
- Use `biothings.utils.common.open_anyfile` to transparently handle .gz files without pandas
- For `.gz` files with pandas: `pd.read_csv(filepath, compression='gzip')`
- For large files, use streaming (`csv.DictReader`) or chunked reads (`pd.read_csv(chunksize=100000)`)
- Convert `numpy.int64` to Python `int` before yielding
- Replace NaN with None: `df = df.where(pd.notnull(df), None)`
- Follow BioThings code style: PEP8, max line length 160, import groups (stdlib / third-party / biothings)

### 4. Choose _id Strategy Based on Target API
- **MyChem.info**: InChIKey (e.g., `KTUFNOKKBVMGRW-UHFFFAOYSA-N`)
- **MyGene.info**: NCBI Gene ID (Entrez) or Ensembl Gene ID
- **MyDisease.info**: MONDO ID (e.g., `MONDO:0005015`). Map from DOID/UMLS/MESH if needed.
- **MyVariant.info**: HGVS notation (use `myvariant.src.utils.hgvs.get_hgvs_from_vcf()`)
- **pending.api**: Most specific unique ID available. Composite IDs like `f"{id1}-{id2}"` are acceptable.

Common ID mapping patterns:
- UMLS/MESH/OMIM → MONDO: Parse `mondo.json` xrefs
- DOID → MONDO: Use `biothings_client.get_client('disease').querymany()`
- Gene symbol/ENSEMBL → Entrez: Use mygene.info queries

### 5. Structure Output Documents
- Top-level: `_id` + one key per datasource
- Group related fields into sub-objects
- Use lists for one-to-many relationships
- Cross-references under `xrefs` sub-key
- For association data, use `subject` / `object` / `relation` structure (FoodData pattern)
- For merged multi-row records, use `associatedWith` list pattern (DISEASES pattern)

### 6. Save Output Files
```
agent_outputs/<datasource_name>_plugin/
├── manifest.json
├── parser.py
└── README.md
```

README.md should include: datasource name/URL, what the plugin does, `biothings-cli` test commands, example document, known limitations.

<!-- ### 7. Provide Testing Instructions
```bash
pip install "biothings[cli]"
cd agent_outputs/<datasource_name>_plugin/
biothings-cli dataplugin validate-manifest
biothings-cli dataplugin dump
biothings-cli dataplugin upload
biothings-cli dataplugin serve
# Visit http://localhost:9999/
``` -->

## Common Patterns (from production plugins)

### Simple CSV/TSV with groupby (DISEASES pattern)
```python
import os, csv
from itertools import groupby
from operator import itemgetter

def load_data(data_folder):
    infile = os.path.join(data_folder, "data.tsv")
    rows = []
    with open(infile) as f:
        for row in csv.DictReader(f, delimiter='\t'):
            rows.append(row)
    rows = sorted(rows, key=itemgetter('disease_id'))
    for key, group in groupby(rows, key=itemgetter('disease_id')):
        merged = [doc for doc in group]
        yield {"_id": key, "source": {"associatedWith": merged}}
```

### Pandas groupby for multi-row aggregation (DisGeNET pattern)
```python
import os
from collections import defaultdict
import pandas as pd
from biothings.utils.dataload import dict_sweep, unlist

def load_data(data_folder):
    df = pd.read_csv(os.path.join(data_folder, "data.tsv.gz"),
                     sep="\t", comment="#", compression="gzip")
    df = df.where(pd.notnull(df), None)
    d = defaultdict(list)
    for grp, subdf in df.groupby(["diseaseId", "source", "geneId"]):
        records = subdf.to_dict(orient="records")
        doc = {"source": grp[1], "gene_id": int(grp[2]), "pubmed": []}
        for rec in records:
            if rec.get("pmid"):
                doc["pubmed"].append(int(rec["pmid"]))
        d[grp[0]].append(doc)
    for _id, records in d.items():
        yield dict_sweep(unlist({"_id": _id, "source": {"genes": records}}), [None])
```

### Variant HGVS ID generation (CCLE/FIRE pattern)
```python
import os, logging
from biothings.utils.common import open_anyfile
import myvariant.src.utils.hgvs as hgvs

def load_data(data_file):
    with open_anyfile(data_file) as f:
        for line in f:
            try:
                parts = line.strip().split("\t")
                _id = hgvs.get_hgvs_from_vcf(parts[0], parts[1], parts[2], parts[3])
                yield {"_id": _id, "source": {"score": float(parts[4])}}
            except Exception as e:
                logging.error("Error with line %s: %s" % (line.strip(), e))
```

### Cross-API ID resolution (DISEASES pattern)
```python
from biothings_client import get_client

def batch_query_mondo_from_doid(doid_list):
    client = get_client('disease')
    mapping = {}
    for i in range(0, len(doid_list), 1000):
        batch = doid_list[i:i+1000]
        res = client.querymany(batch, scopes="mondo.xrefs.doid", fields="_id")
        for doc in res:
            mapping[doc['query']] = doc.get('_id', doc['query'])
    return mapping
```

### Multi-file CSV with deduplication (ECBD pattern)
Use when `data_url` is a list of CSVs with potential ID overlap between files:
```python
import os, csv, glob, logging
from biothings.utils.dataload import dict_sweep, unlist

logger = logging.getLogger(__name__)

def load_data(data_folder):
    csv_files = sorted(glob.glob(os.path.join(data_folder, "*.csv")))
    assert csv_files, f"No CSV files found in {data_folder}"
    seen_ids = set()
    for infile in csv_files:
        logger.info("Parsing %s", os.path.basename(infile))
        for doc in _parse_csv(infile, seen_ids):
            yield doc

def _parse_csv(filepath, seen_ids):
    with open(filepath, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            _id = row.get("id_field")
            if not _id or _id in seen_ids:
                continue
            seen_ids.add(_id)
            doc = {"_id": _id, "source": {"field": row.get("field")}}
            yield dict_sweep(unlist(doc), [None])
```

### JSON with orjson (FoodData pattern)
```python
import os, orjson

def load_data(data_folder):
    with open(os.path.join(data_folder, "data.json"), "rb") as f:
        data = orjson.loads(f.read())
    for record in data:
        yield {"_id": str(record["id"]), "source": record}
```

### REST API dump-then-parse (PGxDB/IGVF pattern)
Use when datasource has no bulk download — dump API to JSON files first, then parse:
```python
# parser.py — reads JSON files produced by a custom dumper or manual API dump
import os, json, glob, logging
from biothings.utils.dataload import dict_sweep, unlist

logger = logging.getLogger(__name__)

def load_data(data_folder):
    json_files = sorted(glob.glob(os.path.join(data_folder, "*.json")))
    assert json_files, f"No JSON files found in {data_folder}"
    for jf in json_files:
        logger.info("Parsing %s", os.path.basename(jf))
        with open(jf, "r") as f:
            records = json.load(f)
        for rec in records:
            _id = rec.get("id") or rec.get("_id")
            if not _id:
                continue
            doc = {
                "_id": str(_id),
                "source": rec  # adapt: nest under datasource key, clean fields
            }
            yield dict_sweep(unlist(doc), [None])
```
For the dumper side, use `requests` to paginate through the API and save each endpoint's results as a separate JSON file. See Section 1c for the dumper template.

## Decision Rules
- Default to singular `uploader` in manifest — standard across both pending.api and mydisease.info
- Use plural `uploaders` only for multiple entity types from the same dump
- If file > 1 GB → streaming or chunked reads
- If `_id` collisions expected → `on_duplicates: "ignore"` or pre-aggregate with `defaultdict(list)` + `groupby`
- If source uses non-standard IDs → build mapping or use `biothings_client`
- Always `dict_sweep()` + `unlist()` before yielding
- Prefer bulk downloads over API crawling when both are available and the bulk data is complete
- If no bulk download exists, use a custom dumper.py to crawl the datasource's API and save JSON files (see Section 1c)
- `.gz` → `uncompress: false`, let pandas handle; `.zip` → `uncompress: true`
- Include `__metadata__` with license info
- Multi-file sources: classify files as superset/independent/subset/composite, then select only what's needed
- Multi-file `data_url` list → parser must glob `data_folder` and deduplicate by `_id` with a `seen_ids` set
- Check `agent_outputs/` for prior inspection reports before re-discovering file relationships

## Reference Repositories
- **pending.api**: https://github.com/biothings/pending.api/tree/master/plugins
- **mydisease.info**: https://github.com/biothings/mydisease.info/tree/master/src/plugins
- **BioThings CLI tutorial**: https://docs.biothings.io/en/latest/tutorial/cli.html
- **BioThings code style**: PEP8, max line 160, flake8: `ignore=E226,E265,E302,E402,E731,F821,W503`
