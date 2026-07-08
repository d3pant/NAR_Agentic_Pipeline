# Output JSON Structure

Maps sample demographics (`subject`) to a microbial taxon (`object`) or phenotype via an association record.

> **VERY IMPORTANT:** For each sample, one record using the structure below must be appended to a single output JSON — one entry per sample→taxon mapping, all collected in the same file.

---

## Sample → Taxon Association

### Field Rules

#### `association` fields

- **`_id`** `string` — Unique identifier for the record. Constructed by concatenating the BioSample ID, predicate, and resolved taxon ID, separated by underscores: `{BioSample ID}_has_taxon_{taxon id}`. Both components must be resolved before construction — do not construct `_id` until `subject.BioSample ID` and `object.id` are confirmed. Must be unique per record; if a BioSample maps to multiple taxa via multiple SRA Runs, each record gets its own `_id` using the respective taxon ID. **Always present; never omit.**

- **`BioProject`** `string` — BioProject ID from the metadata CSV file. May be absent in some cases; if so, follow instructions #.

- **`SRA Run ID`** `string` — SRA Run ID given for each BioSample. ALWAYS present in the CSV; raise an issue to the user if not present.

  > **Note:** For a given sample, there may be multiple SRA Run IDs. In this case, create separate association records mapping the same sample to different microbiome abundance tables based on the SRA Run ID. The downstream `relative_abundance`, `absolute_abundance`, and `instrument` values may differ between SRA Runs and will be indicated accordingly.

- **`project_name`** `string` — Project name given in the CSV; remains the same across SRA Runs from the same BioProject. If absent, omit this field. **Do NOT use `null`/`NaN` — simply omit.**

- **`relative_abundance`** `float` — Map the SRA Run from metadata to the taxon. Relative abundance data may be present either in the same metadata CSV or in a separate CSV file. If not present, raise an issue to the user and continue. **Omit the field if not present.** Note that there are different relative abundances for different SRA Runs from the same BioSample.

- **`absolute_abundance`** `float` — Map the SRA Run from metadata to the taxon. Absolute abundance data may be present either in the same metadata CSV or in a separate CSV file. **If not present, raise an issue to the user and STOP working.** Note that there are different absolute abundances for different SRA Runs from the same BioSample.

- **`instrument`** `string` — Present in the metadata CSV file. If not present, notify the user and continue by omitting the field. May be different or the same across SRA Runs from the same BioSample.

- **`primary_knowledge_source`** `list[string]` — Hardcoded for the database. Remains the same across SRA Runs for the same database. Follow the structure: `"infores:{DB NAME}"`.

- **`agent_type`** `string` — Hardcoded as `"biolink:automated_agent"` or `"biolink:manual_agent"` depending on curation strategy. Does not change for the same databases, may change for different databases.

- **`publication.doi`** `string` — SRA runs have an associated publication DOI under DOI column. Add the DOI if present. If not, can be omitted.

- **`publication.category`** `string` — Hardcoded as `"biolink:Publication"`. Does not change.

- **`anatomical_entity.id`** `string` — Flagged for entity resolution; refer to #.

- **`anatomical_entity.original_name`** `string` — Refers to the body site for the sample. Present in the metadata CSV file. If not present, raise an issue to the user and **omit the entire `anatomical_entity` block**. Remains the same across SRA Runs from the same BioSample.

- **`anatomical_entity.category`** `string` — Hardcoded as `"biolink:AnatomicalEntity"`. Remains the same across databases.

#### `object` fields

- **`id`** `string` — Sample value given (e.g. `taxid:2051`). Refer to the entity resolution tool to resolve the ID. **MUST be resolved for all objects.**

- **`taxid`** `integer` — Use the resolved integer value. **MUST be resolved for all objects.**

- **`name`** `string` — Get the species name from the abundance level file.

- **`original_name`** `string` — Raw species name as it appears in the abundance level file, before any resolution or normalization.

- **`parent_taxid`** `integer` — Use the BioThings CLI to resolve; refer to file #.

- **`lineage`** `list[integer]` — Use the BioThings CLI to resolve; refer to file #.

- **`rank`** `string` — Use Biothings CLI for rank, refer to file #

- **`category`** `string` — Hardcoded as `"biolink:OrganismTaxon"`. Remains the same across databases.

#### `subject` fields

- **`BioSample ID`** `string` — Get from the metadata CSV file.

- **`age`** `number | string`, **`gender`** `string`, **`height`** `string`, **`weight`** `number`, **`BMI`** `number`, **`ethnicity`** `string`, **`country`** `string`, **`continent`** `string`, **`smoke_status`** `string`, **`drinking_status`** `string`, **`diet_type`** `string` — Extract from the metadata CSV file. **If any one of the core fields {`age`, `gender`, `BMI`, `ethnicity`/`country`} is missing, skip the entire node — discard the `subject` and its associated `association` record entirely.** A field is considered missing if its value is `NaN`, an empty string `""`, or the literal string `"nan"` (case-insensitive). For non-core fields, apply the same rule: if the value is invalid or empty, omit the field entirely — do **not** use `null`.

- **`category`** `string` — Hardcoded as `"MaterialSample"`. Does not change.

### JSON Structure

```json
{
  "_id": "SAMN00000000_has_taxon_taxid:2051",
  "association": {
    "category": "MaterialSampletoOrganismTaxonAssociation",
    "predicate": "has_taxon",
    "BioProject": "",
    "SRA Run ID": "",
    "project_name": "",
    "relative_abundance": xxx,
    "absolute_abundance": xxx,
    "instrument": "",
    "primary_knowledge_source": [
      "infores:PRIMEDB"
    ],
    "aggregator_knowledge_source": null,
    "agent_type": "biolink:automated_agent",
    "publication": {
      "doi": "doi:10.2337/db12-0526",
      "category": "biolink:Publication"
    },
    "anatomical_entity": {
      "id": "UBERON:xxx",
      "original_name": "digestive system/gut",
      "category": "biolink:AnatomicalEntity"
    }
  },
  "object": {
    "id": "taxid:2051",
    "taxid": 2051,
    "name": "mobiluncus curtisii",
    "parent_taxid": 2050,
    "lineage": [
      2051,
      2050,
      2049,
      2037,
      1760,
      201174,
      1783272,
      2,
      131567,
      1
    ],
    "rank": "species",
    "category": "biolink:OrganismTaxon",
    "original_name": "mobiluncus curtisii"
  },
  "subject": {
    "BioSample ID": "",
    "age": "",
    "gender": "",
    "height": "",
    "weight": "",
    "BMI": "",
    "ethnicity": "",
    "country": "",
    "continent": "",
    "smoke_status": "",
    "drinking_status": "",
    "diet_type": "",
    "category": "MaterialSample"
  }
}
```

---

## Sample → Phenotype Association

> **Use this structure only for sample-to-phenotype associations.** Each BioSample has exactly one phenotype node — do not create multiple phenotype records per sample.

### Field Rules

#### `_id`

- **`_id`** `string` — Unique identifier for the record. Constructed by concatenating the BioSample ID, predicate, and resolved phenotype/disease CURIE ID, separated by underscores: `{BioSample ID}_has_phenotype_{phenotype id}`. Both components must be resolved before construction — do not construct `_id` until `subject.BioSample ID` and `object.id` are confirmed. Since each BioSample has exactly one phenotype node, this is unique per BioSample. **Always present; never omit.**

#### `association` fields

- **`category`** `string` — Hardcoded as `"biolink:MaterialSampleToDiseaseOrPhenotypicFeatureAssociation"`.
- **`predicate`** `string` — Hardcoded as `"biolink:has_phenotype"`.
- **`BioProject`**, **`project_name`**, **`primary_knowledge_source`**, **`agent_type`**, **`publication`** — Same rules as the sample→taxon association above.
- **`SRA Run ID`**, **`relative_abundance`**, **`absolute_abundance`**, **`instrument`**, **`anatomical_entity`** — **Not present** in this association type.

#### `object` fields

- **`id`** `string` — CURIE ID for the disease/phenotype (e.g. `MONDO:0005015`). Refer to the entity resolution tool to resolve. **MUST be resolved.**
- **`original_name`** `string` — Human-readable disease or phenotype name from the metadata CSV.
- **`category`** `string` — Hardcoded as `"biolink:Disease"` (or `"biolink:PhenotypicFeature"` as appropriate).

#### `subject` fields

Same rules as the sample→taxon association. **If any one of the core fields {`age`, `gender`, `BMI`, `ethnicity`/`country`} is missing, skip the entire node and discard the association record.** A field is considered missing if its value is `NaN`, an empty string `""`, or the literal string `"nan"` (case-insensitive). For non-core fields, omit if invalid or empty — do **not** use `null`.

### JSON Structure

```json
{
  "_id": "SAMN00000000_has_phenotype_MONDO:0005015",
  "association": {
    "category": "biolink:MaterialSampleToDiseaseOrPhenotypicFeatureAssociation",
    "predicate": "biolink:has_phenotype",
    "BioProject": "",
    "project_name": "",
    "primary_knowledge_source": [
      "infores:PRIMEDB"
    ],
    "aggregator_knowledge_source": null,
    "agent_type": "biolink:automated_agent",
    "publication": {
      "doi": "doi:10.2337/db12-0526",
      "category": "biolink:Publication"
    }
  },
  "object": {
    "id": "CURIE ID",
    "original_name": "type 1 diabetes",
    "category": "biolink:Disease"
  },
  "subject": {
    "BioSample ID": "",
    "age": "",
    "gender": "",
    "height": "",
    "weight": "",
    "BMI": "",
    "ethnicity": "",
    "country": "",
    "continent": "",
    "smoke_status": "",
    "drinking_status": "",
    "diet_type": "",
    "category": "MaterialSample"
  }
}
```
