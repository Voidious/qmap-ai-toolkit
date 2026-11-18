
S = dict(sym=False)
item('item_armorInv', -256, -960, -96, **S)             # RA: pit floor
item('item_health', -736, 672, 288, flags=2, **S)       # Mega: tower stand
item('item_armor2', 800, -352, 64, **S)                 # YA: duel platform
item('item_armor2', 288, 320, 160, **S)                 # YA: hub balcony, east end
item('item_armor1', -288, 128, 0, **S)                  # GA: hub floor
item('weapon_rocketlauncher', 0, -160, 48, **S)         # RL: hub plinth
item('weapon_rocketlauncher', -1024, 640, 0, **S)       # RL: tower floor, under the stand
item('weapon_lightning', -448, 704, 288, **S)           # LG: top of the climb
item('weapon_grenadelauncher', -704, -896, -96, **S)    # GL: pit floor
item('weapon_supernailgun', 608, -832, 0, **S)          # SNG: duel hall, by the low passage
item('weapon_supershotgun', -704, -352, 0, **S)         # SSG: tower-pit corridor
item('weapon_nailgun', 160, -832, -96, **S)             # NG: low passage
for cls, x, y, z, f in [('item_health', 320, -320, 0, 0), ('item_health', -1024, -128, 0, 0),
                        ('item_health', -96, -576, 0, 0), ('item_health', 1024, -832, 0, 0),
                        ('item_health', 1024, -160, 0, 0), ('item_health', -224, 320, 160, 1),
                        ('item_health', -768, -960, -96, 0), ('item_rockets', -320, -96, 0, 0),
                        ('item_rockets', -768, 128, 0, 0), ('item_rockets', 1024, -448, 0, 0),
                        ('item_rockets', -832, 544, 288, 0), ('item_cells', -448, 320, 160, 0),
                        ('item_shells', 576, 64, 0, 0), ('item_spikes', 256, -832, -96, 0)]:
    item(cls, x, y, z, flags=f, **S)
