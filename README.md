# Offset Hunter

Small Python CLI that consumes `offsets.json` (or a single `20xx_offsets.json`) to build a searchable map of NBA 2K offsets, find nearby unknown addresses, convert values to readable text, and optionally probe a running game process on Windows.

## Quick start

```bash
python offset_hunter.py gui --version 2K26  # launch GUI browser/converter
python offset_hunter.py --help
python offset_hunter.py search --query headband --version 2K26
python offset_hunter.py show --name HEADBAND --version 2K26
python offset_hunter.py verify --address 0x1EF --version 2K26 --radius 32
python offset_hunter.py map --version 2K26 --output 2k26_map.json
python offset_hunter.py convert --value 48656c6c6f --input hex --output text
```

## GUI mode

- Double-click `offset_hunter.py` (or run `python offset_hunter.py gui`) to launch directly into the GUI.
- Browse offsets for a chosen version with search/filter and scroll; select an offset to see per-version details plus base pointers/game info for the active version.
- Open a different offsets file with **Open offsets.json** (supports both combined and single-version files).
- Convert values between hex/dec/text in the Converter tab (choose encodings and byte lengths for decimals).
- Hex Viewer tab (Windows): choose a base pointer (Player/Team/Staff/Stadium), index, start offset, and span to read live memory. Known bytes from `offsets.json` are highlighted; unknown bytes are shaded separately. A table decodes any known offsets inside the block. You can search the live block for a value (hex/dec/text) to help hunt new offsets.
- Live Probe tab (Windows): attach to the running NBA2K process (auto-detect by executable name), pick an offset name or hex value, select base pointer (or override address), stride, and index, then read and decode the live memory value.
- Use GUI mode for lining up with the current game version, scrolling existing offsets, and spotting gaps for new discoveries.

## Probing a running game (Windows)

```bash
python offset_hunter.py probe --version 2K26 --offset HEADBAND --index 0
```

- The tool looks up the executable name from `offsets.json` (e.g., `NBA2K26.exe`) to find the PID, then reads from the relevant base pointer plus the offset.  
- Use `--pid` to target a specific process, `--base-address` to override the base pointer, and `--stride` to override the entity size if needed.  
- You may need to run the shell with elevated permissions to read another process' memory.

## Commands

- `search`: substring search across display names and variants.  
- `show`: detailed view of a single offset across versions.  
- `map`: build a per-version mapping (print counts or write JSON).  
- `verify`: locate the nearest known offsets around an unknown address.  
- `convert`: helper to turn hex/dec/text into a different representation.  
- `probe`: read and decode bytes from a running NBA 2K process.

Pass `--offsets-file` to point at a different offsets source if you are not using the bundled `offsets.json`.
