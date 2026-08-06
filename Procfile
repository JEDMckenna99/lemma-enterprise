release: python migrations/run_migration.py
web: bash bin/web
billing_worker: python -m billing.billing_outbox_worker
retention_worker: python -m retention.retention_worker
