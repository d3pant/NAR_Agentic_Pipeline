def get_release(self):
    import requests
    resp = requests.get(
        "https://zenodo.org/api/records/15711237",
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    # metadata.publication_date is YYYY-MM-DD
    pub_date = data.get("metadata", {}).get("publication_date", "")
    if pub_date:
        return pub_date.replace("-", "")
    # fallback: updated field is ISO 8601 — take the date part
    updated = data.get("updated", "")
    if updated:
        return updated[:10].replace("-", "")
    return None
