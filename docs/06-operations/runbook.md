# TravelAI Production Runbook

**Stage 4 Vector Search Operations Guide**

Version: 1.0
Last Updated: 2025-12-14

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Production Metrics](#production-metrics)
3. [Common Operations](#common-operations)
4. [Troubleshooting Guide](#troubleshooting-guide)
5. [Backup & Restore Procedures](#backup--restore-procedures)
6. [Performance Tuning](#performance-tuning)
7. [Scaling Considerations](#scaling-considerations)
8. [Monitoring & Alerts](#monitoring--alerts)
9. [Disaster Recovery](#disaster-recovery)
10. [Maintenance Windows](#maintenance-windows)

---

## System Overview

### Architecture

```
TravelAI Vector Search Pipeline
│
├── Stage 1: YouTube Video Crawling
│   └── Transcription with Whisper
│
├── Stage 2: Entity Extraction
│   └── LLM-based extraction (DeepSeek/OpenAI)
│
├── Stage 3: Deduplication & Canonicalization
│   └── Fuzzy matching + LLM consensus
│
└── Stage 4: Vector Search (THIS STAGE)
    ├── Embedding Generation (OpenAI ada-002)
    ├── Vector Indexing (ChromaDB)
    └── Semantic Search API
```

### Components

- **Vector Database**: ChromaDB (local or cloud)
- **Embedding Model**: OpenAI text-embedding-ada-002
- **Storage**: S3 (raw data, backups)
- **Search API**: FastAPI-based semantic search
- **Monitoring**: Custom health checks + metrics

### Data Flow

1. Canonical entities (Stage 3) → Embedding generation
2. Embeddings → ChromaDB indexing
3. Search queries → Semantic search → Results

---

## Production Metrics

### Current Deployment Stats

```yaml
# To be filled after first production run
Total Embeddings: [X embeddings]
Total Cost: $[Y]
Query Latency: [Z]ms p95
Storage Size: [N] MB
Indexing Time: [M] minutes

Collections:
  - entities: [count] embeddings
  - profile_consensus: [count] embeddings
  - experiences: [count] embeddings

Embedding Generation:
  - Total tokens: [X]
  - Cost per embedding: $[Y]
  - Rate: [Z] embeddings/sec

Search Performance:
  - Avg query time: [X]ms
  - Cache hit rate: [Y]%
  - QPS capacity: [Z] queries/sec
```

### Cost Breakdown

```yaml
Embedding Generation:
  - OpenAI ada-002: $0.0001 per 1K tokens
  - Average entity: ~200 tokens
  - Cost per entity: ~$0.00002

Storage:
  - S3: $0.023/GB/month
  - ChromaDB: Varies by deployment

Total Monthly Cost Estimate:
  - 10K entities: ~$0.20 (embeddings) + storage
  - 100K entities: ~$2.00 (embeddings) + storage
```

---

## Common Operations

### Daily Operations

#### 1. Process New Videos

```bash
# Stage 1-4 full pipeline
./crawl.sh youtube --input urls.txt
./crawl.sh process-stage2
./crawl.sh process-stage3
./crawl.sh process-stage4
```

#### 2. Check System Status

```bash
# Overall status
./crawl.sh status

# Stage 4 specific
./crawl.sh stage4-stats

# Health check
./crawl.sh monitor-stage4
```

#### 3. Search Operations

```bash
# Test search
./crawl.sh search --query "beach parties" --city Bangkok

# Interactive search
./crawl.sh search --interactive

# Personalized search
./crawl.sh search --query "romantic dinner" --profile couple_luxury
```

### Weekly Operations

#### 1. Backup Vector Database

```bash
# Full backup
./crawl.sh backup-vectors

# Compressed backup
./crawl.sh backup-vectors --compress

# Specific collections
./crawl.sh backup-vectors --collections entities,profiles
```

#### 2. Review Metrics

```bash
# Detailed stats
./crawl.sh stage4-stats --detailed

# Export JSON report
./crawl.sh stage4-stats --json > weekly_report.json
```

#### 3. Performance Check

```bash
# Comprehensive monitoring
./crawl.sh monitor-stage4 --check-all --generate-report
```

### Monthly Operations

#### 1. Sync to Cloud (if applicable)

```bash
# Dry run first
./crawl.sh sync-to-cloud --dry-run

# Full sync
./crawl.sh sync-to-cloud

# Force resync
./crawl.sh sync-to-cloud --force
```

#### 2. Cleanup Old Backups

```bash
# Manual cleanup (implement retention policy)
aws s3 ls s3://travel-ai-data-divyansh-2025/stage4-vectors/backups/
aws s3 rm s3://travel-ai-data-divyansh-2025/stage4-vectors/backups/old_file.json.gz
```

---

## Troubleshooting Guide

### Issue: Search Queries Slow (>1000ms)

**Symptoms:**
- Query latency > 1000ms
- User complaints about search speed

**Diagnosis:**
```bash
# Check search performance
./crawl.sh monitor-stage4 --check-all

# Check collection sizes
./crawl.sh stage4-stats
```

**Solutions:**
1. **Reduce collection size**: Limit embeddings per collection
2. **Optimize ChromaDB**: Increase memory allocation
3. **Add caching**: Implement Redis for frequent queries
4. **Use cloud ChromaDB**: Better performance for large datasets

### Issue: High Embedding Costs

**Symptoms:**
- Monthly OpenAI bill higher than expected
- Cost per entity > $0.0001

**Diagnosis:**
```bash
# Check embedding stats
./crawl.sh stage4-stats --detailed
```

**Solutions:**
1. **Batch processing**: Increase batch size to reduce API calls
2. **Deduplication**: Ensure Stage 3 deduplication is working
3. **Token optimization**: Reduce input text size
4. **Rate limiting**: Add delays between API calls

### Issue: ChromaDB Connection Errors

**Symptoms:**
- `Connection refused` errors
- Collections not found

**Diagnosis:**
```bash
# Check ChromaDB status
python3 -c "from src.vectordb.chromadb_client import ChromaDBClient; c = ChromaDBClient.initialize_from_env(); print(c.list_collections())"
```

**Solutions:**
1. **Local mode**: Check if `chroma_data/` directory exists
2. **Cloud mode**: Verify `CHROMA_CLOUD_HOST` and `CHROMA_CLOUD_API_KEY`
3. **Restart**: If local, restart the application
4. **Recreate**: Use `reset-stage4` to recreate collections

### Issue: Out of Memory

**Symptoms:**
- Process killed during indexing
- `MemoryError` exceptions

**Diagnosis:**
```bash
# Check system memory
free -h

# Check process memory
ps aux | grep python
```

**Solutions:**
1. **Reduce batch size**: Use `--batch-size 50` instead of 100
2. **Limit processing**: Use `--limit` to process in chunks
3. **Increase RAM**: Upgrade server or use cloud instance
4. **Use cloud ChromaDB**: Offload memory requirements

### Issue: Search Returns No Results

**Symptoms:**
- All searches return empty
- Collection counts show 0

**Diagnosis:**
```bash
# Check collections
./crawl.sh stage4-stats

# Verify Stage 3 output
./crawl.sh stage3-stats
```

**Solutions:**
1. **Run Stage 4**: Ensure `process-stage4` completed successfully
2. **Check Stage 3**: Verify Stage 3 produced canonical entities
3. **Reset and reindex**: Use `reset-stage4` and rerun Stage 4
4. **Sync metadata**: Use `./crawl.sh sync --stage stage_3_deduplicate`

---

## Backup & Restore Procedures

### Backup

#### Full Backup (Recommended Weekly)

```bash
# Backup all collections with compression
./crawl.sh backup-vectors --compress

# Verify backup
aws s3 ls s3://travel-ai-data-divyansh-2025/stage4-vectors/backups/
```

#### Incremental Backup (Optional)

```bash
# Backup only new/changed data
./crawl.sh backup-vectors --incremental --compress
```

### Restore

#### Restore from S3 Backup

```python
# Manual restore script (implement as needed)
from src.storage.s3 import S3Storage
from src.vectordb.chromadb_client import ChromaDBClient
import json
import gzip

# Download backup
s3 = S3Storage()
response = s3.s3_client.get_object(
    Bucket='travel-ai-data-divyansh-2025',
    Key='stage4-vectors/backups/entities_backup_20251214.json.gz'
)

# Decompress
compressed_data = response['Body'].read()
json_data = gzip.decompress(compressed_data).decode('utf-8')
backup_data = json.loads(json_data)

# Restore to ChromaDB
chromadb = ChromaDBClient.initialize_from_env()
collection = chromadb.create_collection(backup_data['collection_name'])

# Add data in batches
data = backup_data['data']
batch_size = 100

for i in range(0, len(data['ids']), batch_size):
    collection.add(
        ids=data['ids'][i:i+batch_size],
        embeddings=data['embeddings'][i:i+batch_size],
        metadatas=data['metadatas'][i:i+batch_size],
        documents=data['documents'][i:i+batch_size]
    )
```

#### Restore from Cloud Sync

```bash
# If synced to cloud, restore by switching mode
# 1. Update .env to use cloud mode
# 2. Update application config
# 3. Restart services
```

---

## Performance Tuning

### Embedding Generation

```yaml
Optimization Strategies:
  1. Batch Size:
     - Increase to 200-500 for better throughput
     - Decrease if hitting rate limits

  2. Text Preprocessing:
     - Truncate to 8000 tokens max
     - Remove unnecessary whitespace
     - Deduplicate identical texts

  3. Concurrency:
     - Use asyncio for parallel API calls
     - Respect OpenAI rate limits (3,000 RPM)

  4. Caching:
     - Cache embeddings for identical texts
     - Use content hash as cache key
```

### Search Performance

```yaml
Optimization Strategies:
  1. Indexing:
     - Use HNSW index (default in ChromaDB)
     - Increase M parameter for better recall
     - Adjust ef_construction for build time vs accuracy

  2. Query Optimization:
     - Limit top_k to 10-20 results
     - Use filters to reduce search space
     - Implement query caching

  3. Hardware:
     - SSD storage for ChromaDB
     - 16GB+ RAM recommended
     - Multi-core CPU for parallel search

  4. Reranking:
     - Use lightweight rerankers
     - Limit reranking to top 50 results
     - Consider cross-encoder only for top 10
```

### Storage Optimization

```yaml
Strategies:
  1. Compression:
     - Enable compression in ChromaDB
     - Use gzip for S3 backups
     - Archive old/unused collections

  2. Partitioning:
     - Split large collections by city/region
     - Use separate collections for different entity types
     - Implement time-based sharding

  3. Cleanup:
     - Remove duplicate embeddings
     - Delete old backup files (>30 days)
     - Prune unused collections
```

---

## Scaling Considerations

### Horizontal Scaling

```yaml
For 100K+ Entities:
  1. Database:
     - Use cloud ChromaDB with auto-scaling
     - Shard by geographical region
     - Implement read replicas

  2. API:
     - Deploy behind load balancer
     - Use Redis for caching
     - Implement rate limiting

  3. Processing:
     - Distribute Stage 4 across multiple workers
     - Use message queue (e.g., Celery + Redis)
     - Process collections in parallel
```

### Vertical Scaling

```yaml
For 10K-100K Entities:
  1. Increase server resources:
     - 32GB RAM
     - 8+ CPU cores
     - 500GB SSD storage

  2. Optimize configurations:
     - Increase ChromaDB cache size
     - Tune batch sizes
     - Enable parallel processing
```

### Cost Optimization at Scale

```yaml
1. Embedding Generation:
   - Use smaller models (e.g., Cohere)
   - Batch API calls
   - Cache aggressively

2. Storage:
   - Use S3 Intelligent-Tiering
   - Compress backups
   - Archive old data to Glacier

3. Compute:
   - Use spot instances for batch processing
   - Schedule off-peak processing
   - Auto-scale based on load
```

---

## Monitoring & Alerts

### Key Metrics to Monitor

```yaml
System Health:
  - ChromaDB connection status
  - Collection counts (should grow steadily)
  - Storage utilization
  - Memory usage

Performance:
  - Query latency (p50, p95, p99)
  - Embedding generation rate
  - API error rate
  - Cache hit rate

Business Metrics:
  - Total embeddings
  - Daily search volume
  - Top search queries
  - User satisfaction (if available)
```

### Alert Thresholds

```yaml
Critical Alerts (Immediate Action):
  - ChromaDB connection lost
  - All searches failing
  - Disk space > 90%
  - Memory usage > 95%

Warning Alerts (Monitor):
  - Query latency > 1000ms
  - Error rate > 1%
  - Embedding cost spike > 50%
  - Collection size increase > 2x/day
```

### Monitoring Commands

```bash
# Daily health check
./crawl.sh monitor-stage4

# Weekly comprehensive check
./crawl.sh monitor-stage4 --check-all --generate-report

# Continuous monitoring (cron job)
# Add to crontab:
# 0 */6 * * * /path/to/TravelAI/crawl.sh monitor-stage4 --alert-email admin@example.com
```

---

## Disaster Recovery

### Recovery Time Objective (RTO): 1 hour
### Recovery Point Objective (RPO): 24 hours

### Disaster Scenarios

#### Scenario 1: ChromaDB Corruption

**Steps:**
1. Stop all write operations
2. Backup corrupt data (for analysis)
3. Restore from latest S3 backup
4. Verify data integrity
5. Resume operations

```bash
# Restore procedure
./crawl.sh reset-stage4 --all --force
python restore_from_backup.py --backup s3://bucket/path/to/backup.json.gz
./crawl.sh stage4-stats  # Verify
```

#### Scenario 2: Complete Data Loss

**Steps:**
1. Restore from S3 backups
2. If backups unavailable, rebuild from Stage 3
3. Verify data integrity
4. Resume operations

```bash
# Rebuild from Stage 3
./crawl.sh reset-stage4 --all --force
./crawl.sh process-stage4 --embedding-types all
./crawl.sh stage4-stats  # Verify
```

#### Scenario 3: Cloud Provider Outage

**Steps:**
1. Switch to local ChromaDB mode
2. Update .env configuration
3. Sync data from backups
4. Redirect traffic to local instance

---

## Maintenance Windows

### Recommended Schedule

```yaml
Daily:
  - Off-peak hours: 2-4 AM local time
  - Duration: 30 minutes
  - Activities: Process new videos, update embeddings

Weekly:
  - Saturday 2-6 AM
  - Duration: 4 hours
  - Activities: Full backup, performance tuning, updates

Monthly:
  - First Sunday 00:00-06:00
  - Duration: 6 hours
  - Activities: Major updates, cloud sync, data cleanup
```

### Maintenance Checklist

#### Pre-Maintenance
- [ ] Announce maintenance window
- [ ] Backup current state
- [ ] Verify backup integrity
- [ ] Prepare rollback plan
- [ ] Check dependencies (OpenAI API status, etc.)

#### During Maintenance
- [ ] Stop write operations
- [ ] Perform updates/changes
- [ ] Run health checks
- [ ] Verify functionality
- [ ] Update documentation

#### Post-Maintenance
- [ ] Resume operations
- [ ] Monitor for issues (24 hours)
- [ ] Generate report
- [ ] Update runbook if needed
- [ ] Announce completion

---

## Quick Reference

### Essential Commands

```bash
# Status
./crawl.sh status
./crawl.sh stage4-stats

# Processing
./crawl.sh process-stage4
./crawl.sh process-stage4 --limit 10  # Test

# Search
./crawl.sh search --query "text"
./crawl.sh search --interactive

# Maintenance
./crawl.sh backup-vectors --compress
./crawl.sh monitor-stage4
./crawl.sh reset-stage4 --dry-run

# Emergency
./crawl.sh reset-stage4 --all --force  # Nuclear option
```

### Support Contacts

```yaml
Technical Lead: [Name/Email]
DevOps: [Name/Email]
On-Call: [Phone/Email]

External Services:
  - OpenAI Support: platform.openai.com/docs
  - ChromaDB Docs: docs.trychroma.com
  - AWS Support: aws.amazon.com/support
```

---

**End of Runbook**

Last Updated: 2025-12-14
Version: 1.0
Next Review: 2026-01-14
