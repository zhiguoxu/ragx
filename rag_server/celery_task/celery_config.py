# docker run -d -p 6379:6379 redis

broker_url = 'redis://localhost:6379/0'
result_backend = 'redis://localhost:6379/1'
task_serializer = 'json'
result_serializer = 'json'
accept_content = ['json']
timezone = 'UTC'
enable_utc = True

# 重试配置
task_acks_late = True
# task_reject_on_worker_lost = True # 当 celery 任务意外停止，可以重启之前被中断的任务，但是实际测试不起作用
task_default_retry_delay = 10  # 重试间隔 10 秒
task_default_max_retries = 3  # 最大重试次数

# 解决 mac celery sentence transformers 的进程冲突问题
# https://chatgpt.com/share/67078ffc-b7a0-8012-9b2f-9f808fe8e039
worker_pool = 'threads'  # 使用线程池
worker_concurrency = 10  # 设置线程数量

broker_connection_retry_on_startup = True

task_time_limit = 3600  # 设置任务的最大执行时间为 300 秒
result_expires = 3600  # 结果过期时间为 1 小时

worker_prefetch_multiplier = 1
# task_track_started = True  # 为 celery 崩溃恢复正在执行的任务，但是不起作用
