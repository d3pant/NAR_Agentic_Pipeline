# BioThings Taxon Resolution

Covers `object.parent_taxid`, `object.lineage`, and `object.rank` in the output JSON. These are looked up from a resolved integer taxid using the `biothings_client` Python library against the MyTaxon.info API — no local database required.

---

## Install

```bash
pip install biothings_client
```

---

## Single Taxon

```python
import biothings_client

t = biothings_client.get_client('taxon')
result = t.gettaxon(2051, fields='parent_taxid,lineage,rank')
# {'_id': '2051', 'lineage': [2051, 2050, ...], 'parent_taxid': 2050, 'rank': 'species'}
```

---

## Batch Taxon (Preferred in Parser)

```python
import biothings_client

t = biothings_client.get_client('taxon')
taxids = [2051, 853, 1263]   # list of plain integers — NOT "taxid:2051"
results = t.gettaxa(taxids, fields='parent_taxid,lineage,rank')

taxon_map = {}
for r in results:
    if r.get('notfound'):
        continue
    taxon_map[int(r['query'])] = {
        'parent_taxid': r.get('parent_taxid'),
        'lineage':      r.get('lineage', []),
        'rank':         r.get('rank'),
    }
```

**Key rules:**
- Input must be plain integers (or strings of integers) — `"taxid:2051"` prefix causes `notfound`
- Missing taxids return `{'query': '...', 'notfound': True}` — check before accessing fields
- `lineage` is always a list of integers ordered from self → root; already in the right shape for the output JSON

---

## Applying to the Output Document

```python
taxon_info = taxon_map.get(taxid, {})

doc['object']['parent_taxid'] = taxon_info.get('parent_taxid')   # int or omit if None
doc['object']['lineage']      = taxon_info.get('lineage', [])     # list[int]
doc['object']['rank']         = taxon_info.get('rank')            # str or omit if None
```

Always run `dict_sweep(doc, [None])` after assignment — this drops any fields where `parent_taxid` or `rank` came back `None`.

---

## Parser Pattern

Resolve all taxids in a single batch call before the document-building loop to avoid per-row API calls:

```python
import biothings_client
from biothings.utils.dataload import dict_sweep, unlist

def load_data(data_folder):
    # --- collect all unique taxids first ---
    rows = list(...)   # load your source rows
    unique_taxids = list({int(row['taxid']) for row in rows if row.get('taxid')})

    t = biothings_client.get_client('taxon')
    taxon_map = {}
    for r in t.gettaxa(unique_taxids, fields='parent_taxid,lineage,rank'):
        if not r.get('notfound'):
            taxon_map[int(r['query'])] = {
                'parent_taxid': r.get('parent_taxid'),
                'lineage':      r.get('lineage', []),
                'rank':         r.get('rank'),
            }

    # --- build documents ---
    for row in rows:
        taxid = int(row['taxid'])
        taxon_info = taxon_map.get(taxid, {})

        doc = {
            '_id': ...,
            'object': {
                'id':           f"taxid:{taxid}",
                'taxid':        taxid,
                'name':         row['species_name'],
                'original_name': row['raw_species_name'],
                'parent_taxid': taxon_info.get('parent_taxid'),
                'lineage':      taxon_info.get('lineage', []),
                'rank':         taxon_info.get('rank'),
                'category':     'biolink:OrganismTaxon',
            },
            ...
        }
        doc = dict_sweep(unlist(doc), [None])
        yield doc
```

---

## Not Found Handling

If a taxid has no hit in MyTaxon.info:
- `parent_taxid` and `rank` are omitted via `dict_sweep`
- `lineage` falls back to `[]` (empty list) — omit it too if empty by including `[]` in the sweep: `dict_sweep(doc, [None, []])`
- Do **not** raise or stop — log and continue

---

## Field → API mapping

| Output JSON field      | API field       | Type         |
|------------------------|-----------------|--------------|
| `object.parent_taxid`  | `parent_taxid`  | `int`        |
| `object.lineage`       | `lineage`       | `list[int]`  |
| `object.rank`          | `rank`          | `str`        |
