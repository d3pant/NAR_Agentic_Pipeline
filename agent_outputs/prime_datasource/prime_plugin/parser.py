import os
import re
import sys
import csv
import time
import glob

import biothings_client
import requests

from biothings.utils.dataload import dict_sweep, unlist

# ---------------------------------------------------------------------------
# OLS4 resolution helpers
# ---------------------------------------------------------------------------

OLS4_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"
_MIN_INTERVAL = 0.2
_MAX_RETRIES = 5
_last_call = 0.0

_DISEASE_KEYWORDS = {
    "disease", "disorder", "cancer", "syndrome", "colitis",
    "diabetes", "carcinoma", "tumor", "tumour", "infection",
    "deficiency", "failure", "injury", "sclerosis", "fibrosis",
    "leukemia", "lymphoma", "cirrhosis", "pneumonia", "arthritis",
}

# Hardcoded sentinels: key = lowercase normalized, value = (curie, category) or None to skip
_PHENOTYPE_SENTINELS = {
    "healthy": ("NCIT:C49651", "biolink:PhenotypicFeature"),
    "negative control": ("NCIT:C94523", "biolink:PhenotypicFeature"),
    "unknown": None,
    "na": None,
    "non-human": None,
    "critically ill": None,  # too broad/vague for ontology mapping
}


def normalize_query(raw):
    return raw.split("/")[0].strip()


def _iri_to_curie(iri):
    m = re.search(r'/obo/([A-Za-z0-9]+)_([A-Za-z0-9]+)$', iri)
    if m:
        return f"{m.group(1).upper()}:{m.group(2)}"
    return None


def _ols4_search(query, ontology):
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


def batch_resolve_ols4(strings, ontology):
    seen = {}
    result = {}
    for raw in strings:
        q = normalize_query(raw)
        if q not in seen:
            seen[q] = _ols4_search(q, ontology)
        result[raw] = seen[q]
    return result


def resolve_phenotype(raw):
    """Resolve a single phenotype string → (curie, biolink_category) or None."""
    query = normalize_query(raw.strip())
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


def _curie_local_id(curie):
    return curie.split(":")[1]


# ---------------------------------------------------------------------------
# Subject core field check
# ---------------------------------------------------------------------------

def _missing(v):
    return v is None or str(v).strip().lower() in ("", "nan")


def _subject_core_present(row):
    for f in ("Host_Age", "Host_Sex", "Host_BMI"):
        if _missing(row.get(f)):
            return False
    if _missing(row.get("Race_or_Ethnicity")) and _missing(row.get("Country")):
        return False
    return True


# ---------------------------------------------------------------------------
# Taxon column helpers
# ---------------------------------------------------------------------------

def _terminal_rank(col_header):
    """
    Extract the last non-empty taxonomic label from a SILVA lineage string.
    SILVA uses rank__name format; species-level often appears as 's__' (empty).
    We walk backwards to find the last segment with an actual name.
    """
    parts = col_header.split(";")
    for part in reversed(parts):
        segments = part.split("__")
        name = segments[-1].strip() if len(segments) > 1 else part.strip()
        if name:
            return name
    return None


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def load_data(data_folder):
    """Parse PRIME database files and yield BioThings-compatible documents."""

    def _find(pattern):
        matches = glob.glob(os.path.join(data_folder, pattern))
        if not matches:
            raise FileNotFoundError(f"No file matching '{pattern}' in {data_folder}")
        return sorted(matches)[-1]

    meta_file = _find("samples_metadata*")
    abs_file = _find("silva_species_absolute*")
    rel_file = _find("silva_species_relative*")

    # -----------------------------------------------------------------------
    # Phase 1 — Pre-resolution
    # -----------------------------------------------------------------------

    sys.stderr.write("[prime] Loading samples_metadata.csv...\n")
    with open(meta_file, "r", encoding="utf-8-sig") as f:
        metadata_rows = list(csv.DictReader(f))
    sys.stderr.write(f"[prime] Loaded {len(metadata_rows)} samples.\n")

    sys.stderr.write("[prime] Reading abundance column headers...\n")
    with open(abs_file, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        abs_headers = next(reader)
    taxon_cols = abs_headers[1:]  # drop 'Sample' column

    # Collect unique base phenotype strings (split multi-value comma fields)
    raw_phenotype_set = set()
    for row in metadata_rows:
        phen_str = row.get("Phenotype", "")
        if phen_str:
            for p in phen_str.split(","):
                p = p.strip()
                if p:
                    raw_phenotype_set.add(p)

    raw_taxa = list({
        _terminal_rank(col)
        for col in taxon_cols
        if _terminal_rank(col)
    })
    raw_body_sites = list({
        row["Body_Site"] for row in metadata_rows if row.get("Body_Site")
    })
    raw_phenotypes = list(raw_phenotype_set)

    sys.stderr.write(f"[prime] Resolving {len(raw_taxa)} unique taxa via OLS4...\n")
    taxon_curie_map = batch_resolve_ols4(raw_taxa, "ncbitaxon")

    sys.stderr.write(f"[prime] Resolving {len(raw_body_sites)} body sites via OLS4...\n")
    body_site_map = batch_resolve_ols4(raw_body_sites, "uberon")

    sys.stderr.write(f"[prime] Resolving {len(raw_phenotypes)} individual phenotypes via OLS4...\n")
    phenotype_map = {raw: resolve_phenotype(raw) for raw in raw_phenotypes}

    # Extract integer taxids
    resolved_taxids = {}
    for name, curie in taxon_curie_map.items():
        if curie and ":" in curie:
            try:
                resolved_taxids[name] = int(curie.split(":")[1])
            except ValueError:
                pass
    unique_taxid_ints = list(set(resolved_taxids.values()))

    sys.stderr.write(f"[prime] Fetching taxon details for {len(unique_taxid_ints)} taxids...\n")
    t = biothings_client.get_client("taxon")
    taxon_detail_map = {}
    for r in t.gettaxa(unique_taxid_ints, fields="parent_taxid,lineage,rank"):
        if not r.get("notfound"):
            taxon_detail_map[int(r["query"])] = {
                "parent_taxid": r.get("parent_taxid"),
                "lineage": r.get("lineage", []) or None,
                "rank": r.get("rank"),
            }

    meta_by_run = {row["Run"]: row for row in metadata_rows}

    # -----------------------------------------------------------------------
    # Phase 2 — Document construction
    # -----------------------------------------------------------------------

    sys.stderr.write("[prime] Streaming abundance files and yielding documents...\n")

    taxon_doc_count = 0
    phenotype_doc_count = 0
    skipped_no_meta = 0
    skipped_bad_subject = 0
    skipped_unresolved_taxon = 0
    skipped_zero_abundance = 0
    # Track per-BioSample which phenotype CURIEs have already been emitted
    yielded_phenotype_pairs = set()  # (biosample, curie)

    with open(abs_file, "r", encoding="utf-8-sig") as abs_f, \
         open(rel_file, "r", encoding="utf-8-sig") as rel_f:

        abs_reader = csv.DictReader(abs_f)
        rel_reader = csv.DictReader(rel_f)

        for abs_row, rel_row in zip(abs_reader, rel_reader):
            run_id = abs_row.get("Sample")
            if not run_id:
                continue

            sample = meta_by_run.get(run_id)
            if not sample:
                skipped_no_meta += 1
                continue

            subject_ok = _subject_core_present(sample)
            biosample = sample.get("BioSample")

            if subject_ok:
                subject = {
                    "BioSample ID": biosample,
                    "age": _safe_float(sample.get("Host_Age")),
                    "gender": sample.get("Host_Sex") or None,
                    "height": _safe_float(sample.get("Host_Height")),
                    "weight": _safe_float(sample.get("Host_Weight")),
                    "BMI": _safe_float(sample.get("Host_BMI")),
                    "ethnicity": sample.get("Race_or_Ethnicity") or None,
                    "country": sample.get("Country") or None,
                    "continent": sample.get("Continent") or None,
                    "smoke_status": sample.get("Smoke_Status") or None,
                    "drinking_status": sample.get("Drinking_Status") or None,
                    "diet_type": sample.get("Diet_Type") or None,
                    "category": "biolink:MaterialSample",
                }
            else:
                skipped_bad_subject += 1
                subject = None

            body_site_raw = sample.get("Body_Site")
            body_site_curie = body_site_map.get(body_site_raw) if body_site_raw else None
            publication_doi = sample.get("Doi") or None

            # --- Taxon association documents ---
            if subject_ok:
                for col in taxon_cols:
                    terminal = _terminal_rank(col)
                    if not terminal:
                        continue

                    abs_val = _safe_float(abs_row.get(col))
                    if abs_val is None or abs_val == 0.0:
                        skipped_zero_abundance += 1
                        continue

                    rel_val = _safe_float(rel_row.get(col))

                    ncbitaxon_curie = taxon_curie_map.get(terminal)
                    taxid = resolved_taxids.get(terminal)
                    if not ncbitaxon_curie or not taxid:
                        skipped_unresolved_taxon += 1
                        continue

                    taxon_info = taxon_detail_map.get(taxid, {})

                    doc = {
                        "_id": f"{biosample}_{run_id}_has_taxon_{taxid}",
                        "association": {
                            "category": "biolink:MaterialSampleToOrganismTaxonAssociation",
                            "predicate": "biolink:has_taxon",
                            "BioProject": sample.get("BioProject") or None,
                            "SRA Run ID": run_id,
                            "project_name": sample.get("Project_name") or None,
                            "relative_abundance": rel_val,
                            "absolute_abundance": abs_val,
                            "instrument": sample.get("Instrument") or None,
                            "primary_knowledge_source": ["infores:PRIMEDB"],
                            "agent_type": "biolink:automated_agent",
                            "publication": {
                                "doi": f"doi:{publication_doi}",
                                "category": "biolink:Publication",
                            } if publication_doi else None,
                            "anatomical_entity": {
                                "id": body_site_curie,
                                "original_name": body_site_raw,
                                "category": "biolink:AnatomicalEntity",
                            } if body_site_curie else None,
                        },
                        "object": {
                            "id": f"taxid:{taxid}",
                            "taxid": taxid,
                            "name": terminal,
                            "original_name": col.split(";")[-1].strip() or terminal,
                            "parent_taxid": taxon_info.get("parent_taxid"),
                            "lineage": taxon_info.get("lineage"),
                            "rank": taxon_info.get("rank"),
                            "category": "biolink:OrganismTaxon",
                        },
                        "subject": subject,
                    }
                    doc = dict_sweep(unlist(doc), [None, []])
                    yield doc
                    taxon_doc_count += 1

            # --- Phenotype association documents (one per resolved phenotype per BioSample) ---
            if subject_ok and biosample:
                phen_str = sample.get("Phenotype", "")
                for phen_raw in (p.strip() for p in phen_str.split(",") if p.strip()):
                    result = phenotype_map.get(phen_raw, (None, None))
                    if result is None or result == (None, None):
                        continue
                    phenotype_curie, phenotype_category = result

                    if not phenotype_curie:
                        continue

                    pair_key = (biosample, phenotype_curie)
                    if pair_key in yielded_phenotype_pairs:
                        continue
                    yielded_phenotype_pairs.add(pair_key)

                    local_id = _curie_local_id(phenotype_curie)
                    doc = {
                        "_id": f"{biosample}_has_phenotype_{local_id}",
                        "association": {
                            "category": "biolink:MaterialSampleToDiseaseOrPhenotypicFeatureAssociation",
                            "predicate": "biolink:has_phenotype",
                            "BioProject": sample.get("BioProject") or None,
                            "project_name": sample.get("Project_name") or None,
                            "primary_knowledge_source": ["infores:PRIMEDB"],
                            "agent_type": "biolink:automated_agent",
                            "publication": {
                                "doi": f"doi:{publication_doi}",
                                "category": "biolink:Publication",
                            } if publication_doi else None,
                        },
                        "object": {
                            "id": phenotype_curie,
                            "original_name": phen_raw,
                            "category": phenotype_category,
                        },
                        "subject": subject,
                    }
                    doc = dict_sweep(unlist(doc), [None, []])
                    yield doc
                    phenotype_doc_count += 1

    sys.stderr.write(
        f"[prime] Done. Taxon docs: {taxon_doc_count}, Phenotype docs: {phenotype_doc_count}, "
        f"Skipped (no meta): {skipped_no_meta}, (bad subject): {skipped_bad_subject}, "
        f"(unresolved taxon): {skipped_unresolved_taxon}, (zero abundance): {skipped_zero_abundance}\n"
    )


def _safe_float(v):
    if v is None or str(v).strip().lower() in ("", "nan", "none"):
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None
