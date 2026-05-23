# Memory Leak Diagnosis Runbook

## Identifying Memory Leaks

### Key Metrics to Watch
- **Heap/RSS Growth:** Steady increase over time without corresponding load increase
- **GC Frequency:** Increasing GC cycles per minute
- **GC Pause Duration:** Stop-the-world pauses exceeding 500ms
- **GC Overhead:** GC consuming >25% of CPU time
- **OOMKilled Events:** Kubernetes pods being killed by OOM killer

### Alert Thresholds
| Metric | Warning | Critical |
|--------|---------|----------|
| Heap Usage | >75% of limit | >90% of limit |
| GC Pause | >500ms | >2000ms |
| GC Overhead | >25% CPU | >45% CPU |
| RSS Growth Rate | >10MB/hour | >50MB/hour |
| OOMKills | 1 in 24h | 2+ in 1h |

## Profiling Tools

### Java
```bash
# Heap dump
jmap -dump:live,format=b,file=heap_dump.hprof <PID>

# Heap histogram (quick)
jmap -histo:live <PID> | head -30

# Enable GC logging
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
```

### Python
```bash
# Install profiler
pip install memory_profiler objgraph

# Profile a script
python -m memory_profiler my_script.py

# In-code tracking
import tracemalloc
tracemalloc.start()
# ... run code ...
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')
for stat in top_stats[:10]:
    print(stat)
```

### Go
```bash
# CPU and memory profile
go tool pprof http://localhost:6060/debug/pprof/heap
go tool pprof -http=:8080 http://localhost:6060/debug/pprof/heap
```

## Common Causes
1. **Unclosed connections** — DB connections, HTTP clients, file handles not closed in error paths
2. **Unbounded caches** — In-memory caches without TTL or max-size eviction (e.g., TransactionCache growing indefinitely)
3. **Circular references** — Objects referencing each other preventing garbage collection
4. **Large object retention** — Holding references to large byte arrays or collections longer than needed
5. **Event listener leaks** — Registering listeners/callbacks without deregistering
6. **Static collections** — Adding items to static/class-level lists or maps without cleanup

## Immediate Mitigation
1. **Restart affected pods** (buys time):
   ```bash
   kubectl rollout restart deployment/<service-name> -n production
   ```
2. **Increase memory limit** (temporary):
   ```bash
   kubectl set resources deployment/<service-name> -n production --limits=memory=1Gi
   ```
3. **Shift traffic** to healthy pods:
   ```bash
   kubectl scale deployment/<service-name> --replicas=6 -n production
   ```
4. **Rollback** if leak was introduced in recent deployment:
   ```bash
   kubectl rollout undo deployment/<service-name> -n production
   ```

## Long-Term Fixes
- Add memory profiling to CI/CD load tests
- Implement bounded caches with TTL (e.g., Guava Cache, caffeine)
- Code review checklist: verify all resources are closed in finally blocks
- Add `-XX:+HeapDumpOnOutOfMemoryError` JVM flag for automatic heap dumps
- Set up Prometheus alerts for RSS growth rate
- Conduct periodic memory profiling in staging environment