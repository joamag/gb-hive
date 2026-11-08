ROM := hive.gb
BUILD := build
PYTHON ?= python3

all: $(ROM)

$(BUILD)/assets.inc: tools/gen.py
	@mkdir -p $(BUILD)
	$(PYTHON) tools/gen.py $@

$(BUILD)/main.o: src/main.asm src/hardware.inc $(BUILD)/assets.inc
	rgbasm -Wall -I src -I $(BUILD) -o $@ src/main.asm

$(ROM): $(BUILD)/main.o
	rgblink -t -n $(BUILD)/hive.sym -m $(BUILD)/hive.map -o $@ $<
	rgbfix -v -c -p 0xFF -t "HIVE" $@

clean:
	rm -rf $(BUILD) $(ROM)

.PHONY: all clean
