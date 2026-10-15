Research notes and tools for the Tokimeki Memorial 2 translation toolkit.

- `game-internals.md` – everything known about the discs, compression, text encoding and script bytecode.
- `../tools/` – pure-Python research tools:
  - `compression.py` – the game's two LZ decompressors
  - `text.py` – nibble-swapped Shift-JIS decoding
  - `script.py` – script-block parser and bytecode disassembler
  - `extract_scripts.py <disc.bin> <out_dir>` – dump all scene dialogue to JSON
  - `cdimage.py` – sector I/O with EDC/ECC, ISO 9660 root listing
  - `rebuild.py` – rebuild a script block with new text (`encode` Japanese, `encode_en` English)
  - `font_en.py` – the English font (editable ASCII art) and the letter-pair encoding
  - `glyphpatch.py` – builds the replacement glyph code for the EXE (needs `pip install keystone-engine`)
  - `scenes.py` – finds every script block and its container (file / bundle / pack / packed)
  - `space_report.py <disc.bin>...` – room each scene has for longer text
  - `translations.py unpack|pack|init` – `translations/` ↔ one workbook per scene (for `mt.py`), and workbooks from the discs
  - `build_patch.py <original.bin> <out.bin> [--tl DIR]` – builds one patched English disc image (default `--tl translations`); `../patch.py <folder>` does every disc
  - `mt.py`, `mt_compare.py`, `llm.py`, `limits.py` – machine translation through LLM APIs (see `translating.md`)
  - `pictures.py find|export|import` – pictures with Japanese text; `make_pictures.py --disc1 … --disc2 … [--check]` remakes `pictures/*.png` from your discs with the edits in `tools/art/`
  - `datepatch.py`, `namepatch.py`, `evsname.py`, `evsgrid.py` – the main-screen date box, Latin name entry, romaji EVS nickname and reading grid
  - `check_translations.py [translations | FILE] [--disc …]` – checks translations without building (line counts, codes, widths, box rows, font, room)
  - `strpack.py` – repacks the name tables (`{char:NN}`, surname lists) so English names fit
  - `verify_glyphpatch.py <SLPM_863.5x>` – checks that code against the original in an emulator (needs `unicorn`, `capstone`)

Extracted data, workbooks and experiments go under `work/` (git-ignored). `translations/` is the translation itself: Japanese and English, one entry per text box.

**Translators:** start with `translating.md`.
