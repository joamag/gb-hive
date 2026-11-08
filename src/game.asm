; Petal Lanes: a top down lane dodger starring the Hive bee (DMG and CGB).
;
; The bee flies up a garden with three lanes. Left and Right switch lanes
; to dodge spider webs and falling raindrops, pollen in a free lane is worth
; five points and the distance flown adds one point every ten pixels.
;
; Efficiency notes:
; - the CPU sleeps in `halt` until VBlank, the only other interrupt is the
;   line split above the score bar
; - the garden is a static 32x32 map that wraps, scrolling is one register
; - the score bar is the window layer pinned to the last 8 lines, so the
;   background scrolls under it; a single line interrupt switches objects
;   off under the bar, so nothing ever draws over the score
; - webs, raindrops and pollen are objects, nothing is written to the map
;   while playing except the 10 score digits during VBlank
; - the best score lives in battery backed cartridge RAM

INCLUDE "hardware.inc"
INCLUDE "game_assets.inc"

DEF ST_TITLE EQU 0
DEF ST_PLAY  EQU 1
DEF ST_DEAD  EQU 2

DEF ITEM_SLOTS  EQU 12
DEF KIND_WEB    EQU 1
DEF KIND_DROP   EQU 2
DEF KIND_POLLEN EQU 3

DEF PAD_A     EQU %00000001
DEF PAD_START EQU %00001000
DEF PAD_RIGHT EQU %00010000
DEF PAD_LEFT  EQU %00100000

DEF SPEED_START EQU $0133 ; 1.2 px per frame
DEF SPEED_MAX   EQU $0300 ; 3.0 px per frame
DEF DEAD_TEXT   EQU 30    ; frames before the game over text

DEF NOTE_LANE   EQU 1798 ; ~524 Hz
DEF NOTE_POLLEN EQU 1860 ; sweeps up
DEF NOTE_DING   EQU 1985 ; C7
DEF NOTE_START  EQU 1899 ; ~880 Hz, sweeps up

DEF LCDC_GAME EQU LCDCF_ON | LCDCF_WIN9C00 | LCDCF_WINON | LCDCF_BG8000 \
    | LCDCF_OBJ16 | LCDCF_OBJON | LCDCF_BGON

SECTION "Game", ROM0

Game::
    di
    call LcdOff

    ld hl, GameTiles
    ld de, _VRAM
    ld bc, GameTilesEnd - GameTiles
    call Copy
    ld hl, GardenMap
    ld de, _SCRN0
    ld bc, 32 * 32
    call Copy
    ld hl, HudRow
    ld de, _SCRN1
    ld bc, 32
    call Copy

    ldh a, [hIsCGB]
    and a
    jr z, .noAttributes
    ld a, 1
    ldh [rVBK], a
    ld hl, GardenAttrs
    ld de, _SCRN0
    ld bc, 32 * 32
    call Copy
    ld hl, _SCRN1
    ld bc, 32
    ld d, PAL_HUD
    call Fill
    xor a
    ldh [rVBK], a
.noAttributes:
    xor a
    call ApplyPalette ; white, the intro ended on white too

    ld hl, wShadowOAM
    ld bc, OAM_COUNT * 4
    ld d, 0
    call Fill
    ld hl, wItems
    ld bc, wGameEnd - wItems
    ld d, 0
    call Fill
    xor a
    ldh [hOAMEnd], a
    ldh [hFrame], a
    ldh [hFadeT], a
    ldh [hScrollY], a
    ldh [hPadHeld], a
    ldh [hPadNew], a
    ld a, $FF
    ldh [hPalReq], a
    ld a, $A5
    ldh [hRng], a
    ldh [hRng + 1], a

    ; a button still held from skipping the intro must not start a game
    call ReadPad
    xor a
    ldh [hPadNew], a

    call LoadBest
    call UpdateHud

    ld a, $80
    ldh [rNR52], a
    ld a, $77
    ldh [rNR50], a
    ld a, $FF
    ldh [rNR51], a

    call EnterTitle

    xor a
    ldh [rSCY], a
    ldh [rSCX], a
    ld a, WIN_Y
    ldh [rWY], a
    ld a, 7
    ldh [rWX], a
    ld a, WIN_Y - 1 ; line interrupt just above the score bar
    ldh [rLYC], a
    ld a, STATF_LYC
    ldh [rSTAT], a
    ld a, LCDC_GAME
    ldh [rLCDC], a
    ld a, IEF_VBLANK | IEF_STAT
    ldh [rIE], a
    xor a
    ldh [rIF], a
    ei

GameLoop:
    halt
    ; the line interrupt also wakes the CPU, only carry on in VBlank
    ldh a, [rLY]
    cp 144
    jr c, GameLoop

    ; VBlank: objects back on, scroll, the 10 score digits and a palette
    ld a, LCDC_GAME
    ldh [rLCDC], a
    ld a, HIGH(wShadowOAM)
    call hDMA
    ldh a, [hScrollY]
    ldh [rSCY], a
    ld hl, wHud
    ld de, _SCRN1 + HUD_SCORE_COL
    REPT 5
        ld a, [hl+]
        ld [de], a
        inc e
    ENDR
    ld e, LOW(_SCRN1 + HUD_BEST_COL)
    REPT 5
        ld a, [hl+]
        ld [de], a
        inc e
    ENDR
    ldh a, [hPalReq]
    cp $FF
    jr z, .noPalette
    call ApplyPalette
    ld a, $FF
    ldh [hPalReq], a
.noPalette:

    ld hl, hFrame
    inc [hl]
    call ReadPad

    ; fade in from white over the first 16 frames
    ldh a, [hFadeT]
    cp 16
    jr nc, .faded
    inc a
    ldh [hFadeT], a
    dec a
    rrca
    jr c, .faded
    ldh [hPalReq], a
.faded:

    ldh a, [hState]
    add a
    add LOW(StateTable)
    ld l, a
    adc HIGH(StateTable)
    sub l
    ld h, a
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    call CallHL
    jr GameLoop

CallHL:
    jp hl

; Line interrupt on the line above the score bar: waits for that line's
; HBlank and switches objects off, so items sliding off the bottom of the
; garden never draw over the score. VBlank switches them back on.
HudSplit::
    push af
.wait:
    ldh a, [rSTAT]
    and STATF_MODE
    jr nz, .wait
    ldh a, [rLCDC]
    res 1, a
    ldh [rLCDC], a
    pop af
    reti

StateTable:
    dw StateTitle
    dw StatePlay
    dw StateDead

; -----------------------------------------------------------------------------
; States
; -----------------------------------------------------------------------------

EnterTitle:
    xor a
    ldh [hState], a ; ST_TITLE
    ldh [hTimer], a
    ld a, 1
    ldh [hLane], a
    ld a, [LaneBeeX + 1]
    ldh [hBeeX], a
    ret

StateTitle:
    ; the garden drifts by and the bee wanders between lanes
    ld hl, hScrollY
    dec [hl]
    ldh a, [hFrame]
    rlca
    rlca
    and 3
    add LOW(AttractLanes)
    ld l, a
    adc HIGH(AttractLanes)
    sub l
    ld h, a
    ld a, [hl]
    ldh [hLane], a
    call MoveBee

    ldh a, [hPadNew]
    and PAD_START | PAD_A
    jp nz, StartGame

    ld hl, wShadowOAM
    call DrawBee
    ld de, TextTitle
    call DrawText
    ldh a, [hFrame]
    and $20
    jr z, .done
    ld de, TextPress
    call DrawText
.done:
    jp FinishOAM

StartGame:
    ; seed the generator with the moment START was pressed
    ldh a, [rDIV]
    ld b, a
    ldh a, [hRng]
    xor b
    ldh [hRng], a
    ldh a, [hFrame]
    ld b, a
    ldh a, [hRng + 1]
    xor b
    or 1
    ldh [hRng + 1], a

    ld hl, wItems
    ld bc, wScore + 3 - wItems
    ld d, 0
    call Fill
    ld a, LOW(SPEED_START)
    ldh [hSpeed], a
    ld a, HIGH(SPEED_START)
    ldh [hSpeed + 1], a
    xor a
    ldh [hSub], a
    ldh [hDropSub], a
    ldh [hAcc], a
    ldh [hTick], a
    ldh [hTimer], a
    ld a, 48
    ldh [hNext], a
    ld a, 7
    ldh [hPrevFree], a
    ld a, ST_PLAY
    ldh [hState], a
    call UpdateHud
    jp PlayStart

StatePlay:
    ; speed ramps up by 1/256 px every 5 frames
    ld hl, hTick
    inc [hl]
    ld a, [hl]
    cp 5
    jr c, .noRamp
    ld [hl], 0
    ldh a, [hSpeed + 1]
    cp HIGH(SPEED_MAX)
    jr nc, .noRamp
    ldh a, [hSpeed]
    add 1
    ldh [hSpeed], a
    ldh a, [hSpeed + 1]
    adc 0
    ldh [hSpeed + 1], a
.noRamp:

    ; whole pixels the ground moves this frame
    ldh a, [hSpeed]
    ld b, a
    ldh a, [hSub]
    add b
    ldh [hSub], a
    ldh a, [hSpeed + 1]
    adc 0
    ldh [hDY], a
    ld b, a
    ldh a, [hScrollY]
    sub b
    ldh [hScrollY], a

    ; raindrops fall 3/8 faster than the ground moves
    ldh a, [hSpeed + 1]
    ld h, a
    ldh a, [hSpeed]
    ld l, a
    srl h
    rr l
    srl h
    rr l
    ld d, h
    ld e, l
    srl h
    rr l
    add hl, de
    ldh a, [hDropSub]
    add l
    ldh [hDropSub], a
    ld a, h
    adc 0
    ld b, a
    ldh a, [hDY]
    add b
    ldh [hDropDY], a

    ; a new row of items every few dozen pixels of ground
    ldh a, [hDY]
    ld b, a
    ldh a, [hNext]
    sub b
    ldh [hNext], a
    call c, SpawnRow

    ldh a, [hPadNew]
    bit 5, a ; left
    jr z, .noLeft
    ldh a, [hLane]
    and a
    jr z, .noLeft
    dec a
    ldh [hLane], a
    call PlayLane
.noLeft:
    ldh a, [hPadNew]
    bit 4, a ; right
    jr z, .noRight
    ldh a, [hLane]
    cp 2
    jr nc, .noRight
    inc a
    ldh [hLane], a
    call PlayLane
.noRight:
    call MoveBee

    ld hl, wShadowOAM
    call DrawBee
    call UpdateItems ; may end the run
    call FinishOAM
    ldh a, [hState]
    cp ST_PLAY
    ret nz

    ; one point every 10 px of ground
    ldh a, [hDY]
    ld b, a
    ldh a, [hAcc]
    add b
    cp 10
    jr c, .noPoint
    sub 10
    ldh [hAcc], a
    ld a, 1
    jp AddScore
.noPoint:
    ldh [hAcc], a
    ret

Die:
    ld a, ST_DEAD
    ldh [hState], a
    xor a
    ldh [hTimer], a
    ldh [hDY], a ; the field freezes
    ldh [hDropDY], a
    call PlayHit
    jp CheckBest

StateDead:
    ld hl, hTimer
    ld a, [hl]
    inc a
    jr z, .saturated
    ld [hl], a
.saturated:
    ld a, [hl]
    cp DEAD_TEXT
    jr c, .draw
    jr nz, .waitStart
    ; clear the field once, so the text never shares lines with items
    ld hl, wItems
    ld bc, ITEM_SLOTS * 4
    ld d, 0
    call Fill
.waitStart:
    ldh a, [hPadNew]
    and PAD_START | PAD_A
    jp nz, StartGame
.draw:
    ld hl, wShadowOAM
    call DrawBee
    ldh a, [hTimer]
    cp DEAD_TEXT
    jr nc, .text
    call UpdateItems
    jp FinishOAM
.text:
    ld de, TextOver
    call DrawText
    ldh a, [hFrame]
    and $20
    jr z, .done
    ld de, TextPress
    call DrawText
.done:
    jp FinishOAM

; -----------------------------------------------------------------------------
; Items
; -----------------------------------------------------------------------------

; Spawns a row: one or two obstacles and maybe pollen in the free lane.
SpawnRow:
    call Rand
    ldh [hRow], a
    and 7
    ld c, a
    add a
    add c
    add LOW(Perms)
    ld l, a
    adc HIGH(Perms)
    sub l
    ld h, a
    ld a, [hl+]
    ldh [hLaneA], a
    ld a, [hl+]
    ldh [hLaneB], a
    ld a, [hl]
    ldh [hLaneC], a
    xor a
    ldh [hBlocked], a

    ldh a, [hLaneA]
    call SpawnObstacle
    ldh a, [hRow]
    bit 3, a
    jr z, .pollen
    ldh a, [hLaneB]
    call SpawnObstacle
.pollen:
    ldh a, [hRow]
    and %00110000
    jr z, .gap
    ldh a, [hLaneC]
    ld b, a
    ld c, KIND_POLLEN
    ld a, YS_POLLEN
    call AddItem
.gap:
    ; remember which lanes this row leaves free
    ldh a, [hBlocked]
    cpl
    and 7
    ldh [hPrevFree], a
    ; next row: the gap for this speed plus up to 15 px
    ldh a, [hSpeed + 1]
    add a
    add a
    ld b, a
    ldh a, [hSpeed]
    rlca
    rlca
    and 3
    add b
    add LOW(RowGaps)
    ld l, a
    adc HIGH(RowGaps)
    sub l
    ld h, a
    ld b, [hl]
    call Rand
    and 15
    add b
    ld b, a
    ldh a, [hNext]
    add b
    ldh [hNext], a
    ret

; in: a = lane
SpawnObstacle:
    ld b, a
    inc a ; lane bit: 0 -> 1, 1 -> 2, 2 -> 4
    cp 3
    jr nz, .bit
    inc a
.bit:
    ld c, a
    ldh a, [hBlocked]
    or c
    ldh [hBlocked], a
    call Rand
    and 7
    cp 5
    jr c, .web
    ; raindrops fall faster than the ground and can reach the row ahead,
    ; so never drop one into the only lane that row leaves free
    ldh a, [hPrevFree]
    cp c
    jr z, .web
    ld c, KIND_DROP
    jr .kind
.web:
    ld c, KIND_WEB
.kind:
    ld a, YS_SPAWN
    ; fall through

; in: b = lane, c = kind, a = y (stored with the YS offset)
AddItem:
    ld e, a
    ld hl, wItems
.find:
    ld a, [hl]
    and a
    jr z, .found
    ld a, l
    add 4
    ld l, a
    cp LOW(wItemsEnd)
    jr nz, .find
    ret ; every slot busy, skip it
.found:
    ld [hl], c
    inc l
    ld [hl], b
    inc l
    ld [hl], e
    ret

; Moves every item, checks the ones level with the bee and draws them, all
; in a single pass over the slots.
; in: hl = next OAM slot
; out: hl = next OAM slot
UpdateItems:
    ld de, wItems
.loop:
    ld a, [de]
    and a
    jp z, .next
    ldh [hKind], a
    cp KIND_DROP
    ldh a, [hDY]
    jr nz, .ground
    ldh a, [hDropDY]
.ground:
    ld b, a
    inc e
    ld a, [de]
    call LaneCenter
    ldh [hItemX], a
    inc e
    ld a, [de]
    add b
    jr c, .remove
    cp YS_DESPAWN
    jr nc, .remove
    ld [de], a
    dec e
    dec e
    ld c, a ; y (stored)

    ; only items level with the bee, and only while playing, can touch it
    ldh a, [hState]
    cp ST_PLAY
    jr nz, .draw
    ld a, c
    sub BEE_YS0 - 14
    cp BEE_YS1 - BEE_YS0 + 14
    jr nc, .draw
    push hl
    call HitTest
    pop hl
    jr nc, .draw
    ldh a, [hKind]
    cp KIND_POLLEN
    jr z, .collect
    push hl
    push de
    push bc
    call Die
    pop bc
    pop de
    pop hl
    jr .draw
.collect:
    xor a
    ld [de], a
    push hl
    push de
    ld a, $05
    call AddScore
    call PlayPollen
    pop de
    pop hl
    jp .next
.remove:
    dec e
    dec e
    xor a
    ld [de], a
    jp .next

.draw:
    ld a, c
    sub 32
    ld c, a ; OAM y
    ldh a, [hItemX]
    ld b, a ; centre x, also the OAM x of a 16 px wide web
    ldh a, [hKind]
    cp KIND_WEB
    jr nz, .small
    ld a, c
    ld [hl+], a
    ld a, b
    ld [hl+], a
    ld a, WEB_TILE
    ld [hl+], a
    ld a, ATTR_WEB
    ld [hl+], a
    ld a, c
    ld [hl+], a
    ld a, b
    add 8
    ld [hl+], a
    ld a, WEB_TILE + 2
    ld [hl+], a
    ld a, ATTR_WEB
    ld [hl+], a
    jr .next
.small:
    ld a, c
    ld [hl+], a
    ld a, b
    add 4
    ld [hl+], a
    ldh a, [hKind]
    cp KIND_DROP
    jr nz, .pollen
    ld a, DROP_TILE
    ld [hl+], a
    ld a, ATTR_DROP
    ld [hl+], a
    jr .next
.pollen:
    ldh a, [hFrame]
    rrca
    rrca
    and 2 ; sparkle frame
    add POLLEN_TILE
    ld [hl+], a
    ld a, ATTR_POLLEN
    ld [hl+], a
.next:
    ld a, e
    add 4
    ld e, a
    cp LOW(wItemsEnd)
    jp nz, .loop
    ret

; in: c = item y (stored), hKind, hItemX
; out: carry set when the item touches the bee (keeps de)
HitTest:
    push de
    ldh a, [hKind]
    dec a
    add a
    add a
    add LOW(ItemBoxes)
    ld e, a
    adc HIGH(ItemBoxes)
    sub e
    ld d, a
    ldh a, [hItemX]
    ld b, a
    ldh a, [hBeeX]
    add 2
    ld l, a ; bee box x0
    add 12
    ld h, a ; bee box x1
    ld a, [de]
    inc de
    add b
    cp h
    jr nc, .miss
    ld a, [de]
    inc de
    add b
    cp l
    jr c, .miss
    jr z, .miss
    ld a, [de]
    inc de
    add c
    cp BEE_YS1
    jr nc, .miss
    ld a, [de]
    add c
    cp BEE_YS0 + 1
    jr c, .miss
    pop de
    scf
    ret
.miss:
    pop de
    and a
    ret

; in: a = lane, out: a = lane centre x (clobbers c)
LaneCenter:
    ld c, a
    swap a
    add a
    add c
    add c
    add c
    add c
    add LANE_CX0
    ret

; -----------------------------------------------------------------------------
; Drawing
; -----------------------------------------------------------------------------

; Eases the bee towards its lane, at most 6 px per frame.
MoveBee:
    ldh a, [hLane]
    add LOW(LaneBeeX)
    ld l, a
    adc HIGH(LaneBeeX)
    sub l
    ld h, a
    ld b, [hl]
    ldh a, [hBeeX]
    cp b
    ret z
    jr c, .right
    sub b
    inc a
    srl a
    cp 7
    jr c, .left
    ld a, 6
.left:
    ld c, a
    ldh a, [hBeeX]
    sub c
    ldh [hBeeX], a
    ret
.right:
    ld c, a
    ld a, b
    sub c
    inc a
    srl a
    cp 7
    jr c, .step
    ld a, 6
.step:
    add c
    ldh [hBeeX], a
    ret

; in: hl = next OAM slot
DrawBee:
    ldh a, [hFrame]
    rrca
    and 3
    add LOW(FlapTiles)
    ld e, a
    adc HIGH(FlapTiles)
    sub e
    ld d, a
    ld a, [de]
    ld d, a ; left column tile
    ld e, ATTR_BEE
    ld c, 0
    ldh a, [hState]
    cp ST_DEAD
    jr nz, .alive
    ld e, ATTR_BEE | OAMF_YFLIP ; belly up, sinking onto its shadow
    ldh a, [hTimer]
    cp 6
    jr c, .sink
    ld a, 6
.sink:
    ld c, a
.alive:
    ld a, BEE_Y + 16
    add c
    ld b, a
    ldh a, [hBeeX]
    add 8
    ld c, a
    ld a, b
    ld [hl+], a
    ld a, c
    ld [hl+], a
    ld a, d
    ld [hl+], a
    ld a, e
    ld [hl+], a
    ld a, b
    ld [hl+], a
    ld a, c
    add 8
    ld [hl+], a
    ld a, d
    add 2
    ld [hl+], a
    ld a, e
    ld [hl+], a
    ; shadow, the right half is the left one mirrored; once the bee lies on
    ; the ground it covers its shadow (and the line keeps 2 objects spare)
    ldh a, [hState]
    cp ST_DEAD
    ret z
    ld a, SHADOW_Y + 16
    ld [hl+], a
    ld a, c
    ld [hl+], a
    ld a, SHADOW_TILE
    ld [hl+], a
    ld a, ATTR_SHADOW
    ld [hl+], a
    ld a, SHADOW_Y + 16
    ld [hl+], a
    ld a, c
    add 8
    ld [hl+], a
    ld a, SHADOW_TILE
    ld [hl+], a
    ld a, ATTR_SHADOW | OAMF_XFLIP
    ld [hl+], a
    ret

; in: de = text (count, then OAM entries), hl = next OAM slot
DrawText:
    ld a, [de]
    inc de
    ld c, a
.loop:
    REPT 4
        ld a, [de]
        inc de
        ld [hl+], a
    ENDR
    dec c
    jr nz, .loop
    ret

; -----------------------------------------------------------------------------
; Score
; -----------------------------------------------------------------------------

; in: a = points (BCD), chimes every hundred
AddScore:
    ld b, a
    ld a, [wScore + 1]
    ld c, a
    ld hl, wScore
    ld a, [hl]
    add b
    daa
    ld [hl+], a
    ld a, [hl]
    adc 0
    daa
    ld [hl+], a
    ld a, [hl]
    adc 0
    daa
    ld [hl], a
    ; the bar shows 5 digits, hold at 99999
    cp $10
    jr c, .inRange
    ld a, $09
    ld [hl-], a
    ld a, $99
    ld [hl-], a
    ld [hl], a
.inRange:
    ld a, [wScore + 1]
    cp c
    call nz, PlayDing
    ld de, wHud
    ld hl, wScore + 2
    jr HudDigits

; Turns the score and the best score into digit tiles for the score bar.
UpdateHud:
    ld de, wHud
    ld hl, wScore + 2
    call HudDigits
    ld hl, wBest + 2
    ; fall through

; in: hl = highest byte of a BCD number, de = 5 digit tiles to fill
HudDigits:
    ld a, [hl-]
    and $0F
    add DIGIT_TILE
    ld [de], a
    inc de
    REPT 2
        ld a, [hl]
        swap a
        and $0F
        add DIGIT_TILE
        ld [de], a
        inc de
        ld a, [hl-]
        and $0F
        add DIGIT_TILE
        ld [de], a
        inc de
    ENDR
    ret

; Keeps the best score and saves it when the run beat it.
CheckBest:
    ld hl, wScore + 2
    ld de, wBest + 2
    ld b, 3
.compare:
    ld a, [de]
    cp [hl]
    jr c, .newBest
    ret nz
    dec hl
    dec de
    dec b
    jr nz, .compare
    ret
.newBest:
    ld hl, wScore
    ld de, wBest
    ld bc, 3
    call Copy
    call SaveBest
    jp UpdateHud

LoadBest:
    ld a, $0A
    ld [rRAMG], a
    ld hl, _SRAM
    ld a, [hl+]
    cp $50 ; "P"
    jr nz, .fresh
    ld a, [hl+]
    cp $4C ; "L"
    jr nz, .fresh
    ld de, wBest
    ld bc, 3
    call Copy
    ; only a valid 5 digit BCD number is accepted
    ld hl, wBest
    ld b, 3
.digits:
    ld a, [hl+]
    ld c, a
    and $0F
    cp 10
    jr nc, .fresh
    ld a, c
    cp $A0
    jr nc, .fresh
    dec b
    jr nz, .digits
    ld a, [wBest + 2]
    cp $10
    jr c, .close
.fresh:
    xor a
    ld [wBest], a
    ld [wBest + 1], a
    ld [wBest + 2], a
.close:
    xor a
    ld [rRAMG], a
    ret

; The signature is cleared first and written last, so a save cut short
; reads back as no save at all, never as a corrupt score.
SaveBest:
    ld a, $0A
    ld [rRAMG], a
    xor a
    ld [_SRAM], a
    ld hl, wBest
    ld de, _SRAM + 2
    ld bc, 3
    call Copy
    ld hl, _SRAM + 1
    ld a, $4C ; "L"
    ld [hl-], a
    ld a, $50 ; "P"
    ld [hl], a
    xor a
    ld [rRAMG], a
    ret

; -----------------------------------------------------------------------------
; Helpers
; -----------------------------------------------------------------------------

; in: a = fade step, 0 white to 7 full colour
ApplyPalette:
    ld c, a
    ldh a, [hIsCGB]
    and a
    jr nz, .cgb
    ld a, c
    add a
    add c
    ld c, a
    ld b, 0
    ld hl, DmgFade
    add hl, bc
    ld a, [hl+]
    ldh [rBGP], a
    ld a, [hl+]
    ldh [rOBP0], a
    ld a, [hl]
    ldh [rOBP1], a
    ret
.cgb:
    ld l, c
    ld h, 0
    add hl, hl
    add hl, hl
    add hl, hl
    add hl, hl
    ld d, h
    ld e, l
    add hl, hl
    add hl, hl
    add hl, de ; step * 80
    ld de, CgbFade
    add hl, de
    ld a, BCPSF_AUTOINC
    ldh [rBCPS], a
    ld c, LOW(rBCPD)
    ld b, 8
.bg:
    REPT 4
        ld a, [hl+]
        ldh [c], a
    ENDR
    dec b
    jr nz, .bg
    ld a, BCPSF_AUTOINC
    ldh [rOCPS], a
    ld c, LOW(rOCPD)
    ld b, 12
.obj:
    REPT 4
        ld a, [hl+]
        ldh [c], a
    ENDR
    dec b
    jr nz, .obj
    ret

; Reads the joypad: held in hPadHeld, newly pressed in hPadNew.
; bits: 0 A, 1 B, 2 Select, 3 Start, 4 Right, 5 Left, 6 Up, 7 Down
ReadPad:
    ld a, P1F_GET_DPAD
    ldh [rP1], a
    ldh a, [rP1]
    ldh a, [rP1]
    cpl
    and $0F
    swap a
    ld b, a
    ld a, P1F_GET_BTN
    ldh [rP1], a
    ldh a, [rP1]
    ldh a, [rP1]
    ldh a, [rP1]
    ldh a, [rP1]
    cpl
    and $0F
    or b
    ld b, a
    ld a, P1F_GET_NONE
    ldh [rP1], a
    ldh a, [hPadHeld]
    cpl
    and b
    ldh [hPadNew], a
    ld a, b
    ldh [hPadHeld], a
    ret

; 16 bit xorshift, out: a = random byte (only touches a, h and l)
Rand:
    ldh a, [hRng + 1]
    ld h, a
    ldh a, [hRng]
    ld l, a
    ld a, h
    rra
    ld a, l
    rra
    xor h
    ld h, a
    ld a, l
    rra
    ld a, h
    rra
    xor l
    ld l, a
    xor h
    ld h, a
    ld a, l
    ldh [hRng], a
    ld a, h
    ldh [hRng + 1], a
    ret

PlayLane:
    xor a
    ldh [rNR10], a
    ld a, $40
    ldh [rNR11], a
    ld a, $61
    ldh [rNR12], a
    ld a, LOW(NOTE_LANE)
    ldh [rNR13], a
    ld a, $80 | HIGH(NOTE_LANE)
    ldh [rNR14], a
    ret

PlayPollen:
    ld a, $15 ; sweep up
    ldh [rNR10], a
    ld a, $80
    ldh [rNR11], a
    ld a, $A2
    ldh [rNR12], a
    ld a, LOW(NOTE_POLLEN)
    ldh [rNR13], a
    ld a, $80 | HIGH(NOTE_POLLEN)
    ldh [rNR14], a
    ret

PlayDing:
    ld a, $80
    ldh [rNR21], a
    ld a, $93
    ldh [rNR22], a
    ld a, LOW(NOTE_DING)
    ldh [rNR23], a
    ld a, $80 | HIGH(NOTE_DING)
    ldh [rNR24], a
    ret

PlayStart:
    ld a, $16
    ldh [rNR10], a
    ld a, $80
    ldh [rNR11], a
    ld a, $C3
    ldh [rNR12], a
    ld a, LOW(NOTE_START)
    ldh [rNR13], a
    ld a, $80 | HIGH(NOTE_START)
    ldh [rNR14], a
    ret

PlayHit:
    xor a
    ldh [rNR41], a
    ld a, $F3
    ldh [rNR42], a
    ld a, $64
    ldh [rNR43], a
    ld a, $80
    ldh [rNR44], a
    ret

SECTION "Game state", WRAM0, ALIGN[8]
wItems: ; kind, lane, y + 48, unused
    ds ITEM_SLOTS * 4
wItemsEnd:
wScore: ; BCD, lowest byte first
    ds 3
wBest:
    ds 3
wHud: ; digit tiles: score then best
    ds 10
wGameEnd:

SECTION "Game variables", HRAM
hState: ds 1
hTimer: ds 1
hFrame: ds 1
hFadeT: ds 1
hPalReq: ds 1
hScrollY: ds 1
hSub: ds 1
hSpeed: ds 2
hTick: ds 1
hDY: ds 1
hDropSub: ds 1
hDropDY: ds 1
hNext: ds 1
hAcc: ds 1
hLane: ds 1
hBeeX: ds 1
hRng: ds 2
hPadHeld: ds 1
hPadNew: ds 1
hKind: ds 1
hItemX: ds 1
hRow: ds 1
hLaneA: ds 1
hLaneB: ds 1
hLaneC: ds 1
hBlocked: ds 1
hPrevFree: ds 1
