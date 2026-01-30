# Claude Code Team Cache & Rules System (Future Proposal)

> **Status:** Parked / Future Enhancement
> **Date:** 2026-01-30
> **Purpose:** Proposal for addressing team context loss and onboarding challenges

---

## Overview

Create a version-controlled cache and rules system in `.claude/` directory that enables ANY Claude Code instance to instantly understand the entire TravelAI project with latest context. This solves the **context loss & onboarding problem** across 3 team members.

**Core Principle:** Cache is a machine-readable knowledge base that Claude reads at session start to understand "all the nooks and crannies" of the project.

---

## Problem Statement

- **Current:** Each Claude Code session starts fresh with zero context
- **Impact:** Team members face context loss, slow onboarding, repeated mistakes
- **Solution:** Shared, version-controlled cache + behavioral rules

---

## Implementation Plan

### Phase 1: Directory Structure Setup

Create `.claude/` subdirectories for cache, rules, and prompts:

```
.claude/
├── cache/                          # Machine-readable project context
│   ├── project-context.json       # Main cache (architecture, commands, patterns)
│   ├── recent-changes.json        # Rolling 30-day change log
│   └── architecture-decisions.md  # ADRs (Architecture Decision Records)
│
├── rules/                          # Claude behavioral rules
│   ├── code-quality.yml           # Quality checks (Black, tests, secrets)
│   ├── safety.yml                 # Safety guardrails (dry-run, backups)
│   ├── workflow.yml               # Git workflow (branches, commits, PRs)
│   └── documentation.yml          # Doc requirements
│
├── prompts/                        # Reusable LLM prompt templates
│   ├── stage2-extraction.md       # Stage 2 entity extraction prompt
│   ├── stage3-enrichment.md       # Stage 3 enrichment prompt
│   └── stage5-rag.md              # Stage 5 RAG generation prompt
│
├── README.md                       # Human-readable guide
└── settings.local.json             # (Existing) Personal settings - KEEP GITIGNORED
```

**Why this structure:**
- `.claude/cache/` - Version controlled, shared context
- `.claude/rules/` - Version controlled, behavioral guardrails
- `.claude/prompts/` - Version controlled, reusable LLM prompts
- `settings.local.json` - REMAINS gitignored (personal preferences)

---

### Phase 2: Git Configuration

**Update `.gitignore` (Line 65):**

```diff
# Change from:
-.claude/
+# Claude Code - Personal settings only
+.claude/settings.local.json
+.claude/cache/.cache-lock
```

**Result:**
- ✅ `.claude/cache/` → Version controlled
- ✅ `.claude/rules/` → Version controlled
- ✅ `.claude/prompts/` → Version controlled
- ❌ `.claude/settings.local.json` → Gitignored (personal)
- ❌ `.claude/cache/.cache-lock` → Gitignored (concurrency)

**Create `.gitattributes` (NEW FILE):**

```
# Auto-merge non-conflicting JSON sections
.claude/cache/project-context.json merge=union
.claude/cache/recent-changes.json merge=union
```

This prevents most merge conflicts in cache files.

---

### Phase 3: Create Main Cache File

**File:** `.claude/cache/project-context.json`

**Purpose:** Comprehensive machine-readable project knowledge base

**Schema (Top-Level Keys):**

```json
{
  "$schema": "https://json-schema.org/draft/07/schema#",
  "version": "1.0.0",
  "last_updated": "2026-01-30T17:54:00Z",
  "updated_by": "team_member_name",

  "project": {
    "name": "TravelAI",
    "description": "Transform YouTube travel vlogs into personalized itineraries",
    "repository": "https://github.com/Divish1032/travel-ai-core",
    "primary_language": "Python 3.11+",
    "team_size": 3
  },

  "architecture": {
    "overview": "5-stage data pipeline",
    "stages": [
      {
        "id": "stage1",
        "name": "YouTube Crawling",
        "commands": ["./crawl.sh youtube --input urls.txt"],
        "primary_files": ["src/crawlers/youtube_crawler.py", "cli/crawl.py"],
        "outputs": "S3: raw/new/",
        "performance": {"time": "2-5 min/video", "cost": "$0.006"}
      },
      {
        "id": "stage2",
        "name": "LLM Entity Extraction",
        "commands": ["./crawl.sh process-stage2"],
        "primary_files": ["src/processors/stage2_extractor.py"],
        "features": ["semantic_chunking", "fuzzy_dedup"],
        "performance": {"time": "15-20s (short), 2-4 min (long)", "cost": "$0.0023-0.03"}
      },
      {
        "id": "stage3",
        "name": "Canonicalization",
        "commands": ["./crawl.sh process-stage3"],
        "features": ["4_tier_dedup", "consensus_building", "geocoding"],
        "performance": {"time": "~10 min for 1000 entities"}
      },
      {
        "id": "stage4",
        "name": "Vectorization",
        "commands": ["./crawl.sh process-stage4 --embedding-types all"],
        "features": ["gte-large embeddings", "geohash search"]
      },
      {
        "id": "stage5",
        "name": "RAG Itinerary Generation",
        "commands": ["./crawl.sh generate-itinerary -q \"QUERY\""],
        "features": ["7_phase_rag", "hallucination_detection"]
      }
    ]
  },

  "common_commands": {
    "pipeline": [
      {"name": "View status", "command": "./crawl.sh status"},
      {"name": "Dashboard", "command": "./crawl.sh dashboard"},
      {"name": "Run tests", "command": "pytest tests/ -v"}
    ],
    "recovery": [
      {"name": "Reset Stage 2", "command": "./crawl.sh reset-stage2 --all --dry-run"},
      {"name": "Audit S3", "command": "./crawl.sh audit --stage stage_2_extract"}
    ]
  },

  "patterns": {
    "code_organization": {
      "cli_commands": "cli/ directory - one file per command",
      "processors": "src/processors/ - stage2, stage3, stage4 processors",
      "storage": "src/storage/ - S3 client, metadata tracker"
    },
    "naming_conventions": {
      "entities": "ATT_001 (attraction), RST_001 (restaurant)",
      "commands": "./crawl.sh {action} [--flags]"
    },
    "testing_patterns": {
      "unit_tests": "tests/unit/test_stage{N}.py",
      "markers": "@pytest.mark.integration, @pytest.mark.slow"
    }
  },

  "gotchas": [
    {
      "issue": "ChromaDB connection errors",
      "solution": "Check CHROMADB_API_KEY in .env. Run ./crawl.sh check-stage5"
    },
    {
      "issue": "Stage 2 extraction quality",
      "solution": "Use semantic chunking (--semantic-chunking) for long videos"
    },
    {
      "issue": "Metadata inconsistencies",
      "solution": "Run ./crawl.sh audit --stage {stage} to find discrepancies"
    }
  ]
}
```

**Populate with:**
- All 5 pipeline stages (detailed breakdown)
- 40+ CLI commands from `crawl.sh`
- Code organization patterns from `docs/`
- Common gotchas from team experience
- Performance metrics, costs, rate limits

**Estimated size:** ~1200 lines JSON (machine-readable, comprehensive)

---

### Phase 4: Create Recent Changes Log

**File:** `.claude/cache/recent-changes.json`

**Purpose:** Rolling 30-day log of significant changes

**Schema:**

```json
{
  "changes": [
    {
      "date": "2026-01-30",
      "author": "team_member",
      "commit_hash": "48bcc00",
      "type": "refactor",
      "scope": "stage2",
      "summary": "Added semantic chunking for long videos",
      "files_changed": ["src/processors/stage2_extractor.py", "cli/process_stage2.py"],
      "impact": "Breaking: Must use --semantic-chunking flag for long videos",
      "commands_affected": ["./crawl.sh process-stage2"],
      "related_docs": ["docs/03-pipeline-stages/stage2-extraction.md"]
    }
  ]
}
```

**Update workflow:**
- PR author adds entry when merging significant changes
- Weekly sync (Friday): Prune entries older than 30 days
- Auto-sorted by date (most recent first)

---

### Phase 5: Create Architecture Decisions Record

**File:** `.claude/cache/architecture-decisions.md`

**Purpose:** Record key architectural decisions with rationale

**Format:** Markdown ADRs

```markdown
# Architecture Decision Records

## ADR-001: Use Gemini as Primary LLM Provider
**Date:** 2025-12-15
**Status:** Accepted
**Context:** Need cost-effective LLM for entity extraction (Stage 2) and enrichment (Stage 3).
**Decision:** Use Gemini 2.5 Flash Lite as primary, DeepSeek as secondary.
**Rationale:**
- Gemini: Free tier (15 req/min, 1M tokens/min, 1500 req/day)
- DeepSeek: Good balance ($0.14/1M tokens)
- OpenAI: Most expensive ($0.15/1M tokens)
**Consequences:** Must handle Gemini rate limits (15 req/min)
**Related Files:** `src/llm/gemini_provider.py`, `.env.example`

## ADR-002: 4-Tier Deduplication Strategy
**Date:** 2025-11-20
**Status:** Accepted
**Context:** Need to deduplicate entities across 100+ videos.
**Decision:** Use 4-tier approach: Exact → Fuzzy → Semantic → Location.
**Rationale:** Handles typos, translations, and geographic variations
**Consequences:** 30-40% deduplication rate, ~10 min for 1000 entities
**Related Files:** `src/processors/stage3_canonicalizer.py`

## ADR-003: Use ChromaDB Cloud vs Local
**Date:** 2025-12-01
**Status:** Accepted
**Context:** Need vector database for semantic search.
**Decision:** Use ChromaDB Cloud (managed service).
**Rationale:** No self-hosting overhead, easy team collaboration, free tier
**Consequences:** Must have CHROMADB_API_KEY, internet required
**Related Files:** `src/vectordb/chroma_client.py`
```

**Populate with:**
- Extract from git history: `git log --grep="ADR" --all`
- Review recent major PRs for decisions
- Document 3-5 critical decisions

---

### Phase 6: Create Rules Files

#### **6.1: Code Quality Rules** (`.claude/rules/code-quality.yml`)

```yaml
version: "1.0.0"
description: "Code quality checks and standards for TravelAI"

pre_commit_checks:
  - name: "Run Black formatter"
    command: "black src/ cli/ tests/ --line-length 100"
    required: true
    fail_on_error: true

  - name: "Run tests"
    command: "pytest tests/ -v"
    required: true
    fail_on_error: true
    skip_for_branches: ["docs/*"]

  - name: "Check for secrets"
    command: "grep -r 'API_KEY.*=.*[A-Za-z0-9]' src/ cli/ || echo 'No secrets found'"
    required: true
    fail_on_error: true

code_standards:
  python:
    style_guide: "PEP 8"
    formatter: "Black (line length: 100)"
    type_hints: "Required for all public functions"
    docstrings: "Required for all public functions (Google style)"

testing_requirements:
  coverage_minimum: 60
  test_categories:
    - name: "Unit tests"
      location: "tests/unit/"
      required: true

naming_conventions:
  files: "snake_case (e.g., stage2_extractor.py)"
  classes: "PascalCase (e.g., S3Client)"
  functions: "snake_case (e.g., extract_entities)"
```

#### **6.2: Safety Rules** (`.claude/rules/safety.yml`)

```yaml
version: "1.0.0"
description: "Safety guardrails for TravelAI operations"

dangerous_operations:
  - operation: "S3 bucket deletion"
    commands: ["aws s3 rb"]
    rule: "ALWAYS deny"

  - operation: "Force git push to main"
    commands: ["git push --force origin main"]
    rule: "ALWAYS deny"

  - operation: "Reset all stages without backup"
    commands: ["./crawl.sh reset-all --force"]
    rule: "REQUIRE confirmation + backup flag"
    safe_alternative: "./crawl.sh reset-all --backup --dry-run"

  - operation: "Delete canonical entities (Stage 3)"
    commands: ["./crawl.sh reset-stage3 --all"]
    rule: "REQUIRE dry-run first"
    safe_alternative: "./crawl.sh reset-stage3 --all --dry-run"

required_flags:
  - operation: "Stage resets"
    flag: "--dry-run"
    enforcement: "ALWAYS run dry-run first"

  - operation: "Pipeline resets"
    flag: "--backup"
    enforcement: "ALWAYS backup before reset-all"

cost_guardrails:
  stage2_extraction:
    max_cost_per_video: "$0.03"
    alert_threshold: "$0.05"

  stage5_itinerary:
    max_cost_per_generation: "$0.03"
    alert_threshold: "$0.03"

anti_patterns:
  - pattern: "Skipping --dry-run for destructive operations"
    consequence: "Data loss, hours of reprocessing"
    prevention: "ALWAYS dry-run first"

  - pattern: "Not updating cache after major changes"
    consequence: "Team context loss"
    prevention: "Update .claude/cache/ after PRs"
```

#### **6.3: Workflow Rules** (`.claude/rules/workflow.yml`)

```yaml
version: "1.0.0"
description: "Git, commit, and PR workflow standards"

git_workflow:
  branching:
    main_branch: "main"
    naming_convention: "{type}/{description}"
    examples:
      - "feature/semantic-chunking"
      - "fix/stage2-extraction-bug"
      - "docs/api-reference-update"

  commit_messages:
    format: "Conventional Commits"
    structure: "{type}({scope}): {subject}"
    types:
      - "feat: New feature"
      - "fix: Bug fix"
      - "docs: Documentation changes"
      - "refactor: Code refactoring"
      - "test: Test changes"
      - "chore: Maintenance tasks"

  pull_requests:
    review_requirements:
      - "At least 1 approval"
      - "All tests pass"
      - "Cache updated (if major changes)"
    merge_strategy: "Squash and merge"

cache_maintenance:
  when_to_update:
    - "After merging feature PRs"
    - "After architectural changes"
    - "Weekly sync (if many small changes)"

  update_process:
    1: "Edit .claude/cache/project-context.json"
    2: "Add entry to .claude/cache/recent-changes.json"
    3: "Commit cache with PR"
```

#### **6.4: Documentation Rules** (`.claude/rules/documentation.yml`)

```yaml
version: "1.0.0"
description: "Documentation requirements and standards"

when_to_update_docs:
  - trigger: "New API endpoints added"
    files: ["docs/04-reference/api-reference.md"]

  - trigger: "New CLI commands added"
    files: ["docs/04-reference/cli-commands.md"]

  - trigger: "Pipeline stage modified"
    files: ["docs/03-pipeline-stages/stage{N}-*.md"]

  - trigger: "New environment variable added"
    files: [".env.example", "docs/04-reference/configuration.md"]

  - trigger: "Architecture decision made"
    files: [".claude/cache/architecture-decisions.md"]

docstring_requirements:
  required_for: ["All public functions", "All classes"]
  format: "Google Style"

comment_guidelines:
  when_to_comment:
    - "Complex algorithms"
    - "Non-obvious behavior"
    - "Workarounds"
    - "Magic numbers"
```

---

### Phase 7: Create Prompt Templates

**File:** `.claude/prompts/stage2-extraction.md`

Extract the actual prompts from:
- `src/processors/stage2_extractor.py` (entity extraction prompt)
- `src/processors/stage3_canonicalizer.py` (enrichment prompt)
- `src/rag/` (RAG generation prompts)

Store as markdown templates for reuse and version control.

---

### Phase 8: Create Human-Readable Guide

**File:** `.claude/README.md`

```markdown
# Claude Code Team Cache System

## What is this?

A shared knowledge base that helps ANY Claude Code instance instantly understand the TravelAI project.

## How it works

1. **Claude reads cache at session start** → Gets full project context
2. **Claude enforces rules** → Prevents mistakes, ensures quality
3. **Team updates cache** → Knowledge stays current

## Files

- `cache/project-context.json` - Main cache (architecture, commands, patterns)
- `cache/recent-changes.json` - Rolling 30-day change log
- `cache/architecture-decisions.md` - Key architectural decisions (ADRs)
- `rules/*.yml` - Behavioral rules (safety, quality, workflow, docs)

## When to update cache

| Trigger | Update | When |
|---------|--------|------|
| New feature | project-context.json | Before PR merge |
| Bug fix | recent-changes.json | After PR merge |
| Architecture change | architecture-decisions.md | Before PR merge |

## How to update cache

1. Edit `.claude/cache/project-context.json` (add to relevant section)
2. Add entry to `.claude/cache/recent-changes.json`
3. Commit with PR: `git add .claude/cache/ && git commit`

## Example

```bash
# After adding semantic chunking feature
vim .claude/cache/project-context.json
# Add semantic_chunking to stage2 features array

vim .claude/cache/recent-changes.json
# Add entry:
{
  "date": "2026-01-30",
  "summary": "Added semantic chunking for long videos",
  "impact": "Breaking: Must use --semantic-chunking flag"
}

git add .claude/cache/
git commit -m "chore(cache): Update cache after semantic chunking"
```

## Weekly sync (Friday 4pm)

Rotating team member:
1. Reviews last week's commits
2. Adds any missing entries to recent-changes.json
3. Prunes entries older than 30 days
4. Commits sync
```

---

## Critical Files to Modify/Create

### Files to CREATE (8 new files):

1. **`.claude/cache/project-context.json`** (~1200 lines)
2. **`.claude/cache/recent-changes.json`** (~100 lines)
3. **`.claude/cache/architecture-decisions.md`** (~200 lines)
4. **`.claude/rules/code-quality.yml`** (~100 lines)
5. **`.claude/rules/safety.yml`** (~150 lines)
6. **`.claude/rules/workflow.yml`** (~100 lines)
7. **`.claude/rules/documentation.yml`** (~80 lines)
8. **`.claude/README.md`** (~100 lines)

### Files to MODIFY (2 files):

1. **`.gitignore`** (Line 65)
2. **`docs/07-development/contributing.md`** (add Cache Maintenance section)

---

## Expected Outcome

### Before Implementation:
- ❌ Each Claude session starts fresh
- ❌ Context loss between team members
- ❌ Repeated mistakes (no guardrails)
- ❌ Slow onboarding

### After Implementation:
- ✅ Claude instantly knows entire project
- ✅ Shared context across all team members
- ✅ Enforced safety rules (dry-run, backups)
- ✅ Consistent code quality
- ✅ Fast onboarding (1-2 min context load)

---

## Future Considerations

When the team is ready to implement this:

1. Review and update the proposal based on current needs
2. Start with a minimal MVP (just project-context.json + safety.yml)
3. Iterate based on team feedback
4. Consider automation (git hooks, cache validation) in Phase 2
