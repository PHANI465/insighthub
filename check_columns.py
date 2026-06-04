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

tables = ["DimCustomer", "DimProduct", "DimEmployee", 
          "DimDate", "FactSales", "FactSupportTickets", 
          "FactCampaignPerformance"]

for table in tables:
    print(f"\n--- {table} columns ---")
    cursor.execute(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        f"WHERE TABLE_NAME = '{table}' ORDER BY ORDINAL_POSITION"
    )
    for row in cursor.fetchall():
        print(f"  {row[0]}")

conn.close()
print("\nDone.")