# fastapi_app/app.py
from fastapi import FastAPI, Query, HTTPException
from datetime import datetime, timedelta
import json, os
from typing import List, Dict

app = FastAPI(title="Ecom Mock API")

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "orders.json")

def load_data() -> List[Dict]:
    if not os.path.exists(DATA_FILE):
        raise HTTPException(status_code=500, detail=f"Data file missing: {DATA_FILE}")
    with open(DATA_FILE) as f:
        return json.load(f)

@app.get("/extract/full")
def full_extract():
    """
    Return all order records (simulates a full extract)
    """
    data = load_data()
    return {"status":"ok","mode":"full","count": len(data), "data": data}

@app.get("/extract/incr")
def incr_extract(since_ts: str = Query(..., description="ISO timestamp, e.g. 2025-11-20T00:00:00")):
    """
    Return orders updated after `since_ts` (simulates incremental extract)
    """
    try:
        since = datetime.fromisoformat(since_ts)
    except Exception:
        raise HTTPException(status_code=400, detail="since_ts must be ISO format: YYYY-MM-DDTHH:MM:SS")
    rows = [r for r in load_data() if datetime.fromisoformat(r["updated_at"]) > since]
    return {"status":"ok","mode":"incr","since": since_ts, "count": len(rows), "data": rows}

@app.get("/health")
def health():
    return {"status":"ok","time": datetime.utcnow().isoformat()}
