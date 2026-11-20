# Item diagnostics (v3.4)

These tools inform design review. They do not rate balance, establish pickup
availability under every mod, or replace a live match.

## Inventory, quantities and frequency

```bash
python3 qmap/itemprofile.py /path/to/map.bsp --inventory-only --json inventory.json
```

Inventory reads actual BSP29 entities, keeps distinct IDs for duplicates (RL1,
RL2, GA1, GA2), and records class, flags, raw origin and XY pickup center.
`spawnflags & 2048` items are listed separately as not-deathmatch. Other
mode/mod conventions are not guessed. Unknown item classes and override fields
are reported rather than silently assigned invented quantities.

`supply` counts embedded pickups and estimates **standard QuakeWorld** loose
ammo/ordinary health from class and small/big flags. Weapon pickup ammo, MH,
armor absorption, backpacks, respawn timers, weapon-stay, and player counts are
not converted into a fictitious supply-per-minute total. Quantity definitions
and centered-versus-corner box conventions follow
[id Software's items.qc](https://github.com/id-Software/Quake/blob/master/QW/progs/items.qc).
For temporal frequency, record the server's real rules and actual pickup events;
the BSP alone cannot establish consumption or respawn pressure.

## Relative placement

```bash
python3 qmap/itemprofile.py /path/to/map.bsp --json placement.json --png-dir figures
python3 qmap/itemprofile.py first.bsp second.bsp --json comparison.json
```

Full mode uses the existing vprofile player-hull movement graph. The default
`vprofile.profile()` and CLI outputs are unchanged; a new explicit
`with_navigation=True` option exports an internal graph bundle for tools.
No AST instrumentation or absolute workspace paths are needed.

Main JSON fields:

- `items`: inventory plus `projection`, with `center_stance`, conservative
  `nearby_touch_stance`, or `unresolved`. A missing stance is not proof that a
  classic-map item is unavailable to a real player.
- `pairs`: **directed** RL/LG/armor/MH/powerup routes. `model_cost` is the
  existing graph's cost: horizontal movement plus jump/gap costs and fixed
  teleporter/pad links. It is not exact physical distance or seconds. Ascent,
  descent, edge kinds and ratio to map travel median retain context. `--paths`
  adds stance coordinates for inspecting the actual modeled route.
- `world_eye_los`: world-BSP rays at the projected standing eye positions. It
  is not a complete projectile/splash or moving-door/func_wall visibility test.
- `nearest_matching_weapon`: nearest matching gun **to** an ammo cache by
  directed model cost. Shells can also support the spawn shotgun; not every
  distant reserve needs an SSG beside it.
- `rl_lg_resource_groups`: each RL + LG + armor/MH trio. Minimum visit cost
  considers all orders, and cycle cost considers return to the start. These
  visit locations, not necessarily three simultaneously available pickups.
  Common-eye counts sample up to 256 reachable stances, seed 7, with a 1,200-unit
  three-dimensional radius to each target. Zero means no sampled common view,
  not no possible control position. An unresolved target gives `null`, not 0.
- `geometry_profile`: the input map's geometry/travel context, excluding old
  item-route measures that would become misleading after a hypothetical move.

Route costs are nullable. Unsupported endpoints and disconnected directions
are never silently treated as zero or straight-line substitutes. The movement
model includes ordinary steps/jumps, limited gap jumps, drops and the existing
teleport/pad approximations; it cannot certify all real QW movement tricks.
Floor reachability is the existing union from recognized starts, not a claim
that every modeled region belongs to one strongly connected arena.

Projection looks below the spawn origin within the standard 256-unit item
drop range. Centered armor/weapons and corner-origin health/ammo are treated
differently. A nearby touch stance may be used only with horizontal trigger
overlap, vertical overlap and a clear world ray. That is a conservative
diagnostic, not an exact item-toss/trigger simulation. Inspect unresolved spots
in the client and retain them in inventory totals.

The figure places pickups over reachable floor, with unresolved ones marked x,
and shows a directed matrix. Gray entries are unknown. Stacked floors can
overlap in plan; use sections and actual views before judging control.

## Compare a proposed move without editing a map

```bash
python3 qmap/itemprofile.py map.bsp --move LG1=320,848,192 --json proposed.json
```

Coordinates are **pickup center X,Y and intended floor Z**, not entity origin.
The report is labeled hypothetical, retains the input BSP hash and records the
move. It never writes a BSP. A candidate settling on a different floor remains
unresolved. Moves do not check spawn margins, item overlap or every box edge;
the generator checker, compiled hull check and runtime still own those checks.
Compare candidates on the same geometry and sample, not against a universal
"minimum weapon distance". `prepare()` and `analyze()` can reuse one graph when
evaluating several candidate placements from Python.

The JSON has `schema_version: 1`, BSP SHA256 and tool-source hashes. Its quantity
basis is explicit. Figures use map-local scales. See
[`gallery/items/README.md`](../gallery/items/README.md) for reference evidence
and the substantial unsupported-endpoint caveats.

## Verify generated pickups in a real server

```bash
python3 qmap/itemcheck.py generated.json edicts.txt --json runtime.json
```

Capture a plain `edicts` dump from an authorized local MVDSV server **after item
settling**, in a mode where the generated items should exist. This checker is
offline: it starts no server, sends no RCON requests, and handles no credentials.
It matches class counts, one-to-one XY centers, bounding-box bottoms against
intended floors, and active `SOLID_TRIGGER`/pickup touch functions. Mismatches
exit nonzero. Runtime ammo/heal values and source hashes are retained.

This was exercised against MVDSV 0.33's text format. Mod-suppressed pickups,
custom classes/touch functions, a truncated dump or different output format
can fail intentionally; diagnose the mode/format before blaming the map.
The check does not simulate a player acquiring an item, prove approach fairness,
or validate timers/combat balance.
