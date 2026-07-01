def get_release(self):
    import requests
    url = "https://primedb.sjtu.edu.cn/api/v1/stats"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        total = data.get("data", {}).get("basicStats", {}).get("totalSamples")
        if total:
            # Version = sample count + fetch date; stable until the database is updated
            from datetime import date
            return f"{total}samples_{date.today().strftime('%Y%m%d')}"
    except Exception:
        pass
    # Fallback: use current date
    from datetime import date
    return date.today().strftime("%Y%m%d")
