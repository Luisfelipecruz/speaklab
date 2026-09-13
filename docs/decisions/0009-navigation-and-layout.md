# 0009 — Navigation, layout and the signed-in shell

Status: accepted · §3 superseded by [0010](0010-reading-the-interface.md)

Read this before changing the frame, adding a section, moving a route, or touching
anything to do with width or the theme.

---

## What was decided

1. **A sidebar, not a wider top bar.** Five sections, each carrying a fact about itself.
   It collapses to an icon rail; below `md` it is a sheet.
2. **`/` splits in two.** A public front door for a stranger; `/home` for somebody signed
   in, which is where signing in lands. The service-status table is at `/status` and is
   not in the navigation.
3. **Width** is one frame measure, set by [0010](0010-reading-the-interface.md) §1 and
   [0011](0011-contrast-gutters-and-the-font.md) §4 (§3).
4. **The `(app)` route group holds every signed-in page.** One layout, no URL of its own.
5. **Dark mode.** The `.dark` block and the sidebar variables are read. The class is set
   by a synchronous script in `<head>`, before first paint.
6. **No new runtime dependency.** `next-themes` is not installed, and neither is the `cn`
   package the component generator tries to add.
7. **The shell is tested**, along with the two other components that had no test.

---

## 1. Why a rail, and why it carries numbers

A menu's job is to tell you whether a section is worth opening. A horizontal bar has room
for names. A vertical one has room for a second column, and the second column is what the
product already knows: how many conversations are stored, how many readings have been
scored, whether the progress figures are behind the practice that produced them. Those
three facts are the difference between a menu and a dashboard you can navigate from.

They cost nothing extra to obtain. `GET /progress` reads materialised snapshots and
computes nothing, and the signed-in layout is a server component, so the counts are
fetched with the session cookie forwarded and are correct at first paint rather than one
round trip after it. **A count that needed its own request would be dropped** — a network
call on every page in the product to decorate a menu is not a trade worth making.

Two properties of the counts are deliberate and easy to lose:

- **They are absent, not zero, for a reader nobody has identified.** `facts` is null when
  the session lookup returns nothing, and "0 conversations" printed beside a sign-in
  prompt states something false about an account that was never looked up.
- **A failure degrades the rail and does not take the page down.** The layout catches, the
  rail loses its badges, and the page inside still reports its own trouble in its own
  words — which is more than a generic error boundary would say.

"Weeks with practice in them" is used where a streak would go. It is the closest thing the
system actually counts, and inventing a daily streak would mean a number on screen that no
stored row supports.

## 2. Why the front page split

A table of `asr`, `tts` and `pron` probes with a database latency is a page for whoever
runs the stack, not the first thing a learner should see. Splitting it is two decisions,
not one:

- **`/status` keeps the diagnostic**, reachable by typing the address and deliberately not
  in the rail. The person who wants it will look for it; nobody else needs a menu entry
  reminding them the stack has parts.
- **`/home` is where signing in lands.** A catalogue of scenario cards knows nothing about
  the person looking at them, while everything needed to answer *how am I doing, and what
  should I do now* is already computed and served. `/home` is assembled entirely from
  three responses that already exist, with no API operation of its own.

Its empty state is the first state and is designed rather than defaulted. A new account
has no trend, no recommendation worth the name and no history; three empty cards read as a
broken product, and "start here, and here is what each one does" reads as an instruction.

## 3. Width

Superseded by [0010](0010-reading-the-interface.md) §1: the frame is one measure — 72 rem,
by [0011](0011-contrast-gutters-and-the-font.md) §4 — and running text narrows itself
inside it.

The requirement that decision meets is this one: a frame fixed at 1024 px at every
viewport leaves roughly 60 % of a 2560 px display as margin, and the page that suffers
most is the one with a heatmap of forty sounds across twelve weeks, while prose wants
about 65 characters whatever the screen. A single width cannot be right for both.

The progress page is not a single column: seven independent panels stacked vertically meant
scrolling past four to reach the fifth, so they sit in two columns from `xl` up. The
phoneme trend stays full width, because it is one row per sound and there can be forty of
them.

## 4. The route group

`app/(app)/` holds one layout for every signed-in section. The parentheses keep it out of
the URL, so `/scenarios`, `/read`, `/sessions` and `/progress` are where they would be
without it — the build output confirms it. The layout is a server component that fetches
the rail's facts once for every section.

## 5. Dark mode: shipped, not deleted

`globals.css` carries a complete `.dark` block and sixteen sidebar variables, and the
sidebar reads those variables. Dead code that reads as a feature is worse than no feature,
so the block is used rather than deleted.

**The hard part is not the toggle, it is the first paint.** The stored choice lives in
`localStorage`, which the server cannot read. A theme applied from a React effect runs
after hydration, which for somebody who chose dark is a white flash on every single
navigation. So a synchronous script runs in `<head>` before anything paints, and `<html>`
carries `suppressHydrationWarning` because the attribute mismatch it produces is the
intended behaviour rather than a bug.

That leaves the same rule expressed twice — once as a string of source that runs before
any module exists, once as functions the toggle calls. **Two expressions of one rule drift
apart, and the drift is invisible**: the toggle keeps working, and only a reload comes back
wrong, which is the case nobody clicks through while making a change. `lib/theme.test.ts`
runs the string and compares the class it sets against the class the functions set, over
all six combinations of stored choice and system preference.

Three states, not two. "System" is the default and only an explicit choice is stored, so
choosing system *removes* the key rather than writing the word — storing it would freeze
today's answer for somebody whose machine later switched.

## 6. No new dependency, and one that had to be taken back out

`next-themes` does what §5 describes and is not installed: the whole of it here is one
string, three functions and a menu, and a dependency whose job is to set one class is a
dependency to justify rather than to reach for.

Running the component generator to add the sidebar, sheet, menu, skeleton and tooltip
primitives also **rewrites existing files' imports from `@/lib/utils` to a package called
`cn`, and adds that package to `package.json`**. That package is not in this repository,
and the imports are `@/lib/utils`. Generated source is still source, and the diff is the
review.

## 7. What is tested, and one measurement worth knowing

`AppShell.test.tsx` covers the property the shell exists for — every section reachable
from every other, at 1280 px and at 375 px — plus `aria-current` on the current section,
the sheet opening and closing on a phone, and that the shell renders its navigation while
the session lookup is still in flight.

It holds two fixes:

- **One "Sign in" control**, in the top bar. Identity belongs there, not also in the
  rail's footer.
- **Focus returns when the mobile sheet closes.** A dialog restores focus to its own
  trigger, and this one is opened by a button outside it flipping a flag — so closing it
  would drop focus on `<body>` and return a keyboard user to the top of the document.
  `NavigationTrigger` puts it back.

**The measurement, because it changes how tests here get written.** Opening any Radix
primitive built on the positioning library costs several seconds per open in jsdom, and it
is not the menu specifically — an open tooltip, which has neither a focus scope nor a
scroll lock, costs the same. What was ruled out: it is not the test body (render 38 ms,
unmount 12 ms, cleanup 1 ms), not an open handle, and not a long timer — a `setTimeout`
patched before the imports recorded nothing above 200 ms. The seconds pass *between* Jest's
hooks, with nothing of ours running in them, which points at work being drained through
React's scheduler rather than at anything this repository controls.

So the theme tests open the menu with the keyboard rather than with synthesised pointer
events. That is faster, and it is the path more likely to be broken without anybody
noticing. **Anything that opens a popper in a test pays this**: the frontend suite took
43–136 s for 174 tests across runs on a machine also running Ollama and a virtual machine,
against about 2 s for 130 tests with no popper opened. The spread is that load; the floor
is the popper, and most of it is three menu openings. Worth a look if the suite becomes
something people stop running.
