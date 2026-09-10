# Project name and compatibility

Solar Bridge is the working name of this independent open-source learning and solar-operations project, formerly Open Permit Kit. The rename broadens the description of the mission; it does not expand the software's authority or production readiness.

## Naming limits

Similar names are already used in the solar sector, including [SolarBridge Technology](https://www.solarbridge.us/). The community project does not claim affiliation with those businesses. This is a working project name, not a completed naming or trademark-clearance review. Check suitability before investing in a separate public brand, domain, or commercial offering. Naming source checked September 10, 2026.

## Existing users

The canonical repository is [kyomi44/solar-bridge](https://github.com/kyomi44/solar-bridge). In an existing clone, update its remote:

```sh
git remote set-url origin https://github.com/kyomi44/solar-bridge.git
```

New instructions use `python3 -m solarbridge`. The existing `python3 -m permitkit` command and `permitkit` imports still work; both entry points call the same review-only implementation. Existing local folder names do not need to change. Run from the repository checkout; this release does not support an installed-package distribution.

The version 1 profile schema retains its original identifier, `urn:open-permit-kit:ahj-profile:v1`, so a branding change does not break references. Only its display title changes. Profile IDs, data structures, output locations, and the private-data boundary are unchanged. Do not bulk-rewrite CRM mappings or private exports for this rename.

The project remains MIT-licensed. Its earlier history is preserved; the new charter records how maintainers intend to guide the project going forward.
