import os
import csv
import glob
import json
from biothings.utils.dataload import dict_sweep, unlist

# Map filenames (stem) to (reference_db, rank) tuples
_FILENAME_MAP = {
    "silva_genus_absolute": ("silva", "genus"),
    "silva_species_absolute": ("silva", "species"),
    "gg_genus_absolute": ("gg", "genus"),
    "gg_species_absolute": ("gg", "species"),
}

_METADATA_FILENAME = "sample_metadata.json"


def _coerce_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _coerce_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _build_metadata_doc(meta):
    return {
        "sample_run": meta.get("Run"),
        "bioproj": meta.get("BioProject"),
        "biosample": meta.get("BioSample"),
        "project_name": meta.get("Project_name"),
        "collection_date": meta.get("Collection_Date"),
        "body_site": meta.get("Body_Site"),
        "system": meta.get("Systems"),
        "phenotype": meta.get("Phenotype"),
        "study_group": meta.get("Study_Group"),
        "study_design": {
            "time_series": meta.get("Time_series"),
            "comparison": meta.get("Comparison"),
            "matched": meta.get("Matched"),
        },
        "host": {
            "age": meta.get("Host_Age"),
            "sex": meta.get("Host_Sex"),
            "bmi": _coerce_float(meta.get("Host_BMI")),
            "height": _coerce_float(meta.get("Host_Height")),
            "weight": _coerce_float(meta.get("Host_Weight")),
            "birth_year": _coerce_int(meta.get("Host_Birth_Year")),
            "country_birth": meta.get("Host_Country_Birth"),
            "race_or_ethnicity": meta.get("Race_or_Ethnicity"),
            "menopausal_status": meta.get("Host_Menopausal_Status"),
        },
        "lifestyle": {
            "smoke_status": meta.get("Smoke_Status"),
            "drinking_status": meta.get("Drinking_Status"),
            "diet_type": meta.get("Diet_Type"),
            "sleep_duration": meta.get("Sleep_Duration"),
            "probiotic_frequency": meta.get("Probiotic_Frequency"),
            "teethbrushing_frequency": meta.get("Teethbrushing_Frequency"),
        },
        "antibiotics": {
            "use": meta.get("Antibiotics_Use"),
            "status": meta.get("Antibiotic_Status"),
            "route": meta.get("Antibiotic_Route"),
        },
        "geography": {
            "country": meta.get("Country"),
            "continent": meta.get("Continent"),
        },
        "sequencing": {
            "instrument": meta.get("Instrument"),
            "library_layout": meta.get("Library_Layout"),
            "variable_region": meta.get("Variable_Region"),
            "sequencing_type": meta.get("Sequencing_Type"),
            "sequencing_quality": meta.get("Sequencing_Quality"),
            "filter_pass": meta.get("Filter_Pass"),
        },
        "doi": meta.get("Doi"),
    }


def load_data(data_folder):
    """
    Parse locally downloaded PRIME files and yield one document per SRA Run ID.

    Expected files in data_folder (written by PRIMEDumper):
      silva_genus_absolute.csv   — SILVA genus-level read counts (53,449 rows × ~4,594 taxa)
      silva_species_absolute.csv — SILVA species-level read counts
      gg_genus_absolute.csv      — Greengenes2 genus-level read counts
      gg_species_absolute.csv    — Greengenes2 species-level read counts
      sample_metadata.json       — per-sample demographics/phenotype (written by dumper.post_dump)

    Each yielded document:
      _id: SRA Run accession (e.g. "DRR396973")
      prime: { sample_run, bioproj, biosample, phenotype, body_site, system,
               host.{age,sex,bmi,...}, lifestyle.*, geography.*, sequencing.*,
               study_design.*, antibiotics.*, doi,
               abundance.{ silva.{genus,species}, gg.{genus,species} } }
    """
    # Load metadata index: run_id → metadata dict
    metadata_path = os.path.join(data_folder, _METADATA_FILENAME)
    metadata_by_run = {}
    if os.path.exists(metadata_path):
        with open(metadata_path, "r", encoding="utf-8") as fh:
            records = json.load(fh)
        metadata_by_run = {r["Run"]: r for r in records if r.get("Run")}

    # Collect abundance data keyed by run_id
    # Structure: { run_id: { "silva": {"genus": {...taxon: count}, "species": {...}}, "gg": {...} } }
    abundance_by_run = {}

    for filepath in sorted(glob.glob(os.path.join(data_folder, "*.csv"))):
        stem = os.path.splitext(os.path.basename(filepath))[0]
        if stem not in _FILENAME_MAP:
            continue
        ref_db, rank = _FILENAME_MAP[stem]

        with open(filepath, "r", newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            taxa_cols = [c for c in (reader.fieldnames or []) if c != "Sample"]
            for row in reader:
                run_id = row.get("Sample", "").strip()
                if not run_id:
                    continue
                entry = abundance_by_run.setdefault(run_id, {})
                db_entry = entry.setdefault(ref_db, {})
                taxa = {}
                for col in taxa_cols:
                    raw = row.get(col, "").strip()
                    if raw and raw != "0":
                        try:
                            taxa[col] = int(raw)
                        except ValueError:
                            try:
                                taxa[col] = float(raw)
                            except ValueError:
                                pass
                if taxa:
                    db_entry[rank] = taxa

    assert abundance_by_run, f"No abundance CSV files found in {data_folder}"

    for run_id, abundance_data in abundance_by_run.items():
        meta = metadata_by_run.get(run_id, {})
        meta_doc = _build_metadata_doc(meta) if meta else {"sample_run": run_id}

        doc = {
            "_id": run_id,
            "prime": {
                **meta_doc,
                "abundance": abundance_data,
            },
        }
        doc = dict_sweep(unlist(doc), [None])
        yield doc
