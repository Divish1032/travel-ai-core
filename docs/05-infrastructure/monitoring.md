# Infrastructure Monitoring

This guide covers logging, metrics, and cost tracking for the TravelAI pipeline.

---

## Table of Contents

1. [Logging](#logging)
2. [Cost Tracking](#cost-tracking)
3. [Performance Metrics](#performance-metrics)
4. [Error Monitoring](#error-monitoring)

---

## Logging

### Logging Configuration

TravelAI uses Python's standard logging module with custom configuration:

**Logger locations:**
- `src/utils/logging.py` - Logger configuration
- Pipeline logs: Stage-specific loggers in each pipeline module

**Log levels:**
- `DEBUG` - Detailed diagnostic information
- `INFO` - General informational messages
- `WARNING` - Warning messages for potential issues
- `ERROR` - Error messages for failures
- `CRITICAL` - Critical failures

### Using Loggers

```python
from src.utils.logging import get_logger

logger = get_logger(__name__)

logger.info("Processing video: {video_id}")
logger.warning("Rate limit approaching")
logger.error("Failed to extract entities", exc_info=True)
```

### Log Output Locations

Pipeline logs are stored in:
- Console output (stdout/stderr)
- Application logs (if configured)

For production deployments, configure centralized logging.

---

## Cost Tracking

### Overview

The RAG Cost Tracker monitors LLM API costs across all Stage 5 (RAG) pipeline phases to prevent budget overruns and optimize spending.

**Implementation:** `src/utils/rag_cost_tracker.py`

### Quick Start

```python
from src.utils.rag_cost_tracker import RAGCostTracker

# Initialize tracker with optional budget limit
tracker = RAGCostTracker(budget_limit=0.10)  # $0.10 limit

# Track a phase
tracker.track_phase(
    phase='intent_parsing',
    cost=0.0001,
    input_tokens=100,
    output_tokens=50,
    metadata={'model': 'deepseek-chat', 'provider': 'deepseek'}
)

# Mark query complete
tracker.track_query_complete()

# Print summary
tracker.print_summary()

# Save report
tracker.save_report()  # Saves to stage5-costs/YYYY-MM-DD_HH-MM-SS.json
```

### Tracked Phases

The cost tracker monitors these RAG pipeline phases:

| Phase | Description |
|-------|-------------|
| `intent_parsing` | User query intent parsing |
| `retrieval` | Vector database retrieval |
| `re_ranking` | Candidate re-ranking |
| `context_building` | Context assembly |
| `generation` | Itinerary generation |
| `validation` | Output validation |
| `narrative` | Narrative generation |

### Integration with RAG Pipeline

The tracker integrates with the RAG pipeline to automatically track costs:

```python
# In src/rag/pipeline.py

from src.utils.rag_cost_tracker import RAGCostTracker

class RAGPipeline:
    def __init__(self, budget_limit: Optional[float] = None):
        self.cost_tracker = RAGCostTracker(budget_limit=budget_limit)

    def generate(self, query: str, **kwargs):
        # Phase 1: Parse Intent
        intent = self.intent_parser.parse_query(query)
        self.cost_tracker.track_phase(
            'intent_parsing',
            cost=self.intent_parser.total_cost,
            input_tokens=getattr(self.intent_parser, 'last_input_tokens', 0),
            output_tokens=getattr(self.intent_parser, 'last_output_tokens', 0)
        )

        # ... other phases

        # Mark complete
        self.cost_tracker.track_query_complete()

        return result
```

### CLI Integration

```bash
# Generate itinerary with budget control
./crawl.sh generate-itinerary \
    -q "5 days Bangkok solo budget" \
    --budget-limit 0.01 \
    --save-cost-report
```

### Cost Report Format

```json
{
  "summary": {
    "total_cost": 0.0121,
    "queries_processed": 1,
    "cost_per_query": 0.0121,
    "elapsed_time": 15.3,
    "cost_per_second": 0.000791
  },
  "breakdown_by_phase": {
    "intent_parsing": {
      "total_cost": 0.0001,
      "count": 1,
      "avg_cost": 0.0001,
      "input_tokens": 100,
      "output_tokens": 50,
      "total_tokens": 150,
      "percentage": 0.8
    },
    "generation": {
      "total_cost": 0.0080,
      "count": 1,
      "avg_cost": 0.0080,
      "input_tokens": 3000,
      "output_tokens": 1500,
      "total_tokens": 4500,
      "percentage": 66.1
    }
  },
  "token_usage": {
    "total": 8350,
    "input": 5800,
    "output": 2550
  },
  "cost_efficiency": {
    "cost_per_1k_input_tokens": 0.002086,
    "cost_per_1k_output_tokens": 0.004745
  },
  "budget": {
    "limit": 0.10,
    "used": 0.0121,
    "remaining": 0.0879,
    "percentage_used": 12.1
  }
}
```

**Reports saved to:** `stage5-costs/YYYY-MM-DD_HH-MM-SS.json`

### Budget Alerts

The tracker automatically warns when approaching budget limits:

```python
tracker = RAGCostTracker(budget_limit=0.01)

# 80% warning
# ⚠️  Approaching budget limit: $0.0080 / $0.01 (80.0%)

# 100% error
# BudgetExceededError: Budget limit exceeded: $0.0101 > $0.01
```

### Cost Optimization Tips

**1. Use cheaper models for simple tasks**
```python
# Use DeepSeek for intent parsing (cheaper)
intent_parser = IntentParser(provider='deepseek')

# Use Gemini for generation (good quality/cost ratio)
generator = ItineraryGenerator(provider='gemini')
```

**2. Skip narrative during development**
```python
result = pipeline.generate(query, skip_narrative=True)
# Saves ~20% of total cost
```

**3. Reduce retry attempts**
```python
result = pipeline.generate(query, max_retries=1)
```

**4. Batch process with caching**
```python
pipeline = RAGPipeline(enable_cache=True)
result1 = pipeline.generate_cached("5 days Bangkok")
result2 = pipeline.generate_cached("5 days Bangkok")  # Free!
```

### Analytics

**Find most expensive phase:**
```python
phase, cost = tracker.get_most_expensive_phase()
print(f"Most expensive: {phase} (${cost:.6f})")
```

**Cost per query tracking:**
```python
for query in queries:
    result = pipeline.generate(query)
    tracker.track_query_complete()

report = tracker.get_report()
print(f"Avg cost per query: ${report['summary']['cost_per_query']:.6f}")
```

---

## Performance Metrics

### Pipeline Stage Metrics

Each pipeline stage tracks:
- **Processing time** - Duration for each batch/query
- **Entity counts** - Number of entities processed
- **Success rate** - Percentage of successful operations
- **Error rate** - Failures per batch

### Key Performance Indicators

**Stage 1 (Crawling):**
- Videos processed per hour
- Transcription time per video
- Whisper API success rate

**Stage 2 (Extraction):**
- Entities extracted per video
- LLM extraction time
- Fuzzy deduplication efficiency

**Stage 3 (Enrichment):**
- Canonicalization success rate
- Enrichment time per entity
- Consensus building accuracy

**Stage 4 (Vectorization):**
- Embeddings generated per minute
- ChromaDB indexing time
- Geohash search performance

**Stage 5 (RAG):**
- Query response time
- Itinerary generation success rate
- Re-ranking latency

### Monitoring Commands

**Check pipeline status:**
```bash
./crawl.sh status
```

**View stage metadata:**
```bash
./crawl.sh show-metadata --stage 5
```

---

## Error Monitoring

### Error Tracking

Errors are logged with:
- Timestamp
- Error type and message
- Stack trace
- Context (video_id, entity_id, query, etc.)

**See also:** [error-handling.md](../06-operations/error-handling.md) for detailed error handling patterns.

### Common Monitoring Patterns

**Check for failed videos:**
```bash
aws s3 ls s3://travel-ai-pipeline-data/stage1_metadata/processed/ \
    | grep "error"
```

**Monitor ChromaDB collection size:**
```python
from src.chroma.client import get_chroma_client

client = get_chroma_client()
collection = client.get_collection("travel_entities")
print(f"Total entities: {collection.count()}")
```

**Track entity lifecycle states:**
- See [entity-lifecycle.md](../04-reference/entity-lifecycle.md)

---

## Production Monitoring Checklist

When deploying to production:

- [ ] Configure centralized logging (CloudWatch, ELK, etc.)
- [ ] Set up cost tracking with budget alerts
- [ ] Monitor ChromaDB performance and capacity
- [ ] Track API rate limits (YouTube, Whisper, LLM providers)
- [ ] Set up error alerting (email, Slack, PagerDuty)
- [ ] Monitor S3 storage costs
- [ ] Track pipeline throughput metrics
- [ ] Configure automatic cost report generation

---

## Best Practices

1. **Set budget limits:** Always configure budget limits for RAG pipeline to prevent unexpected costs
2. **Monitor per-query costs:** Track cost per query to identify expensive patterns
3. **Review cost reports weekly:** Identify optimization opportunities
4. **Cache results:** Use caching to avoid re-generating same queries
5. **Save reports regularly:** Keep historical cost data for trend analysis
6. **Monitor error rates:** High error rates indicate pipeline issues
7. **Track performance trends:** Monitor processing times over time

---

## References

- Cost Tracker Implementation: `src/utils/rag_cost_tracker.py`
- Logging Configuration: `src/utils/logging.py`
- Error Handling Guide: [error-handling.md](../06-operations/error-handling.md)
- Production Runbook: [runbook.md](../06-operations/runbook.md)
