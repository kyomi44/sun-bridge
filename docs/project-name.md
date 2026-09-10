# Project name and compatibility

Sun Bridge is the working name of this independent open-source learning and solar-operations project, previously Solar Bridge and Open Permit Kit. The name does not expand the software's authority or production readiness.

## Naming limits

Similar names are already used in the solar sector, including [Sunbridge Solar](https://sunbridgesolar.com/about/). This community project does not claim affiliation with those businesses. This is a working project name, not a completed naming or trademark-clearance review. Check suitability before investing in a separate public brand, domain, or commercial offering. Naming source checked September 10, 2026.

## Existing users

The canonical repository is [kyomi44/sun-bridge](https://github.com/kyomi44/sun-bridge). In an existing clone, update its remote:

```sh
git remote set-url origin https://github.com/kyomi44/sun-bridge.git
```

New instructions use `python3 -m sunbridge`. Both earlier commands, `python3 -m solarbridge` and `python3 -m permitkit`, and `permitkit` imports still work. All three entry points call the same review-only implementation. Existing local folder names and private files do not need to change. Run from the repository checkout; this release does not support an installed-package distribution.

The version 1 profile schema retains its original identifier, `urn:open-permit-kit:ahj-profile:v1`, so branding changes do not break references. Profile IDs, data structures, and the private-data boundary are unchanged. Do not bulk-rewrite CRM mappings or private exports for this rename.

The project remains MIT-licensed and preserves its earlier history. The adopted charter and governance still use “Solar Bridge”; those documents apply to this same project, not a separate organization. Their substantive commitments have not changed. A [name-only alignment proposal](decisions/0002-name-alignment-proposal.md) follows their seven-calendar-day amendment process instead of silently editing the adopted text.
