# Texture alignment and visual lint

`texcheck.py` audits QuakeEd/Valve 220 `.map` source and compiled BSP29 files.
It prints actionable face identifiers, textures, coordinates, and coverage;
`--report` writes every finding and sampled dark-cell coordinate as JSON.

```bash
python3 qmap/texcheck.py map_b4.map --report texture_lint.json
python3 qmap/texcheck.py map_b4.map --bsp builds/map_b4.bsp --strict
python3 qmap/texcheck.py builds/map_b4.bsp --map source/map_b4.map
python3 qmap/texcheck.py map_b4.map --wad textures/stone.wad --wad textures/signs.wad
python3 qmap/texcheck.py map_b4.bsp --wall-texture '*stone*' --wall-texture '*wall*'
TEXCHECK=1 bash template/build.sh
```

The matching `.map`/`.bsp` beside the input is discovered automatically. Explicit
`--map`/`--bsp` paths must exist. Use matching artifacts from the same build: BSP
files do not contain a source hash, so the checker cannot prove that they match.
When a BSP is available, alignment uses its compiled faces; source remains
necessary for WAD references and original brush entity classification.

Exit codes are **0** for completed advisory checks, **1** for non-ignored
findings with `--strict`, and **2** for input errors or a sampling-budget refusal.
Missing coverage is printed as `NOT CHECKED` and recorded in JSON; exit 0 alone
does not establish that every check ran. The optional build integration runs
advisory checks after compilation and writes `<map>.texcheck.json`, preserving
the existing build/check exit-code conventions.

## Checks

| Code | What it detects |
| --- | --- |
| `wall-course` | Adjoining vertical faces of the same texture whose V coordinates disagree modulo texture height, including corners and walls separated by a narrow band. |
| `wall-u-phase` | U coordinate disagreement modulo texture width along a shared wall/corner seam or across a narrow band. |
| `portal-alignment` | A 64-unit-wide `*` portal whose projected world-U center is not 32 modulo 64. |
| `missing-wad` | A source WAD reference that cannot be resolved. |
| `missing-texture` | Source texture absent from the supplied WAD set, or a compiled face without embedded texture pixels. |
| `illusionary-contents` | A `func_detail_illusionary` brush containing `*` or case-insensitive `sky*` faces, which can retain real hull-0 contents. |
| `sky-overlap` | Positive-area overlap of an ordinary face with a same-facing sky polygon within the decal clearance. |
| `dark-floor` | Exactly black lightmap illumination at grid centers on standable upward-facing floor polygons. |

### Courses and seams

Texture dimensions come from WAD miptex records or embedded BSP textures.
Offsets are compared modulo the actual dimensions: two phases of 32 and 160
are equivalent on a 128-high texture; neither must be zero. QuakeEd rotations,
negative/non-unit scales, and Valve 220 axes participate in the comparison.
Phase variation along the seam also warns, so a scale mismatch cannot hide by
matching only at periodic endpoints. Comparisons use the same texture name,
case-insensitively; different material names are not assumed to share courses.

Shared edges are matched by line and overlapping segment, including split BSP
edges. Coplanar walls with overlapping horizontal extents are also compared
across a band up to `--band-gap 32` units high. Set `--band-gap 0` to restrict
these comparisons to touching surfaces. Disconnected walls are not compared
against a whole-map zero-offset rule.

An intentional seam, an independently fitted pillar, or a mirrored corner can
produce a useful warning without being a design error. Restrict the material
set with repeatable `--wall-texture GLOB`, or use `--ignore wall-u-phase` when
reviewing only horizontal courses. Ignored findings remain in the JSON report,
alongside `ignored_codes`; they do not trigger strict failure. Texture pixel
content is not analyzed for whether a pattern makes a seam noticeable.

Source-only exposure uses the face center and inset vertex probes against
solid brushes. It removes fully buried candidates, but does not replace qbsp
CSG/visibility. Prefer a compiled BSP when checking complex intersections.
Brush-primitives source is refused explicitly; compile it to BSP29 or convert
it to Valve 220. The QuakeEd axis convention follows ericw-tools' default old
axis selection; use the compiled BSP for maps built with different options.

### Portals and sky

By default, portal candidates are vertical `*` textures with `tele` or `portal`
in their names. Repeat `--portal-texture GLOB` to select other names. Connected
coplanar fragments with the same U axis are grouped before measuring width.
Only a projected 64-unit span is tested; larger multi-repeat liquid panels are
not assumed to contain one centered swirl.

The test uses `dot(world_position, U_axis)` and ignores texture translation,
matching ezQuake's turbulent world projection. Thus shifting the texture
cannot repair a misplaced portal. For an ordinary X-projected portal, the
condition is `(cx - 32) % 64 == 0`; rotated portals use their actual U axis.
See [rendering and liquid projection](RENDERING.md#liquid-surfaces-and-preview-limits)
and GUIDE Gotcha 25. Width and phase refer to the static unwarped projection.

Sky overlap uses source polygons when available, so a decal that caused qbsp
to hide the underlying sky face can still be found. `--sky-gap 8` controls the
maximum distance between the projected polygons; edge-only contact is allowed.
Source polygons are clipped without expanding their borders, and invisible
trigger brush entities are excluded from overlap candidates.
The checker needs surviving sky geometry: if a generator replaced every trace
of a sky surface with another texture, compiled/source geometry alone cannot
recover that original intent. See GUIDE Gotchas 14 and 31.

### WADs

Source `worldspawn` WAD lists are split on semicolons. Paths are resolved
relative to the source map, then the current directory, then by portable
basename beside the source map (including old Windows paths on Linux).
Repeatable `--wad` replaces that list; a same-stem WAD is used if no list exists.
The first matching texture in WAD order supplies its dimensions. Names are
case-insensitive. Compiler textures `clip`, `skip`, `hint`, `hintskip`, `origin`,
and `trigger` do not require a WAD entry. WAD2/WAD3 uncompressed miptex directories
are supported; malformed/compressed entries fail clearly.

A BSP-only audit can check embedded texture availability, but cannot recover
the source WAD paths or distinguish merged detail brush classes. These source
checks appear under missing coverage rather than silently passing.

### Dark floors

Samples use a world-aligned 16-unit XY grid by default (`--floor-step`). Only
ordinary upward-facing polygons with normal Z at least 0.7 are sampled.
On an otherwise lit BSP, omitted face lightmaps (`lightofs = -1` or no styles)
are treated as zero illumination: the compiler can omit completely black faces.
`TEX_SPECIAL` faces are excluded. The compiled Quake hull 1 tests whether a 32x32x56 player can stand at
that point against the world and static `func_wall` models, including clearance
above and support immediately below; slopes
include the hull's horizontal footprint. The test does not establish spawn
reachability or replace `vprofile.py --check`.

All stored light styles are combined at their normal intensity and luxels are
bilinearly sampled using the renderer's RGB `.lit` normalization. Display
gamma/contrast is not involved. Fullbright texture texels, liquids, sky, and
maps without lighting are excluded. The default threshold is exactly zero;
`--dark-threshold N` also diagnoses dim samples in the lightmap's 0..255 range.
Floor findings group the dark coordinates by face; JSON retains every cell.

Non-solid illusionary brush models are excluded from floor/support tests.
The checker samples compiled brush poses, not runtime door/platform movement,
dynamic lights, switches, or entity models. Grid centers can miss small dark
patches; lower `--floor-step` when investigating one. `--max-floor-cells`
defaults to 1,000,000 candidate cells and refuses oversized runs explicitly.

## Template course anchors

The default strip now starts at `floor + 144`, ending at `floor + 160`, which
is congruent to the lower wall's `floor + 32` modulo 128. Both the grid wall
writer and `band_role()` (used by prism/ramp details) share `wall_anchor(th)`.
Stone above and below strips therefore keeps the same room-floor course origin
even with explicit strip heights or a custom `WALL_PERIOD`. Strips can move
without resetting the wall pattern. A distinct room/sub-theme remains the way
to choose an independent floor/course origin.
