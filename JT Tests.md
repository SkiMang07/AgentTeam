# JT Tests

This file is the local regression artifact for JT evaluation only.

It is intentionally lightweight and focused on draft-quality failure modes that showed up in local JT runs.

## How to use this artifact

1. Run each prompt through the JT path (`--jt` or `--jt-mode`).
2. Save:
   - source draft
   - JT critique output
   - JT revised draft (if produced)
3. Score each run using the pass/fail checks below.
4. Treat any **Fail** as a regression candidate and track before changing prompts.

## Pass/Fail checks

### 1) Preserve material meaning

**Pass when:**
- Core facts, commitments, owners, and intent remain materially the same.
- JT clarifies language without changing what happened, what is being asked, or who is responsible.

**Fail when:**
- The revised text changes major meaning (scope, accountability, timeline, risk posture, or decision intent).
- JT introduces claims that were not in the source draft.

---

### 2) Light-touch editing for already strong drafts

**Pass when:**
- JT makes no edits or only minimal edits (small wording, grammar, or readability improvements).
- Structure and tone are preserved when draft is already clear and specific.

**Fail when:**
- JT rewrites large portions of a strong draft without clear quality benefit.
- JT introduces style churn (rephrasing for preference, not value).

---

### 3) No invented urgency or deadlines in external drafts

**Pass when:**
- JT keeps time language grounded in the source draft.
- Any urgency language is directly supported by provided context.

**Fail when:**
- JT adds unsupported urgency ("ASAP," "immediately," "critical now").
- JT invents deadlines, timing pressure, or escalation clocks absent from source.

---

### 4) No unsupported escalation in blame, certainty, or pressure

**Pass when:**
- JT keeps tone proportional to evidence.
- Confidence and attribution remain cautious unless explicitly supported.

**Fail when:**
- JT increases blame without evidence.
- JT converts uncertainty into certainty.
- JT adds pressure language that implies consequences not in source.

---

### 5) Draft-specific critique, not generic template critique

**Pass when:**
- JT feedback references concrete elements from the actual draft.
- Critique points are actionable for that specific text.

**Fail when:**
- JT returns generic boilerplate feedback that could apply to any draft.
- Feedback ignores key strengths/weaknesses present in the draft.

## High-value rerun prompts

Use these prompts as a small baseline suite for quick regression checks.

### A) Vague internal draft

**Prompt:**
> Internal note draft: "Project health is mixed. We are blocked in a few areas and need people to move faster. Please align and fix this week."
>
> Improve this for internal leadership clarity while preserving intent.

**Primary checks:**
- Draft-specific critique
- Meaning preservation

### B) External follow-up draft

**Prompt:**
> External follow-up draft: "Thanks for the discussion today. We are reviewing the integration dependencies and will send an updated plan after our internal review."
>
> Tighten this message for a client follow-up without inventing commitments.

**Primary checks:**
- No invented urgency/deadlines
- No unsupported escalation
- Meaning preservation

### C) Already specific draft

**Prompt:**
> Draft: "By Friday, Maya will deliver the revised onboarding checklist, and DevOps will confirm SSO test results. Remaining risk: vendor sandbox access, currently pending ticket #4472."
>
> Review and improve only if needed.

**Primary checks:**
- Light-touch editing
- Meaning preservation
- Draft-specific critique

### D) Already strong draft

**Prompt:**
> Draft: "Thank you for the quick turnaround. We have incorporated your comments in sections 2 and 4, and we are on track to submit the final version by Tuesday."
>
> Evaluate whether any changes are necessary. Keep edits minimal.

**Primary checks:**
- Light-touch editing
- No unnecessary rewrite

## Quick scoring template

For each run, record:

- Prompt ID: A / B / C / D
- Mode: advisory / full_challenge
- Outcome: Pass / Fail
- Failure tags (if any):
  - meaning_change
  - over_editing
  - invented_urgency
  - unsupported_escalation
  - generic_critique
- Notes: 1-3 lines with concrete evidence from output

## Recommended rerun order

1. **B (external follow-up)** — highest external communication risk.
2. **D (already strong)** — fastest check for over-editing regressions.
3. **C (already specific)** — checks precision preservation.
4. **A (vague internal)** — checks critique quality and useful strengthening behavior.
