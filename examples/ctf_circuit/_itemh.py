# --- items (for FFA / TDM / Freeze Tag; Clan Arena mods ignore them) -------
# Positions are item centres on the floor; pairs are rotated copies so both
# halves of the map hold identical stacks. Singles sit on the rotation centre.
items = []   # (classname, x, y, floor_z, spawnflags, label)

# origin offset from (centre, floor) for each item's bounding box
CORNER = ('item_health', 'item_shells', 'item_spikes', 'item_rockets', 'item_cells')
SHORT = {
    'weapon_supershotgun': 'SSG', 'weapon_nailgun': 'NG', 'weapon_supernailgun': 'SNG',
    'weapon_grenadelauncher': 'GL', 'weapon_rocketlauncher': 'RL', 'weapon_lightning': 'LG',
    'item_armor1': 'GA', 'item_armor2': 'YA', 'item_armorInv': 'RA',
    'item_artifact_super_damage': 'QUAD', 'item_health': 'h', 'item_shells': 's',
    'item_spikes': 'n', 'item_rockets': 'r', 'item_cells': 'c',
    'item_flag_team1': 'RED', 'item_flag_team2': 'BLUE',
}


def item(cls, x, y, z, flags=0, sym=True):
    lab = SHORT[cls]
    if cls == 'item_health' and flags & 2:
        lab = 'MH'
    elif cls == 'item_health' and flags & 1:
        lab = 'h15'
    items.append((cls, x, y, z, flags, lab))
    if sym:
        items.append((cls, -x, y, z, flags, lab))       # mirror copy (red half)

