
# --- items (blue half written; sym=True adds the rotated red copy) ----------------------------
item('item_flag_team2', 2624, 0, 144, sym=False)           # BLUE flag (east), on the mezzanine
item('item_flag_team1', -2624, 0, 144, sym=False)          # RED flag (west)
item('item_artifact_super_damage', 0, 0, 32, sym=False)    # Quad: the atrium's lower arena
item('item_armor2', 256, 544, 256)                         # YA: middle of each bridge (pair)
item('item_health', 1248, 160, 256, flags=2)               # Mega: well room, beside the well
item('item_armorInv', 1696, -512, 0)                       # RA: lower hall, the base end
item('weapon_rocketlauncher', 1216, 448, 256)              # RL: north deck
item('weapon_lightning', 1696, 448, 0)                     # LG: lower hall
item('weapon_grenadelauncher', 704, 0, 0)                  # GL: lower hall, atrium end
item('weapon_supernailgun', 1216, -448, 256)               # SNG: south deck
item('weapon_supershotgun', 2176, 0, 0)                    # SSG: base floor
item('weapon_nailgun', 2336, 512, 256)                     # NG: north balcony
item('item_armor1', 2336, -512, 256)                       # GA: south balcony
for cls, x, y, z, f in [('item_health', 896, 0, 0, 0), ('item_health', 1664, 224, 0, 1),
                        ('item_health', 704, 448, 256, 0), ('item_health', 1792, -448, 256, 0),
                        ('item_health', 2048, 0, 0, 1), ('item_health', 1248, -160, 256, 0),
                        ('item_health', 384, -320, 0, 0), ('item_health', 160, 544, 0, 0),
                        ('item_rockets', 1088, 448, 0, 0), ('item_rockets', 1792, 448, 256, 0),
                        ('item_rockets', 2176, 256, 0, 0), ('item_rockets', 384, 320, 0, 0),
                        ('item_cells', 1088, -448, 0, 0), ('item_cells', 704, -448, 256, 0),
                        ('item_shells', 2176, -256, 0, 0), ('item_spikes', 1664, -224, 0, 0),
                        ('item_spikes', 2048, -512, 256, 0)]:
    item(cls, x, y, z, flags=f)
