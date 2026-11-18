# Changes from v1 to v2

## Process and design
* New **concept step** before any blockout: sketch 2-3 structurally different overall shapes,
  compare with the gallery, recommend one (GUIDE sections 2-3). Framed as *fresh takes on
  classic forms*: reuse proven building blocks freely; vary the skeleton and the identity.
* New `gallery/`: plans and preview sheets of all eight maps, with what each skeleton is and the
  family resemblance between three of them (and why it happened).
* New maps start from `template/`, not from a copy of the last map (copying anchored three
  layouts in a row). The guide says plainly that the toolkit's limits are not the map's limits,
  and lists the core's known gaps.
* Option mockups rendered from the human's own screenshot angles when they dislike something.

## Generator (`template/`, new)
* One generic core: `SYM = 'none' | 'rotate' | 'mirror'` (mirror is new), every primitive
  symmetry-aware; zone / floor / strip heights set by the first `carve` of a theme.
* Merged the best of the two v1-era output writers: sill bands under raised openings, risers on
  step-tall edges, sunken-channel kickplates, walls anchored to the band below (Cistern line) +
  per-cell strip heights, panels, teleports, pushes, perches, team spawns (Bastion line).
* New primitives: `strip_ramp` / `strip_ramp_pos` (light strips that follow stairs, including
  starting the climb before the stairs), `inlay` (floor/ceiling textures anchored to their own
  rect), `panel` (pictures on either axis, scaled by texture width), `oculus` (sky ceiling),
  columns with base and capital, `carve_pair`, generic `liquid`, symmetric `jumppad`.
* Floor minlight skin 16 by default; free-standing blocks lit like floors.
* Blockout texture set (`texgen_blockout.py`): eight distinct zone colours with height marks,
  so no earlier map's look leaks into a layout build.
* Generic `plan.py` (auto levels, legend from the main floors) and `views.py` (brightness readout).

## Checks and tools (`qmap/`)
* `check.py`: stair-feet check (stairs running into pillars or stubs), 16-unit slot check,
  unreached floor reported at **all** heights (v1 silently ignored floors below 0), perches
  excluded from "unreached", spawns inside solid reported instead of crashing.
* New `routes.py` (named runs between flags or any two points), `sightlines.py`, `contact.py`
  (CA pacing proxy), `fsq.py` (error-diffusion quantising for colours the palette lacks).
* `pick_spawns_sym.py`: `SYM=rotate|mirror`, written-half bounds, flag radius and exclusion
  rectangles by environment variable (v1 had Bastion's coordinates hard-coded).
* `collide_cmp.py`: bounds read from the maps (v1 had one map's bounds hard-coded).

## Examples
* Added `ctf_circuit` (b5) and `ca_lyceum` (b5) beside `ctf_bastion` (b19); all three verified to
  rebuild byte-identical maps and WADs from a clean copy of this folder.

## Guide
* Rewritten around the above; new gotchas 12-17; demo findings updated (29 demos, CA on a
  CTF-sized map, theta-route arithmetic); lighting notes on pale and dark materials.
