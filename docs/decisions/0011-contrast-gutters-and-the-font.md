# 0011 — Contrast, gutters, and the font that was never loading

Status: accepted · 2026-09-06 · supersedes §1 of
[0010](0010-reading-the-interface.md)

0010 corrected three of 0009's decisions after a person looked at the frame. This records
what came back from the second look, and it is less flattering than the first: the person
said the improvements were not visible. Three complaints, all correct, and a fourth thing
found while measuring the first one that explains why nothing had looked right.

## What was decided

1. **The application font was falling back to the browser's serif on every page**, and now
   is not.
2. **The palette has a hue in it.** Three surfaces that are three surfaces, one accent that
   means "act here", and grey text that passes.
3. **One gutter, on the shell, the same on every section.**
4. **The measure is 72 rem, not 96**, and things with one line in them are as wide as that
   line.
5. **The shared card gets a border and a hairline shadow**, which is the one vendored
   primitive this changes.

---

## 1. The font

`next/font` puts the loaded family into a CSS variable through a class, and the layout put
that class on `<body>`. globals.css applied `font-sans` — which resolves to
`var(--font-sans)` — on `<html>`. A custom property is visible to the element that sets it
and to its descendants, never to its parent, so on `<html>` the lookup failed, the
declaration was dropped, and the computed family was the browser's default. Measured in
the live DOM before the change:

```
getComputedStyle(document.body).fontFamily  →  "Times New Roman"
```

Every screen in the product had been rendering in Times New Roman since the first layout
was written. It is the kind of bug that does not look like a bug: the page has a font, the
font is legible, and nobody says "this looks like a serif" — they say it does not look
like an application, which is what was said. The class moves to `<html>`; the same
expression now returns `Geist, "Geist Fallback"`.

## 2. The palette

The generated theme was pure grey. Every token had zero chroma; page and card were both
white; the rail was two per cent off white; the five chart colours were five greys, the
first of them at 87 % lightness. Measured against WCAG's formula:

| Before | Contrast |
|---|---|
| Muted text on white | 4.73:1 |
| `chart-1` on a white card | 1.48:1 |
| Card border on white | 1.26:1 |
| Rail against the page | 1.04:1 |

The muted text technically passed and everything else was invisible. The replacement is
three moves, and each token belongs to one of them.

**Three surfaces.** The page is a cool off-white, the card is white with a visible border
and a hairline shadow, the rail is a shade darker than the page. A card now reads as a
thing rather than as a region of the page with a faint line round it.

**One accent.** Teal, used for exactly the things that mean "act here" or "this is the
measurement": the primary button, the current section, an active filter, the line on a
trend chart and the bar on a repertoire row. Everything else stays neutral, so the accent
is a signal and not decoration.

**Three greys for text**, not two: foreground near-black with a little blue in it, muted
dark enough to clear 4.5:1 with room, borders a third and lighter step.

| After | Contrast |
|---|---|
| Foreground on the page | 16.70:1 |
| Muted text on a card | 7.12:1 |
| Button text on the accent | 5.23:1 |
| `chart-1` on a card | 4.34:1 |
| Dark mode, foreground on the page | 17.03:1 |
| Dark mode, muted text on a card | 7.07:1 |

Dark mode is the same three surfaces inverted, with the accent lightened enough to carry
dark text. The five chart colours are teal, amber, indigo, rose and green, separable from
each other in both modes, and none of them is grey.

## 3. The gutter

The shell padded the content with 16, 24 or 32 px depending on the breakpoint, which at
desktop widths put the first card 32 px from the rail and 32 px from the window edge. The
complaint was that there was no space around the content, and that whatever space there
was should be the same on every section. It now is by construction: one constant on the
shell, `px-5 sm:px-8 lg:px-12 2xl:px-16`, shared by the top bar so the navigation control,
the title and the first card start on one vertical line; a test renders two sections and
asserts the wrapper is the same class string on both. The status page, which sits outside
the shell on purpose, uses the same values by hand.

## 4. The measure, and things with one line in them

0010 §1 set the frame at 96 rem so a scenario grid could use a large display. What it did
at 1440 px was let a one-line sign-in notice, a card holding four small figures, a list of
five links and a tab row's grey track each stretch to the full 1120 px of the frame with
nothing in their right-hand two thirds. That is what "components that display nothing but
occupy an entire row" describes, and it is exact.

The frame is 72 rem, which a three-column grid still fills. Inside it, a notice is as wide
as its text (`w-fit`, capped at 42 rem); the tab row is `inline-flex`; the four figures are
four tiles in a grid rather than four numbers in one card; the sittings and readings lists
are one card with a rule between rows rather than a card per row; and the empty-state
cards cap themselves at 42 rem. Nothing is wide because it had nowhere to stop.

**Revisit if** a screen genuinely cannot work at 72 rem. The answer then is still a wider
sibling for that content, not a second frame.

## 5. The card

`ui/card.tsx` is vendored, and 0010 §2 left the vendored primitives alone. This changes one:
the card's `ring-1 ring-foreground/10` becomes `border border-border shadow-xs`, and its
title goes from medium to semibold weight. The ring at ten per cent of near-black is the
1.26:1 border in the table above, and no amount of token tuning reaches it because it is
not a token. A border that reads the theme's `--border` is what makes the card follow the
palette in both modes, and the shadow is what separates it from the page in light mode
where the border alone is subtle. It is drift from upstream, and it is the one place the
drift buys something a token could not.

---

## What this is measured against, and what it is not

The font family and the container geometry were measured in the live DOM; the contrast
figures are computed from the token values with WCAG's relative-luminance formula. The
signed-in pages were looked at, in both modes, at 375, 1440 and 1920 px, with a fresh
account that has no practice on it — the browser this time ran on the host, which can
reach the API, so the shell was seen signed in with its footer and sign-out where they
belong.

**What has still not been seen is a page with real practice on it.** The account that has
practice cannot be signed into from here, so the stat tiles with non-zero figures, a trend
chart with a line and its fill, the repertoire bars and the sound-by-sound panel have been
rendered by tests and not by eye. Somebody with that account should open `/home` and
`/progress` and look.
