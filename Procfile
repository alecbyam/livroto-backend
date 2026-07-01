web: uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2
worker: celery -A app.tasks.celery_app worker --loglevel=info --concurrency=2 -Q default,payments,notifications
