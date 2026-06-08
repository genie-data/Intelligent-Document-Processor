from dagster import asset, define_asset_job, ScheduleDefinition, Definitions

# Import the receipt processing logic from main.py
import main

@asset
def process_receipts_asset():
    """
    Asset that triggers the processing of incoming PDF receipts.
    """
    main.process_all_receipts()

# Define a job that materializes the asset
process_receipts_job = define_asset_job(
    name="process_receipts_job", 
    selection="process_receipts_asset"
)

# Schedule to run at 8:00 AM and 6:00 PM every day
process_receipts_schedule = ScheduleDefinition(
    job=process_receipts_job,
    cron_schedule="0 8,18 * * *",
)

defs = Definitions(
    assets=[process_receipts_asset],
    schedules=[process_receipts_schedule],
)
