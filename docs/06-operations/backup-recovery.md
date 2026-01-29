# Backup & Recovery

Guide to backing up TravelAI data and recovering from failures.

---

## What to Backup

### Critical Data

1. **S3 Data Lake** (all stages)
2. **ChromaDB Vectors** (Stage 4)
3. **Configuration** (.env file)
4. **Metadata** (processing_status.jsonl)

### Optional Data

- Logs (for debugging)
- Cost reports (for accounting)
- Local cache (can be regenerated)

---

## S3 Backup

### Backup Strategy

**Good News:** S3 is already durable (99.999999999% durability)

**Additional Protection:**

1. **Enable Versioning:**
```bash
aws s3api put-bucket-versioning \
  --bucket your-travel-ai-data \
  --versioning-configuration Status=Enabled
```

2. **Enable Cross-Region Replication:**
```bash
# Replicate to different region for disaster recovery
aws s3api put-bucket-replication \
  --bucket your-travel-ai-data \
  --replication-configuration file://replication.json
```

3. **Export to Local:**
```bash
# Backup entire bucket
aws s3 sync s3://your-travel-ai-data ./backup/s3-$(date +%Y-%m-%d)/

# Backup specific stages
aws s3 sync s3://your-travel-ai-data/stage3_canonical ./backup/stage3/
aws s3 sync s3://your-travel-ai-data/metadata ./backup/metadata/
```

---

## ChromaDB Backup

### Backup Vectors

```bash
# Use built-in backup command
./crawl.sh backup-vectors

# Output: stage4-vectors/backups/backup_2026-01-29_14-23-45.json
```

### Manual Backup

```python
from src.vectordb import ChromaDBClient

chromadb = ChromaDBClient.initialize_from_env()

# Get all vectors
vectors = chromadb.get_all(collection_name="travel_entities")

# Save to file
import json
with open('chromadb_backup.json', 'w') as f:
    json.dump(vectors, f)
```

### Restore Vectors

```bash
# Reset and reindex from Stage 3
./crawl.sh reset-stage4
./crawl.sh process-stage4 --embedding-types all
```

---

## Configuration Backup

### Backup .env

```bash
# Copy to secure location (DO NOT commit to git!)
cp .env ~/secure-backups/travelai-env-$(date +%Y-%m-%d).txt

# Or use encrypted backup
gpg -c .env  # Creates .env.gpg encrypted file
```

### Restore .env

```bash
# Copy back
cp ~/secure-backups/travelai-env-2026-01-29.txt .env

# Or decrypt
gpg .env.gpg  # Creates .env file
```

---

## Disaster Recovery Scenarios

### Scenario 1: Lost S3 Data

**Impact:** All pipeline data lost

**Recovery:**
1. Restore from S3 versioning or cross-region replica
2. Or re-run entire pipeline from Stage 1:
```bash
./crawl.sh youtube --input urls.txt
./crawl.sh process-stage2
./crawl.sh process-stage3
./crawl.sh process-stage4 --embedding-types all
```

**Time:** Hours to days (depending on video count)
**Cost:** LLM API costs for Stages 2-3

---

### Scenario 2: Lost ChromaDB Vectors

**Impact:** Stage 5 (RAG) unavailable

**Recovery:**
```bash
# Reindex from Stage 3 (fast, free)
./crawl.sh process-stage4 --embedding-types all
```

**Time:** ~5-10 minutes for 1,000 entities
**Cost:** FREE (local embeddings)

---

### Scenario 3: Lost Stage 3 Canonical Entities

**Impact:** Stages 4-5 unavailable

**Recovery:**
```bash
# Re-run canonicalization from Stage 2
./crawl.sh process-stage3
./crawl.sh process-stage4 --embedding-types all
```

**Time:** ~10-30 minutes for 100 videos
**Cost:** ~$0.50 (LLM verification costs)

---

### Scenario 4: Lost All Data

**Impact:** Complete data loss

**Recovery:**
1. Restore .env configuration
2. Re-run entire pipeline:
```bash
./crawl.sh youtube --input urls.txt --limit 100
./crawl.sh process-stage2
./crawl.sh process-stage3
./crawl.sh process-stage4 --embedding-types all
```

**Time:** Days (for 100+ videos)
**Cost:** $50-100 (YouTube API + LLM costs)

---

## Backup Schedule

### Recommended Schedule

| Data | Frequency | Retention | Method |
|------|-----------|-----------|--------|
| S3 Metadata | Daily | 30 days | S3 versioning |
| ChromaDB Vectors | Weekly | 4 weeks | `./crawl.sh backup-vectors` |
| .env Config | On change | Indefinite | Encrypted backup |
| Stage 3 Canonical | Weekly | 4 weeks | S3 sync |
| Logs | Daily | 7 days | Log rotation |

---

## Automated Backup Script

```bash
#!/bin/bash
# backup.sh - Automated TravelAI backup

DATE=$(date +%Y-%m-%d)
BACKUP_DIR="$HOME/travelai-backups/$DATE"

mkdir -p "$BACKUP_DIR"

# Backup S3 metadata
aws s3 sync s3://your-travel-ai-data/metadata "$BACKUP_DIR/metadata/"

# Backup ChromaDB vectors
./crawl.sh backup-vectors

# Backup config (encrypted)
gpg -c .env -o "$BACKUP_DIR/env.gpg"

# Backup Stage 3 canonical
aws s3 sync s3://your-travel-ai-data/metadata/canonical_entities.json \
  "$BACKUP_DIR/canonical_entities.json"

echo "Backup complete: $BACKUP_DIR"
```

**Setup cron job:**
```bash
# Run daily at 2am
0 2 * * * cd /path/to/TravelAI && ./backup.sh >> logs/backup.log 2>&1
```

---

## Storage Estimates

### S3 Storage Costs

| Stage | Per 100 Videos | Per 1,000 Videos |
|-------|----------------|------------------|
| Stage 1 | 1.5 MB | 15 MB |
| Stage 2 | 4.5 MB | 45 MB |
| Stage 3 | 0.5 MB | 5 MB |
| **Total** | **6.5 MB** | **65 MB** |

**S3 Cost:** $0.023 per GB/month = **~$0.001/month for 1,000 videos**

### ChromaDB Storage

| Entities | Vectors | Storage | Chroma Cloud Cost |
|----------|---------|---------|-------------------|
| 100 | 300 | ~5 MB | FREE |
| 1,000 | 3,000 | ~50 MB | $0.001/month |
| 10,000 | 30,000 | ~500 MB | $0.012/month |

---

## Testing Backups

### Verify Backups Work

```bash
# Test S3 restore
aws s3 sync "$BACKUP_DIR/metadata/" s3://test-bucket/metadata/

# Test ChromaDB restore
./crawl.sh reset-stage4
./crawl.sh process-stage4 --embedding-types all

# Verify data integrity
./crawl.sh validate-stage3
./crawl.sh stage4-stats
```

---

## References

- **S3 Storage:** [s3-storage.md](../05-infrastructure/s3-storage.md)
- **ChromaDB:** [chromadb.md](../05-infrastructure/chromadb.md)
- **Troubleshooting:** [troubleshooting.md](troubleshooting.md)
