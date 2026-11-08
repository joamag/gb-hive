<div align="center">

<img src="media/hive-cgb.webp" alt="Hive intro running on the Game Boy Color" width="480">

# Hive Game Boy Intro 🐝

**The Hive Solutions logo, brought to life on the Game Boy in pure assembly.**

[![Play in the browser](https://img.shields.io/badge/%E2%96%B6%20Play-in%20Boytacean-214c90?style=for-the-badge)](https://boytacean.joao.me/?rom_url=https://raw.githubusercontent.com/joamag/gb-hive/master/hive.gb)
[![Download the ROM](https://img.shields.io/badge/Download-hive.gb-5b7fc4?style=for-the-badge)](https://github.com/joamag/gb-hive/raw/master/hive.gb)

[![Game Boy](https://img.shields.io/badge/Game%20Boy-supported-8bac0f)](media/hive-dmg.mp4)
[![Game Boy Color](https://img.shields.io/badge/Game%20Boy%20Color-supported-214c90)](media/hive-cgb.mp4)
[![RGBDS](https://img.shields.io/badge/RGBDS-1.0-e67e22)](https://rgbds.gbdev.io)
[![CPU](https://img.shields.io/badge/CPU%20awake-~4%25%20per%20frame-2ea44f)](#under-the-hood)
[![ROM](https://img.shields.io/badge/ROM-8%20KB%20used-lightgrey)](#under-the-hood)

</div>

## One ROM, two consoles 🕹️

A single `hive.gb` runs on the original Game Boy and on the Game Boy Color. It detects the console at boot and picks the right look: the logo's real blues and a background gradient on the Color, four crisp shades on the original. It also plays on a Game Boy Advance through its Game Boy Color mode.

| Game Boy Color | Game Boy |
| :---: | :---: |
| <img src="media/hive-cgb.webp" alt="Game Boy Color version" width="320"> | <img src="media/hive-dmg.webp" alt="Game Boy version" width="320"> |
| [Watch with sound](media/hive-cgb.mp4) | [Watch with sound](media/hive-dmg.mp4) |

## The show 🎬

1. The screen fades in to the blue gradient of the Hive logo.
2. A bee, the Hive logo in miniature with flapping wings, flies in and loops around the screen leaving a pollen trail.
3. It lands in the middle and grows into the full logo, its squares spreading apart and snapping together with a two note chime.
4. A second bee leaves the hive and writes **HIVE SOLUTIONS** as it flies along the text line.
5. The bee keeps orbiting the logo, slipping behind it on the far side of every loop.

Press **START** or **A** at the end to replay.

## Play it ▶️

* **In the browser:** open it in [Boytacean](https://boytacean.joao.me/?rom_url=https://raw.githubusercontent.com/joamag/gb-hive/master/hive.gb), it loads straight from this repository in Game Boy Color mode.
* **Anywhere else:** grab [`hive.gb`](https://github.com/joamag/gb-hive/raw/master/hive.gb) and load it in any emulator or flash cart.

## Build 🔧

You need [RGBDS](https://rgbds.gbdev.io) 1.0 or later and Python 3 (standard library only, no packages).

```bash
make        # builds hive.gb
make clean  # removes the build output
```

`make` runs `tools/gen.py` to generate `build/assets.inc` (tiles, maps, palettes and motion tables), then assembles, links and fixes the header of `hive.gb`.

<a name="under-the-hood"></a>

## Under the hood ⚙️

The goal was a smooth 60 fps animation that leaves the CPU asleep for as much of each frame as possible.

| Metric | Value |
| --- | --- |
| CPU awake, average | 4.1% of each frame |
| CPU awake, worst frame | 9.9% (the zoom, 26 objects built) |
| ROM used | about 8 KB of 32 KB |
| Code | under 1 KB |
| Interrupts | VBlank only |

*CPU figures measured with the Boytacean core, counting the cycles spent outside `halt`.*

Every frame follows the same short loop:

```text
halt ─► VBlank ─► OAM DMA, SCY, WX (+ palette if requested) ─► build next frame from tables ─► halt
```

The tricks that keep it cheap:

* **Tables, not math.** Flight paths, the zoom, wing flaps, the screen thud and the fades are all precomputed by `tools/gen.py`. At runtime the code only walks tables.
* **A trail for free.** Each pollen dot reads an older entry of the bee's own path table, so the trail needs no state of its own.
* **Reveal by palette.** The logo and the text sit in the background map from the very first frame, hidden by the palette. Swapping the growing sprites for the real logo is one palette write.
* **Write with the window.** The text is uncovered by sliding the window layer, a single register per frame driven by the bee's position.
* **Depth without effort.** The bee slips behind the logo through the object priority bit, stored right in the path table.
* **Hardware limits checked at build time.** The growing logo is built from overlapping 8x16 objects, and the generator verifies every frame against the 40 objects and 10 per scanline limits.
* **A gradient set once.** On the Game Boy Color, each band of the background uses its own palette through the tile attributes, written during init and never touched again.

## Project layout 📁

```text
.
├── Makefile          build rules (RGBDS)
├── hive.gb           prebuilt ROM
├── src
│   ├── main.asm      init, frame loop, state machine and object builders
│   └── hardware.inc  the hardware registers used by the ROM
├── tools
│   └── gen.py        generates tiles, maps, palettes and motion tables
└── media             animations and videos recorded with the Boytacean core
```

## Credits 🙏

* Logo and bee design by [Hive Solutions](https://hive.pt).
* Recorded and tested with [Boytacean](https://github.com/joamag/boytacean), a Game Boy emulator written in Rust.
* Built with [RGBDS](https://rgbds.gbdev.io).
