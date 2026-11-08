#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Asset generator for the Hive Solutions Game Boy intro.

Produces an RGBDS include file with every piece of data the ROM needs
(tiles, tile map patches, CGB attributes, palettes and the motion tables)
so that the runtime code only has to walk tables, keeping the CPU idle
(halted) for most of each frame.

Pure standard library, so it runs with any stock Python 3.
"""

import math
import sys

# -----------------------------------------------------------------------------
# Layout (screen pixels)
# -----------------------------------------------------------------------------

CX, CY = 80, 64  # logo center, tile aligned so the BG logo uses solid tiles only
U_BEE = 4  # unit (small square side) of the flying bee, 16x16 px in total
U_LOGO = 16  # unit of the final logo, 64x64 px in total
TEXT = "HIVE SOLUTIONS"
TEXT_ROW = 14
TEXT_COL = (20 - len(TEXT)) // 2
WIN_Y = 104  # window top, covers the text row until the bee "writes" it
WX_HIDDEN = 167  # any WX >= 167 keeps the window off screen
TRAIL_DOTS = 4
TRAIL_STEP = 7  # frames between pollen dots
TRAIL_PAD = TRAIL_DOTS * TRAIL_STEP

# colour indexes used by every tile: 0 background, 1 white, 2 light, 3 dark
BG, WHITE, LIGHT, DARK = 0, 1, 2, 3

# CGB colours sampled from the Hive Solutions logo
RGB_WHITE = (255, 255, 255)
RGB_LIGHT = (166, 183, 209)
RGB_DARK = (33, 76, 144)
RGB_BG_TOP = (88, 120, 170)
RGB_BG_BOTTOM = (132, 155, 194)
BANDS = 8  # one CGB BG palette per gradient band

# DMG shade (0 lightest .. 3 darkest) for each colour index
DMG_SHADES = (2, 0, 1, 3)

# -----------------------------------------------------------------------------
# Small helpers
# -----------------------------------------------------------------------------


def logo_pixel(x, y, u):
    """Colour of the Hive logo (4u x 4u) at the given local pixel."""
    if y < 2 * u:
        return WHITE if x < 2 * u else DARK
    if x >= 2 * u and y < 4 * u:
        return WHITE
    if u <= x < 2 * u and y < 3 * u:
        return LIGHT
    return BG


def encode_tile(rows):
    """Encodes an 8x8 tile (list of rows of colour indexes) into 2bpp bytes."""
    data = []
    for row in rows:
        lo = hi = 0
        for x, c in enumerate(row):
            bit = 0x80 >> x
            if c & 1:
                lo |= bit
            if c & 2:
                hi |= bit
        data += [lo, hi]
    return data


def blank():
    return [[0] * 8 for _ in range(8)]


def rect_tile(color, x0, y0, x1, y1):
    rows = blank()
    for y in range(max(0, y0), min(8, y1)):
        for x in range(max(0, x0), min(8, x1)):
            rows[y][x] = color
    return rows


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_rgb(a, b, t):
    return tuple(lerp(a[i], b[i], t) for i in range(3))


def cgb_word(rgb):
    r, g, b = (min(31, max(0, int(round(c * 31 / 255)))) for c in rgb)
    return r | (g << 5) | (b << 10)


def ease_out_cubic(t):
    return 1 - (1 - t) ** 3


def ease_in_out_sine(t):
    return 0.5 - 0.5 * math.cos(math.pi * t)


# -----------------------------------------------------------------------------
# Tiles
# -----------------------------------------------------------------------------


class Tiles:
    def __init__(self):
        self.tiles = []
        self.notes = {}

    def add(self, rows, note=None):
        index = len(self.tiles)
        self.tiles.append(encode_tile(rows))
        if note:
            self.notes[index] = note
        return index

    def align(self, n):
        while len(self.tiles) % n:
            self.add(blank())

    def pair(self, pixels16, note=None):
        """Adds an 8x16 object tile pair from 16 rows of 8 pixels."""
        self.align(2)
        index = self.add(pixels16[:8], note)
        self.add(pixels16[8:])
        return index


def column(pixels, x0):
    """Extracts an 8 px wide, 16 px tall column from a 16x16 pixel grid."""
    return [row[x0 : x0 + 8] for row in pixels]


tiles = Tiles()
tiles.pair([[0] * 8 for _ in range(16)], "empty")

# solid rectangles of every height (1..16), one block of 16 pairs per colour,
# tile = RECT_BASE + (colour - 1) * 32 + (height - 1) * 2
RECT_BASE = len(tiles.tiles)
for color in (WHITE, LIGHT, DARK):
    for h in range(1, 17):
        tiles.pair([[color if y < h else 0] * 8 for y in range(16)])


def rect_tile_index(color, h):
    return RECT_BASE + (color - 1) * 32 + (h - 1) * 2


SOLID = {c: rect_tile_index(c, 16) for c in (WHITE, LIGHT, DARK)}

# narrow light squares (4..7 px) for the small square while the logo is tiny
NARROW = {}
for s in range(4, 8):
    NARROW[s] = tiles.pair(
        [[LIGHT if (x < s and y < s) else 0 for x in range(8)] for y in range(16)]
    )

# bee frames: wings (top squares) flutter by losing up to 2 rows from the top
tiles.align(4)
BEE_BASE = len(tiles.tiles)
for squash in (0, 1, 2):
    px = [
        [
            (0 if y < squash else logo_pixel(x, y, U_BEE)) if y < 2 * U_BEE else logo_pixel(x, y, U_BEE)
            for x in range(16)
        ]
        for y in range(16)
    ]
    tiles.pair(column(px, 0))
    tiles.pair(column(px, 8))
FLAP = [BEE_BASE + 4 * f for f in (0, 1, 2, 1)]

# pollen dots, centred on the tile pixel that lands on the bee centre
DOT_SIZES = (3, 2, 2, 1)
DOT_BASE = len(tiles.tiles)
for s in DOT_SIZES:
    x0, y0 = 4 - s // 2, 8 - s // 2
    tiles.pair(
        [[LIGHT if (x0 <= x < x0 + s and y0 <= y < y0 + s) else 0 for x in range(8)] for y in range(16)]
    )

# font, 7x7 glyphs with 2 px stems, drawn in one colour each
GLYPHS = {
    "H": ["##...##", "##...##", "##...##", "#######", "##...##", "##...##", "##...##"],
    "I": ["######.", "..##...", "..##...", "..##...", "..##...", "..##...", "######."],
    "V": ["##...##", "##...##", "##...##", "##...##", ".##.##.", "..###..", "...#..."],
    "E": ["#######", "##.....", "##.....", "######.", "##.....", "##.....", "#######"],
    "S": [".#####.", "##...##", "##.....", ".#####.", ".....##", "##...##", ".#####."],
    "O": [".#####.", "##...##", "##...##", "##...##", "##...##", "##...##", ".#####."],
    "L": ["##.....", "##.....", "##.....", "##.....", "##.....", "##.....", "#######"],
    "U": ["##...##", "##...##", "##...##", "##...##", "##...##", "##...##", ".#####."],
    "T": ["######.", "..##...", "..##...", "..##...", "..##...", "..##...", "..##..."],
    "N": ["##...##", "###..##", "####.##", "##.####", "##..###", "##...##", "##...##"],
}
font = {}


def glyph_tile(ch, color):
    key = (ch, color)
    if key not in font:
        rows = blank()
        for y, line in enumerate(GLYPHS[ch]):
            for x, c in enumerate(line):
                if c == "#":
                    rows[y][x] = color
        font[key] = tiles.add(rows)
    return font[key]


# -----------------------------------------------------------------------------
# Screen map (logo + text), CGB attributes
# -----------------------------------------------------------------------------

screen = [[0] * 20 for _ in range(18)]
ox, oy = CX - 2 * U_LOGO, CY - 2 * U_LOGO
assert ox % 8 == 0 and oy % 8 == 0
for ty in range(4 * U_LOGO // 8):
    for tx in range(4 * U_LOGO // 8):
        c = logo_pixel(tx * 8, ty * 8, U_LOGO)
        if c:
            screen[oy // 8 + ty][ox // 8 + tx] = SOLID[c]

word = 0
for i, ch in enumerate(TEXT):
    if ch == " ":
        word += 1
        continue
    screen[TEXT_ROW][TEXT_COL + i] = glyph_tile(ch, WHITE if word == 0 else LIGHT)

patches = []
for y, row in enumerate(screen):
    used = [x for x, t in enumerate(row) if t]
    if used:
        a, b = used[0], used[-1]
        patches.append((0x9800 + y * 32 + a, row[a : b + 1]))


def band(row):
    """CGB palette (gradient band) for a 32 row map, wrapped rows included."""
    if row < 18:
        return row * BANDS // 18
    return BANDS - 1 if row < 25 else 0


attr_rows = [band(r) for r in range(32)]
win_rows = [band(WIN_Y // 8 + r) if WIN_Y // 8 + r < 18 else BANDS - 1 for r in range(32)]

# -----------------------------------------------------------------------------
# Palettes, 16 steps: 0 white, 1..7 fade in (logo hidden), 8 revealed,
# 9..15 fade out to white
# -----------------------------------------------------------------------------

band_rgb = [lerp_rgb(RGB_BG_TOP, RGB_BG_BOTTOM, b / (BANDS - 1)) for b in range(BANDS)]
cgb_pals = []
dmg_bgp = []
for step in range(16):
    words = []
    if step < 8:
        t = step / 7
        for b in range(BANDS):
            c = cgb_word(lerp_rgb(RGB_WHITE, band_rgb[b], t))
            words += [c] * 4
        level = round(3 * t)
        shades = [min(DMG_SHADES[BG], level)] * 4
    else:
        t = (step - 8) / 7
        for b in range(BANDS):
            for rgb in (band_rgb[b], RGB_WHITE, RGB_LIGHT, RGB_DARK):
                words.append(cgb_word(lerp_rgb(rgb, RGB_WHITE, t)))
        level = 3 - round(3 * t)
        shades = [min(s, level) for s in DMG_SHADES]
    cgb_pals.append(words)
    dmg_bgp.append(shades[0] | shades[1] << 2 | shades[2] << 4 | shades[3] << 6)

obj_pal = [cgb_word(c) for c in (RGB_WHITE, RGB_WHITE, RGB_LIGHT, RGB_DARK)]
dmg_obp = DMG_SHADES[WHITE] << 2 | DMG_SHADES[LIGHT] << 4 | DMG_SHADES[DARK] << 6

# -----------------------------------------------------------------------------
# Paths, one 4 byte entry per frame: OAM Y, OAM X, attributes, WX
# -----------------------------------------------------------------------------

PRI = 0x80
XFLIP = 0x20
BEE_HOME = (CX - 2 * U_BEE, CY - 2 * U_BEE)  # bee top left when it sits on the logo


def catmull(points, steps=64):
    """Dense polyline through the control points (centripetal-free, uniform)."""
    pts = [points[0]] + points + [points[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for s in range(steps):
            t = s / steps
            t2, t3 = t * t, t * t * t
            out.append(
                tuple(
                    0.5
                    * (
                        2 * p1[k]
                        + (-p0[k] + p2[k]) * t
                        + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
                        + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3
                    )
                    for k in range(2)
                )
            )
    out.append(points[-1])
    return out


def walk(poly, frames, profile):
    """Samples a polyline at `frames` points, distance given by profile(t)."""
    dist = [0.0]
    for a, b in zip(poly, poly[1:]):
        dist.append(dist[-1] + math.dist(a, b))
    total = dist[-1]
    out = []
    j = 0
    for f in range(frames):
        d = profile(f / (frames - 1)) * total
        while j < len(dist) - 2 and dist[j + 1] < d:
            j += 1
        seg = dist[j + 1] - dist[j] or 1
        t = min(1.0, max(0.0, (d - dist[j]) / seg))
        out.append((lerp(poly[j][0], poly[j + 1][0], t), lerp(poly[j][1], poly[j + 1][1], t)))
    return out


def facing(points, start_left=False):
    """X flip flags (bee faces its direction of travel), with hysteresis."""
    left = start_left
    flags = []
    for i, p in enumerate(points):
        q = points[min(i + 3, len(points) - 1)]
        dx = q[0] - p[0]
        if dx < -0.6:
            left = True
        elif dx > 0.6:
            left = False
        flags.append(XFLIP if left else 0)
    return flags


def entry(x, y, attr, wx=WX_HIDDEN):
    return (int(round(y)) + 16, int(round(x)) + 8, attr, wx)


PAD = [(0, 0, 0, WX_HIDDEN)] * TRAIL_PAD

# path A: the bee flies in from the left, loops around and lands on the logo
A_POINTS = [
    (-30, 104),
    (8, 92),
    (36, 58),
    (58, 22),
    (100, 14),
    (134, 34),
    (138, 74),
    (112, 104),
    (70, 106),
    (40, 86),
    (32, 56),
    (48, 40),
    BEE_HOME,
]
A_FRAMES = 228
def cruise_land(t0):
    """Constant speed until t0, then a quadratic ease out (C1 continuous)."""
    k = 2 / (1 + t0)
    c = k / (2 * (1 - t0))
    return lambda t: k * t if t < t0 else 1 - c * (1 - t) ** 2


a_poly = catmull(A_POINTS)
a_pts = walk(a_poly, A_FRAMES, cruise_land(0.78))
a_out = []
a_flip = facing(a_pts)
for i, (x, y) in enumerate(a_pts):
    env = min(1.0, (A_FRAMES - 1 - i) / 40)
    a_out.append(entry(x, y + 2.0 * env * math.sin(i * 2 * math.pi / 22), a_flip[i]))
for _ in range(14):  # short hover before the zoom
    a_out.append(entry(*BEE_HOME, 0))
assert a_out[-1][2] == 0

# path C: endless orbit around the logo, behind it on the far (top) side
# the orbit sits low: the near side runs below the logo (where the bee stays
# readable) and the far side passes behind the top squares
C_FRAMES = 240
ORBIT_A, ORBIT_B, ORBIT_DY = 60, 30, 8
c_out = []
for i in range(C_FRAMES):
    th = -2 * math.pi * i / C_FRAMES
    x = BEE_HOME[0] + ORBIT_A * math.cos(th)
    y = BEE_HOME[1] + ORBIT_DY + ORBIT_B * math.sin(th) + 1.0 * math.sin(i * 2 * math.pi / 24)
    attr = (PRI if math.sin(th) < 0 else 0) | (XFLIP if math.sin(th) < 0 else 0)
    c_out.append(entry(x, y, attr))
c_out += c_out[:TRAIL_PAD]

# path B: a bee leaves the logo, writes the text and joins the orbit
B_RUN_Y = WIN_Y - 6
B_POINTS = [
    BEE_HOME,
    (60, 72),
    (40, 88),
    (12, B_RUN_Y),
    (8, B_RUN_Y),
]
b1 = walk(catmull(B_POINTS), 70, ease_in_out_sine)
b2 = walk([(8, B_RUN_Y), (142, B_RUN_Y)], 92, lambda t: t)
orbit_start = (c_out[0][1] - 8, c_out[0][0] - 16)
orbit_next = (c_out[6][1] - 8, c_out[6][0] - 16)
b3 = walk(catmull([(142, B_RUN_Y), (150, 86), orbit_start, orbit_next])[:-64], 44, lambda t: t)
b_out = []
for i, (x, y) in enumerate(b1):
    behind = y < CY + 2 * U_LOGO - 2 and x + 16 > CX - 2 * U_LOGO
    attr = (PRI if behind else 0) | (XFLIP if x < BEE_HOME[0] - 2 else 0)
    b_out.append(entry(x, y, attr, 7))
for i, (x, y) in enumerate(b2):
    wx = min(WX_HIDDEN, max(7, int(round(x)) + 8 + 7))
    b_out.append(entry(x, y + 1.5 * math.sin(i * 2 * math.pi / 24), 0, wx))
for x, y in b3:
    b_out.append(entry(x, y, 0))

# -----------------------------------------------------------------------------
# Zoom: the bee grows into the logo, its squares spread apart then snap back
# -----------------------------------------------------------------------------

Z_FRAMES = 30
SPREAD = 7
YFLIP = 0x40
zoom = []
for f in range(Z_FRAMES):
    t = f / (Z_FRAMES - 1)
    u = int(round(lerp(U_BEE, U_LOGO, ease_out_cubic(t))))
    g = int(round(SPREAD * math.sin(math.pi * min(1.0, t * 1.15)) ** 1.5))
    s = 2 * u
    # top squares are drawn bottom up with Y flipped tiles, so the unused
    # part of their partial row spills upwards (never into the bottom band)
    rects = [
        (CX - s - g, CY - s - g, s, WHITE, True),
        (CX + g, CY - s - g, s, DARK, True),
        (CX + g, CY + g, s, WHITE, False),
        (CX - u - g, CY + g, u, LIGHT, False),
    ]
    frame = []
    for x, y, size, color, up in rects:
        if size < 8:
            base = NARROW[size] - 2 * (size - 1)
        else:
            base = rect_tile_index(color, 1)
        oam_y = (y + size - 16 if up else y) + 16
        frame.append((oam_y, x + 8, size, base & 0xFF, YFLIP if up else 0))
    zoom.append(frame)


def rect_sprites(y, x, size, flags):
    """Mirrors the runtime DrawRect routine, returns (y, x, h) per sprite."""
    out = []
    step = -16 if flags & YFLIP else 16
    rem_h = size
    while True:
        hh = min(rem_h, 16)
        cx, rem_w = x, size
        while True:
            out.append((y, cx, hh))
            if rem_w <= 8:
                break
            if rem_w < 16:
                cx += rem_w - 8
                rem_w = 8
            else:
                cx += 8
                rem_w -= 8
        if rem_h <= 16:
            break
        rem_h -= 16
        y += step
    return out


def rect_pixels(frame):
    """Rasterises a zoom frame the way the hardware would draw it."""
    px = {}
    for (y, x, size, base, flags) in frame:
        for (sy, sx, hh) in rect_sprites(y, x, size, flags):
            rows = range(16 - hh, 16) if flags & YFLIP else range(hh)
            width = size if size < 8 else 8
            for r in rows:
                for c in range(width):
                    px[(sx + c - 8, sy + r - 16)] = 1
    return px


# hardware limits: 40 objects in total and 10 per scanline
for frame in zoom:
    sprites = [s for (y, x, size, _, flags) in frame for s in rect_sprites(y, x, size, flags)]
    assert len(sprites) <= 40, len(sprites)
    for line in range(0, 176):
        n = sum(1 for (y, _, _) in sprites if y <= line < y + 16)
        assert n <= 10, (n, line)

# the last frame must cover exactly the background logo
last = rect_pixels(zoom[-1])
logo = {
    (CX - 2 * U_LOGO + x, CY - 2 * U_LOGO + y)
    for y in range(4 * U_LOGO)
    for x in range(4 * U_LOGO)
    if logo_pixel(x, y, U_LOGO)
}
assert set(last) == logo, "zoom must end on the exact background logo"

# screen "thud" after the snap (SCY values)
SHAKE = [254, 254, 255, 1, 1, 0]

# -----------------------------------------------------------------------------
# Output
# -----------------------------------------------------------------------------


def db(values, per_line=16):
    values = list(values)
    lines = []
    for i in range(0, len(values), per_line):
        lines.append("    db " + ", ".join("$%02X" % (v & 0xFF) for v in values[i : i + per_line]))
    return "\n".join(lines)


def dw(values, per_line=8):
    values = list(values)
    lines = []
    for i in range(0, len(values), per_line):
        lines.append("    dw " + ", ".join("$%04X" % v for v in values[i : i + per_line]))
    return "\n".join(lines)


def path_block(entries):
    return db([b for e in entries for b in e], 16)


assert len(tiles.tiles) <= 256, len(tiles.tiles)

out = []
w = out.append
w("; Generated by tools/gen.py, do not edit.\n")
w("DEF TILE_COUNT EQU %d" % len(tiles.tiles))
w("DEF BEE_BASE EQU $%02X" % BEE_BASE)
w("DEF DOT_BASE EQU $%02X" % DOT_BASE)
w("DEF TRAIL_DOTS EQU %d" % TRAIL_DOTS)
w("DEF TRAIL_STEP EQU %d" % TRAIL_STEP)
w("DEF WIN_Y EQU %d" % WIN_Y)
w("DEF WX_HIDDEN EQU %d" % WX_HIDDEN)
w("DEF PAL_REVEAL EQU 8")
w("DEF DMG_OBP EQU $%02X" % dmg_obp)
w("DEF SHAKE_LEN EQU %d" % len(SHAKE))
w("")
w('SECTION "Tiles", ROM0')
w("TileData:")
for i, t in enumerate(tiles.tiles):
    w(db(t))
w("TileDataEnd:\n")
w('SECTION "Map", ROM0')
w("MapPatches: ; dw destination, db count, db tiles...")
for addr, row in patches:
    w("    dw $%04X" % addr)
    w("    db %d" % len(row))
    w(db(row))
w("    dw 0\n")
w("AttrRows: ; CGB palette per map row, BG map then window map")
w(db(attr_rows + win_rows))
w("")
w('SECTION "Palettes", ROM0, ALIGN[6]')
w("CgbPalettes: ; 16 steps x 8 palettes x 4 colours")
for words in cgb_pals:
    w(dw(words))
w("CgbObjPalette:")
w(dw(obj_pal))
w("DmgPalettes:")
w(db(dmg_bgp))
w("")
w('SECTION "Tables", ROM0, ALIGN[2]')
w("FlapTiles:")
w(db(FLAP))
w("ShakeTable:")
w(db(SHAKE))
w("")
w('SECTION "Paths", ROM0, ALIGN[2]')
w("    ; trail padding, entries with Y = 0 are never drawn")
w(path_block(PAD))
w("PathFly:")
w(path_block(a_out))
w("PathFlyEnd:")
w(path_block(PAD))
w("PathWrite:")
w(path_block(b_out))
w("PathOrbit:")
w(path_block(c_out[:TRAIL_PAD]))
w("PathOrbitLoop:")
w(path_block(c_out[TRAIL_PAD:]))
w("PathOrbitEnd:")
w("")
w('SECTION "Zoom", ROM0')
w("ZoomTable: ; per frame 4 x (OAM Y, OAM X, size, tile base, flags)")
for frame in zoom:
    w(db([b for r in frame for b in r]))
w("ZoomTableEnd:")

with open(sys.argv[1], "w") as fh:
    fh.write("\n".join(out) + "\n")

print(
    "tiles=%d fly=%d write=%d orbit=%d zoom=%d"
    % (len(tiles.tiles), len(a_out), len(b_out), C_FRAMES, len(zoom)),
    file=sys.stderr,
)
