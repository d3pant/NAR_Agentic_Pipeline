# Entity Resolution

Covers resolution of raw biological strings → CURIEs for `object.id` (taxon), `anatomical_entity.id` (body site), and phenotype `object.id` in the output JSON. Uses the [EMBL-EBI OLS4 REST API](https://www.ebi.ac.uk/ols4) — no local database, no API key required.

---

## Install

```bash
pip install requests
```

No additional dependencies beyond the standard parser stack.

---

## Slash-Handling Rule

Many raw metadata strings contain a `/` separator (e.g. `"Stool/feces"`, `"Digestive System/Gut"`).

**Always query only the term to the left of the first `/`.** Drop the right-hand side entirely before calling OLS4.

```python
def normalize_query(raw: str) -> str:
    """Use the left side of '/' as the query string."""
    return raw.split("/")[0].strip()
```

This applies to **all entity types** — taxon, body site, and phenotype/disease.

---

## Core OLS4 Resolution Function

All resolution goes through a single throttled function that calls `GET https://www.ebi.ac.uk/ols4/api/search`. OLS4 returns hits ranked by relevance — **always take the first hit (index 0)** as the canonical CURIE.

```python
import re
import time
import sys
import requests

OLS4_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"
_MIN_INTERVAL = 0.2   # 5 req/s ceiling
_MAX_RETRIES  = 5
_last_call    = 0.0


def _ols4_search(query: str, ontology: str) -> str | None:
    """
    Query OLS4 for `query` scoped to `ontology` (lowercase, e.g. 'uberon').
    Returns the top-ranked CURIE string, or None if no hit.
    Always takes rank-1 result.
    """
    global _last_call
    elapsed = time.time() - _last_call
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)

    params = {
        "q":        query,
        "ontology": ontology.lower(),
        "exact":    "true",
        "rows":     1,
        "lang":     "en",
    }
    backoff = 2.0
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = requests.get(OLS4_SEARCH_URL, params=params, timeout=30)
        except requests.RequestException as exc:
            sys.stderr.write(f"[ols4] attempt {attempt} request error: {exc}\n")
            time.sleep(backoff); backoff *= 2; continue

        _last_call = time.time()

        if resp.status_code == 200:
            docs = resp.json().get("response", {}).get("docs", [])
            if docs:
                return _iri_to_curie(docs[0].get("iri", ""))
            # exact returned nothing — retry with fuzzy
            if params.get("exact"):
                params.pop("exact")
                continue
            return None

        if resp.status_code == 429:
            time.sleep(backoff); backoff *= 2; continue

        sys.stderr.write(
            f"[ols4] attempt {attempt}: HTTP {resp.status_code} for '{query}': "
            f"{resp.text[:200]}\n"
        )
        time.sleep(backoff); backoff *= 2

    sys.stderr.write(f"[ols4] giving up on '{query}' after {_MAX_RETRIES} attempts\n")
    return None


def _iri_to_curie(iri: str) -> str | None:
    """Convert an OBO IRI to a CURIE. Returns None if pattern does not match."""
    m = re.search(r'/obo/([A-Za-z0-9]+)_([A-Za-z0-9]+)$', iri)
    if m:
        prefix, local_id = m.groups()
        return f"{prefix.upper()}:{local_id}"
    return None
```

---

## Batch Resolution Pattern (Use in All Parsers)

Resolve all unique strings **once before the document loop**. Never call OLS4 inside a per-row loop.

```python
def batch_resolve_ols4(strings: list[str], ontology: str) -> dict[str, str | None]:
    """
    Resolve a list of raw strings → {original_string: curie} using OLS4.
    Applies slash-normalization before querying; maps result back to the original key.
    """
    result = {}
    seen_queries: dict[str, str | None] = {}   # cache normalized → curie to avoid duplicate calls

    for raw in strings:
        query = normalize_query(raw)
        if query not in seen_queries:
            seen_queries[query] = _ols4_search(query, ontology)
        result[raw] = seen_queries[query]

    return result
```

---

## Resolution by Entity Type

### 1. Taxon → `NCBITAXON:XXXX`

Raw strings are full taxonomic lineage strings from abundance CSV column headers (e.g. `d__Bacteria;p__Firmicutes;...;s__Lachnospiraceae`). Extract the terminal rank first, then resolve against `ncbitaxon`.

> **Note:** OLS4 returns NCBI taxon CURIEs as `NCBITAXON:XXXX`. Extract the integer for use in `gettaxa()` by stripping the prefix.

```python
def extract_terminal_rank(lineage_string: str) -> str:
    """Extract species/genus name from SILVA/GG lineage string."""
    return lineage_string.split(";")[-1].split("__")[-1].strip()

# Pre-resolution (Phase 1 of parser)
raw_taxa = list({extract_terminal_rank(col) for col in abundance_col_headers})
taxon_curie_map = batch_resolve_ols4(raw_taxa, "ncbitaxon")
# → {"Lachnospiraceae": "NCBITAXON:186803", "Ruminococcus": "NCBITAXON:1263", ...}
```

After resolution, extract the integer taxid for use in `gettaxa()` (see [biothings-taxon-resolution.md](biothings-taxon-resolution.md)):

```python
def extract_taxid_int(curie: str | None) -> int | None:
    """Extract integer from 'NCBITAXON:853' → 853."""
    if curie and ":" in curie:
        try:
            return int(curie.split(":")[1])
        except ValueError:
            return None
    return None
```

The `object.id` field in the output JSON must be stored as `taxid:{integer}` (BioThings convention), not the raw OLS4 CURIE:

```python
taxid_int = extract_taxid_int(taxon_curie_map.get(name))
object_id = f"taxid:{taxid_int}" if taxid_int else None
```

### 2. Body Site → `UBERON:XXXXXXX`

Raw strings come from the `Body_Site` or `Systems` metadata field (e.g. `"Stool/feces"`, `"Digestive System/Gut"`). Slash rule applies — query only the left side.

```python
raw_body_sites = list({row["Body_Site"] for row in metadata_rows if row.get("Body_Site")})
body_site_map = batch_resolve_ols4(raw_body_sites, "uberon")
# "Stool/feces"         → queries "Stool"          → "UBERON:0001988"
# "Digestive System/Gut" → queries "Digestive System" → "UBERON:0001555"
```

### 3. Phenotype / Disease → `MONDO:XXXXXXX` or `HP:XXXXXXX`

Raw strings come from the `Phenotype` metadata field (e.g. `"Healthy"`, `"Type 2 Diabetes"`).

Returns a `(curie, biolink_category)` tuple so the caller can set `object.category` without inspecting the prefix separately.

**Resolution strategy:**

1. **Hardcoded sentinels** — checked before any API call. Currently: `"healthy"` → `("NCIT:C49651", "biolink:PhenotypicFeature")`.
2. **Heuristic routing** — applied to the normalized query (left of `/`, lowercased). If it contains a disease keyword → try MONDO first, HP as fallback. Otherwise → try HP first, MONDO as fallback. This avoids wasting a MONDO call on clearly phenotypic terms like "microcephaly".
3. **Fallback** — if the primary ontology returns `None`, try the other. If both return `None`, return `(None, None)`.

```python
# Terms that indicate a disease — try MONDO first for these
_DISEASE_KEYWORDS = {
    "disease", "disorder", "cancer", "syndrome", "colitis",
    "diabetes", "carcinoma", "tumor", "tumour", "infection",
    "deficiency", "failure", "injury", "sclerosis", "fibrosis",
}

# Hardcoded sentinels — no API call made for these
_PHENOTYPE_SENTINELS: dict[str, tuple[str, str]] = {
    "healthy": ("NCIT:C49651", "biolink:PhenotypicFeature"),
}


def _is_disease_term(query: str) -> bool:
    """Return True if the normalized query looks like a disease rather than a phenotype."""
    tokens = set(query.lower().split())
    return bool(tokens & _DISEASE_KEYWORDS)


def resolve_phenotype(raw: str) -> tuple[str | None, str | None]:
    """
    Resolve a raw phenotype/disease string to (curie, biolink_category).
    Returns (None, None) if unresolved — caller must skip the association record.

    Order:
      1. Sentinel lookup (no API call)
      2. Heuristic routing → MONDO-first or HP-first
      3. Cross-ontology fallback
    """
    query = normalize_query(raw)
    q_lower = query.lower()

    # Step 1 — sentinel
    if q_lower in _PHENOTYPE_SENTINELS:
        return _PHENOTYPE_SENTINELS[q_lower]

    # Step 2+3 — heuristic routing with fallback
    if _is_disease_term(q_lower):
        primary, fallback = "mondo", "hp"
        primary_cat, fallback_cat = "biolink:Disease", "biolink:PhenotypicFeature"
    else:
        primary, fallback = "hp", "mondo"
        primary_cat, fallback_cat = "biolink:PhenotypicFeature", "biolink:Disease"

    curie = _ols4_search(query, primary)
    if curie is not None:
        return curie, primary_cat
    curie = _ols4_search(query, fallback)
    if curie is not None:
        return curie, fallback_cat
    return None, None


raw_phenotypes = list({row["Phenotype"] for row in metadata_rows if row.get("Phenotype")})
phenotype_map = {raw: resolve_phenotype(raw) for raw in raw_phenotypes}
# → {"Type 2 Diabetes": ("MONDO:0005148", "biolink:Disease"),      # disease keyword → MONDO first
#    "microcephaly":    ("HP:0000252",    "biolink:PhenotypicFeature"), # no keyword → HP first
#    "healthy":         ("NCIT:C49651",  "biolink:PhenotypicFeature"), # sentinel, no API call
#    "Crohn's disease": ("MONDO:0005011", "biolink:Disease")}
```

Unpack in the document loop:
```python
curie, category = phenotype_map.get(row.get("Phenotype"), (None, None))
```

> **Adding sentinels:** Extend `_PHENOTYPE_SENTINELS` with any additional no-API-call mappings. Keys must be lowercase normalized (left of `/`, stripped). Value is `(curie, biolink_category)`.

> **Unresolved terms:** `(None, None)` means omit the entire phenotype association record. Never store a raw string or `None` in a CURIE field.

---

## Full Parser Pre-Resolution Block

This is Phase 1 of the three-phase parser pattern. Run this before reading any abundance rows.

```python
import re
import time
import sys
import requests
import biothings_client

OLS4_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"
_MIN_INTERVAL = 0.2
_MAX_RETRIES  = 5
_last_call    = 0.0


def normalize_query(raw: str) -> str:
    return raw.split("/")[0].strip()


def _iri_to_curie(iri: str) -> str | None:
    m = re.search(r'/obo/([A-Za-z0-9]+)_([A-Za-z0-9]+)$', iri)
    if m:
        return f"{m.group(1).upper()}:{m.group(2)}"
    return None


def _ols4_search(query: str, ontology: str) -> str | None:
    global _last_call
    elapsed = time.time() - _last_call
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    params = {"q": query, "ontology": ontology.lower(), "exact": "true", "rows": 1, "lang": "en"}
    backoff = 2.0
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = requests.get(OLS4_SEARCH_URL, params=params, timeout=30)
        except requests.RequestException as exc:
            sys.stderr.write(f"[ols4] attempt {attempt}: {exc}\n")
            time.sleep(backoff); backoff *= 2; continue
        _last_call = time.time()
        if resp.status_code == 200:
            docs = resp.json().get("response", {}).get("docs", [])
            if docs:
                return _iri_to_curie(docs[0].get("iri", ""))
            if params.get("exact"):
                params.pop("exact"); continue
            return None
        if resp.status_code == 429:
            time.sleep(backoff); backoff *= 2; continue
        sys.stderr.write(f"[ols4] HTTP {resp.status_code} for '{query}'\n")
        time.sleep(backoff); backoff *= 2
    return None


def batch_resolve_ols4(strings: list[str], ontology: str) -> dict[str, str | None]:
    seen: dict[str, str | None] = {}
    result = {}
    for raw in strings:
        q = normalize_query(raw)
        if q not in seen:
            seen[q] = _ols4_search(q, ontology)
        result[raw] = seen[q]
    return result


_DISEASE_KEYWORDS = {
    "disease", "disorder", "cancer", "syndrome", "colitis",
    "diabetes", "carcinoma", "tumor", "tumour", "infection",
    "deficiency", "failure", "injury", "sclerosis", "fibrosis",
}

_PHENOTYPE_SENTINELS: dict[str, tuple[str, str]] = {
    "healthy": ("NCIT:C49651", "biolink:PhenotypicFeature"),
}


def resolve_phenotype(raw: str) -> tuple[str | None, str | None]:
    query = normalize_query(raw)
    q_lower = query.lower()
    if q_lower in _PHENOTYPE_SENTINELS:
        return _PHENOTYPE_SENTINELS[q_lower]
    if bool(set(q_lower.split()) & _DISEASE_KEYWORDS):
        primary, fallback = "mondo", "hp"
        primary_cat, fallback_cat = "biolink:Disease", "biolink:PhenotypicFeature"
    else:
        primary, fallback = "hp", "mondo"
        primary_cat, fallback_cat = "biolink:PhenotypicFeature", "biolink:Disease"
    curie = _ols4_search(query, primary)
    if curie is not None:
        return curie, primary_cat
    curie = _ols4_search(query, fallback)
    if curie is not None:
        return curie, fallback_cat
    return None, None


def build_resolution_maps(abundance_col_headers, metadata_rows):
    # --- taxon resolution ---
    raw_taxa = list({
        col.split(";")[-1].split("__")[-1].strip()
        for col in abundance_col_headers
    })
    taxon_curie_map = batch_resolve_ols4(raw_taxa, "ncbitaxon")

    # --- extract integer taxids for biothings_client ---
    resolved_taxids = {}
    for name, curie in taxon_curie_map.items():
        if curie and ":" in curie:
            try:
                resolved_taxids[name] = int(curie.split(":")[1])
            except ValueError:
                pass
    unique_taxid_ints = list(set(resolved_taxids.values()))

    # --- batch gettaxa for parent_taxid, lineage, rank ---
    t = biothings_client.get_client('taxon')
    taxon_detail_map = {}
    for r in t.gettaxa(unique_taxid_ints, fields='parent_taxid,lineage,rank'):
        if not r.get('notfound'):
            taxon_detail_map[int(r['query'])] = {
                'parent_taxid': r.get('parent_taxid'),
                'lineage':      r.get('lineage', []),
                'rank':         r.get('rank'),
            }

    # --- body site resolution ---
    raw_body_sites = list({
        row["Body_Site"] for row in metadata_rows if row.get("Body_Site")
    })
    body_site_map = batch_resolve_ols4(raw_body_sites, "uberon")

    # --- phenotype resolution ---
    raw_phenotypes = list({
        row["Phenotype"] for row in metadata_rows if row.get("Phenotype")
    })
    phenotype_map = {raw: resolve_phenotype(raw) for raw in raw_phenotypes}

    return taxon_curie_map, resolved_taxids, taxon_detail_map, body_site_map, phenotype_map
```

---

## Using Resolution Maps in the Document Loop

```python
for row in metadata_rows:
    original_name = extract_terminal_rank(col_header)
    ncbitaxon_curie = taxon_curie_map.get(original_name)
    taxid = resolved_taxids.get(original_name)
    if not ncbitaxon_curie or not taxid:
        continue  # skip unresolved taxa

    taxon_info = taxon_detail_map.get(taxid, {})
    body_site_curie = body_site_map.get(row.get("Body_Site"))
    phenotype_curie, phenotype_category = phenotype_map.get(row.get("Phenotype"), (None, None))

    doc = {
        "_id": f"{row['BioSample']}_{row['Run']}_has_taxon_{taxid}",
        "object": {
            "id": f"taxid:{taxid}",        # BioThings convention, NOT the raw OLS4 CURIE
            "taxid": taxid,
            "name": original_name,
            "original_name": original_name,
            "parent_taxid": taxon_info.get("parent_taxid"),
            "lineage": taxon_info.get("lineage", []),
            "rank": taxon_info.get("rank"),
            "category": "biolink:OrganismTaxon",
        },
        "association": {
            "anatomical_entity": {
                "id": body_site_curie,
                "original_name": row.get("Body_Site"),
                "category": "biolink:AnatomicalEntity",
            } if body_site_curie else None,
            ...
        },
        ...
    }
```

---

## Unresolved String Handling

| Field | Resolution fails | Action |
|---|---|---|
| `object.id` (taxon) | `curie` is `None` | Skip entire (sample × taxon) record |
| `anatomical_entity.id` | `curie` is `None` | Omit entire `anatomical_entity` block |
| Phenotype `object.id` | `curie` is `None` | Omit entire phenotype association record |

Never store `None` or the raw string in a CURIE field.

---

## Field → Resolution Tool Mapping

| Output JSON field | Raw source | OLS4 ontology | CURIE prefix |
|---|---|---|---|
| `object.id` (taxon) | Abundance CSV column header | `ncbitaxon` | `taxid:` (converted from `NCBITAXON:`) |
| `object.parent_taxid`, `lineage`, `rank` | Resolved taxid integer | `biothings_client` `gettaxa()` | — |
| `anatomical_entity.id` | `Body_Site` metadata field (left of `/`) | `uberon` | `UBERON:` |
| Phenotype `object.id` | `Phenotype` metadata field (left of `/`) | `mondo` → `hp` fallback | `MONDO:` / `HP:` |
