# spark/jobs/transform.py
# Run: python spark/jobs/transform.py

import os
import json
import boto3
from pathlib import Path
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, to_timestamp, expr, date_format

# ===== CONFIG =====
MINIO_ENDPOINT = "http://localhost:9000"
MINIO_ACCESS = "minioadmin"
MINIO_SECRET = "minioadmin"
RAW_BUCKET = "raw"
RAW_PREFIX = "full/"
LOCAL_RAW_DIR = "tmp_raw"
PROCESSED_DIR = "storage/processed"
GOLDEN_DIR = "storage/golden"

# ===== ensure local directories =====
os.makedirs(LOCAL_RAW_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)
os.makedirs(GOLDEN_DIR, exist_ok=True)

# ===== MinIO (S3) client =====
s3 = boto3.client(
    "s3",
    endpoint_url=MINIO_ENDPOINT,
    aws_access_key_id=MINIO_ACCESS,
    aws_secret_access_key=MINIO_SECRET,
)

def list_raw_objects():
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=RAW_BUCKET, Prefix=RAW_PREFIX):
        for obj in page.get("Contents", []):
            yield obj["Key"]

def download_objects(keys):
    local_paths = []
    for k in keys:
        base = os.path.basename(k).replace("/", "_")
        local_path = os.path.join(LOCAL_RAW_DIR, base)
        print("Downloading", k, "->", local_path)
        obj = s3.get_object(Bucket=RAW_BUCKET, Key=k)
        data = obj["Body"].read()
        with open(local_path, "wb") as f:
            f.write(data)
        local_paths.append(local_path)
    return local_paths

# ===== download raw files =====
raw_keys = list(list_raw_objects())
if not raw_keys:
    print("No raw objects in raw/full/. Exiting.")
    raise SystemExit(1)

local_files = download_objects(raw_keys)

# ===== start Spark session =====
spark = SparkSession.builder \
    .appName("ecom-transform") \
    .config("spark.sql.session.timeZone", "UTC") \
    .getOrCreate()

# ===== convert raw JSON files → NDJSON =====
ndjson_temp = os.path.join(LOCAL_RAW_DIR, "ndjson_combined.json")

with open(ndjson_temp, "w", encoding="utf-8") as fh:
    for fp in local_files:
        with open(fp, "r", encoding="utf-8") as rf:
            j = json.load(rf)
            for row in j.get("data", []):
                fh.write(json.dumps(row) + "\n")

print("Created NDJSON:", ndjson_temp)

# ===== use Path.as_uri() — Windows-safe =====
ndjson_uri = Path(ndjson_temp).resolve().as_uri()
df = spark.read.json(ndjson_uri)

# ===== cleaning & enrichment =====
df = df.withColumn("qty", col("qty").cast("int")) \
       .withColumn("price", col("price").cast("double")) \
       .withColumn("total_price", col("qty") * col("price")) \
       .withColumn("order_ts", to_timestamp(col("created_at"))) \
       .withColumn("order_date", date_format(col("order_ts"), "yyyy-MM-dd"))

# =======================
#  SILVER (processed)
# =======================
processed_uri = Path(PROCESSED_DIR).resolve().as_uri()
df.repartition(1).write.mode("overwrite").partitionBy("order_date").parquet(processed_uri)
print("Wrote processed parquet to", processed_uri)

# =======================
#  GOLDEN LAYER
# =======================

# FACT TABLE
fact = df.select(
    "order_id", "customer_id", "product_id",
    "qty", "total_price", "status",
    "created_at", "order_ts"
).dropDuplicates(["order_id"])

fact_uri = Path(GOLDEN_DIR, "fact_orders.parquet").resolve().as_uri()
fact.repartition(1).write.mode("overwrite").parquet(fact_uri)
print("Wrote fact_orders to", fact_uri)

# DIM CUSTOMERS
dim_customers = df.select("customer_id").dropDuplicates()
dim_customers_uri = Path(GOLDEN_DIR, "dim_customers.parquet").resolve().as_uri()
dim_customers.repartition(1).write.mode("overwrite").parquet(dim_customers_uri)
print("Wrote dim_customers to", dim_customers_uri)

# DIM PRODUCTS
dim_products = df.select("product_id").dropDuplicates()
dim_products_uri = Path(GOLDEN_DIR, "dim_products.parquet").resolve().as_uri()
dim_products.repartition(1).write.mode("overwrite").parquet(dim_products_uri)
print("Wrote dim_products to", dim_products_uri)

spark.stop()
print("Transform completed successfully!")
