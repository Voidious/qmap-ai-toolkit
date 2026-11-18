
item('item_flag_team2', 2048, 0, 48, sym=False)            # BLUE flag
item('item_flag_team1', -2048, 0, 48, sym=False)           # RED flag
item('item_artifact_super_damage', 0, 0, 32, sym=False)    # Quad, centre of mid
item('item_health', 320, 512, 192, flags=2)                # Mega on each team's mid ledge
item('weapon_rocketlauncher', 832, 512, 192)               # RL: high route
item('weapon_lightning', 960, -640, -128)                  # LG: undercroft
item('weapon_grenadelauncher', 1056, -64, 0)               # GL: corridor
item('weapon_supernailgun', 1600, -160, 0)                 # SNG: base hall
item('weapon_supershotgun', 1344, 160, 0)                  # SSG: base hall
item('weapon_nailgun', 2176, 256, 192)                     # NG: flag gallery
item('item_armor2', 1280, 512, 192)                        # YA: base balcony
item('item_armor1', 320, -160, 0)                          # GA: mid floor
# mid end-wall perch (over your corridor mouth, 352): two small health, rockets, shells
item('item_health', 416, -144, 352, flags=1)
item('item_rockets', 416, -64, 352)
item('item_shells', 416, 16, 352)
item('item_health', 416, 112, 352, flags=1)
# mid long-wall perch (above your ledge, 384): rockets, cells, nails
item('item_cells', 0 - 96, 544, 384)
item('item_rockets', 0 - 16, 544, 384)
item('item_spikes', 0 + 64, 544, 384)
item('item_health', 1504, -544, 320)                       # base hall perch: health + cells for a defender
item('item_cells', 1600, -544, 320)
for cls, x, y, z, f in [('item_health', 1920, -256, 0, 0), ('item_health', 2176, -192, 0, 0),
                        ('item_health', 1600, -480, 0, 0), ('item_health', 640, 64, 0, 0),
                        ('item_health', 800, -320, -128, 0), ('item_health', 1120, -640, -128, 0),
                        ('item_health', 1088, 512, 192, 1), ('item_health', 384, 0, 0, 1),
                        ('item_rockets', 1696, -320, 0, 0), ('item_rockets', 608, 512, 192, 0),
                        ('item_cells', 1120, -288, -128, 0), ('item_shells', 576, -64, 0, 0),
                        ('item_spikes', 1920, 128, 0, 0), ('item_health', 512, 704, 192, 0), ('item_rockets', -544, 704, -128, 0), ('item_health', 1856, -576, 0, 0), ('item_rockets', 2176, -640, 0, 0), ('item_shells', 1312, 96, 0, 0)]:
    item(cls, x, y, z, flags=f)
