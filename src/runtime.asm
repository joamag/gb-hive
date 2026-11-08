; Runtime shared by every ROM: console detection, the OAM DMA routine,
; the shadow OAM and a few memory helpers.

INCLUDE "hardware.inc"

SECTION "Runtime", ROM0

; Detects the console and installs the OAM DMA routine in HRAM.
; in: a = value of A when the boot ROM handed over control
InitRuntime::
    cp BOOTUP_A_CGB
    ld a, 0
    jr nz, .dmg
    inc a
.dmg:
    ldh [hIsCGB], a
    xor a
    ldh [hOAMEnd], a
    ld hl, DMARoutine
    ld de, hDMA
    ld bc, DMARoutineEnd - DMARoutine
    ; fall through

; in: hl = source, de = destination, bc = length (non zero)
Copy::
    ld a, [hl+]
    ld [de], a
    inc de
    dec bc
    ld a, b
    or c
    jr nz, Copy
    ret

; in: hl = destination, bc = length (non zero), d = value
Fill::
    ld a, d
    ld [hl+], a
    dec bc
    ld a, b
    or c
    jr nz, Fill
    ret

; Switches the LCD off, waiting for VBlank first (required on hardware).
LcdOff::
    ldh a, [rLCDC]
    add a
    ret nc
.wait:
    ldh a, [rLY]
    cp 144
    jr c, .wait
    xor a
    ldh [rLCDC], a
    ret

; Hides the objects left over from the previous frame.
; in: hl = first unused shadow OAM slot
FinishOAM::
    ldh a, [hOAMEnd]
    ld b, a
    ld a, l
    ldh [hOAMEnd], a
.loop:
    cp b
    ret nc
    ld [hl], 0
    add 4
    ld l, a
    jr .loop

SECTION "DMA routine", ROM0
DMARoutine:
LOAD "DMA HRAM", HRAM
; in: a = high byte of the source (shadow OAM)
hDMA::
    ldh [rDMA], a
    ld a, OAM_COUNT
.wait:
    dec a
    jr nz, .wait
    ret
ENDL
DMARoutineEnd:

SECTION "Shadow OAM", WRAM0, ALIGN[8]
wShadowOAM::
    ds OAM_COUNT * 4

SECTION "Runtime variables", HRAM
hIsCGB:: ds 1
hOAMEnd:: ds 1
