# Five-map item-placement survey

Snapshot: 2026-11-20. Local BSP29 copies of aerowalk, ztndm3, dapak12, naked3
and naked4, selected by the mapper as good references. The original BSPs are
not redistributed. `reference.json` retains each BSP SHA256, source-tool hashes,
raw item classes/flags/origins, quantities, projection status and directed pairs.
The adjacent figures show locations and route matrices, not balance rankings.

## Inventory and supply

| Map | RA / YA / GA | RL / LG | MH / Quad | Ordinary health | Loose rockets / cells / nails / shells |
| --- | --- | --- | --- | ---: | --- |
| aerowalk | 1 / 1 / 2 | 2 / 1 | 1 / 0 | 200 | 20 / 24 / 100 / 0 |
| ztndm3 | 1 / 1 / 2 | 2 / 1 | 1 / 1 | 235 | 30 / 24 / 175 / 60 |
| dapak12 | 1 / 1 / 2 | 2 / 1 | 1 / 1 | 155 | 35 / 30 / 175 / 100 |
| naked3 | 1 / 1 / 1 | 2 / 1 | 1 / 0 | 220 | 25 / 48 / 150 / 40 |
| naked4 | 1 / 2 / 1 | 2 / 1 | 1 / 0 | 210 | 35 / 36 / 175 / 60 |

These are **embedded inventories**, not a recommendation to enable every item
in every mode. No listed pickup has the not-deathmatch flag, but other mod
conventions may suppress extra armor or powerups. Totals include special-access
locations such as Dapak12's deep supply stash. Loose quantities use standard
QW small/big crate definitions, not weapon pickup ammo, drops, timers or actual
available supply per minute. See [quantity assumptions](../../qmap/ITEMS.md).

Three maps use RA + YA + two GA; one substitutes a second YA for a GA. The
useful inference is to inspect alternate recovery/control opportunities, not
to declare four armor pickups universally correct. All five have two RLs and
one LG, so "put LG on the other side from RL" is incomplete: which RL, which
armor/MH, and which approach/control position?

## Relative placement, not a minimum separation rule

The matrices distinguish direction, climb/drop and teleport links. Examples
of local ammo support coexist with reserves on longer rotations: modeled
weapon-to-ammo routes in ZTN can be around 48 units; Naked3 also has cell
reserves far from LG. An isolated crate can be intentional, but it needs a
route role rather than merely occupying empty floor.

For the most compact **supported** RL/LG/RA trio on each map:

| Map | Minimum three-location visit cost | Relative to map travel median | Common-eye samples |
| --- | ---: | ---: | --- |
| aerowalk | 1,550 | 1.69 | 0 / 256 |
| ztndm3 | 1,847 | 1.61 | 0 / 256 |
| dapak12 | 1,099 | 1.06 | 0 / 256 |
| naked3 | unknown | unknown | unknown |
| naked4 | unknown | unknown | unknown |

Costs are the existing movement model's units, not seconds or a guarantee of
visiting every pickup with real movement. Common-eye sampling is deterministic,
world-only, and limited to 1,200 units from each target; zero is not proof that
no control vantage exists. The latter two maps have an unresolved RA stance,
so they are not assigned zero cost, omitted without explanation, or graded bad.
Some reverse routes in the first three are also missing in the model even
though the maps are playable; inspect the nullable matrix, not just this table.

**Dapak12 is an important counterexample to a blanket distance rule:** a short
three-item visit can coexist with geometry that prevents a single sampled
standing position from seeing all three. Pair distances, route asymmetry,
height, exposure and nearby counters need to be read together. An item's eye
ray is not the same as weapon control or safety from splash.

### Which resources support which guns?

Directed model costs **from each premium resource to the nearest supported RL
and to LG** make the tradeoffs easier to inspect. Rounded units are not seconds;
the JSON retains both RL identities and both directions, not just this minimum.

| Map | Resource | To nearest RL | To LG |
| --- | --- | ---: | ---: |
| aerowalk | RA | 567 | 609 |
| aerowalk | YA | 999 | 1,832 |
| aerowalk | MH | 583 | 1,416 |
| ztndm3 | RA | 409 | 1,145 |
| ztndm3 | YA | 1,157 | 1,195 |
| ztndm3 | MH | 64 | 1,412 |
| dapak12 | RA | 144 | 907 |
| dapak12 | YA | 858 | 328 |
| dapak12 | MH | unknown | unknown |
| naked3 | RA | unknown | unknown |
| naked3 | YA | 840 | 125 |
| naked3 | MH | unknown | unknown |
| naked4 | RA | unknown | unknown |
| naked4 | YA1 | 821 | 1,246 |
| naked4 | YA2 | 774 | 1,195 |
| naked4 | MH | 490 | 1,916 |

ZTN's MH strongly favors a nearby RL route, whereas Dapak12 and Naked3 put YA
closer to LG than to either modeled RL. Aerowalk's RA has short routes to both
guns: this is another reason not to ban proximity without examining cover and
approaches. These observations describe routes, not ownership or a player's
ability to collect every resource uncontested. Lower-tier armor also matters:
Dapak12's two GAs have LG routes of 446 and 258 units, so useful recovery need
not be isolated from every strong weapon. Inspect the full matrices and play
the transitions rather than applying one preferred arrangement to every map.

## Unresolved endpoints

The model does not connect these sampled pickup stances:

- aerowalk: none.
- ztndm3: first H25 and Quad.
- dapak12: MH, Quad and the deep stash's H25/cells/rockets/shells/nails.
- naked3: RA and MH.
- naked4: RA.

This is **not evidence those items are unavailable in real play**. Projection,
limited running-gap/jump modeling, special access and scripted movement need
client inspection. All raw pickups remain in inventory; unsupported costs and
common-eye results are null. No universal reference ranges are derived by
silently replacing these unknowns with zero or Euclidean distance.

## Reproduce

From the toolkit root, with the BSP files available locally:

```bash
python3 qmap/itemprofile.py \
  /your/maps/aerowalk.bsp /your/maps/ztndm3.bsp /your/maps/dapak12.bsp \
  /your/maps/naked3.bsp /your/maps/naked4.bsp \
  --json gallery/items/reference.json --png-dir gallery/items
```

Requires the same NumPy/numba stack as vprofile, plus matplotlib for figures.
Read [the tool contract and limitations](../../qmap/ITEMS.md). When comparing a
new placement, keep the geometry, model and sample fixed, use `--move` or a
fresh compiled BSP, and verify actual pickup/spawn behavior separately.
