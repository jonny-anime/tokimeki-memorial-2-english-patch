# Game internals — Tokimeki Memorial 2 (PS1, Japan, 5 discs, Rev 1)

Research notes. Every fact says how it was established. **Verified** means
checked against the game's data or code; **hypothesis** means not yet.
Addresses are KSEG0 RAM addresses unless noted. Disc 1 unless noted.

Reference project: TM1 patch (gothamor/tokimeki-memorial-english-patch).
Its structure (per-file overlays, SERIFU/*.BIN, plain Shift-JIS dialogue,
hard-coded LBAs) **does not carry over directly**: see §2.

## 1. Disc images (verified, ISO 9660 walk)

All five discs: single-track MODE2/2352 BIN/CUE, volume ID `KONAMI`, root:

| Disc | EXE | CDPACK00.BIN | XA / STR |
|---|---|---|---|
| 1 | SLPM_863.55 (LBA 24) | LBA 536, 468,357,120 B | XA5.STR, VX095_PR.STR, VX095_OP.STR |
| 2 | SLPM_863.56 | LBA 536, 605,593,600 B | XA1.STR |
| 3 | SLPM_863.57 | LBA 536, 596,267,008 B | XA2.STR |
| 4 | SLPM_863.58 | LBA 536, 610,228,224 B | XA3.STR |
| 5 | SLPM_863.59 | LBA 536, 591,276,032 B | XA4.STR |

Each disc's EXE is different (different MD5). The first sector of each
CDPACK is a leftover build-tool text buffer (`DISC n`, date 2000/02/17–18,
a list of `\STR\XA*.STR` paths); the `DISC n` number matches the XA file
on that disc (Disc 2 → DISC 1 / XA1 …, Disc 1 → DISC 5 / XA5).

## 2. CDPACK00.BIN: one big pack instead of a file tree (verified)

Almost everything is inside `CDPACK00.BIN`. The EXE locates it once with
`CdSearchFile("\CDPACK00.BIN;1")` (`0x80025154`, string at `0x800629C8`)
and keeps the base at `gp+0x288` (`gp+0x280` = base − 0x218). After that
the game reads by **absolute sector number** (e.g. `0x219` = 537).

Read request (built by `0x80024A40`): word 0 = `(sector_count << 23) |
(RAM address & 0x7FFFFF)`, word 1 = absolute LBA. Queued with
`0x800233DC(6, req, 0)`.

Contents seen so far (by sampling sectors):
- Sector 537 (3 sectors, 0x1800 B): **obfuscated** code module loaded at
  `0x80010000` (anti-modchip check, "SOFTWARE TERMINATED / CONSOLE MAY
  HAVE BEEN MODIFIED"). Obfuscation = every byte +0x64; the loader adds
  0x9C back and drops the first byte (`0x800251C4`).
- Other obfuscated code modules contain **plain Shift-JIS UI text**: e.g.
  sectors 1505–1510 hold memory-card prompts, name-entry kana, the
  heroines' full names, and leftover dev paths (`\t2\data\s_option\...`).
- An ending/epilogue module (around sector 109,000) is plain (not
  obfuscated) code+data with Shift-JIS text, `0x0A` line breaks, and a
  table of absolute RAM pointers (`0x800C1Dxx`), i.e. the same style as TM1.
- Many sector-aligned files in two compression formats (§3), and
  "packet" files made of 32-byte headers + 16 KiB compressed chunks
  (§3.3).

**Not found yet:** the table that maps game resources to CDPACK sectors.
No sorted LBA table exists in the EXE's loaded code/data (searched u32
runs, strides 4–16). The loaders take (LBA, size) from their callers.
The EXE has 685 KB of high-entropy data after its loaded image
(file offset 0x58000–0x100000, not loaded by the BIOS); purpose unknown.

## 3. Compression (verified)

### 3.1 lz1 — `0x8002E950` (`tools/compression.py: lz1`)
u24 LE compressed size + 1 byte, then LZ with LSB-first flag bits, 1 KiB
zero-filled ring buffer starting at 0x3DE. Commands: `<0x80` long copy
from absolute ring position, `0x80–0xBF` short copy (0–15 back),
`≥0xC0` literal run. **Verified** by running the game's routine in a MIPS
emulator (Unicorn) on the same input: identical output.

Decoding from the wrong start gives text whose literals are right but
whose back-references are garbage. That's a sign of starting mid-stream,
not of a decoder bug.

### 3.2 lz2 — `0x8001A830` (`tools/compression.py: lz2`)
No header; LSB-first bits; literal / short copy (2–5 B, 8-bit offset) /
long copy (12-bit offset, 4-bit or byte length); `0x0000` ends the stream.
Chosen instead of lz1 by a type byte in the dispatcher at `0x8002E8C4`.
**Verified**: type-0x204 packets decode to exactly 16,384 B, and the bytes
consumed equal the size field of the following packet header.

### 3.3 Packet files (partly verified)
32-byte header: `u32 type, u32 a, u32 b, 20 zero bytes`, then payload.

| type | payload | a / b |
|---|---|---|
| 0x004 | raw 16 KiB | a = 0x4000, b = RAM address |
| 0x100 / 0x104 | lz1 chunk (→ 8 or 16 KiB) | a ≈ neighbouring chunk size, b = RAM address or running offset |
| 0x200 | structured table | ? |
| 0x204 | lz2 chunk (→ 16 KiB) | a = size of a neighbouring chunk |

## 4. Dialogue: text encoding (verified)

**Dialogue is Shift-JIS with the two nibbles of every byte swapped**
(`0x82 0xC8` な is stored as `0x28 0x8C`). Uncompressed on the disc.
`tools/text.py` decodes it.

How it was found (2026-10-11): two DuckStation save states with dialogue on
screen (Disc 1 childhood prologue). The state file is `DUCC` header +
two zstd frames (256×192 RGBA screenshot, then the emulator state); the
2 MB RAM image starts at offset 0x1A62 of the state frame (located by
finding EXE code in it). In RAM:
- the line being drawn is plain Shift-JIS in a per-line buffer
  (`0x8019A458` / `0x8015F458`), pointed to from a fixed text-engine
  structure at `0x800EC008` / `0x800EC0B0`;
- `0x800EC0A0` holds script start / end and `0x800EC0B8` the current
  position: that script block holds the whole message, nibble-swapped
  (aligned against the on-screen 「？？？」 = `18 84` ×3 and
  「おままごと」 = `28 8A 28 CD 28 CD 28 2B 28 6C`).

Earlier negative results explained: Shift-JIS/EUC/UTF-16 searches and the
hiragana scans could not match nibble-swapped text.

### 4.1 Control codes (raw, un-swapped values)

| Bytes | Meaning | Status |
|---|---|---|
| `00 10` | start of a display line | verified (matches on-screen line breaks) |
| `00 80 90` | end of a message (wait for button) | verified (between the two saves' messages) |
| `18 <name> 00` | speaker label (e.g. 「？？？」, 「女の子」) | verified on screen |
| `18 D1` | speaker = the player (name inserted) | hypothesis (player lines show the player's name) |
| `00 1F aa bb` | voice clip (bb counts 00, 01, 02 over one girl's lines) | hypothesis |
| `00 31 xx xx 30 4B 4F` | follows each message in code-module scripts | unknown |
| `09 4E id16 len16 …` | message record in code-module scripts | hypothesis (len = byte length of what follows) |

## 5. Dialogue containers (partly verified)

**A. Standalone script blocks** (Disc 1 childhood scenes, 112 found):
magic `38 35 00 00`, u16 offset of the bytecode section, u16 section
count (5), u16 table, 8-byte ASCII scene ID at +0x18 (`YGROUP00`,
`YG_05501`, …), `FF FF`. Then data tables, then bytecode with the text
embedded. Found inside **bundles**: `u32 count, u32 size[count]`, parts
back to back (e.g. Disc 1 sector 50520: script 0x654 B + 3 more parts).
One table is **per-character timing**: length byte = number of characters
in a message, then one value per character (e.g. `19 02 02 … 13 … 00`
for a 25-character message). Translations will have to regenerate it.

**B. Bytecode inside code modules** (Discs 2–5, the main game): same text
encoding and control codes, records `09 4E id len …`, next to MIPS code;
a `38 35 00 00` block named `DEFAULT` sits nearby, with a different
section count.

### 5.1 Size (first-pass survey, `work/rough_extract.py`)
Runs of nibble-swapped Shift-JIS after a `00 10` line start:

| Disc | display lines | unique | characters |
|---|---|---|---|
| 1 | 3,206 | 2,562 | ~20k |
| 2 | 24,108 | 13,933 | ~236k |
| 3 | 24,569 | 14,622 | ~244k |
| 4 | 26,115 | 14,489 | ~264k |
| 5 | 28,467 | 13,489 | ~290k |

Much is shared between discs (Discs 2 and 3 share 5,144 unique lines).
This survey is not an extractor: it ignores structure and may miss lines
that don't start with `00 10`.

## 6. Script bytecode (verified)

Every scene script (Disc 1 childhood and the main game on all discs) is a
`38 35 00 00` block (§5 A). The main game's blocks have 7-character IDs
(`G000012`, `G_TELG`, `G_COMSCR`, …). The u16 at +0x20 is not a fixed
marker (`FF FF` or `01 01`), so the scanner doesn't rely on it.

Two engines exist, both code modules loaded at `0x800C0000`:

| | childhood (Disc 1 save states) | main game |
|---|---|---|
| where found | RAM dump, module at 0x800C0000 | Disc 2 CDPACK sector 1559 (file→RAM: sector 1559 = 0x800C0000; located by matching `jal` targets to prologues) |
| statement dispatcher | 0x800C4530, table 0x800C0348 | 0x800E4940, table 0x800C1644 |
| expression evaluator | 0x800C3D7C, 27 ops (0x40–0x5A) | 0x800E4070, table 0x800C1504, 34 ops (0x40–0x61) |
| script pointer | 0x800EC0A4 | 0x8011B3BC |

The main engine is a superset for every opcode the childhood scripts use,
so `tools/script.py` uses one table. Operand lengths (read from each
handler; the `a0`/`a2`/`a8` sub-op tables and some handlers with an
automated pointer-advance analysis, spot-checked by hand):

| op | operands | meaning (where known) |
|---|---|---|
| 10, 11 | string | display line |
| 18 | string | speaker label |
| 17 | 1 | |
| 1E | 2 | |
| 1F | u8 + s16 | voice clip |
| 20, 21 / 22, 23 | 0 / 2 | |
| 26, 27, 38, 3E, 3F, 00 | 0 | 38 call fixed subroutine, 3F return, 00/3E no-op |
| 30 | expr + s16 | if (expr) else jump |
| 31 | s16 | goto |
| 40, 88, FD, FE | expr | |
| 80 | 0 | end of message (wait for button) |
| 81, 82 | 1 | (main engine) also seem to end a message; hypothesis |
| 83 | 2 | |
| 87, 89, 8A, 90, F0, F1 | 0 | |
| 98–9B, A7, B8 | 1 | |
| A0 | sub + {00,02–05,20: 2; 01: 4; 06: 3; 07–0B: 1; else 0} | |
| A1 | 2 + (expr if first byte is 0, else 1) | |
| A2 | sub + {01: 5; 02–06: 3; 0B: 2; 07–0A, 0C–0E: 1; else 0} | |
| A3 | 4 | |
| A8 | sub + {00,02,06–08: 2; 01,03,10,11,20,21: 1; 05: 4; 09: 3; 40: 6; else 0} | |
| AF | 1, +1 if (byte & 0xE0) == 0x40 | |
| B0 | 3 | |
| FF | — | end of a path |

Jumps are relative to the end of the instruction. **Check:** all 81,936
jumps on the five discs land exactly on an instruction start found by the
disassembler (none misaligned), so the operand table is consistent.

Expressions: `40` prefix; binary `41–45, 47–4C, 58, 59, 5B`; unary `46`,
`5A`; `4D` assign (target byte + expr; target 0x14 has no expr); `4E`
s16 constant; `4F` variable (1 byte); `50–53` 1-byte argument; `54–57`,
`5C–61` no operands (game date/state queries, e.g. `60` = today is a
birthday).

Strings (expanders: childhood `0x800C3758`, main game `0x800E395C`;
nibble-swapped; **verified by reading the main-game expander**, and every
string on the five discs re-encodes to its original bytes). Names in
braces are the text syntax of `tools/script.py` / `tools/rebuild.py`:

| byte(s) | syntax | meaning | uses (5 discs, each disc counted once) |
|---|---|---|---|
| `00` | — | end of string | |
| ≥ `80` + 1 | text | two-byte character, copied unchanged | |
| `0C` | `{nobreak}` | always at the end of a line: the expander returns 0 instead of 1 and the next line continues on the same row (seen on screen, experiment 6) | 723 |
| `10`–`1C` | `{you:NN}` | how character N addresses the player: `0x800E31B8(N & 0xF)` builds name1/name2 + an honorific or a pronoun from module data (`0x800C1424` さん, `ちゃん`, `君`, `くん`, `あなた`, `キミ`, `お前`, `貴様` …), chosen by relationship state. `{you:12}` showed カレイ君 | 710 (main game) |
| `1D` `1E` `1F` | `{name1}` `{name2}` `{name3}` | player's given name / nickname / third name (`0x80075004/0B/12`) | 22,373 |
| `20`–`2D` | `{char:NN}` | a character's name, `0x800E2EEC(N & 0xF)` (`2E`→匠, `2F`→純 when called with 14/15) | 5,418 |
| `2E`/`2F` + 1 | `{char2E:XX}` | character name chosen by the variable `XX & 0x3F` (table `0x80111548`) | 37 |
| `3X` + 1 | `{numX:YY}` | number variable X (format byte YY) | 173 |
| other < `80` | `{cXX}` | copied, nothing drawn | 0 in dialogue |

The expander stops at 256 output bytes. The childhood engine handles `0C`,
`1D`–`1F`, `2x` (table at `0x800C0220`) and `3x` the same way.

Scripts can continue after an early `FF` (jumps skip over it), so the
extractor follows control flow from the entry point instead of sweeping
linearly.

## 7. Extraction status (tools/extract_scripts.py)

`python tools/extract_scripts.py <disc.bin> <out_dir>` writes one JSON file
per script block (ID `SCENE#n/message`, speaker, lines, byte offsets).

| Disc | blocks (all parse) | messages | display lines | text lines covered* |
|---|---|---|---|---|
| 1 | 148 | 903 | 1,754 | 95.7% |
| 2 | 1,608 | 11,212 | 27,278 | 98.7% |
| 3 | 1,453 | 11,893 | 27,853 | 99.0% |
| 4 | 1,495 | 11,968 | 29,631 | 98.5% |
| 5 | 1,464 | 12,976 | 32,245 | 98.5% |

\* Share of every `00 10`/`00 18` + nibble-swapped Japanese run on the disc
that lies inside an instruction reached by the extractor
(`work/coverage.py`). The rest (57–299 lines per disc) is in a few places:
minigame shopkeeper (おやぢ), shrine fortunes, some date scenes. Either the
`09 4E` record format inside code modules (§5 B) or script entry points
not reachable from the main entry.

## 8. Reinsertion experiments (Disc 1, DuckStation, 2026-10-11)

All on copies under `work/`, built with `tools/cdimage.py` (EDC/ECC,
own ECMA-130 implementation; reproduces stored EDC/ECC on 45 sampled
sectors byte for byte) and `tools/rebuild.py`.

| # | change | result |
|---|---|---|
| 1 | first character of every childhood display line → ◆ (same length, 47 sectors) | **Verified on screen.** No checksum or integrity check: the game reads scripts straight from the disc. Choice options (はい/いいえ) are ordinary `10` lines. A line starting with a name code kept its name (`{name1}`/`{name2}` insert the player's name/nickname; exact roles unconfirmed). |
| 2 | YG_02506: one line longer, two shorter, same bundle size; jumps re-targeted | **Verified on screen:** longer line shown, the Yes/No branch around it works. |
| 2b | YG_01503 (+44 B, two lines) and YG_02501/02/04/05 (+22 B each): bundle part 0 grows, later parts shift, size fields updated | **Verified on screen** (YG_01503): long line shown, scene graphics intact. Save state: part 0 and the shifted part 1 are in RAM back to back (0x8017F014, 0x8017F3A8), byte-identical to the patched disc. The loader uses the bundle's size table. |
| 3 | YG_02506: ASCII letters `LetsGoHomeTogetherOK` (20 B) in Hikari's line; full-width 「ＯＫ，ＧＯ！！」 in the player's reply | **Verified on screen.** ASCII is consumed two bytes at a time as a (invalid) 2-byte code: 10 identical tick-mark placeholder glyphs at full-width spacing. Full-width Latin renders correctly. The player's speaker label showed the given name (フィア) while Hikari's `{name2}` showed the nickname (カレイ): **`{name1}` = given name, `{name2}` = nickname** (verified). |
| 4 | EXE glyph block replaced (§9.3) + YG_02506 in English with letter pairs: "Play the childhood prologue?", Yes/No, Hikari "{name2}-chan, / Let's walk home together!", player "Yeah, let's go." Bundle grew to exactly its 10 sectors (0x5000 B). Only sectors 38–39 and 35550–35559 differ from the original. | **Verified on screen** (fresh boot, new game): prompt, Yes/No menu, Hikari's lines and the player's reply all render as letter pairs; the `{name2}` name (カレイ) and the 「 bracket sit correctly next to them; the box layout is unchanged. |
| 5 | Same as 4, built by `tools/build_patch.py` from a translation workbook | **byte-identical to experiment 4's image**; a build with no translations and no EXE patch is byte-identical to the original disc |
| 6 | Disc 2, no EXE patch: a ◆ added in front of every display line of every `file`-kind scene (1,419 scene instances grow, up to their last sector's end; 29 didn't fit and were skipped) | **Verified on screen** (G200000, Hikari after school; save state + Change Disc): the grown scene loads and shows every ◆. Side finding: in `あっ、{c0C}` + `{c12}。` the ◆ of the second line appeared on the same row, and `{c12}` displayed カレイ君: `0C` = continue on the same row, `12` = how Hikari addresses the player (confirmed by the expander code, §6). |
| 7 | Disc 2: group G200000 (header 69079) moved past the end of the disc by `build_patch.py --move-group 69079`, ★ on the first line of each text box | **Verified on screen**: ★ shown, so the moved copy is what the game reads |
| 8 | Disc 2: ◆ on every phone-call line; phone overlays re-laid and moved past the end of the disc, table entry and EXE size updated | **Verified on screen** (fresh boot, memory-card save): Hikari's call shows the ◆ |
| 9 | Disc 2: ◆ on the first character of 686 code-referenced UI strings (9b: alignment rule added) | **Verified on screen**: marks in menus, file select, phone book, message boxes; 9 garbled the Option Room (two code bytes mistaken for text), 9b fine |
| 10 | Disc 2 + glyph patch: 27 UI strings in English, in place | **Verified on screen**: Option Room, "This week", Yes/No render as English |
| 11 | Disc 2 + glyph patch: phone book (names, profiles, memos), date places, 94 scene place names in English (`work/tl_exp11`) | Phone book and date list **verified on screen**; fixed-width tables found (11b fixes padding, verified); 11c reads the place tables from the header (5,637 records, 108 names); **place label verified** (hold Triangle) |
| 12 | Disc 1 + glyph patch + name-entry patch (`work/exp12`; 12b adds the romaji EVS nickname; 12c romaji labels on the EVS reading grid, pending) | **Verified on screen**: Latin grid, 5-letter names stored as pairs, shown on the entry and confirmation screens and in dialogue ("FIACR ちゃん") |
| 13 | exp12d + English name-entry buttons (picture re-import, `work/exp13`) | First try: no change (wrong copy patched); with the module's own copy patched: **verified on screen**, all six buttons in English in their own colours |
| 14 | Disc 2 + exp11c text + English stat labels (`pictures/main_stats.png`, `work/exp14`) | Labels still Japanese: the packet patched is not the copy the screen uses (§15) |
| 15 | As 14 + the main-screen image records (`pictures/main_stats_hands.png`, `work/exp15`) | English stat labels on screen |
| 16 | As 15 + the date box (`tools/datepatch.py`, `work/exp16`) | Main-screen date in English; file-select date still Japanese (text, not tiles) |
| 17 | As 16 + the file-select date strings (`work/exp17`) | No change on screen: the date there is background art |
| 18 | As 16 + the file-select background (`pictures/file_select_date.png`, `work/exp18`) | Date reads 1999 4/ 5 |
| 19 | As 18 + file-select buttons and messages (`work/exp19`) | Buttons and messages in English; the Yes/No prompts still Japanese |
| 20 | As 19 + prompts with line breaks (`work/exp20`) | Prompts in English |
| 21 | As 20 + title menu (`work/exp21`) | Title menu in English |
| 23 | Disc 2 + first dialogue scene G407000 (`work/tl_exp23`) | Plays in English; names / honorifics still Japanese |
| 24 | As 23 + name tables and honorifics (`work/exp24`) | Pending |

**Bundle layout:** `u32 count, u32 size[count]`, parts back to back (part 0
= script, part 1 = 0x24-byte table, parts 2–3 compressed graphics). Each
bundle is followed, at the next sector, by a companion file starting with
the scene ID in ASCII. The bytes between a bundle's end and its last
sector's end are **stale build-tool leftovers** (an exact copy of another
sector's bytes at the same in-sector offset, e.g. YG_05501's tail =
sector 49720 +0x4A0), so a bundle can grow into them. Growing past its
last sector would move files and is not supported yet.

**Text box:** a line of 18 full-width characters after the 「 fits with
room to spare (YG_01503); the exact limit is still to be measured.

**English:** string bytes 0x20–0x3F are control codes (`2x` fixed insert,
`3x` + 1 byte number), so ASCII space, punctuation and digits can't be
used as-is. English needs its own encoding (as in TM1).

## 9. Text rendering (save state save4, mid-typewriter; static analysis)

**Font: the console BIOS's built-in kanji font**, through `Krom2RawAdd`
(BIOS B(51h), stub at `0x8005A504`): Shift-JIS code → address of a 16×15,
1-bit glyph in BIOS ROM. Invalid codes give a placeholder glyph (the tick
marks in experiment 3). Verified by the stub's code and its callers.

Chain (all in `SLPM_863.55`, resident):

| Address | Role |
|---|---|
| `0x800D84A0` (module) | glyph cache: 96 slots × 28 B at `0x800F0660` (flags, 2-byte code at +2). For each slot that needs drawing: render the glyph, `LoadImage` it to VRAM at x = 0x3C0 + …, y = 0x100 + … (4-bit texture). Text is then drawn as sprites using these cached glyphs. |
| `0x8001D94C` | picks one of two glyph renderers by a mode word at `0x80075198` (0x200 → `0x8001C874`, else `0x8001CAE8`, a variant with a second colour, probably shadow/outline) |
| `0x8001C874` / `0x8001CAE8` | render one character: if the first byte is < 0x80 → **draw nothing** (single-byte path returns immediately); else code = 2 bytes, ask `0x8001C5C0` for a custom glyph, else `Krom2RawAdd`; expand the 1-bit rows (u16 per row, 15 rows) to 4-bit pixels |
| `0x8001C5C0` | **custom-glyph lookup**: a chain of compares for specific codes (`0xE36B`, `0xE6D2`, …, `0x997A`, `0x9DF3`, …) returning 30-byte bitmaps the game ships (around `0x80061874`); 0 if none |

**Glyph renderers in detail:** `0x8001C874` (renderer A) expands a
16-px row to 16 four-bit pixels with one unrolled test per bit. `0x8001CAE8`
(renderer B) keeps 10 of the 16 columns (bits 0x80, 0x20, 0x10, 0x04, 0x02,
0x8000, …) and merges neighbours: a **10-px-wide** glyph for the display
mode with 10 + 1 px cells. Dialogue in the save states uses mode 0x200 →
renderer A (16-px glyphs).

### 9.1 Text layout (verified in save4's slot table)

`0x800D7D10` (childhood engine module) lays out one display line at a time:
- 96 slots × 28 B at `0x800F0660` = **one slot per on-screen cell** (not a
  per-character cache). Slot: +0 flags (0x80 used), +1 spacing (3), +2 code
  (2 bytes, as in the line buffer), +4 delay, +8 appear time, +0x10/+0x12
  screen x/y, +0x14/+0x15 VRAM tile, +0x18/+0x1A glyph w/h (16/15).
- x = column × (16 + 3) + 32, y = row × 18 + 166 (mode 0x200). save4:
  陽 32, ノ 51, 下 70, 「 86 (brackets sit 3 px left), カ 105 …
- **24 columns per row**, automatic wrap; continuation rows indent 4
  columns (the speaker label + 「 fill columns 0–3). 4 rows.
- Each glyph gets its own 16×15 VRAM tile (16 × 15 grid).
- Per-cell typewriter delay comes from the caller (pointer → one byte per
  cell, else a constant); save4 shows 2 frames per cell, 4 after 、.
  、… double the delay, 。！？ ×4. *Inferred, not yet verified:* the
  script's length-prefixed byte tables (`19 02 02 … 13 …`) are these
  per-cell delays (one byte per character, mostly `02`).
- A line is processed 2 bytes at a time; 0x0A as first byte = newline;
  0x00 ends it.

### 9.2 English rendering: letter pairs (implemented, verified on screen)

**Letter-pair codes** (TM1's method, adapted). One 19-px cell shows two
narrow letters; the cell's 2-byte code names both (`tools/font_en.py`):

- lead byte = left letter: `LEAD[i]` = `0xA0`–`0xDF`, then `0x85`–`0x87`,
  then `0xEB`–`0xEF` (72 values the original game never displays);
- trail byte = `0x40` + index of the right letter (`0x40`–`0x87`, so trail
  bytes stay ≥ 0x40 like real Shift-JIS);
- 72 characters: space, A–Z, a–z, 0–9, `. , ! ? ' " - ~ …`. Anything else
  is written as a full-width Shift-JIS cell (e.g. ♪, or a Japanese name
  from `{name1}`); a lone letter before such a cell is paired with a space.

Checked: across all 1,325,453 two-byte characters in every script on the
five discs, none uses those lead bytes; no script uses `0xF…` symbol codes
or trail bytes < 0x40. Both engines' string expanders copy any byte
≥ 0x80 plus the next byte unchanged (`0x800C37E8`, main engine
`0x800E39EC`); the layout only tests the first byte for 0x00, 0x0A and 0x81
(the pause rule for 、。！？…). Bytes 0x20–0x3F can't be used as lead
bytes (string control codes, §6).

**Spacing:** option (a), no layout change: cells stay 19 px apart, letters
sit at x 0 and x 10 of each cell (≈ 9.5 px pitch), about 40 letters per
continuation row. Chosen from offline mock-ups (`work/mockups/`).

**Font:** 5 × 11 px per letter, drawn for this project, at cell rows 3–13
(capitals and ascenders rows 3–11, x-height 6, descenders rows 12–13),
same metrics as the approved mock-up. Packed as 5-bit rows: 495 bytes.

**Encoding/decoding:** `tools/rebuild.py: encode_en()` turns English text
(with `{name1}`-style codes) into script bytes; `tools/script.py` decodes
pair cells back to letters, so the extractor reads patched discs too
(extraction of the original Disc 1 is unchanged: same 148 blocks, 903
messages, 1,754 lines, identical JSON).

### 9.3 The patched glyph block (`tools/glyphpatch.py`, verified in an emulator)

**Original behaviour (verified by running the original code in Unicorn on
all 65,536 codes, and by reading it):**
- Lookup `0x8001C5C0(code)`: only the low 16 bits count. 30 codes
  (`0x98A5`…`0x9F7E`, `0xE056`…`0xE97D`) and all 4,096 codes
  `0xF000`–`0xFFFF` have a glyph of the game's own: 30-byte, 15-row 1-bit
  bitmaps in **46 consecutive slots** at `0x80061874 + 30 × slot` (slot =
  the code's position in a fixed list, or 30 + low nibble for `0xF…`).
  Everything else → 0.
- Renderer A `0x8001C874(src, out)`: if `src[0]` < 0x80 return 1 without
  writing. Else code = `src[0] << 8 | src[1]`; glyph = lookup(code), or
  `Krom2RawAdd(code)` if 0. Glyph −1 → 32 zero words. Otherwise 15 rows:
  u16 `h` → two words of 4-bit pixels (`h` bit 7 → pixel 0 … bit 0 →
  pixel 7; bit 15 → pixel 8 … bit 8 → pixel 15; set pixel = 0xF), then 2
  zero words. Returns 1. Saves ra/s0/s1 on a 0x20-byte stack frame.

**Every caller** (scan of all five discs, `jal` and `lui/addiu` pairs, raw
and +0x64-obfuscated data; each hit disassembled):

| caller | calls |
|---|---|
| EXE `0x8001C8A4`, `0x8001CB18` | lookup (from renderers A and B) |
| EXE `0x8001D964`, `0x8001D974` | renderer B / A (selector `0x8001D94C`) |
| modules, Disc 2 sectors 682 and 942 (Disc 1 720/980), Disc 1 sector 134905 | renderer A directly (`malloc(0x80)`, render one character) |
| module, Disc 1 sector 134941 | lookup directly, then the BIOS-font wrapper `0x80058834`; expands the 30-byte glyph to one byte per pixel (a third renderer) |

All other hits were data. Pair codes work for every caller that reads the
lookup's 30-byte glyph (renderer B samples 10 of the 16 columns, so pairs
look wrong in the 10-px mode; not seen in dialogue yet).

**New block** (same entry points, `0x8001C5C0`–`0x8001CAE8`, renderer B
untouched):

| address | contents |
|---|---|
| `0x8001C5C0` | `j lk_body` + `andi v1, a0, 0xFFFF` (lookup entry) |
| `0x8001C5C8` | the 30 codes in slot order (60 B) |
| `0x8001C604` | nibble → 4 pixels table (32 B) |
| `0x8001C624` | pair glyph buffer (32 B) |
| `0x8001C644` | English font (495 B) |
| `0x8001C874` | renderer A (table-driven, 15-row loop) |
| `0x8001C978` | lookup body: `0xF…` rule, table search, letter-pair composer |

89 bytes are left over. For a pair code the lookup builds the cell bitmap
in the buffer and returns its address; renderer A then expands it like any
glyph, without calling the BIOS. Uses only caller-saved registers; no
stack.

**Verification** (`python tools/verify_glyphpatch.py <EXE>`): original and
patched code side by side in Unicorn (BIOS font stubbed with random
glyphs, some codes returning −1), every one of the 65,536 codes, for the
lookup (also with garbage in the upper 16 bits), renderer A (even and odd
input addresses, 64-byte guard after the output) and renderer B. Result:
identical for every non-pair code; for all 5,184 pair codes the output
equals the Python reference model (`font_en.compose`). Also checked:
callee-saved registers and sp preserved, writes only to the stack, the
output buffer and the pair buffer, no load-delay-slot hazards (Unicorn
doesn't model the R3000 load delay, so this is checked statically on the
disassembly). Mutation test: swapping two table codes, corrupting the
nibble table, rendering 14 rows or flipping one font bit each make the
check fail. All five discs' EXEs have the identical original block
(SHA-1 checked), and the patch changes EXE file sectors 14–15 only.

**Save states:** a DuckStation save state restores all of RAM, including
the EXE code, so a state made before patching brings back the original
glyph code. Test patched discs from a fresh boot (or from a state made on
the same patched build).

## 10. Where the scene blocks live (`tools/scenes.py`, verified on all five discs)

Every block found by the extractor falls into one of four containers:

| kind | what | how it can grow | Disc 1 | Discs 2–5 (each) |
|---|---|---|---|---|
| `file` | block starts a sector; after its bytecode only 1–3 `FF` end bytes, then zeros to the end of its last sector | up to the end of that sector (the game reads whole sectors; verified on screen, experiment 6) | 20 (G_END, G_Y_END) | 1,288–1,448 (the whole main game) |
| `bundle` | block is a whole part of a bundle (§8) | into the stale bytes after the bundle in its last sector (verified, experiments 2b, 4) | 20 (YG_xxxxx childhood scenes) | 0 |
| `pack` | one of several blocks in a **script pack** that is itself a bundle part: `80 35`, u16 count, u32 offsets[count] (relative to the pack, 4-aligned), then the blocks | like `bundle`; the offset table is rewritten (not yet tested on screen) | 84 (YGROUP00, 02–04: the free-roaming childhood chatter) | 0 |
| `packed` | anything else: YGROUP01's pack sits in an unknown container; G_DATE / G_GEKO / G_EXAM / G_COMSCR / G_SOTSU inside code modules; G_TELG phone calls and DEFAULT blocks packed back to back | can't grow yet (shorter is fine) | 21 | 68–83 |

### 10.1 Main-game scene groups (verified by reading the engine and on screen)

The main game's `file` scenes are **variants inside scene groups** (Disc 2:
95 groups hold all 1,539 scene sectors; Discs 3 and 5 likewise):

- An **event module** (code + data loaded at about `0x80181228`; e.g. Disc 2
  sectors 69076–69078) has a table of absolute **group header** sectors and
  calls `0x800F3C10(group sector, variant index, buffer)`; the buffer is a
  constant in the module, right after its own data (`0x801829BC` there).
- The **group header** sector: `90 35`, u16 n, u32 e[n+1]. Variant i is the
  sectors [group + e[i], group + e[i+1]) (empty if equal). `0x800F3E10` reads
  exactly those sectors into the buffer (size = (e[i+1] − e[i]) × 2048).
  Variants are chosen by index (e.g. `girl × 2` or `girl × 2 + 1`), so many
  variants share one scene ID (G200000 has 23 at sectors 69080–69102).
- Nothing else points at a variant, so **a variant can move anywhere after
  its group header and take more sectors** by rewriting e[]. The builder
  rewrites the whole group after the end of the disc image when a variant
  outgrows its sectors (new sectors: Mode 2 Form 1, zero subheader, like the
  disc's own padding; byte-identical format checked).
- The buffer size is not stored anywhere. Rule used (`tools/groups.py`): a
  variant may take as many sectors as the largest variant any group of the
  same event module already has (the game loads that much into the same
  buffer). Disc 2: 22 groups allow 1 sector, 39 two, 12 three, 22 four. Of
  the scenes that don't fit at ×1.2, 66 of 68 can then grow; at ×1.5, 168 of
  176.
- **On screen (experiment 7, Disc 2):** the whole G200000 group (23 variants)
  rewritten after the original end of the disc (sectors 314538–314560, header
  69079 rewritten, old copies left in place) and its first lines marked ★: the
  walk-home scene showed the ★ lines, i.e. the game read the moved copy.
  Not yet seen on screen: a variant grown to more sectors than before (the
  buffer rule above).
- 19 event modules on Disc 2 (found by their calls to `0x800F3C10`); every
  group is referenced from at least one of them.

### 10.2 Code overlays with script packs (phone calls; verified on screen)

- A resource table at disc **sector 541 + 0x440** (RAM `0x80010C40`) lists 8
  overlays as (u32 load address & 0x7FFFFF = `0x0013DD50`, u32 sector). Their
  sizes are in the EXE at **`0x80062178`** (u32 bytes, same order; the EXE also
  holds pointers to the 8 entries at `0x80062198`); the game reads
  ceil(size / 2048) sectors to `0x8013DD50`. Same layout on all five discs.
  Disc 2: #1 = sector 23367 (G_TELT calls, 0x1E800 B), #2 = 12992 (phone
  module with the G_TELG/G_TELP calls, 0x34800 B), #3 = 12229 (DEFAULT) …
- Calls are blocks in script packs (`80 35`, §10) inside the overlay.
  `tools/overlays.py` + the builder lay a changed pack out again; blocks that
  no longer fit go after the end of the overlay (the pack's offsets point
  there), then the overlay is written after the end of the disc, its table
  entry gets the new sector and the EXE its new size.
- Room: in a save state during a call (save6), RAM is zero from the end of the
  phone overlay (`0x80172090`) to `0x80180C00`; event modules load at
  `0x80181228`. Overlays may grow to end at `0x80180000` (about 56 KB more
  for the phone module). Inferred from one snapshot.
- Disc 2: all 47 phone blocks (G_TELG, G_TELP, G_TELT, ~31 KB of text) become
  growable; still fixed: DEFAULT, G_DATE, G_GEKO, G_EXAM, G_COMSCR, G_BOMB,
  G_TELTK, two G3xxxxx (~10 KB).
- **On screen (experiment 8):** ◆ on every line of every call; both phone
  overlays moved past the end of the disc, phone overlay 0x34800 → 0x36800 B.
  Fresh boot + memory-card save: Hikari's call showed every ◆ (her call stayed
  inside the re-laid pack). Calls moved into the overlay's tail (Ijuin,
  Tatebayashi's answering machine) not yet seen.
- A save state keeps the old table and EXE sizes in RAM, so overlay changes
  must be tested from a fresh boot.

**Room** (`tools/space_report.py`, English estimated at 1.2× and 1.5× the
Japanese bytes):

| Disc | `file` scenes that fit (×1.2 / ×1.5) | text in `packed` |
|---|---|---|
| 2 | 1,380 / 1,272 of 1,448 | 41 KB |
| 3 | 1,233 / 1,124 of 1,297 | 42 KB |
| 4 | 1,304 / 1,163 of 1,376 | 41 KB |
| 5 | 1,208 / 1,066 of 1,288 | 41 KB |

Median room in a `file` scene's last sector: ~1.1 KB. So about 90–95% of
the main game's scenes take a translation in place; the rest (about 70–220
scenes per disc, depending on how wordy the English is) and the `packed`
text (~7%) need either relocation (which means finding the game's table of
scene sector numbers, not found yet, §2) or tighter English. Disc 1's
childhood bundles have little room (YG_02506: 4 bytes; YGROUP00's 36-block
bundle: 648 bytes).

## 11. Translation workflow (`tools/translations.py`, `tools/build_patch.py`)

1. `translations/` is the source: scene files grouped by character and disc
   (`<girl>/disc<N>.json`, `others/`, `childhood.json`, `phone_calls.json`,
   `endings.json`, `misc.json`), `menus.json`, `speaker_names.json`. A scene
   entry has the block's `key` (`<scene>-<8 hex of its SHA-1>`; the same
   block on several discs is one entry), `kind`, `room` (tools/limits.py),
   `found` (disc: sectors) and its messages (= text boxes): the lines'
   offsets `at`, the Japanese and English lines joined by `\n`.
2. `translations.py unpack work/tl` / `pack work/tl` convert to and from one
   **workbook** per scene (`{"speaker": {...}, "lines": [{"at", "ja", "en"}]}`
   per message), which `mt.py` works on. `init work/tl <disc1.bin> ...`
   makes the workbooks from the discs (with the English of `translations/`
   merged in).
3. `python tools/build_patch.py <original.bin> <out.bin> [--tl DIR]` builds a
   patched image: EXE patch, every translated scene re-encoded and written
   back into its container, EDC/ECC fixed, the result rescanned (same
   blocks, same containers). Scenes that don't fit stay Japanese and are
   listed with how many bytes they are over; lines wider than a row (20
   cells, a name counted as 4) are listed as warnings. `patch.py <folder>`
   runs it for every disc found and writes an `.m3u`.

Checks done: experiment 4 rebuilt from a workbook is byte-identical; a
build with nothing to do is byte-identical to the original; a stress build
with every Disc 1 string replaced by 1.2× as many letters patched 85 blocks
across `file`, `bundle` and `pack` containers and reported the 30 that
didn't fit.

## 13. Menu and system text (`tools/uitext.py`; verified on screen)

Outside the scene scripts, Disc 2 has about 90 KB of plain (not
nibble-swapped) Shift-JIS strings. The ones the code points at (a u32
pointer or a lui + addiu/ori pair), that start on a 4-byte boundary and are
zero-padded to the next one, are real UI text: **628 unique strings, about
6,000 characters** on Disc 2 in the EXE (girls' given names), the main
engine (names, nicknames, honorifics used by `{you:NN}`, holidays, clubs,
"今週の予定" …), and overlays #1 (profiles), #2 (phone), #3 (exam / news
texts), #5 (Option Room), #6 (memory card, file select).

- **Experiment 9** (◆ on the first character of each, same length): the
  marks appeared in the file-select and memory-card screens, the room's
  schedule box, the Option Room, the phone book and message boxes. A first
  version also marked two "strings" that were really code (single 貯
  followed by non-zero bytes), which garbled the Option Room; the alignment
  rule above removes them.
- **Experiment 10** (glyph patch + English letter pairs written in place):
  Option Room labels and values, "This week", Yes/No all render correctly.
  The menu text routine accepts pair codes.
- Rule: English replaces a string in place and must fit its field (text +
  NUL + alignment padding). Fields padded with full-width spaces keep their
  width. Strings containing ASCII (printf-style formats) and the memory-card
  file titles in the EXE are left alone.
- **Pictures, not text:** the date box, stat labels (体調, 文系 …), screen
  titles ("FILE SELECT ROOM", "OPTION ROOM"), menu icons, the calendar and
  the magazine pages. Need image editing.
- **Not extracted yet:** the remaining ~80 KB of unreferenced or doubtful
  strings, and name entry (katakana only).

### 13.1 Tables: the phone book and the date places (experiment 11)

Some lists are indexed by number, so no pointer leads to each string. The
scanner also takes **runs of 4 or more aligned, zero-padded strings at a
constant stride (≤ 64 bytes)**, and accepts a string right after a pointer
word as well as after zero padding. On Disc 2 that adds (all verified by
reading the bytes; on screen pending):

- **Overlay #1 (phone book / profiles), from 0x8013DD54:** "ＡＢＣＤＥ－";
  12 full names at a 16-byte stride (穂刈　純一郎 … 陽ノ下　　光, padded to 6
  cells); a pointer table; the surnames (陽ノ下, 水無月, 寿 …, fields of 4–8
  bytes, reached by pointers); then per person: birthday (`　９月　６日生まれ`),
  sign + blood type, "ＴＥＬ／…" (the number is drawn with ○△□×), height,
  B/W/H, club, and 40 memo lines (Jun's notes, 32-byte fields), "ＭＥＭＯ／".
- **Overlay #2 (phone), first word = 60, then 21 × 20-byte date places**
  (海, 山, サーカス … 河川敷公園; 16 bytes padded with 　, NUL, padding).
  The rest of the "60 entries" is code and data, not names.
- **On screen (experiment 11):** the English names, profiles and date
  places render. Two rules came out of it:
  - **Fixed-width tables.** Where every entry of a table is padded with
    full-width spaces to the same width, the game draws exactly that many
    cells, ignoring the NUL. A shorter English name showed garbage after it
    ("J. Hokari" + the bytes after its NUL), and a longer one was cut
    ("Takumi Sakak"). `uitext` now marks these (`cells`), pads English to
    the width and limits it to it (phone-book names: 6 cells = 12 letters).
  - **The date-place box** shows about 7 cells (the longest Japanese name)
    although its entries are 8 wide: "Botanical Garden" (8 cells) ran into
    the frame. Keep those to 14 letters.
  - Menus draw cells at a wider pitch than dialogue, so the letter pairs
    show small gaps ("Hi no mo to"). Readable; a later font tweak could
    narrow it.
- The surnames can't hold an English surname in place (寿's field is 4
  bytes). They are reached by pointers, so a later step can move them
  (append to the overlay, as for script packs) and repoint them.

### 13.2 Place names in scene scripts (experiment 11)

The location label of a scene (正門, 廊下, 中央公園前, ひびきの駅 …) is not in
the bytecode but in **32-byte records in the script's data area**. The
table's offset is the third u16 at +0x22 of the block header; records are
2-byte aligned (the first scanner assumed 4 and missed half of them, e.g.
the date at the shopping street; fixed in experiment 11c):

    u16 id, u8 background, u8 number of characters, char name[28] (Shift-JIS, zero-padded)
    ... more records ..., u16 0xFFFF

e.g. G132000 (Disc 2 sector 102183) +0x378: `3c 01 20 05` ひびきの駅. The
fourth byte equals the number of characters in every record: 5,637
records on Disc 2 (108 different names in 1,275 blocks), read by
`uitext.scene_places` from the header pointer. The third byte varies for the
same name (0x16–0x31; the background, see below). The builder writes English in place and
sets the character count to the number of cells drawn. The label box is sized from the text (verified with 7 cells; the longest
Japanese label is 9).

How the game uses them (engine, read in save5's RAM): when a script switches
location, 0x800F9200 looks the id up in the record list (the scene's table
pointer is kept at 0x8011B518), copies the name into 0x8011C139 using the
character count, and 0x800EA994 later draws it into a texture at VRAM
(896, 368) through 0x8001D94C, which calls renderer A (patched) or B
(not patched) depending on the text mode. The third byte is not part of the
label: it selects the background picture (× 2,028-byte entries).

The label is drawn by 0x800EA630 only while a flag at 0x8011B5AA is set
and the scene state (0x8011C130) is not 0, 1, 11 or 15. The flag is set by
a script opcode (handler near 0x800E28D8) and, at 0x800EB6F0, while
controller bit 0x10 is held (Triangle in the usual PlayStation bit order),
**Verified on screen (experiment 11c): holding Triangle during a scene shows
the date box and a box with the place name** ("Station Plaza", drawn with
the English letter pairs; the box fits the text). Nothing shows when the
button isn't held, which is why the label was easy to miss.

Edits like these (and menu text inside overlays) are applied to the disc
data **before** scenes are rebuilt (`Builder.pre`), so a block or an
overlay that is relaid or moved carries them along.

## 14. Name entry (`tools/namepatch.py`, Disc 1; verified on screen)

The name-entry screen is its own module: Disc 1 sector 2038, loaded at
0x800C0000 (read from save9, taken on that screen). Its state is at
0x800F97B0 (0x334 bytes): surname at +0, given name at +7, both 7-byte
fields (3 full-width characters + NUL); field number at +0x1F8, cursor at
+0x1FC (next cell, 0..2; it stays at 2 when the field is full and the
next character replaces the last). On confirmation the fields are copied
with strcpy (0x8005A074) to the game state at 0x80075004 / 0x8007500B.

- Pages: かな and カナ are 18 rows of up to 5 characters each (pointer
  tables at 0x800CD984 and 0x800CD9CC; the "ー～" row is shared). 記号 is one
  453-character string (0x800C0500) that already includes full-width
  0-9, A-Z, a-z; its length is taken with strlen. 漢字 is a list of rows.
  The page tabs are pictures.
- Append: 0x800C8738 (fields 0 and 1 at 0x800C8804); backspace: 0x800C8590
  (fields 0 and 1 at 0x800C8644).

The patch (verified in Unicorn against a model, 24,000 random key presses,
and against the original routine for Japanese input):

- Latin letters (and - . ' space) are stored as letter pairs: a letter
  fills the right half of the last cell if it is empty, otherwise starts a
  new cell. A name holds 6 letters ("Kaitos" = `ab 5b c3 6e c9 6d`).
  Backspace removes one letter. Japanese characters behave as before.
- The routine (440 bytes) sits in the tail of the 記号 list, which is cut
  after ｚ (the page loses kana, Greek and Cyrillic).
- The かな page shows A-Z, a-z, - . ' (and blank cells, which type a space).

On screen (experiment 12): the grid, the name line, the confirmation box
and dialogue all draw the pairs. A name with an odd number of letters ends
in a blank half cell, so text after it has a small gap ("FIACR ちゃん").

**The nickname is the EVS name** (verified from the user's memory card):
the card holds an EVS file ("ときめきメモリアル２ ＥＶＳ 光 ふぃあくれい",
11 blocks, 90 KB) with the nickname as text ("ふぃあくん", file offset
0x21A) followed by a size table (0x280) and one girl's recorded voice data
(here Hikari's). The name-entry module copies the text from the loaded EVS
data into the game state (+0x32 and +0x41 of 0x80074FE0, at 0x800CA678 and
0x800CA694); saves carry it too. It is hiragana the voice system can say,
so it can't become free English. In dialogue it is printed by `{name3}`
(engine 0x800E3B20) and by some `{you:NN}` forms (0x800E3554, also +0x41);
no code compares it with the EVS data (the voice is chosen separately).

`tools/evsname.py` (with namepatch.py) sends both copies at 0x800CA678 /
0x800CA694 through a converter that writes romaji letter pairs (Hepburn,
simplified: きょ kyo, しゃ sha, ふぃ fi, っ doubles, ー repeats the vowel,
first letter capitalised, a final くん/ちゃん/さん hyphenated, at most 14
letters): "ふぃあくん" -> "Fia-kun". Verified in Unicorn against a Python
model on 20,000 kana strings (and two deliberate bugs were caught). The
converter (1 KB + its 344-byte table) replaces the kanji page's rows for
ま-わ readings, which are emptied. Only new games get it: saves keep the
nickname they were made with.

Not handled yet: and names typed on an unpatched disc or imported from another
game's save stay full-width.

### 14.1 The EVS reading screen (`tools/evsgrid.py`; on screen pending)

The EVS setup ("SOUND ROOM", "<name> の読み方") is another 0x800C0000
module: Disc 1 sector 1505, **obfuscated** (every byte +0x64, the first
byte dropped; it matches save10's RAM byte for byte after undoing that).
Its kana grid is 17 row strings at 0x800C03BC, listed by a table of 24-byte
entries at 0x800E6DA0 (string pointer first). The pick handler 0x800CB924
reads the character from the entry's string at 0x800CBA00 / 0x800CBA18 and
keeps it at 0x800FE8B8+0x16E. The voice needs kana, so the patch only
changes the labels: a copy of the rows with each kana as a romaji letter
pair (same size) goes to 0x800C0170, over unreferenced developer paths
("\t2\data\s_option\h64...tim"); the table points at the copy and the two
reads get +0x24C, so a pick still yields the kana. Two letters per cell:
si ti tu fu ji di du; the small kana, which change the cell before
them, show as -a -i -u -e -o ("fu" + "-i" = fi), -t (っ) and Ya Yu Yo
("ki" + "Ya" = kya). The large slots
showing the reading typed so far are drawn differently and stay kana.

## 15. Pictures (`tools/pictures.py`, `tools/lz1enc.py`, `tools/lz2enc.py`; verified on screen)

Labels drawn as pictures (buttons, stat names, titles) are textures. Found
for the name-entry buttons (save9):

- **Packets.** CDPACK holds streams of packets: 32-byte header (u32 type,
  u32 a, u32 b, 20 zero bytes) + payload. Types: 0x100 / 0x104 lz1 (8 / 16
  KiB out), 0x204 lz2 (16 KiB), 0x004 raw (also RAM data, a = RAM address).
  Disc 1 has about 1,700. Header `a` of a packet equals the previous
  packet's lz1 size + 8; the decoder stops at the payload's own u24 size.
- **To VRAM.** Decoded chunks are queued (EXE 0x8002E6F0: source pointer
  with the type in the top byte, RECT) and decoded / uploaded with LoadImage
  by 0x8002E7E8. A chunk is a block of VRAM rows: the buttons are packet
  73751:1416 (lz1, 8 KiB = 128 rows x 64 bytes), a 4-bit 128x128 texture
  at VRAM (960, 0) holding all six buttons.
- **Copies.** The packet above is not the copy the name-entry screen uses:
  the module embeds its own textures as bare lz1 streams (u24 size + 0 +
  stream) in its file, and the buttons on screen come from Disc 1 2067:952
  (found because patching only the packet changed nothing on screen,
  experiment 13). `pictures.py find --range` searches sectors for such
  streams; patch every copy that lands at the same VRAM position.
- **Palettes** are separate: the name-entry module keeps its CLUTs (at
  0x800CDEC4...) and uploads them to VRAM row 480 (x 464, 480, 496...); each
  button colour is its own CLUT over the same pixels.
- **Save states.** VRAM is at 0x201A5C of the decompressed DuckStation state
  (6 bytes before what earlier notes said: with that, CLUTs fall on
  multiples of 16 and the button texture on its texture-page boundary).

- **Image records.** Code modules also store textures as records: u32 2,
  u16 x, y, w, h (a rectangle, w in 16-bit units; x, y are 0 in the main-screen ones, so where it lands in VRAM is set elsewhere), then an lz2
  stream of w\*h\*2 bytes; the next record starts at the next 4-byte
  boundary. Disc 2 has about 1,150 (`all_records`, a few seconds per disc).
- **Main screen (Disc 2, save13/save14).** The texture the screen draws is
  a 4-bit 128x128 image record at VRAM (192,256), in two modules: Disc 2
  r11403:516 and r12419:1688 (lz2, 2,353 bytes). It holds the weekday
  kanji, 年, the date digits, the hand cursors, R1 and the nine stat
  labels. Packet 966:1472 (lz1) has the same glyphs and labels but no hands;
  it goes to VRAM (992,0) and is not what the main screen shows (experiment
  14 patched only it: English at (992,0), Japanese on screen). Found by
  comparing VRAM rows of save14 with the decoded packet, then searching the
  disc byte by byte for an lz2 stream decoding to the (192,256) rows. The
  labels (40x16 slots, ink colour + 1-px outline, 3 per row at y 80/96/112).
  The command icons have no text. 今日の予定 / -なし- are ordinary text
  (section 13). The date box builds 「5月16日(日)」 from these tiles; 月 and
  日 are also the Monday and Sunday tiles, so the date needs a layout
  change, not just new tiles (below).
- **Date box (`tools/datepatch.py`, experiment 16).** The main-screen
  module (Disc 2: code from sector 1643, the draw function at 0x800E9E5C)
  draws year, month, day and weekday with GsSortFastSprite on texture page
  0x1C (VRAM 768,256): digit d is tile u = (d % 5)\*16 + 48, v = (d / 5)\*16
  + 16; the weekday is tile u = weekday\*16, v = 0 at x -75 (the CLUT picks
  red / blue for Sunday, Saturday and holidays). The fixed 年 月 日 ( ) come
  from a table of 12-byte entries (s16 x, s16 y, u8 u, v, w, h, u32 flags,
  x relative to the box) at 0x80116A50 (Disc 2 1732:592; another copy at
  12418:1648 in a module without this code). The patch makes the weekday
  tiles Su..Sa, redraws the 年 tile as "/" and points 月 at it, points 年
  and 日 at an empty patch of the texture, moves ( ) and the weekday left
  and gives days a leading zero (the slti before the tens digit), giving
  "1999  5/16 (Su)". The month can't get a leading zero: its tens tile is
  fixed to "1".
- **File-select date (Disc 2, save15/save16).** A different screen and
  method: the digits are cells of the file-select module's sprite bank
  (codes 0x40-0x49 on the 966 texture, drawn by 0x80147D64 at x 0x153 + 12n,
  y 0x29), and 年 月 日 are baked into the screen's background art: packet
  968:1440 (pic-a256f52375, VRAM 640,0, CLUT 144,480; it also holds the
  ニュー / ロード buttons). `pictures/file_select_date.png` blanks 年 and 日
  and draws "/" in place of 月 (experiment 18). The module's strings
  「　　年　　月　　日」 and 「０１２３４５６７８９　年月日」 (ui-7e95f3e3fe,
  ui-4d6d47f7f4) are not what this screen shows: translating them changed
  nothing (experiment 17), so they are left untranslated for now.
- **File-select buttons (experiment 19).** ニュー ロード コピー クリア セーブ
  and セーブシステムヲツクリナオス are index-1 letters cut out of a per-row
  gradient in the screen's 4-bit background pieces (packets 967:1880,
  968:1440, 969:360, stream s966:152). `tools/art/file_select.py` restores the
  gradient and draws bold font_en capitals (NEW LOAD COPY ERASE SAVE,
  REBUILD SYSTEM FILE). The screen's messages, slot names ("File 1"), club
  names and girls' names are OV6 menu strings (`translations/_ui.json`).
- **Line breaks in menu strings.** The file-select prompts
  (「ロードを実行\nしますか？」 and 13 more) contain 0x0A,
  which the menu text routine takes as a new line; `uitext` now accepts it
  (and `encode` passes "\n" through), and also takes packed strings the code
  points at directly.
- **Title menu (Disc 2, save19).** ゲームスタート オプション ポケットステーション
  おまけ are two 4-bit 128x128 pictures side by side at VRAM (832,0) / (864,0):
  packets 728:1988 and 730:1820, CLUT (0,482). A long label is two POLY_FT4
  strips ("ゲームスタ" u 0-127 row 0 + "ート" u 0-39 row 1), and every label
  exists twice (rows 0-47 and 96-127, different shading). PUSH ANY START
  BUTTON is already English. `tools/art/title_menu.py` draws GAME START, OPTIONS,
  POCKETSTATION, EXTRAS (Poppins Medium, coloured row by row from the
  Japanese, 2-px shadow; experiment 21).
- **Inserted names and honorifics (`tools/strpack.py`, experiment 24).**
  `{char:NN}` (engine 0x800E3030) copies a name from the table at 0x80111588
  (3 pointers per character: surname, given name, nickname; which one, and
  whether さん or ちゃん (0x800C1424 / 0x800C142C) follows, depends on bits
  23-25 of the character's state word +0x64). `{you:NN}` (0x800E31B8) builds
  the player's name or nickname + さん / 君 / くん, or copies a pronoun
  (あなた キミ お前 貴様, fixed 7-byte copies). The name strings (engine
  0x800C132C-0x800C1424), the surname list (engine 0x800C04D4, table
  0x80110640), the given names in the EXE (0x8006C994, table 0x80063048) and
  the phone module's surnames (OV1 0x8013DE38, 32 lui + addiu pairs) are
  reached only through pointers or addiu immediates, so the builder packs the
  English into each block and repoints them. Honorifics are dropped
  (`{none}`), pronouns are "you", 「 (0x800C14D4) is "：".
- **Odd-length names** end in a letter + blank cell, so "Akane" is followed
  by a half-cell gap ("Akane ."); the same for the player's name. Fixing it
  needs the renderer to draw a final single letter as a half cell.
- **Save-state VRAM.** The VRAM's place in a decompressed DuckStation state
  varies: it follows the tag "GPU-VRAM" (0x201A5C in save12, 0x201DDC in
  save14). Earlier positions in this section that were read with the fixed
  offset are off by that difference for save14 (the main-screen texture is
  at 768,256, not 192,257; the lz1 packet at 544,0).

The tool finds which packets are in VRAM in a save state (`find`), exports
one as an indexed PNG with a palette from VRAM (`export --clut X,Y`), and
re-imports an edited PNG (`import`): indices are packed, compressed with
`lz1enc` (an optimal-parsing encoder for the game's format; it compresses
the buttons to 1,703 bytes where the original has 1,757) and written over
the old payload, which must not grow (a record may also use its
alignment padding). lz2 pictures are compressed with `lz2enc` (same idea;
the main-screen texture goes from 2,353 to 1,843 bytes). Packet and
record headers are left unchanged.

## 12. Next steps
0. UI text: check the romaji EVS nickname on screen (§14), the phone-book surnames (need repointing, §13.1), and the picture-only labels (§13).
1. Japanese words inserted by codes (`{you:NN}` honorifics/pronouns, `{char:NN}`
   names) live in the main-engine module's data: translate them with the
   module text (menus, name entry).
2. Room for the scenes that don't fit: find the table of scene sector
   numbers (needed to move a scene), and YGROUP01's container; until then
   translations must fit (the builder says by how much they don't).
3. The 10-px renderer B mode and where it is used; punctuation pauses for
   English (the pause rule only knows Shift-JIS 、。！？).
4. Find the remaining ~1.5% of text (extra entry points, `09 4E` records).
5. Per-character delay tables (§9.1); typing speed looked fine in
   experiment 4.
