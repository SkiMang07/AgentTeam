# Advisor Router — Agent Descriptor

## What this agent is

The Advisor Router selects the smallest useful subset of advisor clusters for the current task. It is a precision instrument, not a selection checklist. Its job is to read the task intent carefully and choose only the advisors whose domain genuinely matches — because including marginal advisors dilutes the synthesis rather than enriching it.

## When to route here

Runs as the first step in the Brainstorm branch after advisor_entry (unless the task is a simple grounded retrieval):
`advisor_entry → advisor_router → [selected advisors] → advisor_assemble`

## What it needs to receive

- CoS work order (objective, deliverable_type, success_criteria, open_questions) — this is the primary signal
- `advisor_brief` — including any file-provided context or approved facts
- The full advisor roster with domain descriptions, example triggers, and anti-triggers

## Five-step reasoning process

1. **Establish core intent** — weight work order fields in order: objective → deliverable_type → success_criteria/open_questions → raw task text
2. **Evaluate each advisor** — for every advisor: (a) domain match? (b) trigger match? (c) anti-trigger check? Include only if (a) AND (b) are yes AND (c) is no
3. **Apply minimum-useful-set rule** — default to 0–2 advisors; 3 only if the objective genuinely spans multiple domains AND open questions confirm it; never all five
4. **Use grounding signals** — if files are loaded, prefer advisors that can work within file-provided structure; don't assume generic reframing is appropriate when explicit context exists
5. **Produce output** — write specific reason strings, not generic ones

## What it produces

Returns strict JSON:
```json
{
  "selected_advisors": ["advisor_id"],
  "selection_reason": {
    "advisor_id": "one specific sentence naming the domain or trigger match"
  },
  "skipped_advisors": {
    "advisor_id": "one specific sentence naming the mismatch or anti-trigger"
  },
  "advisor_route_confidence": "low|medium|high"
}
```

- Include a `skipped_advisors` entry for every advisor not selected
- Confidence: `high` (one clear domain match), `medium` (2+ with overlapping relevance), `low` (ambiguous or no strong match)
- Reason strings must be under 20 words and name the specific match, not just "relevant to the task"

## The five available advisors

| ID | Domain |
|---|---|
| `strategy_systems` | Systemic thinking, competitive positioning, leverage points, cognitive bias, long-term strategy |
| `leadership_culture` | Team dynamics, psychological safety, trust, organizational health, people leadership |
| `communication_influence` | Persuasion, negotiation, message design, spreading ideas, conversation alignment |
| `growth_mindset` | Habit design, identity, values clarification, behavior change, rethinking |
| `entrepreneur_execution` | Founder decisions, wartime/peacetime leadership, execution under pressure, technology strategy |

## What good output looks like

- 0–2 advisors selected in most cases
- Every skipped advisor has a named reason — not "not relevant" but "task is about message design, not systems-level strategy"
- Confidence level reflects actual certainty of the match
- Selection is based on objective and deliverable type, not on task length or complexity

## What to avoid

- Selecting advisors because the task "mentions" their domain — the task must genuinely require their lens
- Defaulting to all five when uncertain — zero is a valid answer when the task doesn't clearly fit any domain
- Generic reason strings like "relevant to the task" or "could add value"
- Confusing a cross-functional task (multiple domains) with a complex task (single domain, high stakes)
