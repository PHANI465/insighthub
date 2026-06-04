import pyodbc

conn_str = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=insighthub-sql-phani01.database.windows.net,1433;"
    "DATABASE=insighthub-db;"
    "UID=insighthubadmin;"
    "PWD={XQesxs@nr5GWP9R};"
    "Encrypt=yes;"
    "TrustServerCertificate=yes;"
    "Connection Timeout=60;"
)

conn = pyodbc.connect(conn_str)
cursor = conn.cursor()

# Read the views file
with open(r"E:\PHANI\Projects\insighthub\database\schema\05_views.sql", "r", encoding="utf-8") as f:
    content = f.read()

# Split on GO and run each batch separately
batches = [b.strip() for b in content.split("\nGO") if b.strip()]

for i, batch in enumerate(batches, 1):
    if not batch or batch.startswith("--"):
        continue
    try:
        cursor.execute(batch)
        conn.commit()
        print(f"✅ Batch {i} succeeded")
    except Exception as e:
        print(f"❌ Batch {i} failed: {e}")
        print(f"   SQL preview: {batch[:200]}")

conn.close()
print("Done.")