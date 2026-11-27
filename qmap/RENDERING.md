# BSP previews and camera comparisons

`render.py` loads BSP29 textures and the companion `<map>.lit` automatically.
QLIT version 1 files must contain exactly three RGB bytes for every sample in
the BSP lighting lump. A missing companion uses monochrome lighting; an invalid
or unreadable companion emits a warning and falls back to monochrome. Use
`--no-lit` to check how the map reads without colored lighting.

```bash
python3 qmap/render.py map_b4.bsp view.png -470 -40 -30 90 0 106.2602 \
  --width 640 --height 360 --gamma 0.5 --contrast 1.2
python3 template/views.py map_b4.bsp views.png --gamma 0.5 --contrast 1.2
python3 template/views.py map_b4.bsp comparison.png --before map_b3.bsp \
  --gamma 0.5 --contrast 1.2 --strict-cameras --report comparison.json
```

## Shared cameras and safe sheets

Edit `CAMS` in your map's copy of `views.py`, or pass `--cameras cameras.json`:

```json
[
  ["north wall", [-470, -40, -30], 90, 0],
  ["teleporter", [-960, 736, 14], 180, 30]
]
```

Positions are eye coordinates; yaw 0 faces +X, yaw 90 faces +Y, positive pitch
looks down. `--views 0 1` selects an ordered subset. Both builds are rendered
afresh with the same camera list, FOV, image size, gamma, contrast, and lighting
settings. Each row places the old build on the left and the new build on the
right; neither image is taken from an earlier sheet with potentially different
cameras. Each BSP independently loads its own `.lit` companion. `--before` with
no value looks for `_b(N-1).bsp` beside `_bN.bsp`; use an explicit path when builds
are in separate directories.

The renderer checks the eye against solid and sky hull-0 leaves, including visible
brush submodels, excluding invisible triggers. It also clips every visible
face against the whole eye-to-near-plane viewing volume, catching thin
obstructions that can fall between sampled rays. The default near plane is 2u,
matching ezQuake's `r_nearclip`; `--near` changes both clipping and the check.
Water contents are not solid. Checks use the compiled brush pose, not runtime
door/platform movement or entity rotations.

Warnings go to stderr with the build and camera. Unsafe tiles have a red border
and warning label; their brightness is excluded from the mean. `--strict-cameras`
exits with code 2 before saving the sheet if any selected camera is unsafe in
either build, reporting every unsafe build/camera pair in one run. Cameras are
never moved automatically. A safe camera can still
face a wall or give a poor composition; these checks establish clearance, not
whether a screenshot is useful. The optional JSON report records the exact
cameras, render settings, warnings, and per-view brightness (`null` for unsafe
views).

## Client response and calibration

Defaults are `--gamma 1 --contrast 1 --lightmode 1 --modulate 1`.
`--lightmode 1` and `2` match ezQuake's nonzero `gl_lightmode`; `0` selects its
alternate response. `--modulate` corresponds to `gl_modulate` (0.5 to 3).
Contrast is applied before the gamma exponent. `render()` returns an image with
those settings already applied; do not apply the old `**0.55` sheet curve again.
Existing map scripts that still apply that curve should migrate to this
template or remove their separate gamma step.

The example `0.5 / 1.2` settings match the client configuration used for the
validation. They are not ezQuake defaults, and old brightness targets measured
with monochrome lighting and the fitted `0.55` curve are not directly comparable.
Measure preferred maps again using the same explicit settings as the new map.

The reference implementation is [ezQuake 3.6.9](https://github.com/QW-Group/ezquake-source/tree/3.6.9):

- [`Mod_LoadLighting`](https://github.com/QW-Group/ezquake-source/blob/3.6.9/src/r_brushmodel_load.c)
  rescales RGB samples to the BSP sample's perceived brightness using
  `sqrt(0.241 R² + 0.691 G² + 0.068 B²)`. It uniformly limits their peak to 170
  (nonzero lightmode) or 128 (zero), retaining hue; black RGB samples fall back
  to the BSP sample.
- [`VID_SetPalette`](https://github.com/QW-Group/ezquake-source/blob/3.6.9/src/r_palette.c)
  brightens ordinary brush textures by 4/3, with per-channel clipping, in
  nonzero lightmode. Turbulent textures and fullbright overlays use the original
  palette.
- [`R_BuildLightMap`](https://github.com/QW-Group/ezquake-source/blob/3.6.9/src/r_lightmaps.c)
  multiplies by 1.5 (nonzero lightmode) or 2 (zero), times modulation. The preview
  combines all stored styles at normal `m` intensity (264/256), performs the
  client's integer hue-preserving limit, then bilinearly filters luxels.
  Switchable and animated styles are shown steadily on, rather than simulating
  server state.
- The [post-process shader](https://github.com/QW-Group/ezquake-source/blob/3.6.9/src/glsl/post_process_screen.fragment.glsl)
  applies contrast then gamma. Fullbright texels bypass lightmaps, but still
  receive the display adjustment.

Renderer FOV is **horizontal**. ezQuake's `fov` is specified for a 4:3 view;
at 640x360, client `fov 90` corresponds to horizontal FOV 106.2602. For a
widescreen image, use `2*atan(tan(client_fov/2)*(width/height)/(4/3))`, in degrees.
Match eye position, angles, FOV, viewport, palette, and cvars before attributing
a pixel difference to lighting. Hardware gamma, external textures, and dynamic
lights can also change client screenshots.

### Measured client checks

Controlled ezQuake 3.6.9 captures of `ca_tell_b4` were compared at 640x360,
client `fov 90`, `gl_lightmode 2`, `gl_oldlitscaling 0`, `gl_loadlitfiles 1`,
`gl_texturemode gl_nearest`, `vid_gammacorrection 0`, and no dynamic lights.
Post-processing supplied gamma/contrast; hardware gamma was disabled.
SDL offscreen rendering used Mesa llvmpipe. The same local palette was verified
for both renderers. Mean absolute error is per RGB channel on a 0–255 scale:

| View / settings | Original preview | Updated preview |
| --- | ---: | ---: |
| North tunnel wall, gamma 1 / contrast 1 | 3.91 | 2.05 |
| North tunnel wall, gamma 0.5 / contrast 1.2 | 16.70 | 4.28 |
| NW portal, gamma 0.5 / contrast 1.2 | 13.70 | 3.60 |
| South tunnel, gamma 1 / contrast 1 / modulation 3 | n/a | 2.97 |

For the tunnel wall rectangle `x=8:632, y=8:240`, excluding the client-only
health pickup and cursor, errors were 0.73 (neutral display) and 1.60
(gamma/contrast), down from 3.42 and 14.31. Whole-image results retain the
unrendered health model and animated portal; they are not claims of pixel-exact
engine equivalence. The original gamma-adjusted preview used its historical
`**0.55` fit; the raw comparison used its unadjusted output. It had no modulation
control, so no baseline is reported for modulation 3.

Eye coordinates (including ezQuake's 1/16u anti-plane offset) were
`(-469.9375, -39.9375, -29.9375), yaw 90, pitch 0` for the north wall;
`(-959.9375, 736.0625, 14.0625), yaw 180, pitch 30` for the portal; and
`(-419.9375, 40.0625, -29.9375), yaw 270, pitch 0` for the bright south wall.
The local server's spectator view adds 22u to `cam_pos` Z before that offset.
Results are specific to these settings: `vid_gammacorrection 1` enables a
different sRGB pipeline and is not modeled by this preview.

## Liquid surfaces and preview limits

`*` textures retain the `texinfo` axes but ignore its translation offsets, using
`dot(world_position, axis) / 64` for normalized texture coordinates, as in
[`EmitWaterPolys`' surface builder](https://github.com/QW-Group/ezquake-source/blob/3.6.9/src/r_brushmodel_warpsurfaces.c).
Repeat distance is 64 units even for a texture image that is not 64x64. This
exposes the shifted teleporter alignment that the old renderer hid. Ordinary
textures still honor their offsets. Liquids without lightmaps are fullbright;
liquids with compiled lightmaps use them.

These are static previews: liquid ripple animation, transparency, scrolling
skies, dynamic lights, sprites, models, external replacement textures, and
runtime brush movement are not simulated. Texture sampling uses nearest
filtering without mipmaps. Inspect liquid alignment in this unwarped view and
verify the moving surface in-client. The classic and modern ezQuake liquid
animation paths differ; a static preview cannot reproduce every animation frame.
