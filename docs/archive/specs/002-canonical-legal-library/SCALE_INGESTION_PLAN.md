# Plan: Automatic Ingestion at Scale

**Feature**: 002-canonical-legal-library  
**Date**: 2025-01-27  
**Related Specs**: 002 (curation tools), 006 (web UI ingestion)

## Executive Summary

This plan outlines how to scale document ingestion from manual curation to automatic, distributed processing capable of handling thousands of documents per day across multiple legal sources (Justia.com, NYSCEF, NYC Admin Code, etc.) while respecting rate limits, maintaining data quality, and providing observability.

## Current State Analysis

### Existing Infrastructure

✅ **Strengths**:
- Async ingestion CLI (`scripts/ingest.py`) with concurrency control (semaphore-based)
- Checkpoint/resume support for long-running batches
- Statistics tracking and error reporting
- Content hash deduplication (prevents duplicate processing)
- Entity deduplication (EntityResolver)

⚠️ **Limitations**:
- **Single-machine processing**: All ingestion runs on one machine
- **Manual trigger**: Requires CLI execution, not automated
- **No job queue**: Can't distribute work across multiple workers
- **No priority handling**: All sources processed equally
- **Limited observability**: Stats only at end of batch
- **No rate limit management**: Per-source rate limiting not enforced
- **No scheduling**: Can't automatically ingest new documents on schedule
- **Memory constraints**: Large batches may exhaust memory
- **Failure recovery**: Limited retry strategies

### Current Performance

- **Throughput**: ~3-5 documents/minute (with concurrency=3)
- **Bottlenecks**:
  1. LLM API calls (entity extraction) - ~2-5 seconds per document
  2. Network I/O (fetching URLs) - variable, ~0.5-2 seconds
  3. Entity resolution search - ~1-2 seconds per entity
  4. Vector embedding generation - ~0.1-0.5 seconds per chunk

## Scale Targets

### Short-term Goals (Phase 1)
- **10x throughput**: 30-50 documents/minute (single worker)
- **24/7 operation**: Continuous ingestion without manual intervention
- **Multi-source**: Handle Justia.com, NYSCEF, NYC Admin Code simultaneously
- **Rate limit compliance**: Respect ToS and rate limits per source

### Medium-term Goals (Phase 2)
- **100x throughput**: 300-500 documents/minute (distributed workers)
- **Horizontal scaling**: Add/remove workers dynamically
- **Priority queues**: High-priority sources processed first
- **Auto-discovery**: Automatically discover new documents from sources

### Long-term Goals (Phase 3)
- **1000x throughput**: 3000-5000 documents/minute (large-scale distributed)
- **Intelligent scheduling**: ML-based prediction of document availability
- **Cost optimization**: Smart batching to minimize API costs
- **Multi-region**: Distribute workers across regions

## Architecture Options

### Option 1: Celery + Redis/RabbitMQ (Recommended)

**Pros**:
- ✅ Battle-tested, mature queue system
- ✅ Built-in task retry, priority, rate limiting
- ✅ Multiple broker options (Redis, RabbitMQ, SQS)
- ✅ Flower for monitoring
- ✅ Supports distributed workers
- ✅ Task routing and priorities

**Cons**:
- ⚠️ Additional infrastructure (Redis/RabbitMQ)
- ⚠️ Learning curve for Celery configuration
- ⚠️ Overhead for simple use cases

**Best for**: Production deployment with multiple workers, need for monitoring

### Option 2: RQ (Redis Queue)

**Pros**:
- ✅ Simpler than Celery
- ✅ Redis-only (no additional broker)
- ✅ Built-in dashboard (rq-dashboard)
- ✅ Easy to get started

**Cons**:
- ⚠️ Less features than Celery
- ⚠️ Redis single point of failure
- ⚠️ Limited priority support

**Best for**: Simple distributed processing, smaller scale

### Option 3: Custom Async Worker Pool

**Pros**:
- ✅ No additional dependencies
- ✅ Full control over behavior
- ✅ Minimal overhead

**Cons**:
- ⚠️ Need to implement queue persistence
- ⚠️ Need to implement monitoring
- ⚠️ Need to implement failure handling
- ⚠️ More maintenance burden

**Best for**: Small scale, single-machine processing

### Option 4: Cloud Queue Services (AWS SQS, Google Cloud Tasks)

**Pros**:
- ✅ Fully managed, no infrastructure
- ✅ Auto-scaling
- ✅ Built-in retry and DLQ
- ✅ Integrates with cloud monitoring

**Cons**:
- ⚠️ Vendor lock-in
- ⚠️ Cost at scale
- ⚠️ Network latency for local workers

**Best for**: Cloud-native deployments

## Recommended Architecture: Celery + Redis

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        INGESTION SYSTEM                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  SOURCES                    QUEUE              WORKERS              │
│  ───────                    ─────              ───────              │
│                                                                     │
│  [Manifest] ──┐                                                    │
│               │                                                    │
│  [Web UI] ────┼──→ [Redis Queue] ──→ [Worker Pool]                │
│               │       ├─ Priority        ├─ Worker 1               │
│  [Scheduler] ─┘       ├─ Rate Limits     ├─ Worker 2               │
│                        ├─ Retry Queue     ├─ Worker 3               │
│                        └─ DLQ             └─ Worker N               │
│                                                                     │
│  MONITORING & OBSERVABILITY                                         │
│  ────────────────────────                                           │
│  • Flower (task monitoring)                                        │
│  • Prometheus metrics                                              │
│  • Structured logging                                              │
│  • Task tracing                                                    │
│                                                                     │
│  DATA STORES                                                       │
│  ──────────                                                        │
│  • ArangoDB (entities, relationships, sources)                    │
│  • Qdrant (text chunks, embeddings)                               │
│  • Redis (queue, rate limit counters, locks)                      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Design

#### 1. Task Queue (Redis)

**Queues**:
- `ingestion:high` - High-priority sources (user-initiated, important cases)
- `ingestion:normal` - Normal-priority (curated manifests)
- `ingestion:low` - Low-priority (bulk imports, archival)
- `ingestion:retry` - Failed tasks for retry
- `ingestion:dlq` - Dead letter queue (permanently failed)

**Rate Limiting**:
- Per-source rate limit counters in Redis (e.g., `rate:justia:10min`)
- Token bucket or sliding window algorithm
- Configurable limits per source type

#### 2. Celery Tasks

**Task: `ingest_document_task`**
```python
@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    rate_limit='10/m',  # Per source
    queue='ingestion:normal'
)
def ingest_document_task(
    self,
    manifest_entry: dict,
    source_type: str,
    priority: int = 5
):
    """Ingest a single document from manifest entry."""
    # 1. Check rate limit for source_type
    # 2. Fetch text
    # 3. Process document
    # 4. Update manifest entry status
    # 5. Handle errors with retry
```

**Task: `ingest_batch_task`**
```python
@celery_app.task(queue='ingestion:normal')
def ingest_batch_task(manifest_path: str):
    """Process entire manifest file, enqueueing individual tasks."""
    # Read manifest
    # Enqueue individual ingest_document_task for each entry
    # Track batch progress
```

**Task: `discover_new_documents_task`**
```python
@celery_app.task(
    queue='ingestion:low',
    periodic=True  # Scheduled task
)
def discover_new_documents_task(source: str):
    """Discover new documents from source (Justia, NYSCEF, etc.)."""
    # Search for new documents
    # Add to manifest
    # Enqueue ingestion tasks
```

#### 3. Celery Workers

**Worker Configuration**:
- **Concurrency**: 2-4 workers per machine (memory/CPU dependent)
- **Pool**: `prefork` (CPU-bound) or `gevent` (I/O-bound)
- **Autoscaling**: Scale workers based on queue depth
- **Resource limits**: Memory limits, CPU limits per worker

**Worker Types**:
- **Ingestion Workers**: Handle document ingestion tasks
- **Discovery Workers**: Handle source discovery tasks (lower priority)

#### 4. Rate Limiting Service

**Per-Source Rate Limits**:
```python
class RateLimiter:
    def __init__(self, redis_client):
        self.redis = redis_client
    
    def check_rate_limit(self, source: str, limit: int, window: int) -> bool:
        """Check if source is within rate limit."""
        key = f"rate:{source}:{window}"
        count = self.redis.incr(key)
        if count == 1:
            self.redis.expire(key, window)
        return count <= limit
```

**Rate Limit Configuration**:
- Justia.com: 10 requests/minute
- NYSCEF: 5 requests/minute (more restrictive)
- NYC Admin Code: 20 requests/minute (readthedocs is more permissive)
- LLM API: Track separately, respect provider limits

#### 5. Monitoring & Observability

**Metrics** (Prometheus):
- `ingestion_tasks_total` - Total tasks enqueued
- `ingestion_tasks_processed` - Tasks completed
- `ingestion_tasks_failed` - Tasks failed
- `ingestion_tasks_duration_seconds` - Processing time histogram
- `ingestion_documents_per_minute` - Throughput
- `ingestion_queue_depth` - Queue size
- `ingestion_rate_limit_hits` - Rate limit violations

**Logging**:
- Structured JSON logs
- Task IDs for tracing
- Correlation IDs for batch tracking

**Dashboard**:
- Flower for Celery monitoring
- Grafana for metrics visualization
- Custom dashboard for ingestion stats

## Implementation Plan

### Phase 1: Foundation (Weeks 1-2)

**Goal**: Set up Celery infrastructure and migrate existing ingestion

**Tasks**:
1. **Setup Infrastructure**
   - [ ] Install Celery, Redis (or use existing Redis)
   - [ ] Configure Celery app with Redis broker
   - [ ] Set up Flower for monitoring
   - [ ] Configure logging and metrics

2. **Migrate Ingestion to Celery**
   - [ ] Create `tasks/ingestion.py` with Celery tasks
   - [ ] Convert `ingest_entry()` to `ingest_document_task()`
   - [ ] Implement `ingest_batch_task()` for manifest processing
   - [ ] Add task retry logic with exponential backoff
   - [ ] Add task result tracking

3. **Rate Limiting**
   - [ ] Implement `RateLimiter` service
   - [ ] Add rate limit checks to tasks
   - [ ] Configure per-source rate limits
   - [ ] Add rate limit metrics

4. **Testing**
   - [ ] Unit tests for Celery tasks
   - [ ] Integration tests for queue workflow
   - [ ] Load tests (100 documents)

**Success Criteria**:
- ✅ Can process manifest via Celery queue
- ✅ Rate limiting prevents violations
- ✅ Failed tasks retry automatically
- ✅ Monitoring dashboard shows task status

### Phase 2: Scaling & Optimization (Weeks 3-4)

**Goal**: Optimize throughput and add distributed workers

**Tasks**:
1. **Performance Optimization**
   - [ ] Profile bottlenecks (LLM calls, entity resolution)
   - [ ] Optimize entity resolution (batch searches)
   - [ ] Implement connection pooling for DBs
   - [ ] Cache frequent queries (source metadata)

2. **Distributed Workers**
   - [ ] Deploy multiple worker processes
   - [ ] Configure worker autoscaling
   - [ ] Add worker health checks
   - [ ] Implement graceful shutdown

3. **Priority Queues**
   - [ ] Implement priority-based routing
   - [ ] Add priority to task parameters
   - [ ] Configure queue priorities
   - [ ] Test priority handling

4. **Error Handling**
   - [ ] Implement dead letter queue (DLQ)
   - [ ] Add error classification (transient vs permanent)
   - [ ] Create DLQ monitoring and alerts
   - [ ] Manual retry from DLQ

**Success Criteria**:
- ✅ 10x throughput improvement (30-50 docs/min)
- ✅ Multiple workers processing in parallel
- ✅ Priority queues working correctly
- ✅ DLQ captures permanent failures

### Phase 3: Automation & Discovery (Weeks 5-6)

**Goal**: Automate document discovery and scheduled ingestion

**Tasks**:
1. **Scheduled Tasks**
   - [ ] Set up Celery Beat for periodic tasks
   - [ ] Implement `discover_new_documents_task()` for each source
   - [ ] Configure discovery schedules
   - [ ] Add discovery metrics

2. **Source Discovery**
   - [ ] Implement Justia.com discovery (search for new cases)
   - [ ] Implement NYSCEF discovery (monitor new filings)
   - [ ] Implement NYC Admin Code discovery (check for updates)
   - [ ] Add duplicate detection before enqueueing

3. **Manifest Integration**
   - [ ] Auto-add discovered documents to manifest
   - [ ] Update manifest entry status during processing
   - [ ] Track discovery sources in manifest metadata

4. **Monitoring & Alerts**
   - [ ] Set up alerts for queue depth
   - [ ] Set up alerts for failure rates
   - [ ] Set up alerts for rate limit violations
   - [ ] Create ingestion reports (daily/weekly)

**Success Criteria**:
- ✅ New documents discovered automatically
- ✅ Discovery runs on schedule
- ✅ No manual intervention needed for 24+ hours
- ✅ Alerts notify on issues

### Phase 4: Advanced Features (Weeks 7-8, Optional)

**Goal**: Add advanced features for large-scale operation

**Tasks**:
1. **Cost Optimization**
   - [ ] Track LLM API costs per document
   - [ ] Implement batching for LLM calls
   - [ ] Add cost budgets and alerts
   - [ ] Optimize embedding generation (batch processing)

2. **Advanced Scheduling**
   - [ ] ML-based prediction of document availability
   - [ ] Adaptive rate limiting based on source behavior
   - [ ] Dynamic worker scaling based on queue depth

3. **Multi-Region**
   - [ ] Deploy workers in multiple regions
   - [ ] Route tasks based on source region
   - [ ] Handle regional rate limits

## Resource Requirements

### Infrastructure

**Minimal Setup** (Phase 1):
- 1 Redis instance (2GB RAM) - Queue + rate limits
- 1 Worker machine (4 CPU, 8GB RAM) - Process tasks
- Monitoring: Flower (lightweight)

**Production Setup** (Phase 2+):
- Redis cluster (for HA) or managed Redis
- Multiple worker machines (auto-scaling group)
- Prometheus + Grafana for metrics
- Centralized logging (ELK stack or cloud logging)

### Cost Estimation

**Infrastructure** (monthly):
- Redis: $20-50 (managed) or self-hosted
- Workers: $50-200 (depending on scale)
- Monitoring: $10-30 (optional managed services)

**API Costs** (per document):
- LLM API: ~$0.01-0.05 per document (entity extraction)
- Vector embeddings: ~$0.001 per chunk (if using API, or free if self-hosted)

**At 1000 documents/day**: ~$30-60/month API costs + infrastructure

## Migration Strategy

### Step 1: Parallel Operation
- Deploy Celery alongside existing CLI
- Run both systems in parallel
- Compare results and performance

### Step 2: Gradual Migration
- Migrate low-priority sources first
- Monitor and adjust
- Migrate high-priority sources last

### Step 3: Deprecation
- Mark CLI as deprecated
- Keep CLI for debugging/manual runs
- Full migration to Celery queue

## Risk Mitigation

### Technical Risks

1. **Queue Backlog**: Queue grows faster than workers can process
   - **Mitigation**: Auto-scale workers, alert on queue depth
   - **Monitoring**: Queue depth metrics

2. **Rate Limit Violations**: Workers exceed source rate limits
   - **Mitigation**: Strict rate limiting, token bucket algorithm
   - **Monitoring**: Rate limit hit metrics

3. **Worker Failures**: Worker crashes or becomes unresponsive
   - **Mitigation**: Health checks, automatic restart, task retries
   - **Monitoring**: Worker health metrics

4. **Data Corruption**: Concurrent writes cause data issues
   - **Mitigation**: Proper locking, idempotent operations
   - **Testing**: Concurrent ingestion tests

### Operational Risks

1. **Cost Overruns**: API costs exceed budget
   - **Mitigation**: Cost tracking, budgets, alerts
   - **Monitoring**: Per-document cost metrics

2. **Source Changes**: Legal source websites change formats
   - **Mitigation**: Version detection, graceful degradation
   - **Monitoring**: Parsing failure rates

## Success Metrics

### Performance Metrics
- **Throughput**: Documents processed per minute
- **Latency**: Time from queue to completion (P50, P95, P99)
- **Queue Depth**: Average and peak queue size
- **Worker Utilization**: CPU/memory usage per worker

### Quality Metrics
- **Success Rate**: % of documents successfully ingested
- **Error Rate**: % of documents with errors
- **Duplicate Rate**: % of documents skipped as duplicates
- **Data Quality**: Entity extraction accuracy

### Operational Metrics
- **Uptime**: % of time workers are available
- **Rate Limit Violations**: Count per source
- **DLQ Size**: Number of permanently failed tasks
- **Cost per Document**: Total cost / documents processed

## Next Steps

1. **Review & Approve**: Review plan with team, get approval
2. **Phase 1 Kickoff**: Start with foundation setup
3. **Proof of Concept**: Build minimal Celery setup, test with 100 documents
4. **Iterate**: Adjust based on learnings, proceed to Phase 2

## References

- [Celery Documentation](https://docs.celeryq.dev/)
- [Redis Documentation](https://redis.io/docs/)
- [Flower Monitoring](https://flower.readthedocs.io/)
- Existing codebase: `scripts/ingest.py`, `services/document_processor.py`

