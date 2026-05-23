# Database Troubleshooting Runbook

## 1. Connection Pool Exhaustion

### Symptoms
- Application logs show `ERR-DB-POOL-001` or "Cannot acquire connection"
- Connection wait times exceed 3000ms
- Pool utilization consistently above 90%
- Cascading 503 errors in dependent services

### Diagnosis Steps
1. Check current pool stats:
   ```
   SELECT count(*) FROM pg_stat_activity WHERE state = 'active';
   SELECT count(*) FROM pg_stat_activity WHERE state = 'idle';
   SELECT count(*) FROM pg_stat_activity WHERE wait_event IS NOT NULL;
   ```
2. Identify long-running queries:
   ```
   SELECT pid, now() - pg_stat_activity.query_start AS duration, query
   FROM pg_stat_activity
   WHERE state != 'idle'
   ORDER BY duration DESC LIMIT 10;
   ```
3. Check for connection leaks — look for idle connections older than 5 minutes:
   ```
   SELECT pid, usename, client_addr, state, query_start
   FROM pg_stat_activity
   WHERE state = 'idle' AND query_start < now() - interval '5 minutes';
   ```

### Immediate Fix
1. Kill idle connections older than 5 minutes:
   ```
   SELECT pg_terminate_backend(pid)
   FROM pg_stat_activity
   WHERE state = 'idle' AND query_start < now() - interval '5 minutes';
   ```
2. Temporarily increase pool max_size:
   ```
   ALTER SYSTEM SET max_connections = 200;  -- default is usually 100
   SELECT pg_reload_conf();
   ```
3. Restart the affected application pods to reset connection state:
   ```
   kubectl rollout restart deployment/auth-service -n production
   ```

### Long-Term Fix
- Implement PgBouncer for connection pooling (transaction mode recommended)
- Add connection leak detection in application code (finally blocks, context managers)
- Set pool configuration:
  - `max_pool_size=50` (per pod)
  - `min_pool_size=5`
  - `max_idle_time=300` (seconds)
  - `connection_timeout=5000` (ms)
- Add connection pool metrics to Prometheus/Grafana dashboards
- Set alerts for pool utilization > 80%

## 2. High Latency Queries

### Symptoms
- Query response times exceeding SLA thresholds
- `SLOW-QUERY-001` alerts in monitoring
- High CPU or I/O wait on database server

### Diagnosis Steps
1. Enable slow query logging:
   ```
   SET log_min_duration_statement = 1000;  -- log queries > 1s
   ```
2. Use EXPLAIN ANALYZE to identify bottlenecks:
   ```
   EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) SELECT ...;
   ```
3. Check for missing indexes:
   ```
   SELECT relname, seq_scan, idx_scan
   FROM pg_stat_user_tables
   WHERE seq_scan > 1000 AND idx_scan < 100
   ORDER BY seq_scan DESC;
   ```

### Fix
- Add indexes for frequently queried columns
- Rewrite queries to avoid full table scans
- Consider query caching for read-heavy workloads
- Review and optimize ORM-generated queries

## 3. Replication Lag

### Symptoms
- Read replicas returning stale data
- Replication lag exceeding 30 seconds

### Monitoring
```
SELECT client_addr, state, sent_lsn, write_lsn, replay_lsn,
       (sent_lsn - replay_lsn) AS replication_lag
FROM pg_stat_replication;
```

### Failover Procedure
1. Promote standby: `pg_ctl promote -D /var/lib/postgresql/data`
2. Update application connection strings
3. Notify on-call DBA team

## 4. Disk Space Issues

### Monitoring
```
SELECT pg_size_pretty(pg_database_size('production'));
SELECT tablename, pg_size_pretty(pg_total_relation_size(tablename::text))
FROM pg_tables WHERE schemaname = 'public' ORDER BY pg_total_relation_size(tablename::text) DESC LIMIT 10;
```

### Cleanup
- VACUUM FULL on bloated tables
- Archive old data to cold storage
- Truncate log/audit tables older than retention period