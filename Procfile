release: python migrations/run_migration.py
web: gunicorn app:app --worker-class gevent --workers ${WEB_CONCURRENCY:-2} --worker-connections ${GUNICORN_WORKER_CONNECTIONS:-1000} --timeout ${GUNICORN_TIMEOUT:-120} --graceful-timeout ${GUNICORN_GRACEFUL_TIMEOUT:-30} --keep-alive ${GUNICORN_KEEPALIVE:-5}
billing_worker: python -m billing.billing_outbox_worker
retention_worker: python -m retention.retention_worker
