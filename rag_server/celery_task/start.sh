cd /Users/xuzhiguo/workspace/python/rag_server1
celery -A celery_task.celery_app worker --loglevel=info --concurrency=4