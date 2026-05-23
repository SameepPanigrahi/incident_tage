# Deployment Rollback Standard Operating Procedure

## Pre-Rollback Checklist
- [ ] Confirm the issue is caused by the new deployment (not infrastructure)
- [ ] Identify the last known good version (check deployment history)
- [ ] Notify the incident commander and on-call team
- [ ] Check if database migrations in the new version are backward-compatible
- [ ] Verify rollback will not cause data loss

## Kubernetes Rollback

### Check Deployment History
```bash
kubectl rollout history deployment/<service-name> -n production
```

### Rollback to Previous Version
```bash
kubectl rollout undo deployment/<service-name> -n production
```

### Rollback to Specific Revision
```bash
kubectl rollout undo deployment/<service-name> -n production --to-revision=<N>
```

### Verify Rollback
```bash
kubectl rollout status deployment/<service-name> -n production
kubectl get pods -n production -l app=<service-name>
```

## Docker Compose Rollback

### Stop Current Version
```bash
docker-compose down
```

### Deploy Previous Version
```bash
export IMAGE_TAG=<previous-version>
docker-compose up -d
```

### Verify
```bash
docker-compose ps
docker-compose logs --tail=50 <service-name>
```

## Canary Deployment Failure

### Symptoms
- Error rate in canary pods exceeds 5% threshold
- Latency in canary pods > 2x baseline
- Health check failures in canary replicas

### Action
1. Immediately route all traffic to stable pods
2. Scale down canary replicas to 0
3. Investigate logs from canary pods before deleting them
4. Roll back the canary deployment

## Post-Rollback Verification
1. Confirm all pods are running the previous version
2. Check health endpoints for all affected services
3. Verify error rates have returned to baseline
4. Confirm dependent services have recovered
5. Monitor for 30 minutes before declaring stable

## Communication Protocol
1. **T+0 min:** Notify incident channel: "Rollback initiated for <service> from v<new> to v<old>"
2. **T+5 min:** Confirm rollback complete and pods healthy
3. **T+30 min:** Declare stable or escalate if issues persist
4. **T+60 min:** Post brief incident summary to stakeholders