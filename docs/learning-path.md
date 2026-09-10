# Learn to operate Sun Bridge

Sun Bridge helps people build judgment they can explain, practice, and teach. You can begin with the [no-install examples](training-preview.md), then work with a mentor or technical helper on the [20-minute exercise](operator-guide.md). Progress depends on demonstrated skills, not a job title or coding background.

## Start with the working exercise

From the repository folder, run:

```sh
python3 -m sunbridge demo
```

Read `private/demo/review.md` in your editor's Markdown preview. The exercise uses fictional messages and permits. It proposes events and matches for review; it does not monitor an inbox, change a CRM, or include controls to pause or roll back a monitor. The legacy `python3 -m permitkit` command remains available for compatibility.

## Five competency milestones

| Milestone | Practice | Evidence to show a mentor |
| --- | --- | --- |
| Interpret a notice | Compare receipt, corrections, ready-to-issue, issued, and inspection messages. | Identify the exact phrase, event scope, and what remains unknown. Distinguish receipt time from the event's actual time. |
| Reconcile a match | Match AHJ plus permit number, or a unique full address including unit. | Explain the match and check for multiple permits on one deal. Decline a name-only match or a jurisdiction inferred from postal city. |
| Catch a planted failure | Find the repeated message, ambiguous permit number, unsupported subject, and unexpected sender in the demo. | Show why each needs a skip or further review, even if its wording appears convincing. |
| Describe and test a rule | Write an original synthetic message and its expected interpretation. Add a closely related example that must not receive that interpretation. | Submit both examples through the issue form; a technical helper can turn them into a rule and regression test. Explain why both outcomes are correct. |
| Investigate an exception | Choose an unmatched or ambiguous result and describe the next evidence needed. | Record the unresolved question, the official verification source to seek, and a concise handoff. Unknown verification channels remain unknown until researched. |

Use the [event model](event-model.md) and [CRM guide](crm-data.md) as references, not answer sheets to memorize. An operator should be able to explain a fresh example and recognize when the evidence is insufficient.

## Mentor rubric

For each milestone, record **needs practice**, **can explain with prompts**, or **can demonstrate independently**. Keep a short evidence note and agree on one next exercise. This is a learning record, not a professional credential or permission to access production systems.

| Check | Demonstrated when the learner can… |
| --- | --- |
| Evidence | Point to the relevant text and separate observation from inference. |
| Matching | Identify the right permit or clearly explain why a unique match is unavailable. |
| Boundaries | Keep approval, issuance, inspections, closeout, and utility permission distinct. |
| Exceptions | Catch misleading, duplicate, missing, or conflicting input and choose a sensible verification step. |
| Handoff | Explain the decision so another operator can reproduce it, without exposing private data. |

Do not average away a wrong-project match or an unsupported approval. Revisit that case with a new example before recording independent competence. Invite questions and let learners correct their reasoning; speed is not the goal.

## From practice to responsibility

A future private pilot should pair an operator with a technical helper and a responsible workflow owner. Access, supported event types, verification expectations, and escalation contacts must be explicit. A learner can contribute synthetic cases and public documentation without receiving private records.

Live monitoring and reviewed CRM updates are [future roadmap stages](roadmap.md). Before anyone operates them, training must include the implemented authority limits, how to pause processing, incident escalation, and how a reviewed change can be reversed. Those controls must exist and be tested before they become an exercise or an operational responsibility.

Possible future community programs include paid learning placements, supported mentorship, and compensated maintenance. Each would need an organizer, funding, clear responsibilities, and published participation terms. No such program, job placement, or funding is promised by this repository.
