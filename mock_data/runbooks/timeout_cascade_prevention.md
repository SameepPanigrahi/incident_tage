# Timeout Cascade Prevention Runbook

## Understanding Cascading Timeouts
A cascading timeout failure occurs when a slow downstream service causes upstream
services to exhaust their thread pools and connection resources, eventually bringing
down the entire request pipeline.

**Failure chain:** Slow DB query -> Service A timeout -> Service B thread pool saturation -> API Gateway 504s

## Circuit Breaker Configuration

### Resilience4j (Java / Spring Boot)
```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-service:
        slidingWindowSize: 10
        failureRateThreshold: 50       # Open after 50% failures
        waitDurationInOpenState: 30s   # Wait before half-open
        permittedNumberOfCallsInHalfOpenState: 3
        slowCallRateThreshold: 80
        slowCallDurationThreshold: 2s
```

### Python (pybreaker)
```python
import pybreaker
breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=30,
    listeners=[LoggingListener()],
)
```

## Timeout Tuning Strategy

### Golden Rule: Downstream timeout < Upstream timeout
```
API Gateway timeout:  30s
  -> Order Service timeout:  10s
    -> Inventory Service timeout:  3s
      -> Database query timeout:  1s
```

Each layer should have a timeout SHORTER than the layer above it to prevent
thread pool saturation at higher levels.

### Setting Timeouts
- Connection timeout: 1-3 seconds
- Read/response timeout: 3-10 seconds (depends on operation)
- Total request timeout: sum of retries * read timeout

## Bulkhead Pattern
Isolate resources so that failure in one dependency does not exhaust resources
needed by other dependencies.

```yaml
resilience4j:
  bulkhead:
    instances:
      inventory-service:
        maxConcurrentCalls: 25    # max parallel calls
        maxWaitDuration: 500ms   # max wait time for a permit
```

## Retry Policies

### Exponential Backoff with Jitter
```python
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=0.5, max=10, jitter=2),
)
def call_inventory_service(sku: str):
    resp = httpx.get(f"http://inventory-service/api/check/{sku}", timeout=3.0)
    resp.raise_for_status()
    return resp.json()
```

### Retry Budget
- Never retry more than 3 times per request
- Implement a global retry budget: max 10% additional traffic from retries
- Do NOT retry on 4xx errors (client errors)

## Fallback Strategies
1. **Cached responses:** Return last-known-good data for read endpoints
2. **Degraded functionality:** Skip non-critical features (e.g., skip recommendations)
3. **Default values:** Return safe defaults when a dependency is unavailable
4. **Queue for later:** Accept the request and process asynchronously when service recovers

## Monitoring & Alerting Thresholds

| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| p99 latency | >2x baseline | >5x baseline | Investigate slow dependency |
| Error rate | >5% | >20% | Check circuit breakers |
| Thread pool utilization | >70% | >90% | Scale up or shed load |
| Circuit breaker state | HALF-OPEN | OPEN | Page on-call engineer |
| Request queue depth | >70% capacity | >90% capacity | Enable load shedding |

