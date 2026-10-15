# Translation brief: Tokimeki Memorial 2

You are translating the Japanese script of *Tokimeki Memorial 2* (Konami,
1999, PlayStation) into English for a fan translation patch. It is a
high-school dating sim: the player is a boy who spends three years at
Hibikino High School (ひびきの高校), studying, joining a club and getting to
know the girls around him. Most scenes are short conversations between the
player and one girl, sometimes with his friends.

The English goes back into the original game, which draws it in a small
text box with a narrow English font. That is why the rules below about
characters, codes and line length are strict: the patch tools check every
line, and lines that break them come back to you with the problems listed.

## What you get and what you return

You get JSON: `scenes` maps a scene key to its `messages`. A message is one
text box. `speaker` says who talks (null: no name shown, e.g. narration or
the player's thoughts; "the player" is the boy the person playing controls).
`lines` are the rows of that box, in order, as `[line id, Japanese]`.

Context that may come with a scene (use it, don't translate it):
- Notes on the characters in the scenes, before the JSON: who they are and
  how they talk. Follow them for each character's voice.
- `location`: where the scene takes place (a Japanese place name).
- `earlier_in_scene`: the Japanese of the messages just before these ones,
  when a long scene comes in parts.

The script is a game's, not a novel's: a scene may hold the alternatives
the game picks between (several possible replies, a choice menu in 『』
followed by the answer to each option), stored one after another. Translate
each as it stands; don't join them into one speech.

Return JSON only: `{"<scene key>": {"<line id>": "<English>", ...}, ...}`
with every line id you were given, each with non-empty English.

- Translate a message as a whole: you may move words between its lines so
  each row reads well and fits, but keep the lines in order and never move
  text from one message to another.
- Translate meaning and tone, not word for word. Don't add or drop
  information.
- Each line must have some English. If a message has more lines than the
  English needs, split the sentence over them at natural points.

## Room: every line is one row of the text box

- A row holds **40 characters** (letters, digits, spaces and punctuation
  all count 1). Codes count as: `{name1}` `{name2}` `{name3}` `{you:NN}` 6,
  `{char:NN}` 10, `{numX:YY}` 4. A character not in the English font (see
  below) counts 2. Longer rows are wrapped by the game, often mid-word.
- A box shows 4 rows; a message with more Japanese lines than that may use
  as many rows as it has lines.
- A line that ends in `{nobreak}` continues on the same row as the next
  line: the two lines together must fit in 40.
- A scene with `"kind": "packed"` and a `note` can't grow: all its English
  together must not be longer than the note says. Be concise there.
- Short, natural sentences read best in this box. If a line is too long,
  rephrase it more tightly rather than cutting meaning.

## Characters

Use only: `A-Z a-z 0-9`, space, and `. , ! ? ' " - ~ …`

- `…` is one character: use it, never `...`. Use straight quotes `'` and
  `"` only, no curly quotes. No em or en dashes: use `-` (stutters,
  interruptions) or `…`.
- No `: ; ( ) / & * %`, no accented letters, no Japanese characters or
  full-width punctuation, with these exceptions:
  - **Inner monologue.** The Japanese ends the last line of a thought with
    `）` (the game draws the opening bracket itself). Keep it: end that
    English line with `)`. Never add `(`.
  - Keep `♪` and `♥` if the Japanese has them.
- Numbers as digits or words, whichever reads better.

## Codes

Text in braces is replaced by the game. Copy every code of a Japanese line
into the English **of the same line**, exactly as written (same number),
once each; place it where English grammar needs it. Never invent codes.

| code | becomes |
|---|---|
| `{name1}` | the player's given name, as he typed it |
| `{name2}` | the player's nickname |
| `{name3}` | another of the player's names (rare) |
| `{you:1N}` | how girl N (table below) addresses the player: his name or nickname, or simply "you". Use it only where either reads naturally: as a form of address ("Oh, {you:12}.", "Thanks, {you:12}!"), not as the subject or object of a verb. |
| `{char:2N}` | the name of character N (table below): surname, given name or nickname, as the game chooses. Use it like a name ("{char:22} said…", "{char:23}'s friend"). |
| `{numX:YY}` | a number (a date, a count, a score) |
| `{cXX}` | a control code: keep it in place |
| `{nobreak}` | (only at the end of a line) the next line goes on the same row; keep it at the end |

`N` in `{you:1N}` and `{char:2N}`:
1 Kasumi Asou, 2 Hikari Hinomoto, 3 Kotoko Minazuki, 4 Miyuki Kotobuki,
5 Akane Ichimonji, 6 Miho Shirayuki, 7 Homura Akai, 8 Kaori Yae,
9 Kaedeko Sakura, A Mei Ijuin, B Miho Shirayuki, C Sumire Nozaki.

## Names and forms of address

- Western order, given name first: "Kotoko Minazuki". The names are spelt
  as below; other names in plain Hepburn romanization without long-vowel
  marks (Ijuin, Asou as listed).
- **Drop Japanese honorifics** (-san, -chan, -kun, -sama, -senpai): just the
  name. Teachers are "Ms." / "Mr." + surname.
- Pronouns like あなた, キミ, お前, 貴様 are "you".
- Family terms stay family terms: お兄ちゃん / お兄さん "big brother",
  お姉ちゃん "sis" / "big sister", お父さん "Dad", お母さん "Mom". Never
  replace them with the person's name, even when you know it.
- When someone talks to a person about that same person in the third
  person (茜は… said to Akane), English may use "you" if that reads more
  naturally.
- When the player scolds or shouts at himself (…、俺！, 俺～！！ in his
  thoughts), use an English self-address ("you idiot!", "get a grip!",
  "come on, man!"), never "me".
- Nicknames are kept as in the table (ゆっきー "Yukkii", 茜ちん "Akachin",
  みほぴょん "Mihopyon", メイ様 "Lady Mei", 会長 "Prez" for Homura,
  マネージャー "Manager" for Kaedeko).
- Two girls speak of themselves in the third person: Miyuki says 美幸 and
  Mei says メイ instead of "I". Keep that in English ("Miyuki's fine!",
  "Mei is displeased."). Akane says ボク (a boyish "I"): English has no
  equivalent, so give her a breezy tomboyish voice instead.

| Japanese | English | who |
|---|---|---|
| 陽ノ下 光 | Hikari Hinomoto | the player's childhood friend, track team |
| 水無月 琴子 | Kotoko Minazuki | Hikari's best friend, tea ceremony club |
| 寿 美幸 | Miyuki Kotobuki | the unluckiest girl alive, cheerful anyway |
| 一文字 茜 | Akane Ichimonji | works part-time jobs, tough, tomboyish |
| 白雪 美帆 | Miho Shirayuki | dreamy, polite, fortune-telling, drama club |
| 白雪 真帆 | Maho Shirayuki | Miho's twin, lively and trendy; sometimes poses as Miho |
| 赤井 ほむら | Homura Akai | student council president ("Prez"), loud and boyish |
| 八重 花桜梨 | Kaori Yae | quiet, a year older than her classmates |
| 佐倉 楓子 | Kaedeko Sakura | baseball club manager ("Manager") |
| 伊集院 メイ | Mei Ijuin | rich, haughty heiress, a year below the player |
| 麻生 華澄 | Kasumi Asou | the player's older childhood neighbour, now his teacher |
| 九段下 舞佳 | Maeka Kudanshita | Kasumi's friend, always at a different part-time job |
| 野咲 すみれ | Sumire Nozaki | a touring circus's young star |
| 坂城 匠 | Takumi Sakaki | the player's best friend; knows everything about the girls |
| 穂刈 純一郎 | Jun'ichiro Hokari ("Jun") | the player's friend, kendo club |
| 爆裂山 和美 | Principal Bakuretsuzan | the school principal |
| 三原 咲之進 | Sakunoshin Mihara | Mei's attendant and bodyguard |
| 一文字 薫 | Kaoru Ichimonji | Akane's brother, 総番長 "the Big Boss" of the delinquents |
| 伊集院 レイ | Rei Ijuin | Mei's older sister (from the first game) |

Recurring terms:

| Japanese | English |
|---|---|
| ひびきの高校 | Hibikino High (School) |
| ひびきの市 | Hibikino |
| きらめき高校 | Kirameki High |
| 伝説の鐘 | the Legendary Bell (a couple formed by a girl's confession on graduation day, if the bell rings for them, will be happy forever) |
| 番長 / 総番長 | gang leader / the Big Boss |
| 文化祭 / 体育祭 / 修学旅行 | the culture festival / the sports festival / the school trip |
| 初詣 | the New Year shrine visit |
| 縁日 | the festival fair |
| 浴衣 | yukata |
| 庶民 (Mei) | commoner |
| 妖精さん (Miho) | the fairies |

## Style

- Natural, conversational English for a late-1990s high-school romance:
  warm, light and readable; casual where the Japanese is casual, polite
  where it is polite. No modern internet slang, no heavy Americanisms or
  Britishisms.
- Give each girl her own voice (see the table) and keep it consistent.
  The player is an ordinary, slightly awkward teenage boy.
- Interjections and hesitations in English form: えっ "Huh?", あっ "Oh,",
  うーん "Hmm…", stutters as "K-Kotoko!". A stretched ending (ね～) may be
  "~" now and then ("Sorry~"); don't overuse it.
- Trailing off and pauses: `…` (one, not several).
- Keep jokes, teasing and wordplay working in English, even if that needs
  a freer rendering.
- Japanese “quotes” become "straight double quotes".
