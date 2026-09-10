# Start here: no installation needed

This is a short practice exercise, not a live permitting record. All identifiers, addresses, and messages below are fictional. You can do it in this page without Python, a CRM, or an inbox connection.

Your job is to explain the evidence and spot what is missing. The tool can suggest an event or a project match; the operator decides whether the evidence supports it.

## Your fictional CRM

All these permits belong to **Example Training County**, a fictional jurisdiction.

| Deal | Permit number | Service address |
| --- | --- | --- |
| demo-deal-001 | DEMO-SOLAR-001 | 100 Example Way, Unit A, Example City, ZZ 00000 |
| demo-deal-001 | DEMO-ELECTRICAL-001 | 100 Example Way, Unit A, Example City, ZZ 00000 |
| demo-deal-003 | DEMO-SOLAR-003 | 300 Example Way, Unit C, Example City, ZZ 00000 |
| demo-deal-004 | DEMO-SOLAR-003 | 400 Example Way, Unit D, Example City, ZZ 00000 |

The duplicate number in the last two rows is intentional. Do not silently choose one. Also notice that one deal has two permits.

## Five messages to review

Imagine these subjects have arrived from the expected fictional notification sender. A recognized sender address is not proof of authenticity: verify the message and its context before relying on it.

| Case | Message subject | Your questions |
| --- | --- | --- |
| 1 | Application DEMO-SOLAR-001 received | Which deal? Does this prove the application was accepted or approved? |
| 2 | Permit DEMO-SOLAR-001 ready to issue | Has a permit actually been issued? What would establish that? |
| 3 | Inspection passed for DEMO-SOLAR-001 | Does this close the permit or establish utility permission to operate? |
| 4 | Permit DEMO-SOLAR-003 issued | Can you pick a unique deal? What conflict needs resolution? |
| 5 | Your application has not been approved | Is a keyword like “approved” enough? What if the body quotes an older “permit issued” email? |

For each, write one sentence about what the message establishes and one about what you still need. The inbox arrival time does not necessarily tell you when the underlying event happened.

## Compare your reasoning

1. **Receipt, not acceptance or approval.** The verified jurisdiction plus DEMO-SOLAR-001 identifies a candidate on demo-deal-001. Check the original evidence before accepting it.
2. **Ready to issue, not issued.** Follow the department's official process and look for the actual issuance evidence. Do not advance the permit just because a message contains the word “issue.”
3. **A passed inspection, not automatic closeout.** Identify which inspection passed and whether other inspections or closeout steps remain. Utility authorization is a separate process.
4. **Ambiguous project match.** Two permit records share the identifier. Investigate the original permit documentation and CRM records; do not pick the first result or match on a customer name alone.
5. **Unsupported format: hold for review.** The starter parser abstains. A negated statement and quoted old correspondence cannot be interpreted safely by looking for isolated positive words.

The fictional profile has no verified status-checking channel. “Research the official verification channel” is a valid next step. In a real profile, maintain that channel separately from the way notifications arrive.

## What to do next

Run the [working review example](../README.md#review-a-permitting-inbox-sample), with a technical helper if useful, then complete the [20-minute operator exercise](operator-guide.md). It adds duplicate notifications, unknown senders, unmatched permit numbers, and address-only matching.

Already know a department's official process? You can contribute through **Issues → New issue → Jurisdiction knowledge**, with public source links and no customer data. Read the [contribution guide](../CONTRIBUTING.md).
