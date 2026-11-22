# v3.6 (collide_cmp solidity rules)

* `GUIDE.md`: caveat on `collide_cmp.py` in section 5 and new gotcha 31 — v3.5 counts solid
  brushes in `worldspawn`/`func_group` only and ignores face textures, so solid brushes in the
  `func_detail` family, walls retextured to `*`-prefixed liquids, and changes inside `liquid()`
  pools all read as "collision identical". Documents the window before the code fix below.
* `qmap/collide_cmp.py`: count solid brushes in every entity qbsp merges into the world collision
  hull, not just `worldspawn`/`func_group`. `func_detail`, `func_detail_wall` and
  `func_detail_fence` are all solid to players (measured: one 128-unit cube per entity flavour in
  a sealed room, compared by clipnode count against an empty control), so a solid brush added in
  any of them used to land on the identical-geometry fast path and report "collision identical"
  at every `--step`. `func_detail_illusionary` stays excluded, and `func_illusionary_visblocker`
  is excluded explicitly — it passes qbsp's `IsWorldBrushEntity()` but its contents are replaced
  with `ILLUSIONARY_VISBLOCKER`, so deriving the set from that predicate would wrongly add it.
  Classnames are now matched case-insensitively, as qbsp does. Every ignored brush is accounted
  for in a stderr `note:` line, split by reason, which is what stops the blind spot returning:

      note: ca_saddle_b7.map: ignored 123 brush(es) in entities with no player collision:
            func_detail_illusionary x123
      note: ca_saddle_b7.map: ignored 8 brush(es) in submodel entities (own collision hull,
            solidity set at runtime): func_illusionary x3, trigger_teleport x3, trigger_push x2

  Submodel brush entities (`func_wall`, `func_illusionary`, `trigger_*`) remain out of scope:
  each becomes its own BSP model with its own hull, so comparing them means per-model comparison
  rather than an allowlist entry.
* `qmap/collide_cmp.py`: read face textures for contents, so `*`-prefixed liquids are no longer
  counted as solid. `parse_brush()` now returns each brush's face texture names in file order and
  `brush_contents()` classifies the brush the way qbsp does. This fixes a false positive
  (retexturing a solid wall `*lava` turned a wall into a lava volume and still reported "collision
  identical") and a false negative (a `liquid()` pool counted as solid both masked real solid
  changes inside it and reported `COLLISION DIFFERS` for a pool added to open air). The rules,
  measured the same way as above rather than read off the source:
  - `*water` / `*slime` / `*lava` (any `*` name) are liquid, not solid. `!`-prefixed names are
    Half-Life only and are solid here. `clip`, `skip`, `sky*` and `trigger` are all solid — none
    of them may be excluded on the strength of the name. `hint` / `hintskip` and `origin` are not.
  - **Mixed-face brushes follow qbsp exactly: the first face in file order decides.** One `*lava`
    face in slot 1 makes a whole wall a pool; the same face in slot 6 leaves it solid. Such
    brushes also get a loud stderr warning, since a `*` texture in a wall or floor theme slot is
    almost always a mistake.
  - The one rule that source-reading gets backwards: **a single `hint` face anywhere** drops the
    whole brush from the collision hulls, whatever the other faces say. `face_get_contents()`
    returns *empty* for `hint`, which the first-face rule skips over, predicting solid;
    `MapBrush_IsHint()` tests *any* face and wins. Only a compile shows this.

  Water, slime and lava are then compared as three separate content classes alongside the solid
  space, each with its own ROI set, reporting e.g. `WATER CONTENTS DIFFER` / `LAVA CONTENTS
  DIFFER` and exiting 1. Separate classes rather than one "non-solid" space on purpose: a `*water`
  pool retextured `*lava` fills exactly the same volume, so a combined pass would report nothing
  while the room became lethal. The solid pass's wording and exit codes are unchanged, so
  "collision identical" still means what GUIDE section 5 says it means.

# v3.5 (template texture & alignment fixes, collide_cmp half-space support, GUIDE gotchas)

Fixes and lessons found while building `ca_saddle`:

* `qmap/collide_cmp.py`: fixed float coordinate parsing (`%.3f` on `sface`/`vface` brushes was
  previously split at the decimal point and silently dropped), extended voxelization from
  axis-aligned boxes to general convex half-space brushes (ramps, prisms, chamfers, veneers),
  and added exact differing-brush ROI prefiltering so sub-unit `--step` (e.g. `--step 0.5`)
  runs in megabytes instead of gigabytes, with CLI/memory guards and stderr warnings on
  degenerate/skipped brushes.
* `template/_core.py`: `_lamp_spot()` requires a non-sky solid ceiling at `z == ceil`, preventing
  `room_lamps()` from mounting ceiling lamp boxes on flush or recessed sky oculi, and logs a
  stderr note if `room_lamps()` finds zero valid ceiling spots.
* `template/_out.py`: `brush_text()` checks rect bounds and surface height when matching
  `FLOOR_DECALS` / `CEIL_DECALS` so multiple inlays sharing a texture each anchor to their own
  rect instead of the last decal's corner.
* `template/_out.py`: prism outward air probes march in 8-unit steps (`8..40`) and stop at the
  first non-`'diag'` solid cell so chamfered corners pick up room bands (`base`, `strp`, `trim`,
  `SPLIT_Z`, `TRIM_Z`) without ever reading through a thin wall.
* `template/_out.py`: ramp texturing and alignment fixes (verified voxel-identical with the fixed
  `qmap/collide_cmp.py` down to `--step 0.5` against single-wedge ramps):
  - `info()` detects the first 16-unit cell (`d = 0`, exact `f == rz0`) of every ramp (including
    `bands=False`), eliminating horizontal wall light-strip bleed at ramp feet without matching
    stacked mezzanines above `rz0`.
  - Wall courses above/beside ramps compare `mid` against nominal `STRIPE_Z[th]` so stone stays
    vertically aligned with the main room.
  - When a ramp's lateral face borders a differently-themed room, the main walking wedge stays in
    `EXTRA['skin']` (preserving `FLOOR_MINLIGHT` across the walkable slope except the 1-unit wall
    sliver) while a 1-unit outer veneer is partitioned by contiguous adjacent rooms and
    `band_cuts(adj)` in `worldspawn` (matching lower/upper wall courses, strips, and worldspawn
    lightmaps seamlessly).
* `template/_out.py`: sloped ramp band overlays thinned from 2 units to 1 unit proud to reduce
  visual parallax at horizontal-to-slope bends.
* `template/_core.py` & `template/_out.py`: structural walls over open air (`zbot is not None`)
  get a gated bottom 16-unit architrave `'trim'` band (only cutting brushes where a face actually
  takes the architrave role, preserving intersecting light strips, with `NOARCH` /
  `carve(..., noarch=False)` opt-out mirroring `NOCAP`).
* `template/_layout.py`: added a small side alcove beside the demo's ramp so both the exposed-ramp
  1-unit veneer and the gated overhang architrave paths are exercised in-repo.
* `GUIDE.md`: added Gotchas 24–30 (visible slipgate teleporter framing and torch clearance,
  ezQuake's world-UV liquid rendering requiring 64-unit alignment on `*` teleporter portals,
  per-level sub-themes and bend junction collars on ramped wings, exact-height multiple-of-16
  crate/object textures, excluding olive-green indices 80–85 from wood palettes, redundant
  overlapping `carve()` theme pollution, and shipping `.lit` alongside `.bsp`).

# v3.4 (item economy and relative placement)

* `qmap/itemprofile.py`: BSP29 inventories, standard loose quantities, distinct
  duplicate pickup IDs, directed RL/LG/armor/MH/powerup matrices, ascent/descent,
  world eye rays and neutral three-location visit/cycle diagnostics. Optional
  hypothetical moves do not edit BSPs. Unsupported endpoints remain explicit.
* `qmap/itemcheck.py`: offline comparison of generated item JSON with a captured
  authorized MVDSV `edicts` dump: exact counts, positions/floors and touch setup.
* A small explicit `vprofile.profile(..., with_navigation=True)` export replaces
  research-only AST instrumentation. Existing default metrics and CLI behavior
  are preserved.
* GUIDE adds mode-aware item economy: separate premium control from recovery,
  check strong-weapon/resource clusters, give supply caches route roles, and
  distinguish item count/quantity from mod-dependent respawn frequency.
* `gallery/items/` and `qmap/ITEMS.md` document the five-map evidence, reproducible
  commands, schema and model limits. These are diagnostics, not balance grades;
  no universal minimum RL/LG distance or per-player armor formula is prescribed.

# v3.3 (map sizing, bug fix)

* **Size by travel**: vprofile measures the median and 90th-percentile walking distance between
  random spots (`travel_median`, `travel_p90`), and `build.sh` prints a size line with a suggested
  player range. Floor area overrated Helix (more floor than any classic duel map, the shortest
  travel of all fifteen maps); GUIDE section 3 has the bands.
* Preview renders no longer draw trigger brushes (teleporters, pads).

# v3.2 (first map built on v3)

* **Player-hull check**: `vprofile.py --check` (run by `build.sh`) reports cut-off spawns, traps and
  unreachable items on the compiled map's real collision with a 32x32x56 player. Concept C passed
  `check.py` and still trapped players in a tunnel in game: a rock column left a 24-unit gap at
  one end (the grid read it as 32), and the stair at the other end ran down under an 80-tall
  ceiling that caught a player still standing on the second step. The hull check finds both.
* vprofile's walk moves now need headroom at the higher of the two heights (the stair case above);
  push pads push on every frame they are touched, chained pads included (aerowalk's lift); the main
  area for the check is the biggest two-way-reachable one. The height measures of all fourteen
  profiled maps are unchanged.
* Prism stand-ins now cover every cell the prism overlaps (not only cells whose centre is inside),
  so the grid checks never see a gap wider than it is.

# v3.1 (bug fix)

Bug fixes for angled walls:

* An angled pillar standing on the floor could leave a hole in the floor at its edges.
* A corner cut made before the room around it was carved got hollowed out again, and a lamp could
  end up inside it.

# Changes from v2 to v3

Why: after nine maps the group felt our layouts lacked vertical complexity. v3 measures height,
adds the geometry the core was missing for it, and puts height into the process.

## Design and process (GUIDE sections 2-3)
* New **Design for height** section: a survey of our nine maps against five classic QW maps
  (aerowalk, ztndm3, dapak12, naked3, naked4). The classics change height two to five times as
  much item to item, spread floor over more levels, overlook more, use angled walls and
  teleporters. Targets, techniques, and the Strata lesson: stacked is not vertical.
* Concepts are drawn **in section as well as plan**; blockouts are delivered with sections and an
  iso cutaway; the height profile is read every build; the layout is settled before the visual pass.
* Gallery: ctf_strata added; `gallery/profiles/` holds the survey (figures, numbers as JSON; the
  reference BSPs themselves are not included).

## Generator (`template/`)
* **Ramps**: `ramp(rect, axis, z0, z1, rev)` writes a true wedge brush (rise <= run). Walls beside
  it get a sloped kickplate and light strip from the foot room's strip to the head room's. The
  grid holds a stepped stand-in for the checks; the foot is registered for the stair-feet check.
* **Angled walls**: `prism(points, z0, z1, kind)` (convex), `chamfer(rect, corner, size, z0, z1)`,
  `diag_wall(x0, y0, x1, y1, thick, z0, z1)`. Faces use Valve 220 texture axes so textures run
  along the face; bands continue round chamfered corners. The air in covered cells becomes a grid
  stand-in (`'diag'`) that is never written and never gets a lamp; solid already there stays, so a
  prism can start below the floor. Call prisms after the carves they stand in.
* From Strata: `split_halves` / `side_of` (team colours by half), `TRIM_Z` + `TRIM_H` (string
  course), `SPLIT_Z` (a second wall stone below a height), `SUN` (worldspawn sunlight), wall stone
  anchored to the room's nominal strip (fixes stone sliding beside stairs).
* The demo map now has an octagonal hall (four chamfers), a ramp up to a ledge with sloped bands,
  and an octagonal pillar; `views.py` has a camera on them.
* `build.sh` ends with `vprofile.py --targets` (`VPROFILE=0` skips it).

## Tools
* `qmap/vprofile.py`: height profile of any compiled BSP29 from its collision hulls: stacking,
  effective levels, biggest level, overlooks, cross-level sight, route height change and level
  changes between items, angled walls, teleporters, pads, rocket-jump-only floor. `--targets`
  rates each against the classics. Needs numba.
* `qmap/section.py`: vertical slices of a generated map; `qmap/iso.py`: isometric cutaways.
* `demos/vert.py`: height change in real play (floor change per 1000 units travelled, airborne
  share); `ca_run.py` and `ctf_run.py` report it.

## Examples
* New `examples/ctf_strata` (b6): two stacked levels, side lanes, light wells, "The dig" textures,
  team lights by half, direction signs and `signcheck.py`. Rebuilds byte-identical.
* ctf_bastion, ctf_circuit, ca_lyceum unchanged.

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

## v2.1 (fixes found while building ctf_strata)
* `routes.py`: no longer crashes when nothing is reachable near the target point; it reports
  "unreachable with these rectangles forbidden" instead.
* Template `zone()`: blockout themes named `blue` and `red` always get the blue and red zone
  colours, whatever order the rooms are carved in (before, two bases could come out the same colour).
* Template `room_lamps()`: a ceiling lamp that would land inside a pillar, baffle or pier now moves to
  the nearest clear spot in the room (before, the light compiler warned "couldn't nudge light out of
  solid" and the lamp was lost). Call `room_lamps` after the room's pillars, as the demo does.
* Template `views.py`: the docstring had the pitch sign backwards. In the renderer, as in Quake,
  a positive pitch looks DOWN and a negative one looks up.
