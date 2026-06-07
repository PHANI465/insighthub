"""
One-shot script: load FactCampaignPerformance from campaigns.csv in Azure Blob.
Reuses all existing ETL modules — does NOT touch FactSales or FactSupportTickets.

Run from project root:
  python load_campaigns_only.py
"""
import sys, os, time, logging

# Bootstrap path so ETL modules resolve
ETL_DIR = os.path.join(os.path.dirname(__file__), 'etl-pipelines', 'python-local')
sys.path.insert(0, ETL_DIR)
os.chdir(ETL_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

from db_connection import get_connection
from blob_reader import download_csv
from validators import validate_campaigns
from transformers import transform_campaigns, transform_fact_campaigns
from loaders import load_dim_campaign, load_fact_campaign_performance

def main():
    t0 = time.time()
    log.info("=== Loading FactCampaignPerformance (campaigns only) ===")

    with get_connection() as conn:
        # Step 1: Download + validate campaigns.csv from blob
        log.info("[1/3] Downloading campaigns.csv from Azure Blob …")
        raw = download_csv("campaigns")
        log.info("  Downloaded %d rows", len(raw))

        raw, error_count = validate_campaigns(raw)
        log.info("  After validation: %d valid, %d errors", len(raw), error_count)

        # Step 2: Merge DimCampaign to get/refresh the campaign key map
        log.info("[2/3] Merging DimCampaign …")
        dim_df = transform_campaigns(raw)
        campaign_key_map = load_dim_campaign(conn, dim_df)
        log.info("  campaign_key_map has %d entries", len(campaign_key_map))

        # Step 3: Transform + load FactCampaignPerformance (full reload)
        log.info("[3/3] Loading FactCampaignPerformance (TRUNCATE + INSERT) …")

        # Truncate first for a clean full reload
        cursor = conn.cursor()
        cursor.execute("TRUNCATE TABLE dbo.FactCampaignPerformance")
        conn.commit()
        cursor.close()
        log.info("  Truncated FactCampaignPerformance")

        fact_df = transform_fact_campaigns(raw, campaign_key_map)
        inserted = load_fact_campaign_performance(conn, fact_df)
        log.info("  Inserted %d rows into FactCampaignPerformance", inserted)

        # Verify
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM dbo.FactCampaignPerformance")
        final_count = cur.fetchone()[0]
        cur.execute("SELECT MIN(ROI_Pct), MAX(ROI_Pct), AVG(ROI_Pct) FROM dbo.FactCampaignPerformance")
        roi_row = cur.fetchone()
        cur.close()

        log.info("  Final count: %d rows", final_count)
        log.info("  ROI_Pct range: min=%.1f  max=%.1f  avg=%.1f",
                 roi_row[0] or 0, roi_row[1] or 0, roi_row[2] or 0)

    elapsed = time.time() - t0
    log.info("=== Done in %.1f seconds ===", elapsed)

if __name__ == "__main__":
    main()
