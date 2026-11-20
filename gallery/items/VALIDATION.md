# Candidate validation

This repository had no existing test suite. Validation used its real CLI/build
workflow and separate manual boundary-case checks, not an added test framework.

- All five default `vprofile.py` reports match **every numeric field** in the
  shipped `gallery/profiles/profiles.json` for the corresponding reference maps.
  The navigation export is opt-in; existing CLI/default API metrics are unchanged.
- A fresh `template/` texture/WAD/generator/QBSP/VIS/light build passes the full
  grid and compiled-hull reports: no item/connectivity problems, no traps, all
  seven stair feet clear. The new item tool also handles this one-RL/no-LG map.
- Full item diagnostics, JSON and figures were produced for all five reference
  BSPs. IDs, hashes, nullable endpoints and standard quantities are retained.
- Boundary checks exercised duplicate IDs, not-deathmatch filtering, health
  flag precedence, centered/corner coordinates, big crates, unknown classes and
  override fields, hypothetical moves, nonfinite/invalid input, unresolved
  routes and visibility independent of route connectivity.
- The runtime checker was exercised against actual MVDSV 0.33 dumps from a new
  map with 34 pickups, and failure cases for missing items, wrong floors and
  nonfinite generator coordinates. All actual pickups settled as intended with
  active touch setup. Player acquisition and multiplayer balance were not tested.

The original maps, local runtime dumps, game binaries/data and new-map source
are intentionally not included in the toolkit commits. Reference data hashes
allow the mapper to reproduce against the same BSP copies. The source hashes
in `reference.json` identify the exact diagnostics used; a BSP or tool source
changing during analysis is rejected rather than silently misattributed.

Reproduce the reference study with the command in `README.md`, compile the
template with its normal build recipe, and use `qmap/ITEMS.md` for the runtime
check contract. Compiler/environment configuration remains the existing
toolkit's responsibility. Semantic checker reports must still be read: older
toolkit checks can report problems without a failing process exit status.
