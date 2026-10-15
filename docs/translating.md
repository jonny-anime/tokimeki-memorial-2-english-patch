# Translating Tokimeki Memorial 2

You don't need to know anything about the game's internals. The
translation is JSON files in `translations/`, with the Japanese next to the
English; `patch.py` builds the English discs from them. The README's
"Helping improve the translation" is the short version of this page.

## Setup (once)

You need Python 3.10 or newer and, to build and test, your own five disc
images (BIN/CUE, "Rev 1").

```
py -m pip install -r requirements.txt
```

## The translation files

`translations/<character>/disc<N>.json` hold the scenes where that girl
talks most, by the first disc they're on; `others/`, `childhood.json`,
`phone_calls.json`, `endings.json` and `misc.json` the rest;
`menus.json` the menus and system text; `speaker_names.json` the speaker
labels. A scene can be moved to another file: the tools only go by its
`key`.

```json
{"key": "G200000-0be95c9a", "location": "Shoe Lockers / Hallway / Classroom / Main Gate", "kind": "file", "room": 248, "found": {"2": [69080]},
 "messages": [
  {"at": [1325, 1337, 1346], "speaker": "Hikari", "speaker_ja": "陽ノ下",
   "ja": "あっ、{nobreak}\n{you:12}。\n私も帰るところだよ。",
   "en": "Oh, {nobreak}\n{you:12}.\nI'm just heading home too."}]}
```

- One **message** is one text box; `\n` separates its lines, and each line
  normally starts a new row. The English needs exactly as many lines as
  the Japanese: one per number in `at` (the byte offsets of the lines in
  the scene).
- Fill in `"en"` only. An empty `"en"` keeps the Japanese.
- Don't touch `key`, `at`, `ja` or the `{codes}`' spelling.
- `room`: how many bytes the scene's English may add to the Japanese, all
  messages together (1 letter = 1 byte, a Japanese character 2, English
  speaker labels count too). `kind` `packed` scenes have `room` 0: their
  English must not be longer than the Japanese. `found` is where the scene
  is: disc number and sector.
- Speaker labels: `speaker` is only for reading. Names are translated once,
  in `speaker_names.json` (`"陽ノ下": "Hikari"`), and fit 6 letters before
  the 「.

## What you can type

- Letters, digits, space and `. , ! ? ' " - ~ …` are drawn in the English
  font, two letters per cell.
- Any other character (♪, ♥, Japanese) is drawn as one full-width cell, and
  a letter left over before it is paired with a space.

## Codes

Codes are written in braces, exactly as in the `"ja"` text. Keep them where
the English needs them; you may move or drop them.

| code | what the game puts there | notes |
|---|---|---|
| `{name1}` | the player's given name | as entered at the start (currently katakana) |
| `{name2}` | the player's nickname | |
| `{name3}` | a third name (rare) | |
| `{you:11}` … `{you:1C}` | how character N addresses the player, e.g. `{you:12}` = Hikari's "カレイ君" | the game picks name or nickname plus a Japanese honorific (さん/ちゃん/君/くん) or a pronoun (あなた/キミ/お前/貴様) by relationship. Those words are still Japanese for now. |
| `{char:20}` … `{char:2D}` | a character's name | e.g. the girls' names in "meet X at …" lines |
| `{char2E:49}`, `{char2F:4A}` … | a character's name chosen by the game's state | |
| `{num8:80}` etc. | a number (month, day, count …) | |
| `{nobreak}` | **at the end of a line**: the next line continues on the same row | e.g. a greeting split from a name: "Oh,{nobreak}" + " Karei." |

## Room and width

- A row holds **20 cells = about 40 letters** (an inserted name counts as
  about 4 cells). The game wraps longer rows itself, possibly mid-word; the
  builder warns about them.
- A text box has 4 rows; the first one starts after the speaker label.
- English may be longer than the Japanese, but each scene has a limited
  amount of spare room on the disc. Most main-game scenes (about 90%) take
  a translation of up to 1.5 times the Japanese length. The builder tells
  you which scenes don't fit and by how many bytes (1 letter = 1 byte).
  Some scenes (phone calls, the walk-home choice, the childhood free
  roaming) can't grow at all yet.

## Menus and system text

`translations/menus.json` holds the text outside the scenes (menus, file screens,
names, clubs, holidays, the phone book and its profiles, date places, and
the place labels of scenes), one entry per Japanese string:

```json
"ui-0b6c2f9a1d": {"ja": "振動設定", "en": "Vibration", "max_bytes": 15, "where": ["2:OV5@8013dd54"]}
```

- Fill in `"en"`; it replaces that Japanese everywhere it occurs. The same
  word used in two places (e.g. 遊園地 as a date choice and as a scene
  label) is one entry, limited by the smaller field.
- It must fit `max_bytes`. Letters go two to a byte pair, so a text takes
  its letter count rounded up to even ("Hikari Hinomoto", 15 letters, takes
  16 bytes); a full-width character takes 2. There is no wrapping; the
  builder rejects anything longer. Characters the font doesn't have
  (`: / ( )` …) are drawn as their full-width form and take 2 bytes each.
- Lists whose entries are padded to the same width (the phone book, the
  profiles, the date places, Option Room values) are drawn at exactly that
  width: `max_bytes` is the Japanese width (2 letters per Japanese
  character) and shorter English is padded with blanks. Some boxes are
  narrower still: the date-place list shows about 14 letters.
- `where` tells you where it is: `2:OV1@8013de14` is overlay 1 (phone book)
  on Disc 2; `2:SCENE:G132000-06496ae2@0000037c` is a place label in that scene.
- No `{codes}` here. Some labels are cut off by the screen layout (e.g. an
  icon panel covers part of the Option Room), so short is better.
- Names inserted by `{char:NN}` and `{you:NN}`, and the surname and given-name
  lists, are ordinary entries here (光 → Hikari, 水無月 → Minazuki). Their
  `max_bytes` is too small, but the builder repacks these tables
  (`tools/strpack.py`), so any length that fits the table as a whole works;
  it says so if a table overflows. `"{none}"` makes a string empty: the
  honorifics さん ちゃん 君 くん are `{none}` (dropped), the pronouns あなた キミ
  お前 貴様 are "you", and the speech mark 「 is "：".
- Labels that are pictures (stat names, the date box, screen titles) are not
  in this file. The phone book's surname list can't take English yet (its
  fields are 3–7 bytes).

## Pictures

Some labels are pictures (buttons, stat names, titles). Edited ones live in
`pictures/` with a manifest, `pictures/pictures.json`, and the builder puts
them in automatically. To do a new one:

1. Make a DuckStation save state with the picture on screen.
2. `py tools/pictures.py find <disc.bin> <state.sav>` lists the stored
   pictures that are in video memory (add `--range FIRST,LAST` to search a
   block of sectors, e.g. a code module, for pictures stored without a
   packet header: bare lz1 streams and image records). Note every copy at
   the same VRAM position. If an edit doesn't show, the screen draws
   another copy: compare the state's VRAM with the picture.
3. `py tools/pictures.py export <disc.bin> <state.sav> <chunk> out.png --clut X,Y`
   writes a PNG in the game's colours (X,Y = the palette's place in VRAM).
4. Edit it in an editor that keeps palette indices (indexed PNG; no new
   colours, same size).
5. Copy it to `pictures/` and add an entry to `pictures.json` with the key
   `find` printed, the PNG name and the locations (`"at"`: chunk names,
   or `"packets"` / `"records"` for every copy of that kind on the disc).

The edited picture must compress to no more than the original; the builder
says so if it doesn't.

The pictures made so far were drawn by scripts, not by hand: `tools/art/`
holds one module per screen and `py tools/make_pictures.py --disc1 …
--disc2 …` remakes every PNG from your own discs (`--check` compares
with the committed ones). A new scripted picture is a recipe in
`make_pictures.py`. The title-menu font is Poppins Medium
(`tools/art/fonts/`, SIL Open Font License).

## Checking your work

```
py tools/check_translations.py                                 # everything
py tools/check_translations.py translations/miyuki/disc2.json  # one file
```

lists, by file, scene and line (`G407000-6ddcedd5/1588`: the scene key and
the line's `at`), what would break or look wrong: a message whose English
has a different number of lines than the Japanese, unknown `{codes}`, codes
of the Japanese that went missing, a scene that grows by more than its
`room`, rows wider than 20 cells, boxes that would need more than 4 rows,
speaker labels over 6 letters, typographic quotes and dashes (’ “ — are
not in the font), menu text over `max_bytes`. It takes seconds and needs
no disc; `--disc "path/to/Disc 2.bin"` measures the room on your discs
instead, and `--json` writes the list for scripts. ERRORs must be fixed;
WARNs are worth a look. The last line counts how much is translated.

## Machine translation (first drafts)

`tools/mt.py` sends the workbooks to an LLM API (Claude, OpenAI or Gemini)
and gets English back that already passes the checker as far as possible.
It is for first drafts and for comparing models; a person should still read
the result in the game.

Setup, once:

1. Put your API keys in `.env` in the repository root (git-ignored, never
   commit it):
   ```
   CLAUDE_KEY=...
   OPENAI_KEY=...
   GEMINI_KEY=...
   ```
   Only the providers you use need a key.
2. Check `mt/models.json`: the model ids, their prices (US$ per million
   tokens; check them on the providers' pricing pages) and options such as
   reasoning effort, which are passed to the API as written (`extra`).
3. `py tools/mt.py ping` sends each model a one-line request and shows
   whether the key and options work, what it cost and how long it took.

The tools work on one file per scene (workbooks) in `work/` (git-ignored),
made from `translations/`:

```
py tools/translations.py unpack work/tl
```

Run:

```
py tools/mt.py run work/tl --run pilot --scenes mt/pilot.txt --estimate
py tools/mt.py run work/tl --run pilot --scenes mt/pilot.txt --models opus,astra,argon
py tools/mt.py compare pilot
```

- `--estimate` prints a rough cost and sends nothing.
- `--scenes` is a file of scene keys, one per line (`mt/pilot.txt` is a
  sample of 9 Disc 2 scenes); `--all` takes every workbook in the folder.
- Each request carries `mt/prompt.md` (the translation brief: style, names,
  codes, room) and one or more scenes as JSON. Edit the brief to change the
  style; `mt/names.json` tells the model who each speaker label is.
- With each scene go notes on the characters in it (`mt/characters.json`:
  who they are and how they talk, from Japanese fan wikis and from counts of
  pronouns and sentence endings in the script; a character is included when
  she speaks or a `{char:2N}` / `{you:1N}` code names her), where the scene
  takes place (its `location`), and for a long scene cut
  into parts, the messages just before each part. Repair requests carry the
  whole scene with its English so far, and only the messages with problems
  are rewritten.
- Every reply is checked like `check_translations.py` does. Messages with
  problems (too wide, a code missing, a character the font lacks, a phone
  call longer than the Japanese) go back to the model with the problems
  listed, up to `--repairs` times (default 2).
- `--fallback MODEL` hands what is still wrong after that to a second model
  (with the problems listed, up to `--fallback-rounds` times, default 2).
  The project's setup is Gemini 4 Argon for everything and Claude Opus 5.5
  for what Argon can't get right:
  `--models argon --fallback opus`. Each scene file records which messages
  came from the fallback ("mt": {"fallback": ...}), the compare page marks
  them, and the summary counts its cost separately.
- `--budget` (optional, off by default) is in US$ per model and run: a model stops starting new
  requests when it has spent that much. `--jobs` (default 4) requests run
  at once per model.
- Results go to `work/mt/<run>/<model>/` (one workbook per scene, with the
  English and any problems left, a `log.jsonl` of every request and a
  `summary.json`). Replies are cached in `work/mt/cache/`: running the same
  command again costs nothing, and a run stopped by the budget or an error
  picks up where it was. Changing the brief or a model's options makes new
  requests.

Scene size limits: some scenes can only grow so much (the event module
that loads a main-game scene reads it into a buffer of a fixed size;
phone calls and other packed scenes can't grow at all). `unpack` writes
each scene's `room` to `work/tl/_limits.json` and `mt.py run` picks it up:
a scene whose English would not fit goes back to the model to be shortened
(its request also says how much room there is when it is tight).
`tools/limits.py work/tl/_limits.json "Disc 1.bin" ... "Disc 5.bin"`
measures the limits on the discs again.

`compare` writes `work/mt/<run>/compare.html`: the Japanese next to each
model's English, the models labelled A, B, C in random order. Pick the best
version of each scene, then "Reveal models" shows which is which with the
picks, the problems left, cost and the cost projected to the whole folder.
The page contains the game's text, so keep it to yourself.

To use a model's English:

```
py tools/mt.py apply work/mt/pilot/opus work/tl
py tools/translations.py pack work/tl
```

`apply` fills the empty `"en"` of the workbooks (`--overwrite` replaces
existing English too, including corrections people made: use it only on
scenes nobody has edited); `pack` writes them back into `translations/`
(each scene stays in its file). Then check and build as usual.

## Build and test

```
py patch.py "path/to/your/discs" -f
```

builds every disc it finds into `<game> [English]/` next to them (give one
`.cue` to build only that disc). `tools/build_patch.py <original.bin>
<out.bin> [--tl DIR]` builds one image wherever you want it. Scenes that
don't fit or whose line count is wrong are listed as `NOT PATCHED` and stay
Japanese; everything else is still written.

Open the `.m3u` (or a `.cue`) in DuckStation. Save states made with the
original disc bring the original back when loaded: load the state, then
use System → Change Disc to switch to the English image, and make a new
state.

## Sharing your work

Commit your changes to `translations/` and send a pull request. Never
commit `work/`, disc images or screenshots.

## Making the files from your discs

`translations/` was made from the discs; if a tool change finds more text,
make it again:

```
py tools/translations.py init work/tl "path/to/Disc 1.bin" ... "path/to/Disc 5.bin"
py tools/limits.py work/tl/_limits.json "path/to/Disc 1.bin" ... "path/to/Disc 5.bin"
py tools/translations.py pack work/tl
```

`init` writes a workbook per scene with the English of `translations/`
filled in; `pack` puts new scenes in the file of the girl who talks most
and leaves the others where they are. It says if old files are left over.
