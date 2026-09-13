# 0010 — Reading the interface: measure, type scale, and one family at a time

Status: accepted · supersedes §3 of [0009](0009-navigation-and-layout.md) · §1's value superseded by [0011](0011-contrast-gutters-and-the-font.md) §4

This is what came back from putting a person in front of [0009](0009-navigation-and-layout.md)'s
frame. Three of the four findings correct decisions 0009 made deliberately: each was
reasoned, and each was wrong in a way that is only visible once the pages are on a screen
together.

## What was decided

1. **One measure for every screen**, with a narrower column that running text opts into.
2. **The type scale moves up one step at the small end**, where the entire product lives.
3. **The progress page shows one metric family at a time**, with the section in the URL.
4. **A series with one measured period is a reading, not a chart.**
5. **The page is one `main` landmark**, not two.

---

## 1. Width: the frame stopped moving

Per-page measures — three named widths each page chose from — give a product whose content
box changes size on every navigation. Measured at a 1440 px viewport:

| Route | Container |
|---|---|
| `/scenarios`, `/read` | 1120 px |
| `/sessions`, `/sessions/[id]` | 1024 px |
| `/scenarios/[slug]`, `/home`, `/status` | 768 px |

Three left edges. Going from the catalogue to a scenario to the history moves the page
under the pointer twice, which reads as three products rather than one — and three chosen
widths are enough to cause the problem a rule against "eleven slightly different content
widths that nobody chose" is about.

The requirement behind per-page widths is real — a paragraph and a heatmap of forty sounds
do not want the same room — and it is met at the level it should be. **The frame is one
measure. Running text narrows itself with `Prose`, inside a page whose size does not
change.** A paragraph gets its 70 characters; the card above it stays where it was. The
measure is 72 rem ([0011](0011-contrast-gutters-and-the-font.md) §4).

**Revisit if** a single screen genuinely cannot work at this measure. The answer then is a
wider `Prose` sibling for that content, not a second page width.

## 2. The type scale

Almost nothing here is set in `text-base`. Cards, tables, captions and the navigation are
all `text-sm` or `text-xs`, so those two sizes *are* the application. Counted on
`/scenarios` at the old scale: of 76 leaf text nodes, **56 were 12 px** and 10 were 14 px.
A scenario card's entire content — level, category, target grammar — was 12 px. The period
figures under a trend chart, which are the thing a learner came for, were 11 px.

The scale is redefined once, in `globals.css`, rather than at a hundred call sites:
`text-xs` 12 → 13 px, `text-sm` 14 → 15 px, `text-base` 16 → 17 px, `text-lg` 18 → 19 px.
The names keep their meanings — a page still says `text-sm` and still means body copy —
and what changes is what body copy measures. There are no hand-written `text-[10px]` or
`text-[11px]` literals; a size small enough to need escaping the scale is a sign the scale
is wrong.

The vendored shadcn primitives are left alone, including the `size="sm"` button at
0.8 rem. Editing them is drift from upstream for a control that is chrome.

## 3. One family at a time

Four metric families on one page is eleven series, and on the corpus this was measured
against — 2 conversations, 2 scored readings, one calendar day — **every one of the eleven
held a single measurement**. The page was eleven 320×72 boxes each with one dot in the
middle, some fifty date/value pairs at 11 px, and two families gated off with a paragraph
of explanation each. It read as a control panel, not as an answer to "how am I doing".

Families are independent by construction: a fluency trend says nothing about an accuracy
trend. There is nothing to compare across them, so there is no reason to put them on one
screen and every reason not to. Each is its own section — 5, 1, 3 and 0 readings
respectively on that corpus — and breadth sits with the family it qualifies rather than
floating beside it, because a narrowing range of forms lowers an error rate without
anybody improving and the two only mean something read together.

**The overview is an answer, not a contents page.** Practice totals as figures large
enough to read, what to practise next, and one line per family saying whether it has
anything to show yet — counted from the same points the charts draw, so it cannot
disagree with them.

**Sections are links, not a tab widget.** The state lives in the URL, so a section can be
shared and reached with the back button, the server renders only the one being looked at,
and it works before any JavaScript arrives. `nav` with `aria-current`, not
`role="tablist"` — the ARIA tab pattern promises arrow-key movement between panels, and
these are separate addresses.

## 4. One period is a reading

A chart with a single point is the shape of a chart that failed to load. The same number
set large, with the week it came from and the sentence "a line needs a second week with
practice in it", says more in less room and is honest about being one measurement.

This is not a special case grafted on — it is the same principle the rest of the page is
built on. [0007](0007-progress-metrics.md) gates a series that cannot be drawn and says what
it is waiting for. A one-point series passes that gate and then fails to communicate
anyway, which is the gap this closes.

## 5. Two main landmarks

The vendored `SidebarInset` is itself a `<main>`, so the shell renders no other inside it:
a screen reader offered two main regions finds neither is the page. A test asserts there
is one.

---

## What this is measured against, and what it is not

Every figure above was counted against the running stack: the container widths and font
sizes by measuring the live DOM at 375, 1440 and 2560 px, the eleven single-point series by
fetching `/progress` for the one account with real practice on it.

`/progress` was verified by reading the server-rendered HTML — element counts per section,
not pixels. The layout, the type scale and the landmark were verified visually; the tab row
and the reading blocks were not.
