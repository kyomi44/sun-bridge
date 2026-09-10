# A 20-minute operator exercise

The goal is to explain why an event belongs to a particular permit and what it actually establishes. You need no live inbox or CRM account for this exercise.

An operator reviews evidence, resolves exceptions, and decides the next action. A technical helper installs the tool, prepares private input mappings, adds synthetic regression cases, and maintains integrations. One person may perform both roles. The operator remains responsible for the permitting interpretation.

## Minutes 0–4: Create your review

Open a terminal in the repository folder. Check that `python3 --version` reports Python 3.10 or newer, then run:

```sh
python3 -m sunbridge demo
```

Open `private/demo/review.md` in your editor's Markdown preview. It is a generated preview based on made-up records. The underlying Markdown encodes punctuation to prevent message text from turning into active links or images; the preview displays it normally. You can inspect the input messages in `examples/messages.json` and permit records in `examples/permits.json`.

## Minutes 4–9: Read four kinds of event

Find examples of receipt, corrections, permit issuance, and inspections. For each, locate the message evidence and answer: what happened, when did it happen, and which permit does it concern?

| Message meaning | What you may conclude | What still needs evidence |
| --- | --- | --- |
| Application received | The recipient acknowledged receipt. | Whether intake is complete or a permit is approved. |
| Corrections required | A response or revision is needed for the stated scope. | Whether the whole application was denied. |
| Permit issued | A permit was issued if the message explicitly identifies it. | Whether inspections passed or work is closed out. |
| Inspection result | The named inspection has the stated result. | Whether it is the final required inspection or the permit is closed. |

Notice the distinction between a scheduled inspection and a completed inspection, and between an approved review and an issued permit. Read [event boundaries](event-model.md) when a phrase is ambiguous.

## Minutes 9–14: Check the match

Compare the jurisdiction and permit/application identifier in each message with the permit record. If matching by address, compare the complete normalized service address, including the unit. A matching customer name is supporting context only.

Ask whether more than one permit could match. A single deal may contain building, electrical, or revision permits; an address may also have permits from earlier projects. Missing unit information, a mismatched AHJ, or more than one plausible candidate requires a person to resolve the match. The postal city does not establish the permitting jurisdiction.

## Minutes 14–18: Recognize exceptions

Review any duplicate, old, missing-field, or uncertain cases in the output. Then consider these changes without editing a real record:

- The same notification arrives twice. The second copy should not create a second business event.
- A receipt message arrives after an issuance message. Arrival order should not move the permit backward.
- An email names a customer but contains no reliable permit identifier or full address. There is not enough evidence for an automatic match.
- An email says “final inspection scheduled.” It does not establish completion.
- No email arrives. Silence does not establish approval, rejection, or continued review; the inbox may be incomplete.

## Minutes 18–20: Make a review decision

For one clear example, write a short note explaining the permit match, event, evidence, and proposed next action. For one uncertain example, say what information you would seek and where the jurisdiction profile says to verify it.

The fictional training profile has an unknown verification channel. For this exercise, “verification channel needs research” is a valid answer; explain which official source or department contact you would seek before accepting the event.

The demo ends with a review decision. It does not send messages or apply CRM changes. If you can explain both examples to another operator, you are ready to help assess a private sample with a technical helper.

Use the [learning path](learning-path.md) with a mentor to record what you can demonstrate and what still needs practice. Publishing personal assessment results or contributing code is not required to learn.

## Reviewing your own workflow

Have a technical helper prepare private inputs using the examples' structure and your organization's access rules. Start with a small set of permits whose histories an operator already knows. Compare previews against the original evidence and official records, recording incorrect matches, missed events, and ambiguous wording.

Review unknown templates, conflicting messages, absent expected updates, changed sender or portal details, and older events that could alter an existing record. Track which lifecycle events a channel has actually demonstrated. Reliable examples of issuance emails do not prove reliable submission, rejection, or inspection coverage.

Any future automatic updates should be limited to rules that have been checked against representative private cases, with an audit trail and a way for an operator to correct the outcome. This repository's synthetic exercise establishes no production accuracy threshold.
