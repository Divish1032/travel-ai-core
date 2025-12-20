# RAG Cost Tracking Guide

This guide shows how to integrate cost tracking into your Stage 5 RAG pipeline.

## Quick Start

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

---

## Integration with Pipeline Components

### 1. Update RAGPipeline to use tracker

```python
# In src/rag/pipeline.py

from src.utils.rag_cost_tracker import RAGCostTracker

class RAGPipeline:
    def __init__(self, budget_limit: Optional[float] = None):
        # ... existing initialization
        self.cost_tracker = RAGCostTracker(budget_limit=budget_limit)

    def generate(self, query: str, **kwargs):
        # ... existing code

        # Phase 1: Parse Intent
        intent = self.intent_parser.parse_query(query)
        self.cost_tracker.track_phase(
            'intent_parsing',
            cost=self.intent_parser.total_cost,
            input_tokens=getattr(self.intent_parser, 'last_input_tokens', 0),
            output_tokens=getattr(self.intent_parser, 'last_output_tokens', 0)
        )

        # Phase 3: Re-rank
        reranked = self.reranker.rerank_candidates(candidates, intent)
        self.cost_tracker.track_phase(
            're_ranking',
            cost=self.reranker.total_cost,
            input_tokens=getattr(self.reranker, 'last_input_tokens', 0),
            output_tokens=getattr(self.reranker, 'last_output_tokens', 0)
        )

        # Phase 5: Generate
        itinerary = self.generator.generate_itinerary(context, intent)
        self.cost_tracker.track_phase(
            'generation',
            cost=self.generator.total_cost,
            input_tokens=getattr(self.generator, 'last_input_tokens', 0),
            output_tokens=getattr(self.generator, 'last_output_tokens', 0)
        )

        # Phase 7: Narrative
        if not skip_narrative:
            narrative = self.narrative_gen.generate_narrative(itinerary, intent)
            self.cost_tracker.track_phase(
                'narrative',
                cost=self.narrative_gen.total_cost,
                input_tokens=getattr(self.narrative_gen, 'last_input_tokens', 0),
                output_tokens=getattr(self.narrative_gen, 'last_output_tokens', 0)
            )

        # Mark query complete
        self.cost_tracker.track_query_complete()

        # Add cost tracking to result
        result['cost_report'] = self.cost_tracker.get_report()

        return result
```

### 2. Update individual components to track tokens

```python
# In src/rag/intent_parser.py

class IntentParser:
    def __init__(self):
        # ... existing code
        self.last_input_tokens = 0
        self.last_output_tokens = 0

    def parse_query(self, query: str):
        # ... existing code

        # After LLM call
        result = extract_with_llm(prompt, ...)

        if result['success']:
            self.last_input_tokens = result['tokens_used']['input']
            self.last_output_tokens = result['tokens_used']['output']
            self.total_cost += result['cost_usd']

        return intent
```

### 3. CLI Integration

```python
# In cli/generate_itinerary.py

from src.rag.pipeline import RAGPipeline

@click.command()
@click.option('--query', '-q', required=True)
@click.option('--budget-limit', type=float, help='Budget limit in USD')
@click.option('--save-cost-report', is_flag=True, help='Save cost report')
def generate(query, budget_limit, save_cost_report):
    """Generate itinerary with cost tracking."""

    # Initialize pipeline with budget
    pipeline = RAGPipeline(budget_limit=budget_limit)

    try:
        # Generate
        result = pipeline.generate(query)

        # Print itinerary
        click.echo(result['formatted_output'])

        # Print cost summary
        pipeline.cost_tracker.print_summary()

        # Optionally save report
        if save_cost_report:
            filepath = pipeline.cost_tracker.save_report()
            click.echo(f"\n💾 Cost report saved to: {filepath}")

    except BudgetExceededError as e:
        click.echo(f"\n❌ Budget exceeded: {e}", err=True)
        pipeline.cost_tracker.print_summary()
        raise click.Abort()
```

---

## Cost Report Example

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
    "re_ranking": {
      "total_cost": 0.0015,
      "count": 1,
      "avg_cost": 0.0015,
      "input_tokens": 1500,
      "output_tokens": 200,
      "total_tokens": 1700,
      "percentage": 12.4
    },
    "generation": {
      "total_cost": 0.0080,
      "count": 1,
      "avg_cost": 0.0080,
      "input_tokens": 3000,
      "output_tokens": 1500,
      "total_tokens": 4500,
      "percentage": 66.1
    },
    "narrative": {
      "total_cost": 0.0025,
      "count": 1,
      "avg_cost": 0.0025,
      "input_tokens": 1200,
      "output_tokens": 800,
      "total_tokens": 2000,
      "percentage": 20.7
    }
  },
  "token_usage": {
    "total": 8350,
    "input": 5800,
    "output": 2550,
    "input_percentage": 69.5,
    "output_percentage": 30.5
  },
  "cost_efficiency": {
    "cost_per_1k_input_tokens": 0.002086,
    "cost_per_1k_output_tokens": 0.004745,
    "cost_per_1k_total_tokens": 0.001449
  },
  "budget": {
    "limit": 0.10,
    "used": 0.0121,
    "remaining": 0.0879,
    "percentage_used": 12.1
  }
}
```

---

## Budget Alerts

The tracker automatically warns when approaching budget limits:

```python
# Set budget limit
tracker = RAGCostTracker(budget_limit=0.01)  # $0.01 limit

# 80% warning
# ⚠️  Approaching budget limit: $0.0080 / $0.01 (80.0%)

# 100% error
# BudgetExceededError: Budget limit exceeded: $0.0101 > $0.01
```

---

## Analytics & Optimization

### Find most expensive phase:
```python
phase, cost = tracker.get_most_expensive_phase()
print(f"Most expensive: {phase} (${cost:.6f})")
# Output: Most expensive: generation ($0.0080)
```

### Cost per query tracking:
```python
# Process multiple queries
for query in queries:
    result = pipeline.generate(query)
    tracker.track_query_complete()

# Get average cost per query
report = tracker.get_report()
print(f"Avg cost per query: ${report['summary']['cost_per_query']:.6f}")
```

### Batch cost analysis:
```python
# Generate batch
queries = ["5 days Bangkok", "3 days Phuket", "7 days Chiang Mai"]
results = pipeline.generate_batch(queries)

# Print cumulative cost report
pipeline.cost_tracker.print_summary()

# Save detailed report
pipeline.cost_tracker.save_report(format='txt')
```

---

## Best Practices

1. **Set budget limits**: Always set a budget limit to prevent unexpected costs
2. **Monitor per-query costs**: Track cost per query to identify expensive patterns
3. **Optimize expensive phases**: Focus optimization on the most expensive phase (usually generation)
4. **Use skip-narrative**: Skip narrative generation during testing to reduce costs
5. **Cache results**: Use pipeline caching to avoid re-generating same queries
6. **Save reports**: Regularly save cost reports for historical analysis

---

## Cost Optimization Tips

### 1. Use cheaper models for simple tasks
```python
# Use DeepSeek for intent parsing (cheaper)
intent_parser = IntentParser(provider='deepseek')

# Use Gemini for generation (good quality/cost ratio)
generator = ItineraryGenerator(provider='gemini')
```

### 2. Skip narrative during development
```python
result = pipeline.generate(query, skip_narrative=True)
# Saves ~20% of total cost
```

### 3. Reduce retry attempts
```python
result = pipeline.generate(query, max_retries=1)
# Saves cost on validation failures
```

### 4. Batch process with caching
```python
pipeline = RAGPipeline(enable_cache=True)

# Duplicate queries return cached results (no cost)
result1 = pipeline.generate_cached("5 days Bangkok")
result2 = pipeline.generate_cached("5 days Bangkok")  # Free!
```

---

## Usage Examples

### Example 1: Development with budget control
```bash
./crawl.sh generate-itinerary \
    -q "5 days Bangkok solo budget" \
    --budget-limit 0.01 \
    --skip-narrative \
    --save-cost-report
```

### Example 2: Production batch processing
```python
from src.rag.pipeline import RAGPipeline

pipeline = RAGPipeline(
    enable_cache=True,
    budget_limit=1.0  # $1 for batch
)

queries = load_queries_from_file('user_queries.txt')
results = pipeline.generate_batch(queries, parallel=True)

# Save comprehensive cost report
pipeline.cost_tracker.save_report('batch_costs.json')
```

### Example 3: Cost monitoring dashboard
```python
# Real-time cost monitoring
tracker = get_global_tracker(budget_limit=10.0)

while True:
    query = get_next_query()
    result = pipeline.generate(query)

    # Check if approaching limit
    report = tracker.get_report()
    if report['budget']['percentage_used'] > 90:
        alert_admin("Budget 90% used!")
        break
```

---

## Files

- **Tracker**: `src/utils/rag_cost_tracker.py`
- **Reports**: `stage5-costs/*.json`
- **Integration**: Update `src/rag/pipeline.py` as shown above

---

## Summary

✅ Track costs across all RAG phases
✅ Set budget limits with automatic alerts
✅ Generate detailed cost reports
✅ Optimize spending with analytics
✅ Historical cost logging
✅ Simple integration with existing code

**Cost tracking is essential for production RAG systems!**
