# 0027 — A persona that answers the question asked, and counts that agree

Status: accepted

The letting agent's brief carries the facts a viewer asks for and tells the persona to give
a fact in its first sentence when it is asked for one, measured by a set of questions whose
answers are checked by arithmetic; the navigation rail's `History` badge counts the
conversations the History page lists; and a sentence the voice could not be reached for is
asked once more before a reply is handed over as text. This records why the fix for a
persona that dodges is in the brief and not in the rules every persona shares, how a dodge
is counted without a judge, why the badge stopped reading the trend window, and why the
retry is one.

## What was decided

1. **The brief carries the facts, and says to give them first.** The cover's exchange, and
   the second conversation behind it, show the letting agent answering "how much it cost
   every month?" with "an absolute steal at its current price point" — no figure. The
   brief told the persona to be slightly evasive and to answer about the deposit and the
   heating only when asked directly, and gave it nothing to answer with: no rent, no
   deposit, no date. A model given a role and no facts fills the gap with the role. The
   brief now states what Elena knows — rent, deposit, contract and break clause, size and
   floor, the date the flat is free, last winter's heating, the noise — and one rule: a
   direct question with a figure or a fact for its answer gets it in the first sentence,
   then the selling. The evasiveness stays; it applies to what was not asked.
2. **The rule lives in the brief, not in the shared guardrails.** Only this persona
   carries facts. A shared rule to "answer with the fact" would tell ten personas with
   no facts to produce one, and the other briefs have their own shapes — the interviewer
   who pushes for a number, the agent who offers the least convenient flight first — that
   the rule would cut across. Each brief that gains facts gains the rule with them.
3. **The facts are a list, so a spoken fact is not a quoted brief.** The deterministic
   leak check counts a run of six words shared with the brief. Facts written as prose —
   "it is free from the first of next month" — would make every honest answer a leak.
   They are written as `label: value` fragments, and the suite counts quoting on the
   question replies as well, so a false leak from a fact would show where it happens.
4. **A dodge is counted, not judged.** Seven questions to the letting agent, the cover's
   own first, each asked ten times in a scene one line long; a reply is checked for any
   figure — a digit or a number word, a date's ordinal included — and for the brief's
   figure, matched however it is written or spoken. Both are arithmetic, in the same
   module as the rest of the persona rules, and the drift test fails the day a question's
   figure leaves the seeded brief. The change ships only if every existing probe figure
   stays inside its documented range, and it did.
5. **The cover is not retaken.** The panel is a real run, and a run that shows the dodge
   is an honest run of the version it names. It is retaken when the owner asks.
6. **The `History` badge counts what the History page lists.** The badge read the progress
   totals' `sessions`, which is what the trend window rests on: sessions with turns in
   them, summed period by period, so a conversation older than thirty days dropped out and
   one spanning two weeks counted twice, and a conversation deleted since the rollup
   stayed counted. On the account behind the screens the badge read 1 beside a page
   listing none. The totals now also carry `conversations` — every conversation on the
   account, counted with the same predicate as the list — and the rail reads that. The
   window's count is untouched for the pages that describe the window. No second request:
   the rail still reads one response.
7. **One retry, after half a second, for a sentence the voice could not be reached for.**
   Seen once: a reply stored text-only, "The voice was unavailable", while `tts` reported
   healthy and logged no request — a connection the service never received. The reply
   was kept as text by design; losing its voice to one dropped connection was the cost. A
   sentence whose synthesis raised `TtsUnavailable` is asked once more after
   `TTS_RETRY_PAUSE_S`; a refusal is not retried, because the same text will be refused
   again; a second failure is reported as the first would have been, with both in the
   detail the turn carries. One retry, because the failure this covers clears in the time
   of one, and a voice that is down should hand the text over within the turn rather than
   after a series of pauses.

## Measured

- Before the brief carried the facts, `gemma4:e4b` answered the seven questions with any
  figure in **22 of 70** attempts and with the brief's figure in 3 (the contract, where
  "twelve months" is a common default); asked the cover's question, 4 of 10. After: any
  figure **70 of 70**, the brief's figure **70 of 70**, quoting the brief 0 of 70. Asked
  the cover's question once more on the live stack: "The rent for this beautiful flat is
  £1,450 a month, but honestly, you'll be so taken with everything else that it's a
  bargain!", in 723 ms.
- The existing probes, on the same two runs: 9 of 9 replies clean before and after; the
  persona gave its instructions away 3 then 4 of 150 (the range across runs is 2 to 14),
  stepped out of the scene 5 then 4 of 150 (4 to 10); the judge agreed with the hand
  labels on 8 of 10 both times, missing the same two.
- The account behind the screens: its snapshot counts one session with turns in the
  window — a conversation deleted after the take — so the badge read 1 beside a History
  page listing none. Read from the account's conversations, it reads nothing, as the page
  does.

## Costs

- **The letting agent is the one persona with facts.** Asked for a figure, the other ten
  still have nothing to give; the questions measure one brief. The other briefs gain facts
  when a reader shows them dodging.
- **A failing voice costs half a second more per sentence** before the reply goes out as
  text: one pause, then the same detail as before.
- **The persona suite makes 70 more model calls**, five to six minutes instead of three.

## Revisit if

- A second persona is seen answering a direct question with no fact in it: give that brief
  its facts and its questions, the same way.
- The retry is seen firing on a healthy voice more than once in a session's log: the
  failure is then not a dropped connection and needs its own cause found.
- A reader wants the cover to show the answered question: retake it from a run of this
  version.
