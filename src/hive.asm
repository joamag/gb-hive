; Hive Solutions intro ROM: the intro plays and keeps looping, START or A
; replays it from the start.

INCLUDE "hardware.inc"

SECTION "VBlank", ROM0[$0040]
    reti

SECTION "Header", ROM0[$0100]
    nop
    jp Start
    ds $0150 - @, 0 ; filled in by rgbfix

SECTION "Start", ROM0[$0150]
Start:
    di
    ld sp, $E000
    call InitRuntime
    xor a ; standalone, never returns
    jp Intro
