
# How to Test — E-Commerce Data Lakehouse (MindGraph)

This short guide shows the exact steps an evaluator (or you) can use to validate the project locally.
It assumes Docker Desktop is installed and running on the machine and you are at the project root
`mindgraph-lakehouse-project/` where `docker-compose.yml` is located.

> Reference: Technical Assessment brief (uploaded with the project). If you need to cross-check requirements, see the assessment PDF: `/mnt/data/Technical Assessment -MindGraph (2).pdf`

---

## 1 — Quick checklist before starting
- Docker Desktop (or Docker daemon) is running.
- You have at least 8 GB free disk and enough memory to run multiple containers (recommended 8–16 GB total for system).
- Open a terminal / PowerShell in the project root directory:
  ```
  C:\Users\<you>\... \mindgraph-lakehouse-project
  ```
- (Optional) Confirm `docker` and `docker compose` are available:
  ```bash
  docker --version
  docker compose version
  ```

---

## 2 — Start the entire stack
Run from project root (this builds and runs containers in background):
```bash
docker compose up --build -d
```

Check containers status:
```bash
docker compose ps
# or
docker ps --filter "name=mindgraph-lakehouse-project"
```

Expected containers (at least):
- `fastapi` (exposes port 8000)
- `minio` (exposes port 9000)
- optionally `airflow`, `spark` depending on your compose setup

If nothing appears, run in foreground to view errors:
```bash
docker compose up --build
# watch the logs and fix any build/runtime errors shown
```

---

## 3 — Validate FastAPI (basic smoke tests)

**Health endpoint** (should return JSON with status):
```bash
curl http://localhost:8000/health
# PowerShell alternative
Invoke-WebRequest -Uri http://localhost:8000/health | Select-Object -ExpandProperty Content
```

**OpenAPI docs** (browser):
```
http://localhost:8000/docs
```

**Full extraction** (should return JSON array / sample):
```bash
curl http://localhost:8000/extract/full
```

**Incremental extraction** (replace timestamp if needed):
```bash
curl "http://localhost:8000/extract/incremental?since=2025-11-22T00:00:00Z"
```

Expected: `full` returns a larger payload, `incremental` returns only recent records (subset).

If anything 404s, check FastAPI logs:
```bash
docker logs <fastapi_container_name> --tail 200
```

---

## 4 — Check MinIO (raw layer)

Open browser:
```
http://localhost:9000
```
Login (default unless changed):
- Access Key: `minioadmin`
- Secret Key: `minioadmin`

Look for a bucket (example: `mybucket` or named per project). Verify these directories are present:
```
raw/full/date=YYYY-MM-DD/part-000.json
raw/increment/date=YYYY-MM-DD/part-000.json
```
Open a sample file to inspect JSON structure. You can also use `mc` (MinIO client) if installed:
```bash
mc alias set localminio http://localhost:9000 minioadmin minioadmin
mc ls localminio/mybucket/raw/
mc cat localminio/mybucket/raw/full/date=2025-11-23/part-000.json | jq '.[0]'
```

---

## 5 — Trigger Airflow DAG (if using Airflow)

Open Airflow UI (if included in compose):
```
http://localhost:8080
```

Locate DAG (likely `ecommerce_lakehouse_dag`), trigger a dag run (Full or Incremental).  
Watch logs for tasks and confirm that an extraction task invoked FastAPI and uploaded files to MinIO.

You can also trigger DAG from CLI (inside the Airflow container):
```bash
docker exec -it <airflow_scheduler_container> airflow dags list
docker exec -it <airflow_scheduler_container> airflow dags trigger ecommerce_lakehouse_dag --conf '{"mode":"full"}'
```

---

## 6 — Run Spark transformation manually (optional)

If you prefer to run Spark job manually (not via Airflow), run inside the spark container or locally if configured:
```bash
# if spark container is available
docker exec -it <spark_container> bash
python /opt/app/spark/jobs/transform.py   # adjust path to your repo path inside container
```

Or run locally (if you have PySpark configured):
```bash
python spark/jobs/transform.py
```

Expected: Spark reads raw JSON from MinIO and writes Iceberg tables into the configured catalog location (or writes Parquet in `storage/transformed/` depending on setup).

Check logs for errors (missing credentials, S3 path, or permission issues).

---

## 7 — Validate Iceberg / Transformed layer

Using Spark SQL or a small PySpark script, run quick checks:
```sql
-- example spark-sql (from container or spark-sql CLI)
SHOW TABLES IN lakehouse_db;
SELECT COUNT(*) FROM lakehouse_db.orders_transformed;
DESCRIBE lakehouse_db.orders_transformed;
```
Also check that partition folders exist if partitioned by `order_date`.

---

## 8 — Validate Golden Layer (facts & dims)

Run sample analytical query to ensure joins and aggregations work:
```sql
SELECT d.region, SUM(f.total_amount) as revenue
FROM lakehouse_db.fact_sales f
JOIN lakehouse_db.dim_customers d ON f.customer_id = d.customer_id
GROUP BY d.region
ORDER BY revenue DESC
LIMIT 10;
```

If results look sensible (non-zero, sensible ranges), golden layer is correct.

---

## 9 — Data Quality Checks (basic)

A few quick checks you can run as smoke tests:
- No duplicate `order_id` in fact table:
```sql
SELECT order_id, COUNT(*) FROM lakehouse_db.fact_sales GROUP BY order_id HAVING COUNT(*) > 1;
```
- No negative amounts:
```sql
SELECT COUNT(*) FROM lakehouse_db.fact_sales WHERE total_amount <= 0;
```
- Referential integrity (customer ids in fact exist in dim):
```sql
SELECT COUNT(*) FROM lakehouse_db.fact_sales f LEFT JOIN lakehouse_db.dim_customers d ON f.customer_id=d.customer_id WHERE d.customer_id IS NULL;
```

If any of these return non-zero, inspect the upstream transform logic in `spark/jobs/transform.py`.

---

## 10 — Cleanup and repo checks

Before submission, confirm repository cleanliness (no large files or venv):
```bash
git status
# ensure .venv/ and tmp folders are not tracked
```

If you want to produce a ZIP for submission (tracked files only):
```bash
git archive --format zip --output ../mindgraph_submission.zip HEAD
```

---

## 11 — Troubleshooting common issues

- **Docker Compose shows no containers**: ensure Docker Desktop is running. Run `docker compose up --build` and check the output for errors.
- **FastAPI build failing due to `.venv`**: ensure `.dockerignore` contains `.venv` (we already added that).
- **MinIO permission issues on Windows**: check volume mapping and ensure host path exists and Docker has permission to access it.
- **File locked on Windows during `git clean`**: stop containers, close editors, or reboot, then rerun clean.

---

## 12 — Notes for the evaluator

- The assignment spec is included with the repo. See the uploaded PDF in the project workspace for the full brief: `/mnt/data/Technical Assessment -MindGraph (2).pdf`.
- The easiest validation path is:
  1. `docker compose up --build -d`
  2. `curl http://localhost:8000/health`
  3. `curl http://localhost:8000/extract/full`
  4. Check MinIO buckets for `raw/` files
  5. Trigger DAG manually in Airflow (if present) to run full → run Spark transform → verify Iceberg/golden outputs

