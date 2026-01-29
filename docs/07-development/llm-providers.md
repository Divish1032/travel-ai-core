# LLM Providers

Guide to configuring and switching between LLM providers in TravelAI.

---

## Supported Providers

TravelAI supports 3 LLM providers:

1. **Gemini** (Google) - Recommended, cheapest
2. **DeepSeek** - Good balance of cost and quality
3. **OpenAI** - Highest quality, highest cost

---

## Configuration

### Set Provider in .env

```bash
# Choose one
LLM_PROVIDER=gemini    # Recommended
# LLM_PROVIDER=deepseek
# LLM_PROVIDER=openai
```

### Provider-Specific Settings

**Gemini:**
```bash
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash-lite  # Or: gemini-1.5-pro
```

**DeepSeek:**
```bash
DEEPSEEK_API_KEY=your_key_here
DEEPSEEK_MODEL=deepseek-chat
```

**OpenAI:**
```bash
OPENAI_API_KEY=your_key_here
# Uses gpt-4o-mini by default
```

---

## Cost Comparison

### Per 1M Tokens

| Provider | Input | Output | Total (50/50) |
|----------|-------|--------|---------------|
| **Gemini 2.5 Flash Lite** | $0.075 | $0.30 | **$0.1875** |
| DeepSeek Chat | $0.14 | $0.28 | $0.21 |
| OpenAI GPT-4o-mini | $0.150 | $0.600 | $0.375 |

### Per 100 Videos (Stages 2-3)

| Provider | Stage 2 | Stage 3 | Total |
|----------|---------|---------|-------|
| **Gemini** | ~$0.40 | ~$0.10 | **~$0.50** |
| DeepSeek | ~$0.60 | ~$0.15 | ~$0.75 |
| OpenAI | ~$1.00 | ~$0.25 | ~$1.25 |

### Per Itinerary (Stage 5)

| Provider | Cost |
|----------|------|
| **Gemini** | **~$0.010** |
| DeepSeek | ~$0.015 |
| OpenAI | ~$0.020 |

**Recommendation:** Use Gemini for best cost/quality balance

---

## Quality Comparison

### Entity Extraction (Stage 2)

| Provider | Quality | Speed | Notes |
|----------|---------|-------|-------|
| Gemini | ⭐⭐⭐⭐ | Fast | Good entity recognition, occasionally misses nuances |
| DeepSeek | ⭐⭐⭐⭐ | Fast | Comparable to Gemini, good VIBE inference |
| OpenAI | ⭐⭐⭐⭐⭐ | Medium | Best entity extraction, excellent context understanding |

### LLM Verification (Stage 3)

| Provider | Quality | Speed | Notes |
|----------|---------|-------|-------|
| Gemini | ⭐⭐⭐⭐ | Fast | Reliable for duplicate verification |
| DeepSeek | ⭐⭐⭐⭐ | Fast | Good consensus decisions |
| OpenAI | ⭐⭐⭐⭐⭐ | Medium | Most accurate, best for ambiguous cases |

### RAG Generation (Stage 5)

| Provider | Quality | Speed | Notes |
|----------|---------|-------|-------|
| Gemini | ⭐⭐⭐⭐ | Fast | Good itineraries, occasionally generic |
| DeepSeek | ⭐⭐⭐⭐ | Fast | Creative recommendations, good explanations |
| OpenAI | ⭐⭐⭐⭐⭐ | Medium | Most personalized, best explanations |

---

## Switching Providers

### Change Provider

```bash
# Edit .env
LLM_PROVIDER=deepseek  # Change from gemini to deepseek

# No code changes needed - automatic
./crawl.sh process-stage2
```

### Fallback Strategy

Configure fallback providers in case primary fails:

```python
# src/llm/factory.py (example)
providers = [
    os.getenv('LLM_PROVIDER', 'gemini'),  # Primary
    'deepseek',                            # Fallback 1
    'openai'                               # Fallback 2
]
```

---

## Provider-Specific Features

### Gemini

**Pros:**
- Cheapest option
- Fast response times
- Good multilingual support
- High rate limits (15 req/min free tier)

**Cons:**
- Occasionally less nuanced than OpenAI
- May miss subtle context

**Best For:**
- Production use (cost-effective)
- High-volume processing
- Budget-conscious users

---

### DeepSeek

**Pros:**
- Good cost/quality balance
- Fast response times
- Competitive with GPT-4o-mini
- Good for technical reasoning

**Cons:**
- Smaller context window than OpenAI
- Less brand recognition

**Best For:**
- Balance of cost and quality
- Users who want alternatives to big tech

---

### OpenAI

**Pros:**
- Highest quality responses
- Best context understanding
- Most personalized outputs
- Excellent for complex reasoning

**Cons:**
- Most expensive option
- Slower response times
- Lower rate limits

**Best For:**
- High-quality requirements
- Complex itineraries
- Users who prioritize quality over cost

---

## Rate Limits

### Free Tiers

| Provider | Requests/Min | Tokens/Min | Requests/Day |
|----------|--------------|------------|--------------|
| Gemini | 15 | 1M | 1,500 |
| DeepSeek | 10 | 100k | No limit |
| OpenAI | 3 | 200k | No limit |

**Note:** Paid tiers have much higher limits

---

## Testing Different Providers

```bash
# Test with Gemini
LLM_PROVIDER=gemini ./crawl.sh process-stage2 --limit 1

# Test with DeepSeek
LLM_PROVIDER=deepseek ./crawl.sh process-stage2 --limit 1

# Test with OpenAI
LLM_PROVIDER=openai ./crawl.sh process-stage2 --limit 1

# Compare costs
cat logs/cost_tracking.log
```

---

## References

- **Configuration:** [configuration.md](../04-reference/configuration.md)
- **Installation:** [installation.md](../01-getting-started/installation.md)
- **Gemini API:** https://ai.google.dev/
- **DeepSeek API:** https://platform.deepseek.com/
- **OpenAI API:** https://platform.openai.com/
