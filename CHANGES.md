# v3.7 (collide_cmp hull-0 pass, non-inflating ROI merge, parser hardening)

* `qmap/collide_cmp.py` & `GUIDE.md`: **compare hull 0 (projectile solid + sky) alongside the
  player collision hull** (`CDEFG-5`). In hulls 1/2, `clip` and `sky*` are byte-for-byte as solid
  as a wall, so retexturing a wall to either used to report `collision identical` and exit 0 while
  rockets, nails and hitscan started passing through (`clip`) or vanishing (`sky*`). Verified
  across the full 7×10 `(entity × texture)` matrix against live `qbsp` (clipnode counts for hulls
  1/2, hull-0 node-tree walk at cube centre):
  - `worldspawn`, `func_group`, `func_detail`, `func_detail_wall`, `func_detail_fence`: player
    hull keeps `{solid, clip, sky}`; hull 0 keeps `{solid, sky, water, slime, lava}` (`skip` and
    `trigger` stay `CONTENTS_SOLID` in both hulls, while `clip` is hull-0 `EMPTY`).
  - `func_detail_illusionary`: player hull drops everything, while hull 0 keeps **both liquids
    and `sky*`** — neither satisfies `contents.is_any_solid()` (`qbsp/brush.cc`), so a `sky1` cube
    in `func_detail_illusionary` adds 0 clipnodes yet writes a `CONTENTS_SKY` leaf that swallows
    projectiles.
  - `func_illusionary_visblocker`: player hull keeps `{clip}` only; hull 0 drops everything
    (visible contents stripped, `clip` stays hull-0 `EMPTY`).
  - `WORLD_ENTITY_TYPES` now maps each world entity to `(player_hull_types, hull0_types)`, and
    `compare()` checks six independent classes (`solid`, `proj`, `sky`, `water`, `slime`, `lava`).
    Player collision (`solid`) always prints its full verdict line; other checked classes print
    full lines on a difference or under-resolution and collapse into one `hull-0/contents
    identical: ...` summary line when clean. A wall retextured `clip` now reports
    `collision identical` + `PROJECTILE COLLISION DIFFERS` (exit 1); retextured `sky1`, it also
    reports `SKY CONTENTS DIFFER` (exit 1); retextured `skip`, it stays exit 0. When excluded
    `clip`/`sky` brushes are geometry-identical between both maps and never intersect `solid`'s
    diff ROIs, `proj` reuses `solid`'s voxel result directly instead of sweeping the same grid
    twice. `GUIDE.md` section 5 and gotcha 31 are updated accordingly (removing the v3.6 caveat
    that projectile collision had to be checked by hand).
* `qmap/collide_cmp.py`: **non-inflating ROI merge with exact lattice overlap masking**
  (`CDEFG-6`). `merge_boxes()` previously merged overlapping AABBs unconditionally to a fixed
  point, which could inflate L-shaped / corner-overlapping diffs across empty space and push
  resolvable sub-unit comparisons over `MAX_TOTAL_VOXELS` (exit 2). Each component now tracks its
  non-compounding original input volume (`orig_vol`) and merges only containments or overlaps
  whose enclosing box is at most 1.5× the sum of the two components' original volumes (with
  `roi_grid()` snapping at `max_bloat=1.0` so the two passes never compound, and `max_area =
  MAX_SLICE` so merging never creates an oversized slice). Remaining ROI overlaps on the shared
  integer lattice are masked out inside `compare()`'s Z-slice loop so every differing voxel is
  counted at most once, and the per-ROI `subA`/`subB` AABB prefilter is vectorized in NumPy.
  - Synthetic L-shaped corner overlap: **20.8× fewer voxels** (`65.54G -> 3.15G` at `--step 0.25`,
    turning an exit-2 budget refusal into a clean run).
  - 4,000 randomized overlapping box configurations: 0 volume inflations over the 1.5× bound, 0
    regressions vs v3.6, 2,226 improved (median 3.44×, p90 11.79×, max 84.56×); 100/100 randomized
    multi-brush overlap comparisons match a brute-force full-bbox sweep to the exact voxel.
  - Real `ca_saddle` pairs at `--step 0.5`: `b1->b4` drops `26.36G -> 2.14G` (**12.3×**, turning
    an exit-2 refusal into an exact 786,432-voxel diff matching `192 × 16³`), and `b5->b6` drops
    `17.75G -> 5.11G` (**3.5×**, back inside the 10G budget). Across 25 sequential pairs of
    `ca_saddle`, `ca_crosscut`, and `ca_offset` at `--step 8`, 25/25 match v3.6 verdicts and voxel
    counts exactly at equal or faster wall-clock time.
* `qmap/collide_cmp.py`: **brush-block parser hardening** (`CDEFG-17`, 12/12 verified against
  live `qbsp`):
  - Strip `//` and `;` comments (at start of line or after `<= 0x20` whitespace, preserving
    newlines and mid-token `//`) before `PT_RE` in `parse_brush()` and the empty-block `skipped`
    check, so a commented-out face line (`// ( ... ) *lava ...` or `; ( ... ) hint ...`) cannot
    spoof brush contents or trigger a spurious degenerate-brush warning on an empty block.
  - Skip the brush-primitives `( ( a b c ) ( d e f ) )` texture matrix after the third plane point
    in `parse_brush()` so `brushDef` `*lava`, `hint`, `clip`, and `sky*` brushes classify
    accurately instead of reading `'('` as `'solid'`.
  - Check rare quoted tokens (`kind == 1`) inside `depth >= 2` in `entities()` so quoted brush
    braces (`"{" ... "}"`) balance with zero overhead on bare brush tokens (`kind == 3`).
  - Zero new warnings and 0 count/note diffs across all 42 real `.map` files in the tree (73,025
    solid brushes, 22 sky brushes).

# v3.6 (collide_cmp solidity rules)

* `GUIDE.md`: new gotcha 31, **what is solid to a player is not what you would guess** — the full
  measured solidity table `collide_cmp.py` now implements: which brush entities are in the player
  collision hull, that `*`-prefixed faces make a liquid rather than a solid, that `clip` / `skip` /
  `sky*` / `trigger` are all solid despite their names, and that a mixed-texture brush is decided
  by its first face in file order except for `hint` / `hintskip`, one of which anywhere drops the
  whole brush. It also names the two reasons reading the qbsp source is not enough on its own, so
  that the next person extending the tool starts from a compile: `face_get_contents()` states the
  `hint` rule in a way that reads backwards (it returns *empty* contents, which the first-face
  rule skips over, predicting solid), and the liquid rules live in hull 0 while the solid ones live
  in hulls 1/2, so the two need different instruments — clipnode counts cannot see a liquid at
  all. Section 5 points at it and now states the pass criterion as **exit 0** rather than the
  words "collision identical", because with four content classes the solid pass can print
  "collision identical" while a later class takes the exit code to 1.
* `qmap/collide_cmp.py`: count solid brushes in every entity qbsp merges into the world collision
  hull, not just `worldspawn`/`func_group`. `func_detail`, `func_detail_wall` and
  `func_detail_fence` are all solid to players (measured: one 128-unit cube per entity flavour in
  a sealed room, compared by clipnode count against an empty control), so a solid brush added in
  any of them used to land on the identical-geometry fast path and report "collision identical"
  at every `--step`. An ordinary wall brush in either illusionary entity is excluded from the
  *solid* space — `func_illusionary_visblocker` explicitly, because it passes qbsp's
  `IsWorldBrushEntity()` but has its visible contents replaced with `ILLUSIONARY_VISBLOCKER`, so
  deriving the set from that predicate would wrongly add it. Neither exclusion is unconditional:
  `func_detail_illusionary` still contributes its *liquids* and `func_illusionary_visblocker` its
  `clip` brushes, both below — so what the tool carries is a per-entity table of which content
  types survive, not an allowlist of classnames. Classname values are matched case-insensitively,
  as qbsp does. Every ignored brush is accounted for in a stderr `note:` line, split by reason,
  which is what stops the blind spot returning:

      note: ca_saddle_b7.map: ignored 123 brush(es) whose entity drops them from every
            collision hull: func_detail_illusionary x123
      note: ca_saddle_b7.map: ignored 8 brush(es) in submodel entities (own collision hull,
            solidity set at runtime): func_illusionary x3, trigger_teleport x3, trigger_push x2

  Submodel brush entities (`func_wall`, `func_illusionary`, `trigger_*`) remain out of scope:
  each becomes its own BSP model with its own hull, so comparing them means per-model comparison
  rather than a table entry.
* `qmap/collide_cmp.py`: **`func_detail_illusionary` is only non-solid, not contentless** — its
  liquids are now compared. qbsp converts a brush there to illusionary mist behind
  `if (contents.is_any_solid())` (`qbsp/brush.cc`), so a `*water`/`*slime`/`*lava` brush is never
  converted and keeps real `CONTENTS_LAVA`/`WATER`/`SLIME` in hull 0 — the hull `SV_PointContents`
  reads. Skipping the whole entity before looking at face textures therefore tallied a lava pool
  dropped into a decal entity as just another ignored brush and exited 0.
  It adds no clipnodes, so the clipnode probe behind the rest of these rules could not see it;
  measured instead by counting hull-0 leaf contents, where a `*lava` cube in
  `func_detail_illusionary` yields a `CONTENTS_LAVA` leaf exactly as it does in `worldspawn`.
  `func_illusionary_visblocker` is the contrast that makes this a per-entity rule:
  `Brush_GetContents()` strips every visible content there and substitutes
  `ILLUSIONARY_VISBLOCKER` whatever the textures say, so a liquid really does vanish (measured:
  no liquid leaf, no clipnodes). A `hint` face still wins over a liquid in either entity — hull 0
  forces hint brushes to empty contents too, not just the clip hulls.
* `qmap/collide_cmp.py`: **a `clip` brush in a `func_illusionary_visblocker` is as solid to a
  player as a wall**, and was being ignored along with the rest of that entity. The substitution
  above masks off `EWT_ALL_VISIBLE_CONTENTS` only, and `PLAYERCLIP` is an *invisible* content, so
  it survives — and unlike `func_detail_illusionary`, a visblocker is not `continue`d out of hulls
  1/2 before `qbsp/brush.cc` converts `clip` to `CONTENTS_SOLID` there. Measured: a `clip` cube in
  a `func_illusionary_visblocker` gives a full clipnode count, identical to the same cube in
  `worldspawn`, while the same entity holding a plain, `*lava` or `sky1` cube measures at the empty
  control. The two illusionary entities therefore need opposite rules — `func_detail_illusionary`
  keeps its liquids and drops its `clip`, `func_illusionary_visblocker` the reverse — which is why
  the classname sets became one table of per-entity content types. The first-face and any-`hint`
  rules apply inside a visblocker as everywhere else (measured: `clip` in slot 1 of 6 is solid,
  `clip` in slots 2–6 behind a wall face is not, and a `hint` face anywhere drops it).
* `qmap/collide_cmp.py`: **only read contents off the faces qbsp keeps.** `parse_brush()` recorded
  every face's texture before checking whether its three plane points gave a normal, on the stated
  belief that "qbsp reads the contents of every face regardless". It does not:
  `ParseBrushFace()` returns `std::nullopt` for a face with no normal and `ParseBrush()` skips it,
  so the face never reaches `brush.faces` and neither `MapBrush_IsHint()` nor `Brush_GetContents()`
  can see it. Measured with a 7-face brush whose face 1 has three collinear points — a degenerate
  `*lava` face ahead of six wall faces compiles **solid** (180 clipnodes, no lava leaf), and a
  degenerate `hint` face does **not** drop the brush — so the old order got it wrong in both
  directions at once: it would call that brush a pool, and drop a solid brush that qbsp keeps.
  A face with no normal is now counted and reported on stderr rather than silently ignored, since
  a generator emitting one is a bug even though it changes nothing downstream.
* `qmap/collide_cmp.py`: **the mixed-contents warning now fires exactly where qbsp's does.**
  `face_class()` returns qbsp's content *type* rather than this tool's comparison class, so `clip`
  and `sky*` are distinct from ordinary solid (a new `SOLID_TYPES` folds all three into the solid
  space, which is still exactly right for the player hull). They had been lumped together, so a
  `clip` or `sky*` face landing in a wall or floor theme slot — the same theme-slot mistake the
  warning exists to catch — passed silently while qbsp warned. Measured against qbsp on the whole
  cross product: `clip`, `sky*`, `*lava` and `origin` mixed with solid all warn; `skip` and
  `trigger` do not, because they genuinely *are* `CONTENTS_SOLID`. The warning is also now
  computed over the faces `Brush_GetContents()` weighs — every face except `hint`/`hintskip`,
  which return empty contents — so it fires on a hint brush over its remaining faces, as qbsp's
  does, while `*lava`×5 + `hint` stays quiet because those faces agree. Zero real maps in the tree
  contain a mixed-contents brush, so this adds no noise to existing builds.
* `qmap/collide_cmp.py`: **split entities, find brushes and read classnames by walking .map
  tokens**, instead of counting brace characters, matching brushes with `\{\n(\(.*?)\n\}` and
  searching the text for a key. All three guessed at where the tokens were, and each wrong guess
  had the same consequence — a solid entity or brush dropped from the comparison, or a submodel
  counted as world geometry, reported as `collision identical` with exit 0 on the geometry-key
  fast path. One regex now spells out the whole lexical grammar in `parse_token()`'s precedence
  order (`common/parser.cc`) and one walk consumes it in `map_entity_t::parse()`'s
  (`common/mapfile.cc`), doing the entity split, the brush find and the classname read in a
  single pass. Everything below is measured by compiling a 128-unit cube in a sealed room — 180
  clipnodes means the entity merged into the world as `func_detail` and the cube is solid, 24 means
  it became its own BSP model, 12 means the cube reached no hull — and every one of them was a
  wrong answer first:
    * **A key and a value are the same kind of token**, so only position tells them apart.
      `"target" "classname"` ahead of a real `"classname" "func_detail"` compiles solid (180) but
      a key search read the classname as `origin`; the same decoy ahead of `"func_detail" "1"`
      and no real classname is a submodel (24) but read as `func_detail`.
    * **A comment is not a token at all**, so it has to be consumed rather than ignored:
      `parse_token()` tests for `//` or `;` before it tests for a quote, so a double quote in a
      comment would shift the pairing for the rest of the entity. Scanning the alternatives in
      its order gets both directions right — `// a "comment"` above a classname reads correctly
      (180), and `"wad" "a//b.wad"` is still an ordinary epair, because a quote swallows the `//`
      after it just as a comment marker swallows the quotes after it.
    * **A quoted token runs to its closing quote across newlines**, which is a different thing
      from a value sitting on another line than its key: `"message" "line1⏎line2"` is one value
      (180), where ending the token at the newline produced two half-tokens.
    * **A `\` takes the next character into the token**, whatever it is, so an escaped quote does
      not end it — `"message" "say \"hi\" now"` is one value (180). What it takes may be a second
      `\`, which then escapes nothing, so the *parity* of a run of backslashes decides: an odd run
      before the closing quote escapes it, an even run leaves it as the terminator. Measured
      across runs 1–5 long in four trailing contexts: with anything following on the line, a value
      ending `\\"` is closed (180) where one ending `\"` runs on and loses the classname (24, a
      submodel). Enumerating the two-character escapes instead of
      applying that one rule read every even run one short — the last backslash paired with the
      terminator, the value ran on, and the entity reported no classname. The exception is `\"` at
      end of line, which qbsp warns about and treats as the terminator; that is the
      `"wad" "c:\foo\"` shape some editors emit, and it reads at 180 as well.
    * **A token need not be quoted.** `parse_token()`'s other branch takes any run of characters
      above ASCII 32, so `classname func_detail` is a valid epair (180) — and a quote-only scan
      did not merely miss one, since `message "hi"` leaves an odd number of quoted tokens and
      mis-pairs everything after it.
    * **`{` and `}` are structural by position, not spelling.** `map_entity_t::parse()` compares
      the token text in a key slot without asking whether it was quoted, and a value slot takes a
      brace like any other token. So a brace inside a quoted value is text: `"message" "a{b"`
      compiles at 180, where counting brace characters collapsed the whole file into one entity
      block.
    * **A brush is a `{` in that same key slot, and its layout marks nothing.** `parse_brush()`
      opens with `parse_token(PARSE_PEEK)`, which skips whitespace and comments before deciding
      anything, so qbsp keeps a brush whose `{` is followed by a comment, a blank line, a trailing
      space, or its own first face on the same line (measured: 180 clipnodes for all four, as for
      the plain layout). The old `\{\n(\(.*?)\n\}` found no brush at all in those, so the tool
      reported `collision identical` and exit 0 with the same brush count on both sides — and,
      unlike every other way a brush can leave this comparison, no `note:` naming it. A blank line
      or a trailing space after `{` is not an exotic thing to find in a hand-edited `.map`.
    * **A key is whitespace-trimmed, a value is not.** `parse_entity_dict()` erases leading and
      trailing `std::isspace` from the key before storing it, so `" classname "` and a
      tab-padded key both mean classname (180). Internal whitespace is untouched, so
      `"class name"` is a different key (24).
    * **A repeated key keeps its last value.** `parse_entity_dict()` stores pairs with
      `entdict_t::set()` (`common/entdata.cc`), which overwrites `it->second` in place rather than
      appending, so `find()` returning the first match returns the overwritten one. `"classname"
      "func_illusionary"` then `"classname" "func_detail"` is merged into the world (180) and the
      same two reversed is a submodel (24): stopping at the first match is wrong both ways.
    * **The key stays case-sensitive**, because `entdict_t::find()` compares with
      `key == it->first`. qbsp does not read `"CLASSNAME"` as a classname at all (24, not 180),
      and a `"CLASSNAME"` repeat does not overwrite a real one (180). Only the classname *value*
      is case-insensitive, which is where qbsp uses `Q_strcasecmp`.
    * **`PARSE_SAMELINE` still holds the value to the key's line.** A newline between the two
      makes qbsp refuse the map outright (`parse_token: line is incomplete`), as does a comment
      there, so reading across one would describe maps that cannot compile. Tabs, runs of spaces,
      several epairs on one line and an entity header sharing the line with its opening brace are
      all fine (180), so a line-anchored pattern would have missed a solid entity.
  Checked against every entity of all 22 real maps in the tree (4,449 of them): the walk splits
  every file into the same blocks as before, finds the same 50,136 brushes with the same face
  lines in each, and reads the same classname for every entity, so nothing in anyone's build
  moves. One pass now does the work of three, so parsing costs 1.59× the old scan-plus-search and
  a full run on the heaviest real pair goes 2.11s → 2.42s. Voxelization still dominates.
* `qmap/collide_cmp.py` module docstring and `GUIDE.md` gotcha 31: state the two things the tool
  does **not** claim, so "exit 0" cannot be read as more than it means. It compares the player
  collision hull and liquid contents — not projectile collision, where `clip` and `sky*` diverge
  from a wall even though all three are identically solid to a player (a `clip` brush is absent
  from hull 0, so rockets pass through; `sky*` makes a SKY leaf that swallows them). Covering that
  needs a second hull-0 pass and is its own ticket. The other gap is a false positive rather than
  a false negative: because each liquid class is compared independently, reshaping a liquid brush
  buried inside an unchanged solid wall reports a difference that solid CSG makes unreachable.
  That direction is the safe one for a tool whose job is to refuse to certify.
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
  - The one rule that source-reading gets backwards: **a single `hint` or `hintskip` face
    anywhere** drops the whole brush from the collision hulls, whatever the other faces say.
    `face_get_contents()` returns *empty* for both names, which the first-face rule skips over,
    predicting solid; `MapBrush_IsHint()` tests *any* face and wins. Only a compile shows this.

  Water, slime and lava are then compared as three separate content classes alongside the solid
  space, each with its own ROI set, reporting e.g. `WATER CONTENTS DIFFER` / `LAVA CONTENTS
  DIFFER` and exiting 1. Separate classes rather than one "non-solid" space on purpose: a `*water`
  pool retextured `*lava` fills exactly the same volume, so a combined pass would report nothing
  while the room became lethal. The solid pass's own wording is unchanged, but **the pass
  criterion is the exit code, not the string** — on a `*water` → `*lava` swap stdout prints
  `collision identical` for the solid pass and `WATER`/`LAVA CONTENTS DIFFER` after it, and the
  process exits 1. GUIDE section 5 says so explicitly now.

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
