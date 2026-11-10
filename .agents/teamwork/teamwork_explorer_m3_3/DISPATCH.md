# Dispatch Assignment: Milestone 3 Explorer 3 (Jev Design Quality Gate & UI Validation)

## Mission
Investigate the local Jev MCP engine capability `jev_review_design` and formulate the automated design quality gate for the trading visualization UI (Feature F18).

## Mandatory Context
Read `ORIGINAL_REQUEST.md` verbatim (especially the user follow-up regarding @jev):
`c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\ORIGINAL_REQUEST.md`

Read `PROJECT.md` at root:
`c:\Users\AmirM\Documents\Agentic trading\PROJECT.md`

Read `TEST_INFRA.md` at root:
`c:\Users\AmirM\Documents\Agentic trading\TEST_INFRA.md`

## Investigation Scope & Questions
1. Investigate the local Jev engine `jev_review_design`:
   - Inspect tool input schemas, expected parameters (e.g., HTML/CSS content, layout structure, color palette, visual hierarchy metrics), and output payload format.
   - Test or trace how `jev_review_design` performs heuristic design evaluation in offline mode.
2. Design the automated Jev UI Quality Gate:
   - Automated test runner or validation script that submits the rendered UI template / CSS structure to `jev_review_design`.
   - Acceptance criteria: visual hierarchy score, information density, contrast accessibility, typography balance, and consistency score thresholds.
3. Integration with test suites:
   - How `tests/e2e/test_tier1_f15_f18_visualization.py` and unit tests verify Jev design review pass/fail criteria.
4. Provide concrete code specifications, adapter wrappers, and unit test designs for the Worker.

Deliver `analysis.md` and `handoff.md` in your working directory and notify the parent orchestrator via send_message.
## 2026-11-06T19:39:41Z
You are teamwork_explorer_m3_3, Explorer 3 for Milestone 3 (Jev Design Review & Quality Gate).
Your working directory is c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_m3_3\

Read your dispatch instructions in your working directory:
c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_m3_3\DISPATCH.md

Read ORIGINAL_REQUEST.md verbatim (especially user follow-up regarding @jev):
c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\ORIGINAL_REQUEST.md

Read PROJECT.md at root:
c:\Users\AmirM\Documents\Agentic trading\PROJECT.md

Investigate local Jev engine jev_review_design capability, payload contracts, and automated UI design quality gating.
Deliver analysis.md and handoff.md in your working directory and notify the parent orchestrator via send_message.
