import os
import json
import requests
from biothings.hub.dataload.dumper import HTTPDumper

_API_BASE = "https://primedb.sjtu.edu.cn/api/v1"
_METADATA_BATCH_SIZE = 200
_METADATA_FILENAME = "sample_metadata.json"


class PRIMEDumper(HTTPDumper):
    """
    Downloads PRIME data in two phases:
      1. The 4 abundance cache CSVs are declared in manifest.data_url and
         downloaded automatically by the base HTTPDumper.
      2. After the CSVs land, this dumper fetches all sample metadata from
         the PRIME REST API and writes sample_metadata.json to the same folder.
    """

    SRC_NAME = "prime"
    SRC_ROOT_FOLDER = os.path.join(os.environ.get("DATA_ARCHIVE_ROOT", ".biothings_hub/archive"), SRC_NAME)

    def create_todump_list(self, force=False):
        # Let the parent class handle the manifest data_url CSV downloads
        super().create_todump_list(force=force)

    def post_dump(self, *args, **kwargs):
        """Called by the hub after all manifest URLs have been downloaded."""
        self._fetch_sample_metadata()

    def _fetch_sample_metadata(self):
        self.logger.info("Fetching sample list from PRIME API...")
        resp = requests.get(f"{_API_BASE}/samples/list", timeout=60)
        resp.raise_for_status()
        payload = resp.json()
        # The endpoint returns either {"data": [...]} or {"runs": [...]}
        run_ids = payload.get("data") or payload.get("runs") or []
        if not run_ids:
            raise RuntimeError("PRIME /samples/list returned empty run list")

        self.logger.info(f"Fetching metadata for {len(run_ids)} samples in batches of {_METADATA_BATCH_SIZE}...")
        all_metadata = []
        for i in range(0, len(run_ids), _METADATA_BATCH_SIZE):
            batch = run_ids[i: i + _METADATA_BATCH_SIZE]
            try:
                r = requests.post(
                    f"{_API_BASE}/metadatas/sample",
                    json={"runs": batch},
                    timeout=120,
                )
                r.raise_for_status()
                result = r.json()
                if result.get("success") and result.get("data"):
                    all_metadata.extend(result["data"])
            except Exception as e:
                self.logger.warning(f"Metadata batch {i}–{i+len(batch)} failed: {e}")
            if i % 10000 == 0 and i > 0:
                self.logger.info(f"  ...fetched metadata for {i} samples so far")

        # Write to the archive data folder alongside the CSVs
        out_path = os.path.join(self.new_data_folder, _METADATA_FILENAME)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(all_metadata, fh)
        self.logger.info(f"Wrote {len(all_metadata)} metadata records to {out_path}")
