# TravelAI – Internal VIBE Framework (v1)

## Purpose of this Document
This document defines the **VIBE framework** used internally by TravelAI to translate user preferences into concrete itinerary decisions.

VIBE is not a personality quiz or a UI feature. It is a **decision constraint system** that guides what the AI includes, excludes, prioritizes, and how it explains recommendations.

This spec is meant for:
- Product alignment (founders, PMs)
- LLM prompt design
- Evaluation & metrics

---

## What VIBE Means at TravelAI

**VIBE = how a user wants their trip to *feel***.

It governs:
- Experience selection
- Daily pacing
- Transport choices
- Accommodation areas
- Tone and confidence of recommendations

**Key principle:**
> Two users visiting the same cities for the same duration should receive meaningfully different itineraries.

---

## VIBE Dimensions (v1 – Final)

TravelAI uses **five core VIBE dimensions** in v1. These are intentionally limited to avoid overfitting and user fatigue.

### 1. Trip Intent (Primary Driver)
**Question answered:** Why is the user traveling?

Possible intents:
- Calm & slow
- Explore & discover
- Food & cafes
- Scenic & nature
- Social & lively

**Used to decide:**
- Which experience categories dominate
- What to down-rank or exclude
- Crowd tolerance

---

### 2. Pace Preference
**Question answered:** How full should each day feel?

Spectrum:
- Very relaxed
- Balanced
- Packed

**Used to decide:**
- Number of activities per day
- Transit buffer times
- Early morning / late evening usage

---

### 3. Comfort vs Adventure
**Question answered:** How much uncertainty or friction does the user enjoy?

Spectrum:
- Comfort-first
- Balanced
- Adventure-seeking

**Used to decide:**
- Transport modes (flight vs overnight bus, train vs car)
- Accommodation areas (central vs remote)
- Activity risk level

---

### 4. Spending Philosophy
**Question answered:** How does the user emotionally relate to spending money?

Categories:
- Value-conscious but comfortable
- Mid-range, good experiences
- Willing to spend if it feels worth it

**Used to decide:**
- Restaurant tiers
- Hotel class
- Experience trade-offs

(Note: No absolute budgets are collected in v1.)

---

### 5. Structure Preference
**Question answered:** How planned does the user want the trip to feel?

Spectrum:
- Structured & planned
- Flexible framework
- Go-with-the-flow

**Used to decide:**
- Itinerary rigidity
- Presence of free exploration blocks
- How strongly recommendations are phrased

---

## How VIBE Is Represented Internally

Each user session generates a **VIBE profile**, expressed as structured signals (not shown to the user).

Example:
```json
{
  "primary_intent": "calm",
  "secondary_intents": ["food", "scenic"],
  "daily_activity_cap": 3,
  "buffer_time_multiplier": 1.4,
  "transport_risk_tolerance": "low",
  "price_sensitivity": "medium",
  "itinerary_rigidity": "medium"
}
```

This profile is passed as **hard constraints + soft biases** into itinerary generation.

---

## How VIBE Influences Itinerary Generation

### Hard Constraints
Applied deterministically or via rules:
- Maximum activities per day
- Minimum buffer times
- City sequencing feasibility

### Soft Biases
Applied via LLM prompting and re-ranking:
- Which experiences are prioritized
- Which attractions are avoided or softened
- Tone of explanation (assertive vs suggestive)

---

## What VIBE Is NOT

- ❌ Not a visible score
- ❌ Not a personality label
- ❌ Not a static user profile

VIBE is session-based and can change per trip.

---

## Product Principles Around VIBE

- Fewer questions > more inference
- Allow skipping; infer later if needed
- Always explain *why* something fits the user
- Prefer saying “this may not suit your vibe” over generic inclusion

---

## v1 Scope Guardrails

In v1, VIBE **will not**:
- Optimize purely for cost
- Guarantee popularity or must-see coverage
- Replace user control

In v1, VIBE **must**:
- Reduce planning effort
- Prevent obvious mismatches
- Feel human and thoughtful

---

## Success Criteria (Internal)

A VIBE-aligned plan is successful if:
- Users feel understood without over-explaining
- Regeneration requests decrease after edits
- Users accept exclusions (e.g., skipping hyped spots)
- Itineraries differ clearly across VIBE profiles

---

**This document is the single source of truth for VIBE in v1.**

