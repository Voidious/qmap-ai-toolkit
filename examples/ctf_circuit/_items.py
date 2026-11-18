
# --- items (blue half written; sym=True adds the red mirror copy) ------------------------------
item('item_flag_team2', 2848, 0, 48, sym=False)            # BLUE flag (east)
item('item_flag_team1', -2848, 0, 48, sym=False)           # RED flag (west)
item('item_artifact_super_damage', 0, -160, 32, sym=False)  # Quad: mid chamber, south of the central column
item('item_health', 0, 1568, 192, flags=2, sym=False)      # Mega: north court
item('item_armorInv', 0, -1568, -128, sym=False)           # RA: south court
item('weapon_rocketlauncher', 1264, 1024, 192)              # RL: middle of the aqueduct bridge
item('weapon_lightning', 1264, -1120, -128)                # LG: undercroft
item('weapon_grenadelauncher', 1136, 224, 0)               # GL: spine junction
item('weapon_supernailgun', 2640, 960, 192)               # SNG: gatehouse
item('weapon_supershotgun', 2640, -960, -128)             # SSG: cellar
item('weapon_nailgun', 2560, 352, 0)                       # NG: flag hall
item('item_armor2', 512, 1472, 192)                        # YA: north court (each side)
item('item_armor1', 512, -1472, -128)                      # GA: south court (each side)
for cls, x, y, z, f in [('item_health', 1136, 768, 0, 0), ('item_health', 896, -800, -128, 0),
                        ('item_health', 1952, 1056, 192, 0), ('item_health', 1952, -1056, -128, 0),
                        ('item_health', 2080, 288, 0, 1), ('item_health', 3168, 0, 0, 0),
                        ('item_health', 2912, -352, 0, 0), ('item_health', 384, 320, 0, 1),
                        ('item_health', 1280, -256, 0, 0),
                        ('item_rockets', 800, 1184, 192, 0), ('item_rockets', 1600, -800, -128, 0),
                        ('item_rockets', 2080, -288, 0, 0), ('item_rockets', 384, -320, 0, 0),
                        ('item_cells', 1600, -1120, -128, 0), ('item_cells', 1264, 1216, 0, 0),
                        ('item_shells', 3072, 1056, 192, 0), ('item_shells', 3072, -1056, -128, 0),
                        ('item_spikes', 960, -256, 0, 0), ('item_spikes', 2464, 0, 0, 0)]:
    item(cls, x, y, z, flags=f)
# b2: perch stacks
item('item_rockets', 416, -48, 288)
item('item_health', 416, 48, 288, flags=1)
item('item_cells', 1216, 1248, 352)
item('item_health', 1312, 1248, 352, flags=1)
item('item_health', 1856, 128, 256)
item('item_rockets', 1856, 256, 256)
