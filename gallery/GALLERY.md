# Gallery — the nine maps built so far

Each map has a plan (`*_plan.jpg`) and a sheet of preview renders (`*_views.jpg`).

**How to use this.** It is a reference, not a blacklist. Reuse the building blocks you see here
freely — hubs, balconies, loops, broad stairs, a high ground with two ways up, a contested
powerup room are the vocabulary of every good map. What to avoid is *defaulting* to the same
overall skeleton or the same look as a map already in this list. Aim for a fresh take on a
classic form (GUIDE section 3).

| Map | Mode | Symmetry | Skeleton | Look |
|---|---|---|---|---|
| ca_agora | CA 6–10 | rotation | Four quadrants of ground halls (0) and galleries (128) round a central court (0); upper walks (224) meet on a bridge over the court (RA on the bridge, Quad below it) | industrial base |
| ca_vigil | CA | rotation | Cruciform church: nave and aisles (0), chapels in the corners, a crypt (−128) under the crossing, upper galleries (224) along both sides of the nave with bridges across | gothic |
| ca_crucible | CA | two-sided (hammer / anvil) | One great foundry hall with a lava pool and an RA island in the middle; a conduit loop round the outside; furnace rooms at the ends linked by teleporters; two decks (192) joined by a bridge over the lava | runic foundry, lava |
| relay | FFA | none | Central atrium / reactor; a sunken yard (−64) along the south and west; a balcony and mezzanine (160) along the north with a vault (256) in the corner; teleporters and a jump pad | slipgate tech |
| ca_cistern | CA/TDM 8–12 | none | A row of halls (0); a sunken cistern band (−96) with tunnels along the south; a gallery and colonnade (160) along the north | drowned waterworks, teal |
| ctf_bastion | CTF 8–12 | rotation | Bases at the east and west ends; a central mid room; side routes; an undercroft (−128) and a high route (192); hook-only perches | rival forts, black and gold mid |
| ca_lyceum | CA/TDM 8–12 | none | A hub with three distinct satellites (tower with a 288 stand, sunken pit, duel hall); a balcony (160) over the hub leading to a gallery and to a climb up to the stand | lamplit academy: marble, an observatory under the night sky, a black fresco hall |
| ctf_circuit | CTF 8–12 | mirror | A "theta" racetrack round a solid core: a high arc (192) along the north, a low arc (−128) along the south, and a spine through the core and a mid chamber (Quad) | desert citadel: sandstone, glazed team-coloured tile, a gilded cupola |
| ctf_strata | CTF 8–12 | rotation | Two whole levels stacked base to base: lower halls (0) under upper decks (256); a tall open-sky atrium in the middle where the decks cross as bridges over the arena (Quad); covered side lanes (undercroft below each bridge, arcade wall beside it); a well through the slab in each half; flags on a mezzanine (128) between the levels | "The dig": banded ironstone, slate, chalk and flint strata, team-coloured cable strips and lamps by half, direction signs |

**A family resemblance to know about.** Relay, Cistern and Lyceum share one skeleton: a central
hall at floor level, a broad stair to a balcony strip along the north edge, a sunken band along
the south, a tall room in the west. It came from starting each map by copying the previous one.
Each is a good map — but a fourth in that family would not be news. Circuit broke the pattern by
sketching three different skeletons before building anything.

**What the group liked most:** Crucible, then Agora and Relay (before Lyceum and Circuit were
built); Lyceum's hub and observatory and Circuit's look were called out as striking. The most
recent maps (Circuit, Strata) are the group's favourites; Strata's light wells were singled out.
Disliked elsewhere: maze-like CTF with close flags (ctf6).

## Height profiles (`profiles/`)

After nine maps the group asked why the layouts felt flat. `qmap/vprofile.py` measured our nine
maps against five classic QuakeWorld maps the group rates (aerowalk, ztndm3, dapak12, naked3,
naked4). The reference BSPs are not included; only their numbers are, in `profiles/profiles.json`.

| | stacked | levels | biggest level | overlook | cross-level sight | route height /1000 | angled walls | teleporters |
|---|---|---|---|---|---|---|---|---|
| **five classics** | 0.19–0.21 | 3.9–5.2 | 0.28–0.41 | 0.46–0.62 | 0.31–0.42 | 251–551 | 0.03–0.22 | 2–5 |
| ca_agora | 0.03 | 3.1 | 0.46 | 0.34 | 0.32 | 104 | 0 | 0 |
| ca_vigil | 0.29 | 3.8 | 0.57 | 0.41 | 0.36 | 128 | 0 | 0 |
| ca_crucible | 0.15 | 2.0 | 0.78 | 0.23 | 0.27 | 114 | 0 | 2 |
| relay | 0.00 | 4.1 | 0.48 | 0.55 | 0.40 | 229 | 0 | 2 |
| ca_cistern | 0.00 | 4.1 | 0.43 | 0.50 | 0.42 | 110 | 0 | 0 |
| ctf_bastion | 0.01 | 3.4 | 0.58 | 0.39 | 0.30 | 112 | 0 | 0 |
| ca_lyceum | 0.00 | 4.0 | 0.58 | 0.41 | 0.40 | 202 | 0 | 0 |
| ctf_circuit | 0.00 | 3.7 | 0.43 | 0.26 | 0.18 | 71 | 0 | 0 |
| ctf_strata | 0.32 | 2.5 | 0.56 | 0.31 | 0.17 | 61 | 0 | 0 |

What it says: the classics change height about **two to five times as often along their routes**
(item to item), spread their floor over **more levels with no level dominant**, let you **see
floor below you** from most places, and use **angled walls and teleporters**. Ours mostly stack
nothing, put half their floor on one level, and route along it. Strata stacks more than any
classic (0.32) and is still the flattest to *play*: two big level slabs, each crossed on its own
level (route height 61). **Stacked is not vertical**; what counts is how often a route climbs or
drops, and what you can see above and below you.

* `verticality_compare.jpg`: every measure, ours against the reference range.
* `verticality_refs.jpg`, `verticality_ours.jpg`: floor height maps of each map.
* `ctf_strata_section.png`, `ctf_strata_iso.png`: `qmap/section.py` and `qmap/iso.py` on Strata,
  which show the two slabs at a glance.
