# Microbiome Datasource — Bulk Download Reference

Used during Step 1 of relevancy analysis when the datasource is microbiome-focused.
Determines where bulk data lives and how to score it before proceeding to the standard relevance/openness evaluation.

---

## Step 1: Locate the Metadata Umbrella

Check the datasource's own download page first. If no bulk download exists there, check Zenodo (or equivalent archive: Figshare, Dryad, OSF).

**The umbrella is whichever location you find sample-level demographic metadata in.**
If both locations have it, use the more recent or more complete deposit and note the other in `risks[]`.

---

## Ladder A — Metadata found on datasource's own site

1. Confirm the file is bulk-downloadable via a public URL (no login, no paywall).
2. Check whether it contains **sample-level demographic metadata** (age, BMI, disease status, body site, or equivalent). If absent, this is not a viable datasource — note in evidence and move toward DO_NOT_INGEST.
3. Score taxonomic resolution and add directly to the relevance score:
   - Species level: **+2**
   - Genus or phylum level: **+1**
   - No abundance data or taxonomic annotation: **+0**
**HIGHLY IMPORTANT — read before selecting files:**
1. **Database preference**: Use SILVA (newer, well-maintained). Fall back to Greengenes only if SILVA is absent.
2. **Abundance type preference**: Prefer both absolute and relative abundance. If only one is available, prefer absolute over relative.
3. **File selection rule**: Only download the minimum necessary files in this priority order: **Metadata → Absolute SILVA abundance → Relative SILVA abundance**. Nothing beyond these three. Example: if a deposit has metadata + SILVA (absolute + relative) + Greengenes (absolute + relative), download only Metadata, Absolute SILVA, and Relative SILVA.
4. Check license once for the whole deposit → feeds openness score.

---

## Ladder B — Metadata found on Zenodo (or equivalent archive)

1. Confirm the deposit is publicly accessible without login.
2. Check whether the deposit is **canonical** (datasource site links to it as the primary release) or a **snapshot/mirror** (an older or partial upload). If it is a snapshot, note the version gap in `risks[]`.
3. Check whether it contains **sample-level demographic metadata**. Same rule as Ladder A — if absent, move toward DO_NOT_INGEST.
4. Score taxonomic resolution and add directly to the relevance score:
   - Species level: **+2**
   - Genus or phylum level: **+1**
   - No abundance data or taxonomic annotation: **+0**
5. Check license once for the whole deposit → feeds openness score.

---

## Shared Fallback (both ladders exhausted)

If no bulk download exists on the datasource site or any archive:

1. **Return to the paper** — check supplementary data for a linked dataset. If the supplement is machine-readable and complete, note it; otherwise flag as non-machine-readable.
2. **API only** — if the only access path is a REST/GraphQL API, cap openness score at 3 and flag for future API-first dumper. Do not treat as a bulk download.
3. If neither exists, record this explicitly in `evidence` and default toward DO_NOT_INGEST unless there is a compelling reason for NEEDS_REVIEW.

---

## Notes

- Openness is checked **once** for the umbrella — metadata and abundance are co-located, so a single license/access check covers both.
- File format (BIOM, HDF5, FASTA, etc.) is handled by a later relevance metric — do not penalize here.
- A Zenodo deposit that is behind the live site by a major version should be noted in `risks[]` but does not block scoring.
