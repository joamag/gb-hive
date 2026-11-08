#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Asset generator for Petal Lanes, the top down lane dodger starring the
Hive bee.

Builds the tiles, the garden map (static, it only scrolls), the CGB
attributes, the palette fades, the text sprites and the tuning tables, so
the runtime code only walks tables.

Pure standard library, so it runs with any stock Python 3.
"""

import math
import random
import sys

# -----------------------------------------------------------------------------
# Layout (screen pixels)
# -----------------------------------------------------------------------------

LANE_CX = (44, 80, 116)  # lane centres
BEE_Y = 106  # bee top
SHADOW_Y = 122
WIN_Y = 136  # score bar (window) on the last 8 lines
YS_OFS = 48  # item y is stored as y + 48 so it fits in a byte while above the screen
YS_SPAWN = -16 + YS_OFS
YS_POLLEN = -40 + YS_OFS
YS_DESPAWN = 136 + YS_OFS
HUD_SCORE_COL, HUD_BEST_COL = 1, 15

# BG colour indexes: 0 grass, 1 dark grass, 2 petal / text, 3 centre / bar
# CGB colours
GARDEN = ((104, 180, 92), (60, 136, 72), (246, 160, 196), (255, 226, 104))
HUD = ((34, 78, 50), (34, 78, 50), (255, 244, 214), (34, 78, 50))
BUSH = ((104, 180, 92), (40, 106, 62), (250, 250, 246), (226, 84, 98))
BLOOM = ((104, 180, 92), (60, 136, 72), (186, 132, 226), (255, 214, 92))
PAL_GARDEN, PAL_HUD, PAL_BUSH, PAL_BLOOM = 0, 1, 2, 3
OBJ = (
    ((255, 255, 255), (166, 183, 209), (33, 76, 144)),  # 0 bee
    ((240, 244, 252), (170, 178, 196), (120, 128, 150)),  # 1 web
    ((40, 92, 176), (124, 180, 240), (240, 248, 255)),  # 2 raindrop
    ((255, 212, 56), (255, 250, 226), (168, 108, 24)),  # 3 pollen
    ((34, 78, 50), (34, 78, 50), (255, 255, 255)),  # 4 text (shadow, -, glyph)
    ((48, 116, 62), (48, 116, 62), (48, 116, 62)),  # 5 bee shadow
)
# DMG shades per colour index
DMG_BG = (1, 2, 0, 3)
DMG_OBP0 = (0, 0, 2, 3)  # bee, pollen, text, shadow
DMG_OBP1 = (0, 3, 2, 0)  # web, raindrop
ATTR_BEE, ATTR_WEB, ATTR_DROP, ATTR_POLLEN, ATTR_TEXT, ATTR_SHADOW = 0x00, 0x11, 0x12, 0x03, 0x04, 0x05

# -----------------------------------------------------------------------------
# Tile helpers
# -----------------------------------------------------------------------------


def encode(rows):
    data = []
    for row in rows:
        lo = hi = 0
        for x, c in enumerate(row):
            if c & 1:
                lo |= 0x80 >> x
            if c & 2:
                hi |= 0x80 >> x
        data += [lo, hi]
    return data


def parse(art):
    return [[0 if ch == "." else int(ch) for ch in line.ljust(8, ".")[:8]] for line in art]


def canvas(w, h):
    return [[0] * w for _ in range(h)]


def cut(px, x0, y0, w=8, h=8):
    return [row[x0 : x0 + w] for row in px[y0 : y0 + h]]


class Bank:
    def __init__(self):
        self.tiles = []
        self.index = {}

    def add(self, rows, dedupe=True):
        data = tuple(encode(rows))
        if dedupe and data in self.index:
            return self.index[data]
        self.tiles.append(data)
        self.index.setdefault(data, len(self.tiles) - 1)
        return len(self.tiles) - 1

    def pair(self, px16):
        """8x16 object tile pair, always consecutive and never shared."""
        while len(self.tiles) % 2:
            self.add(canvas(8, 8), dedupe=False)
        top = self.add(px16[:8], dedupe=False)
        self.add(px16[8:16], dedupe=False)
        return top


def pad16(px, y0=0):
    """Places an image of up to 8x16 at row y0 of an 8x16 cell."""
    out = canvas(8, 16)
    for y, row in enumerate(px):
        for x, c in enumerate(row[:8]):
            if 0 <= y0 + y < 16:
                out[y0 + y][x] = c
    return out


def line(px, x0, y0, x1, y1, c):
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    while True:
        if 0 <= y0 < len(px) and 0 <= x0 < len(px[0]):
            px[y0][x0] = c
        if x0 == x1 and y0 == y1:
            return
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


# -----------------------------------------------------------------------------
# Object art
# -----------------------------------------------------------------------------


def logo_pixel(x, y, u):
    if y < 2 * u:
        return 1 if x < 2 * u else 3
    if x >= 2 * u and y < 4 * u:
        return 1
    if u <= x < 2 * u and y < 3 * u:
        return 2
    return 0


GLYPHS = {
    "A": [".#####.", "##...##", "##...##", "#######", "##...##", "##...##", "##...##"],
    "B": ["######.", "##...##", "##...##", "######.", "##...##", "##...##", "######."],
    "E": ["#######", "##.....", "##.....", "######.", "##.....", "##.....", "#######"],
    "G": [".#####.", "##...##", "##.....", "##.####", "##...##", "##...##", ".#####."],
    "L": ["##.....", "##.....", "##.....", "##.....", "##.....", "##.....", "#######"],
    "M": ["##...##", "###.###", "#######", "##.#.##", "##...##", "##...##", "##...##"],
    "N": ["##...##", "###..##", "####.##", "##.####", "##..###", "##...##", "##...##"],
    "O": [".#####.", "##...##", "##...##", "##...##", "##...##", "##...##", ".#####."],
    "P": ["######.", "##...##", "##...##", "######.", "##.....", "##.....", "##....."],
    "R": ["######.", "##...##", "##...##", "######.", "##.##..", "##..##.", "##...##"],
    "S": [".#####.", "##...##", "##.....", ".#####.", ".....##", "##...##", ".#####."],
    "T": ["######.", "..##...", "..##...", "..##...", "..##...", "..##...", "..##..."],
    "V": ["##...##", "##...##", "##...##", "##...##", ".##.##.", "..###..", "...#..."],
    "0": [".#####.", "##...##", "##..###", "##.#.##", "###..##", "##...##", ".#####."],
    "1": ["..##...", ".###...", "..##...", "..##...", "..##...", "..##...", ".####.."],
    "2": [".#####.", "##...##", ".....##", "..####.", ".##....", "##.....", "#######"],
    "3": [".#####.", "##...##", ".....##", "..####.", ".....##", "##...##", ".#####."],
    "4": ["...###.", "..####.", ".##.##.", "##..##.", "#######", "....##.", "....##."],
    "5": ["#######", "##.....", "######.", ".....##", ".....##", "##...##", ".#####."],
    "6": [".#####.", "##.....", "##.....", "######.", "##...##", "##...##", ".#####."],
    "7": ["#######", ".....##", "....##.", "...##..", "..##...", "..##...", "..##..."],
    "8": [".#####.", "##...##", "##...##", ".#####.", "##...##", "##...##", ".#####."],
    "9": [".#####.", "##...##", "##...##", ".######", ".....##", ".....##", ".#####."],
}


def glyph_tall(ch):
    """7x14 glyph (rows doubled, colour 3) with a drop shadow (colour 1)."""
    px = canvas(8, 16)
    for y, row in enumerate(GLYPHS[ch]):
        for x, c in enumerate(row):
            if c == "#":
                px[2 * y][x] = px[2 * y + 1][x] = 3
    for y in range(15, 0, -1):
        for x in range(7, 0, -1):
            if px[y][x] == 0 and px[y - 1][x - 1] == 3:
                px[y][x] = 1
    return px


def glyph_hud(ch):
    """8x8 glyph for the score bar: colour 2 on the colour 3 bar."""
    px = [[3] * 8 for _ in range(8)]
    for y, row in enumerate(GLYPHS[ch]):
        for x, c in enumerate(row):
            if c == "#":
                px[y][x] = 2
    return px


def web():
    px = canvas(16, 16)
    cx, cy = 7, 7
    spokes = [(int(round(cx + 7.4 * math.cos(a))), int(round(cy + 7.4 * math.sin(a)))) for a in [k * math.pi / 4 + 0.2 for k in range(8)]]
    for sx, sy in spokes:
        line(px, cx, cy, sx, sy, 1)
    for r in (2.6, 4.8, 7.0):
        pts = [(int(round(cx + r * math.cos(k * math.pi / 4 + 0.2))), int(round(cy + r * math.sin(k * math.pi / 4 + 0.2)))) for k in range(8)]
        for i in range(8):
            line(px, *pts[i], *pts[(i + 1) % 8], 1)
    return px


DROP = [
    "...11...",
    "...11...",
    "..1221..",
    "..1221..",
    ".122221.",
    "12222221",
    "12322221",
    "12322221",
    "12222221",
    ".122221.",
    "..1111..",
]
POLLEN_A = ["..3333..", ".311113.", "31121113", "31211113", "31111113", "31111113", ".311113.", "..3333.."]
POLLEN_B = ["..3333..", ".311113.", "31111113", "31111213", "31111123", "31111113", ".311113.", "..3333.."]
SHADOW = ["...22222", ".2222222", ".2222222", "...22222"]

tiles = Bank()
tiles.pair(canvas(8, 16))

while len(tiles.tiles) % 4:
    tiles.add(canvas(8, 8), dedupe=False)
BEE_TILE = len(tiles.tiles)
for squash in (0, 1, 2):
    px = [[0 if (y < 8 and y < squash) else logo_pixel(x, y, 4) for x in range(16)] for y in range(16)]
    tiles.pair(cut(px, 0, 0, 8, 16))
    tiles.pair(cut(px, 8, 0, 8, 16))
FLAP = [BEE_TILE + 4 * f for f in (0, 1, 2, 1)]

SHADOW_TILE = tiles.pair(pad16(parse(SHADOW)))
w = web()
WEB_TILE = tiles.pair(cut(w, 0, 0, 8, 16))
tiles.pair(cut(w, 8, 0, 8, 16))
DROP_TILE = tiles.pair(pad16(parse(DROP), 2))
POLLEN_TILE = tiles.pair(pad16(parse(POLLEN_A)))
tiles.pair(pad16(parse(POLLEN_B)))
TEXT_TILE = {ch: tiles.pair(glyph_tall(ch)) for ch in "PETALNSRGMOV"}
OBJ_END = len(tiles.tiles)

# -----------------------------------------------------------------------------
# Background tiles and the garden map
# -----------------------------------------------------------------------------

BG_ART = {
    "grass": ["........"] * 8,
    "blades_a": ["........", "...1....", "...1..1.", "......1.", "........", ".1......", ".1...1..", ".....1.."],
    "blades_b": ["........", "......1.", ".1....1.", ".1......", "....1...", "....1...", "........", "..1....."],
    "petals": ["........", ".2......", "........", ".....2..", "....22..", "........", "..2.....", "........"],
    "flower": ["........", "...2....", "..232...", "...2....", "...1....", "..11....", "...1....", "........"],
    "lane_l": ["......1.", "......1.", "......1.", "......1.", "........", "........", "........", "........"],
    "lane_r": ["..1.....", "..1.....", "..1.....", "..1.....", "........", "........", "........", "........"],
    "tuft": ["........", ".1...1..", ".11.11..", "..111...", "...1....", "........", ".....1..", "....11.."],
}
BUSH_ART = [
    "................",
    "....111111......",
    "..11111111111...",
    ".1111121111111..",
    ".11112321111111.",
    "1111112111121111",
    "1111111111232111",
    "1121111111121111",
    "1232111111111111",
    ".121111211111111",
    ".11111232111111.",
    "..1111121111111.",
    "...11111111111..",
    ".....1111111....",
    "................",
    "................",
]
BLOOM_ART = [
    "................",
    "......222.......",
    ".....22222......",
    "..222.222.222...",
    ".22222.2.22222..",
    ".222223332222...",
    "..2223333322....",
    "....2333332.....",
    "..2223333322....",
    ".222223332222...",
    ".22222.2.22222..",
    "..222.222.222...",
    ".....22222......",
    "......222..1....",
    "..........11....",
    "...........1....",
]

bg = {name: tiles.add(parse(art)) for name, art in BG_ART.items()}


def block(art):
    px = [[0 if ch == "." else int(ch) for ch in row] for row in art]
    return [[tiles.add(cut(px, tx * 8, ty * 8)) for tx in range(2)] for ty in range(2)]


BUSH_TILES = block(BUSH_ART)
BLOOM_TILES = block(BLOOM_ART)
bush_set = {t for row in BUSH_TILES for t in row}
bloom_set = {t for row in BLOOM_TILES for t in row}

rng = random.Random(7)
gmap = [[bg["grass"]] * 32 for _ in range(32)]
gattr = [[PAL_GARDEN] * 32 for _ in range(32)]


def place_block(tl, row, col, pal):
    for dy in range(2):
        for dx in range(2):
            gmap[(row + dy) % 32][col + dx] = tl[dy][dx]
            gattr[(row + dy) % 32][col + dx] = pal


for row in range(32):
    for col in range(20):
        if col in (7, 12):
            gmap[row][col] = bg["lane_l"] if col == 7 else bg["lane_r"]
            continue
        roll = rng.random()
        if col in (2, 17):
            gmap[row][col] = bg["tuft"] if roll < 0.35 else bg["flower"] if roll < 0.55 else bg["blades_a"]
        elif 3 <= col <= 16:
            gmap[row][col] = (
                bg["blades_a"] if roll < 0.14 else bg["blades_b"] if roll < 0.26 else bg["petals"] if roll < 0.33 else bg["flower"] if roll < 0.36 else bg["grass"]
            )
        else:
            gmap[row][col] = bg["blades_b"] if roll < 0.5 else bg["grass"]
# flower beds on both edges, two tile blocks stacked down the whole map
for col, phase in ((0, 0), (18, 1)):
    for i, row in enumerate(range(0, 32, 2)):
        kind = (i + phase) % 3
        if kind == 0:
            place_block(BUSH_TILES, row, col, PAL_BUSH)
        elif kind == 1:
            place_block(BLOOM_TILES, row, col, PAL_BLOOM)

HUD_BAR = tiles.add([[3] * 8 for _ in range(8)])
DIGIT_TILE = tiles.add(glyph_hud("0"))
for d in "123456789":
    tiles.add(glyph_hud(d), dedupe=False)
best_tiles = [tiles.add(glyph_hud(ch)) for ch in "BEST"]
hud_row = [HUD_BAR] * 32
for i in range(5):
    hud_row[HUD_SCORE_COL + i] = DIGIT_TILE
    hud_row[HUD_BEST_COL + i] = DIGIT_TILE
for i, t in enumerate(best_tiles):
    hud_row[10 + i] = t
assert len(tiles.tiles) <= 256, len(tiles.tiles)

# -----------------------------------------------------------------------------
# Palettes: 8 fade steps from white
# -----------------------------------------------------------------------------


def cgb_word(rgb):
    r, g, b = (min(31, max(0, int(round(c * 31 / 255)))) for c in rgb)
    return r | (g << 5) | (b << 10)


def mix(c, t):
    return tuple(255 + (v - 255) * t for v in c)


def dmg_reg(shades, level, obj=False):
    s = [min(v, level) for v in shades]
    if obj:
        s[0] = 0
    return s[0] | s[1] << 2 | s[2] << 4 | s[3] << 6


cgb_fade, dmg_fade = [], []
for step in range(8):
    t = step / 7
    words = []
    for pal in (GARDEN, HUD, BUSH, BLOOM):
        words += [cgb_word(mix(c, t)) for c in pal]
    for pal in OBJ:
        words += [cgb_word((0, 0, 0))] + [cgb_word(mix(c, t)) for c in pal]
    cgb_fade.append(words)
    level = round(3 * t)
    dmg_fade.append((dmg_reg(DMG_BG, level), dmg_reg(DMG_OBP0, level, True), dmg_reg(DMG_OBP1, level, True)))

# -----------------------------------------------------------------------------
# Tuning
# -----------------------------------------------------------------------------

# rows of items spawn at ground distances that grow with speed, so two
# lane switches always fit between them; indexed by speed in quarter pixels
row_gaps = [min(240, int(round(30 + 18 * (lv / 4)))) for lv in range(16)]
# collision boxes relative to the lane centre and the stored y: x0, x1, y0, y1
ITEM_BOXES = ((-6, 6, 3, 13), (-3, 3, 4, 12), (-4, 4, 0, 8))
PERMS = ((0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0), (1, 0, 2), (1, 2, 0))

# -----------------------------------------------------------------------------
# Output
# -----------------------------------------------------------------------------


def db(values, per_line=16):
    values = list(values)
    return "\n".join(
        "    db " + ", ".join("$%02X" % (v & 0xFF) for v in values[i : i + per_line])
        for i in range(0, len(values), per_line)
    )


def dw(values, per_line=8):
    values = list(values)
    return "\n".join(
        "    dw " + ", ".join("$%04X" % v for v in values[i : i + per_line])
        for i in range(0, len(values), per_line)
    )


def text_sprites(text, y):
    x0 = (160 - 8 * len(text)) // 2
    return [(y + 16, x0 + 8 + 8 * i, TEXT_TILE[ch], ATTR_TEXT) for i, ch in enumerate(text) if ch != " "]


out = []
o = out.append
o("; Generated by tools/gen_game.py, do not edit.\n")
for name, value in (
    ("BEE_Y", BEE_Y),
    ("SHADOW_Y", SHADOW_Y),
    ("WIN_Y", WIN_Y),
    ("YS_SPAWN", YS_SPAWN),
    ("YS_POLLEN", YS_POLLEN),
    ("YS_DESPAWN", YS_DESPAWN),
    ("BEE_YS0", BEE_Y + 3 + YS_OFS),
    ("BEE_YS1", BEE_Y + 13 + YS_OFS),
    ("LANE_CX0", LANE_CX[0]),
    ("LANE_STEP", LANE_CX[1] - LANE_CX[0]),
    ("SHADOW_TILE", SHADOW_TILE),
    ("WEB_TILE", WEB_TILE),
    ("DROP_TILE", DROP_TILE),
    ("POLLEN_TILE", POLLEN_TILE),
    ("DIGIT_TILE", DIGIT_TILE),
    ("HUD_SCORE_COL", HUD_SCORE_COL),
    ("HUD_BEST_COL", HUD_BEST_COL),
    ("PAL_HUD", PAL_HUD),
    ("ATTR_BEE", ATTR_BEE),
    ("ATTR_WEB", ATTR_WEB),
    ("ATTR_DROP", ATTR_DROP),
    ("ATTR_POLLEN", ATTR_POLLEN),
    ("ATTR_SHADOW", ATTR_SHADOW),
):
    o("DEF %s EQU %d" % (name, value))
o("")
o('SECTION "Game tiles", ROM0')
o("GameTiles:")
for t in tiles.tiles:
    o(db(t))
o("GameTilesEnd:\n")
o('SECTION "Game map", ROM0')
o("GardenMap:")
for row in gmap:
    o(db(row))
o("GardenAttrs:")
for row in gattr:
    o(db(row))
o("HudRow:")
o(db(hud_row))
o("")
o('SECTION "Game palettes", ROM0')
o("CgbFade: ; 8 steps x (4 BG + 6 OBJ palettes)")
for words in cgb_fade:
    o(dw(words))
o("DmgFade: ; 8 steps x (BGP, OBP0, OBP1)")
o(db([b for step in dmg_fade for b in step]))
o("")
o('SECTION "Game tables", ROM0, ALIGN[4]')
o("FlapTiles:")
o(db(FLAP))
o("LaneBeeX:")
o(db([cx - 8 for cx in LANE_CX]))
o("AttractLanes:")
o(db([1, 0, 1, 2]))
o("RowGaps:")
o(db(row_gaps))
o("ItemBoxes:")
o(db([v for box in ITEM_BOXES for v in box]))
o("Perms:")
o(db([v for p in PERMS for v in p]))
for label, text, y in (("TextTitle", "PETAL LANES", 36), ("TextPress", "PRESS START", 64), ("TextOver", "GAME OVER", 44)):
    spr = text_sprites(text, y)
    o("%s: ; count, then OAM entries" % label)
    o(db([len(spr)] + [b for s in spr for b in s]))

with open(sys.argv[1], "w") as fh:
    fh.write("\n".join(out) + "\n")

print("tiles=%d (objects %d)" % (len(tiles.tiles), OBJ_END), file=sys.stderr)
