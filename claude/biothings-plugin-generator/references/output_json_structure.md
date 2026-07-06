# Output JSON Structure

Maps sample demographics (`subject`) to a microbial taxon (`object`) or phenotype via an association record.

> **VERY IMPORTANT:** For each sample, one record using the structure below must be appended to a single output JSON — one entry per sample→taxon mapping, all collected in the same file.

---

## Sample → Taxon Association

### Field Rules

#### `association` fields

- **`BioProject`** — BioProject ID from the metadata CSV file. May be absent in some cases; if so, follow instructions #.

- **`SRA Run ID`** — SRA Run ID given for each BioSample. ALWAYS present in the CSV; raise an issue to the user if not present.

  > **Note:** For a given sample, there may be multiple SRA Run IDs. In this case, create separate association records mapping the same sample to different microbiome abundance tables based on the SRA Run ID. The downstream `relative_abundance`, `absolute_abundance`, and `instrument` values may differ between SRA Runs and will be indicated accordingly.

- **`project_name`** — Project name given in the CSV; remains the same across SRA Runs from the same BioProject. If absent, omit this field. **Do NOT use `null`/`NaN` — simply omit.**

- **`relative_abundance`** — Map the SRA Run from metadata to the taxon. Relative abundance data may be present either in the same metadata CSV or in a separate CSV file. If not present, raise an issue to the user and continue. **Omit the field if not present.** Note that there are different relative abundances for different SRA Runs from the same BioSample.

- **`absolute_abundance`** — Map the SRA Run from metadata to the taxon. Absolute abundance data may be present either in the same metadata CSV or in a separate CSV file. **If not present, raise an issue to the user and STOP working.** Note that there are different absolute abundances for different SRA Runs from the same BioSample.

- **`instrument`** — Present in the metadata CSV file. If not present, notify the user and continue by omitting the field. May be different or the same across SRA Runs from the same BioSample.

- **`primary_knowledge_source`** — Hardcoded for the database. Remains the same across SRA Runs for the same database. Follow the structure: `"infores:{DB NAME}"`.

- **`agent_type`** — Hardcoded as `"biolink:automated_agent"`. Does not change under any circumstances.

- **`publication.doi`** — Use the exact DOI link used during relevancy analysis. MUST be a DOI link. Remains the same across SRA Runs for the same database.

- **`publication.category`** — Hardcoded as `"biolink:Publication"`. Does not change.

- **`anatomical_entity.id`** — Flagged for entity resolution; refer to #.

- **`anatomical_entity.original_name`** — Refers to the body site for the sample. Present in the metadata CSV file. If not present, raise an issue to the user and **omit the entire `anatomical_entity` block**. Remains the same across SRA Runs from the same BioSample.

- **`anatomical_entity.category`** — Hardcoded as `"biolink:AnatomicalEntity"`. Remains the same across databases.

#### `object` fields

- **`id`** — Sample value given (e.g. `taxid:2051`). Refer to the entity resolution tool to resolve the ID. **MUST be resolved for all objects.**

- **`taxid`** — Use the resolved integer value. **MUST be resolved for all objects.**

- **`name`** — Get the species name from the abundance level file.

- **`parent_taxid`** — Use the BioThings CLI to resolve; refer to file #.

- **`lineage`** — Use the BioThings CLI to resolve; refer to file #.

- **`rank`** — Hardcoded as `"species"`. Remains the same across databases.

- **`category`** — Hardcoded as `"biolink:OrganismTaxon"`. Remains the same across databases.

#### `subject` fields

- **`BioSample ID`** — Get from the metadata CSV file.

- **`age`, `gender`, `height`, `weight`, `BMI`, `ethnicity`, `country`, `continent`, `smoke_status`, `drinking_status`, `diet_type`** — Extract from the metadata CSV file. **If any one of the core fields {`age`, `gender`, `BMI`, `ethnicity`/`country`} is missing, skip the entire node — discard the `subject` and its associated `association` record entirely.**

- **`category`** — Hardcoded as `"MaterialSample"`. Does not change.

### JSON Structure

```json
{
  "_id": "",
  "association": {
    "category": "biolink:AnatomicalEntitytoAnatomicalEntityAssociation",
    "predicate": "biolink:has_member",
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

#### `association` fields

- **`category`** — Hardcoded as `"biolink:MaterialSampleToDiseaseOrPhenotypicFeatureAssociation"`.
- **`predicate`** — Hardcoded as `"biolink:has_phenotype"`.
- **`BioProject`**, **`project_name`**, **`primary_knowledge_source`**, **`agent_type`**, **`publication`** — Same rules as the sample→taxon association above.
- **`SRA Run ID`**, **`relative_abundance`**, **`absolute_abundance`**, **`instrument`**, **`anatomical_entity`** — **Not present** in this association type.

#### `object` fields

- **`id`** — CURIE ID for the disease/phenotype (e.g. `MONDO:0005015`). Refer to the entity resolution tool to resolve. **MUST be resolved.**
- **`original_name`** — Human-readable disease or phenotype name from the metadata CSV.
- **`category`** — Hardcoded as `"biolink:Disease"` (or `"biolink:PhenotypicFeature"` as appropriate).

#### `subject` fields

Same rules as the sample→taxon association. **If any one of the core fields {`age`, `gender`, `BMI`, `ethnicity`/`country`} is missing, skip the entire node and discard the association record.**

### JSON Structure

```json
{
  "_id": "",
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
