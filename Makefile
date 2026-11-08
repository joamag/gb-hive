BUILD := build
PYTHON ?= python3
ASFLAGS := -Wall -I src -I $(BUILD)

all: hive.gb petal-lanes.gb

$(BUILD)/intro_assets.inc: tools/gen.py
	@mkdir -p $(BUILD)
	$(PYTHON) tools/gen.py $@

$(BUILD)/game_assets.inc: tools/gen_game.py
	@mkdir -p $(BUILD)
	$(PYTHON) tools/gen_game.py $@

$(BUILD)/intro.o: src/intro.asm src/hardware.inc $(BUILD)/intro_assets.inc
$(BUILD)/game.o: src/game.asm src/hardware.inc $(BUILD)/game_assets.inc
$(BUILD)/runtime.o: src/runtime.asm src/hardware.inc
$(BUILD)/hive.o: src/hive.asm src/hardware.inc
$(BUILD)/petal.o: src/petal.asm src/hardware.inc

$(BUILD)/%.o: src/%.asm
	@mkdir -p $(BUILD)
	rgbasm $(ASFLAGS) -o $@ $<

# Hive Solutions intro, loops forever
hive.gb: $(BUILD)/hive.o $(BUILD)/runtime.o $(BUILD)/intro.o
	rgblink -t -n $(BUILD)/hive.sym -m $(BUILD)/hive.map -o $@ $^
	rgbfix -v -c -p 0xFF -t "HIVE" $@

# Petal Lanes, the intro then the game (MBC1 with battery RAM for the best score)
petal-lanes.gb: $(BUILD)/petal.o $(BUILD)/runtime.o $(BUILD)/intro.o $(BUILD)/game.o
	rgblink -t -n $(BUILD)/petal-lanes.sym -m $(BUILD)/petal-lanes.map -o $@ $^
	rgbfix -v -c -p 0xFF -t "PETAL LANES" -m 0x03 -r 0x02 $@

clean:
	rm -rf $(BUILD) hive.gb petal-lanes.gb

.PHONY: all clean
