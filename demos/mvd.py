"""Minimal QuakeWorld MVD reader: player positions over time, prints (frags / flag events), userinfo.
Coords are short/8 (no FTE float coords in this demo). Unknown svc -> rest of that block skipped."""
import struct, sys

DF_ORIGIN, DF_ANGLES, DF_EFFECTS, DF_SKINNUM = 1, 1 << 3, 1 << 6, 1 << 7
DF_DEAD, DF_GIB, DF_WEAPONFRAME, DF_MODEL = 1 << 8, 1 << 9, 1 << 10, 1 << 11


class R:
    def __init__(s, b):
        s.b, s.p = b, 0
    def left(s): return len(s.b) - s.p
    def u8(s): v = s.b[s.p]; s.p += 1; return v
    def s8(s): v = struct.unpack_from('<b', s.b, s.p)[0]; s.p += 1; return v
    def u16(s): v = struct.unpack_from('<H', s.b, s.p)[0]; s.p += 2; return v
    def s16(s): v = struct.unpack_from('<h', s.b, s.p)[0]; s.p += 2; return v
    def i32(s): v = struct.unpack_from('<i', s.b, s.p)[0]; s.p += 4; return v
    def f32(s): v = struct.unpack_from('<f', s.b, s.p)[0]; s.p += 4; return v
    def coord(s): return s.s16() / 8.0
    def string(s):
        e = s.b.index(0, s.p); v = s.b[s.p:e]; s.p = e + 1
        return v.decode('latin-1')


def qstr(t):   # strip Quake high-bit "red text" and specials
    out = []
    for ch in t:
        c = ord(ch) & 127
        if c == 16: out.append('[')
        elif c == 17: out.append(']')
        elif 18 <= c <= 27: out.append(str(c - 18))
        elif c < 32 and c != 10: out.append('')
        else: out.append(chr(c))
    return ''.join(out)


def parse(path):
    data = open(path, 'rb').read()
    p, t = 0, 0.0
    players = {}          # num -> dict(name, team, pos)
    track = []            # (t, num, x, y, z, dead)
    prints = []           # (t, text)
    stats = []            # (t, num, stat, value)
    unknown = {}
    cur = None
    while p < len(data):
        dt = data[p]; cmd = data[p + 1]; p += 2
        t += dt / 1000.0
        typ = cmd & 7
        if typ == 2:                       # dem_set
            p += 8; continue
        if typ == 0:                       # dem_cmd (not in mvd)
            break
        target = None
        if typ == 3:                       # dem_multiple
            mask = struct.unpack_from('<I', data, p)[0]; p += 4
            if mask == 0:                  # hidden message block
                n = struct.unpack_from('<i', data, p)[0]; p += 4 + n; continue
        elif typ in (4, 5):
            target = cmd >> 3
        n = struct.unpack_from('<i', data, p)[0]; p += 4
        blk = data[p:p + n]; p += n
        r = R(blk)
        try:
            while r.left() > 0:
                svc = r.u8()
                if svc in (1,): continue
                if svc == 3: num, v = r.u8(), r.u8(); stats.append((t, target, num, v))
                elif svc == 38: num, v = r.u8(), r.i32(); stats.append((t, target, num, v))
                elif svc == 6:
                    ch = r.u16()
                    if ch & (1 << 15): r.u8()
                    if ch & (1 << 14): r.u8()
                    r.u8(); r.coord(); r.coord(); r.coord()
                elif svc == 8: lvl = r.u8(); prints.append((t, qstr(r.string())))
                elif svc in (9, 26, 31): r.string()
                elif svc == 10: r.u8(); r.u8(); r.u8(); r.u8()
                elif svc == 12: r.u8(); r.string()
                elif svc == 14: r.u8(); r.s16()
                elif svc == 36: r.u8(); r.s16()
                elif svc == 53: r.u8(); r.u8()
                elif svc == 37: r.u8(); r.f32()
                elif svc == 40:
                    num = r.u8(); r.i32(); ui = r.string()
                    kv = ui.split('\\')[1:]
                    d = dict(zip(kv[::2], kv[1::2]))
                    pl = players.setdefault(num, {'name': '', 'team': '', 'pos': [0, 0, 0], 'dead': False})
                    pl['name'] = qstr(d.get('name', '')); pl['team'] = qstr(d.get('team', ''))
                elif svc == 51:
                    num = r.u8(); k = r.string(); v = r.string()
                    pl = players.setdefault(num, {'name': '', 'team': '', 'pos': [0, 0, 0], 'dead': False})
                    if k == 'name': pl['name'] = qstr(v)
                    if k == 'team': pl['team'] = qstr(v)
                elif svc == 52: r.string(); r.string()
                elif svc == 39: r.u16()
                elif svc == 19: r.u8(); r.u8(); r.coord(); r.coord(); r.coord()
                elif svc == 23:
                    te = r.u8()
                    if te in (2, 12): r.u8()
                    if te in (5, 6, 9): r.u16(); [r.coord() for _ in range(6)]
                    else: r.coord(); r.coord(); r.coord()
                elif svc == 30: [r.coord() for _ in range(3)]; [r.u8() for _ in range(3)]
                elif svc in (32, 44, 24): r.u8()
                elif svc in (34, 35, 27, 28, 33): pass
                elif svc in (49, 50): r.f32()
                elif svc == 16: r.u16()
                elif svc == 43: c = r.u8(); r.p += 6 * c
                elif svc == 54: c = r.u8(); r.p += 7 * c
                elif svc == 42:
                    num = r.u8(); fl = r.u16(); r.u8()
                    pl = players.setdefault(num, {'name': '', 'team': '', 'pos': [0, 0, 0], 'dead': False})
                    pl.setdefault('fx', 0)
                    for i in range(3):
                        if fl & (DF_ORIGIN << i): pl['pos'][i] = r.coord()
                    for i in range(3):
                        if fl & (DF_ANGLES << i): r.u16()
                    if fl & DF_MODEL: r.u8()
                    if fl & DF_SKINNUM: r.u8()
                    if fl & DF_EFFECTS: pl['fx'] = r.u8()
                    if fl & DF_WEAPONFRAME: r.u8()
                    pl['dead'] = bool(fl & (DF_DEAD | DF_GIB))
                    track.append((round(t, 3), num, *pl['pos'], pl['dead'], pl['fx']))
                else:
                    unknown[svc] = unknown.get(svc, 0) + 1
                    break
        except (IndexError, struct.error, ValueError):
            unknown['err'] = unknown.get('err', 0) + 1
    return players, track, prints, stats, unknown, t


if __name__ == '__main__':
    pl, tr, pr, st, unk, t = parse(sys.argv[1])
    print('duration', round(t, 1), 's; track samples', len(tr), '; prints', len(pr))
    print('unknown svc counts', unk)
    for k, v in sorted(pl.items()):
        print(k, v['name'], v['team'])
