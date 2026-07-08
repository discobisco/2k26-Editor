# AGENTS.md

## Project Docs First
- Before making changes, read the project documentation to understand intent, workflows, and constraints.
- Start with the docs folder.
- Ignore unrelated top-level folders; for runtime/editor work, focus on `nba2k_editor/`.

## Repo Operating Contract
- Exact instruction alignment is required. Partial compliance is failure.
- Do not assume missing data. Do not infer intent. Do not fill gaps with "helpful" behavior.
- No fallback logic, compatibility logic, silent correction, or substitute behavior unless explicitly approved.
- Work one clearly scoped objective at a time.
- Stay inside the defined files, offsets, contracts, and systems for the active task.
- Source-of-truth files and contracts override guesses, abstractions, and convenience logic.
- Fix root cause, not symptoms. Do not monkey-patch around the defect.
- Prefer deleting wrong logic over layering compensating logic on top of it.
- Do not optimize, generalize, or broaden scope unless explicitly requested.
- If something is missing or unproven, state that directly.

## Evidence Standard
- Do not claim a fix without direct evidence from the exact affected path.
- Tests support a claim but do not replace runtime evidence when the problem is live-memory, UI-state, ordering, or editor behavior.
- Completion is evidence-gated: show the exact proof that the target behavior now matches the requested contract.
- If evidence is incomplete, report the remaining uncertainty instead of claiming success.

## Communication Contract
- Be direct, minimal, and mechanical.
- No padding, no social tone, no motivational framing.
- No repetition of the user's instructions.
- No agreement without validation.
- No explanation unless it helps solve the active task.



## Important
NO HARD FAILURES ALLOWED IN THIS REPO

