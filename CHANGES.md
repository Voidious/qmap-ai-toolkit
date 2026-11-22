# v3.5 (template texture & alignment fixes, GUIDE gotchas)

Fixes and lessons found while building `ca_saddle`:

* `template/_core.py`: `_lamp_spot()` rejects `'sky'` ceiling cells so `room_lamps()` never mounts
  ceiling lamp boxes on sky oculi.
* `template/_out.py`: `brush_text()` checks rect bounds and surface height when matching
  `FLOOR_DECALS` / `CEIL_DECALS` so multiple inlays sharing a texture each anchor to their own
  rect instead of the last decal's corner.
* `template/_out.py`: prism outward air probes step past 16-unit `'diag'` stand-in cells
  (`d = 24, 32, 40, 12`), restoring kickplates, light strips, cornices, `SPLIT_Z`, and `TRIM_Z`
  on chamfered corners.
* `template/_out.py`: ramp texturing and alignment fixes (zero collision change) — `info()`
  detects the first 16-unit ramp cell (`d = 0`) via `RAMPS` bounds so horizontal strips no longer
  bleed at ramp feet; wall courses above/beside ramps compare `mid` against nominal `STRIPE_Z` so
  stone stays aligned with the main room; exposed lateral ramp faces bordering another room take
  that room's wall texture, carry its light strip across backed cells, and emit in `worldspawn`
  for a seamless lightmap match; sloped ramp band overlays thinned to 1 unit proud.
* `template/_out.py`: structural walls over open air (`zbot is not None`) get a bottom 16-unit
  architrave `'trim'` band (preserving intersecting light strips), eliminating half-sliced courses
  on hanging overhangs and framing doorway lintels class-wide.
* `GUIDE.md`: added Gotchas 24–30 (visible slipgate teleporter framing and torch clearance,
  ezQuake's world-UV liquid rendering requiring 64-unit alignment on `*` teleporter portals,
  per-level sub-themes and bend junction collars on ramped wings, exact-height multiple-of-16
  crate/object textures, excluding olive-green indices 80–95 from wood palettes, redundant
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
