; Petal Lanes ROM: the Hive Solutions intro plays once (START or A skips it)
; and hands over to the game.

INCLUDE "hardware.inc"

SECTION "VBlank", ROM0[$0040]
    reti

SECTION "STAT", ROM0[$0048]
    jp HudSplit

SECTION "Header", ROM0[$0100]
    nop
    jp Start
    ds $0150 - @, 0 ; filled in by rgbfix

SECTION "Start", ROM0[$0150]
Start:
    di
    ld sp, $E000
    call InitRuntime
    ld a, 1 ; embedded, returns when the intro is over
    call Intro
    jp Game
