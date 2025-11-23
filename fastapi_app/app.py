from fastapi import FastAPI, HTTPException, Query
import json
import logging
from typing import List, Dict, Optional

app = FastAPI()
logger = logging.getLogger("uvicorn.error")

SAMPLE_DATA: List[Dict] = [
    {"order_id":"O-1001","customer_id":"C-101","product_id":"P-201","product_name":"Wireless Bluetooth Headphones","category":"Electronics","qty":1,"price":299.0,"status":"DELIVERED","created_at":"2025-11-15T10:00:00","updated_at":"2025-11-15T12:00:00"},
    {"order_id":"O-1002","customer_id":"C-102","product_id":"P-202","product_name":"Smart Fitness Watch","category":"Electronics","qty":2,"price":199.0,"status":"SHIPPED","created_at":"2025-11-16T11:30:00","updated_at":"2025-11-16T13:00:00"},
    {"order_id":"O-1003","customer_id":"C-103","product_id":"P-203","product_name":"Gaming Keyboard","category":"Electronics","qty":1,"price":499.0,"status":"CANCELLED","created_at":"2025-11-17T09:20:00","updated_at":"2025-11-17T09:25:00"}
]

def load_orders(path: str = "/app/data/orders.json") -> List[Dict]:
    """
    Load JSON array from path using utf-8-sig (consumes BOM).
    Raises exception if not parseable or not a list.
    """
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("orders.json must be a JSON array")
    return data

@app.get("/health")
def health():
    from datetime import datetime
    return {"status": "ok", "time": datetime.utcnow().isoformat()}

@app.get("/extract/full")
def extract_full():
    try:
        data = load_orders()
        return {"status": "ok", "mode": "full", "count": len(data), "data": data}
    except Exception as e:
        logger.exception("Failed to load orders.json, falling back to SAMPLE_DATA: %s", e)
        warning = f"Failed to read /app/data/orders.json — using in-memory sample. Error: {str(e)}"
        return {"status": "ok", "mode": "full", "count": len(SAMPLE_DATA), "data": SAMPLE_DATA, "warning": warning}

@app.get("/extract/incremental")
def extract_incremental(since: Optional[str] = Query(None, description="ISO timestamp, e.g. 2025-11-22T00:00:00Z")):
    """
    Simple incremental: compares ISO-like strings (works for YYYY-MM-DDTHH:MM:SS).
    If parsing/reading fails, falls back to sample too.
    """
    try:
        data = load_orders()
    except Exception as e:
        logger.exception("Failed to load orders.json for incremental: %s", e)
        data = SAMPLE_DATA
    if since:
        # naive ISO string compare (valid for ISO8601 without timezone or with same format)
        filtered = [r for r in data if "created_at" in r and r["created_at"] >= since]
    else:
        filtered = data
    return {"status": "ok", "mode": "incremental", "since": since, "count": len(filtered), "data": filtered}
