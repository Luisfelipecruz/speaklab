# 0009 — Navigation, layout and the signed-in shell

**Status:** accepted · **Date:** 2026-09-06 · **Milestone:** m12

Read this before changing the frame, adding a section, moving a route, or touching
anything to do with width or the theme. It is the milestone that turned a stated minimum
into an interface, and four of the seven decisions below were left open on purpose by the
plan for this document to close.

---

## What was decided

1. **A sidebar, not a wider top bar.** Five sections, each carrying a fact about itself.
   It collapses to an icon rail; below `md` it is a sheet.
2. **`/` splits in two.** A public front door for a stranger; `/home` for somebody signed
   in, which becomes where signing in lands. The service-status table moves to `/status`
   and is not in the navigation.
3. **Width belongs to the page.** The shell imposes no maximum. Three named measures —
   `prose`, `wide`, `full` — and each page picks one.
4. **The `(app)` route group lands.** Four duplicated layouts become one. No URL changes.
5. **Dark mode ships.** The `.dark` block and the sidebar variables are now read. The
   class is set by a synchronous script in `<head>`, before first paint.
6. **No new runtime dependency.** `next-themes` was considered and is not installed; the
   `cn` package the component generator tried to add was removed.
7. **The shell is tested**, along with the two other components that had no test.

---

## 1. Why a rail, and why it carries numbers

The four sections were four text links in a row beside the wordmark, with no disclosure at
any width. That is not a navigation failure on its own — four links fit. It fails at the
thing a menu is for, which is telling you whether a section is worth opening.

A horizontal bar has room for names. A vertical one has room for a second column, and the
second column is what the product already knew and was not saying: how many conversations
are stored, how many readings have been scored, whether the progress figures are behind
the practice that produced them. Those three facts are the difference between a menu and a
dashboard you can navigate from.

They cost nothing extra to obtain. `GET /progress` reads materialised snapshots and
computes nothing, and the signed-in layout is a server component, so the counts are
fetched with the session cookie forwarded and are correct at first paint rather than one
round trip after it. **A count that needed its own request would have been dropped** — a
network call on every page in the product to decorate a menu is not a trade worth making.

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

`/` rendered no shell at all, so it had no navigation on it, and its content below the
introduction was a table of `asr`, `tts` and `pron` probes with a database latency. That
is a page for whoever runs the stack, and it was the first thing a learner saw.

Splitting it is two decisions, not one:

- **`/status` keeps the diagnostic**, reachable by typing the address and deliberately not
  in the rail. The person who wants it will look for it; nobody else needs a menu entry
  reminding them the stack has parts.
- **`/home` becomes where signing in lands.** `DEFAULT_AFTER_LOGIN` pointed at
  `/scenarios` — eight cards, none of which knows anything about the person looking at
  them — while everything needed to answer *how am I doing, and what should I do now* was
  already being computed and served. `/home` is assembled entirely from three responses
  that already existed. No API operation was added: the count stays at 25 of 30.

Its empty state is the first state and is designed rather than defaulted. A new account
has no trend, no recommendation worth the name and no history; three empty cards read as a
broken product, and "start here, and here is what each one does" reads as an instruction.

## 3. Width

`max-w-5xl` sat on both the header and `<main>`, so every screen was 1024 px at every
viewport. On a 2560 px display roughly 60 % of the screen was margin, and the page that
suffered most was the one with a heatmap of forty sounds across twelve weeks.

The fix is not a bigger number. Prose wants about 65 characters — a paragraph set 2400 px
wide is unreadable in the other direction, and a shell-wide maximum cannot be right for
both. So the shell imposes nothing and the page declares its own measure.

**Three named measures rather than a free value.** An open `max-w-*` on every page is how
a product ends up with eleven slightly different content widths that nobody chose. The
three are `prose` for text read in sequence, `wide` for lists, forms and transcripts, and
`full` for charts and grids. The test that protects this asserts they are three
*different* classes — a tidy-up that collapsed them to one would restore the old problem
while every page still read as though it had made a choice.

The progress page also stops being a single column: seven independent panels stacked
vertically inside 1024 px meant scrolling past four to reach the fifth, so they sit in two
columns from `xl` up. The phoneme trend stays full width, because it is one row per sound
and there can be forty of them.

## 4. The route group

Four `layout.tsx` files, four lines each, each wrapping `AppShell`, each with a comment
explaining that a route group would be tidier but would move every page to a path the
plan did not name. That objection was correct twice and stopped being correct when the
plan named the path.

`app/(app)/` replaces all four. The parentheses keep it out of the URL, so `/scenarios`,
`/read`, `/sessions` and `/progress` are exactly where they were — the build output
confirms it. What changed is a repository path, and the layout can now be a server
component that fetches the rail's facts once for every section rather than four
client-side wrappers that fetch nothing.

## 5. Dark mode: shipped, not deleted

`globals.css` carried a complete `.dark` block and sixteen sidebar variables. Nothing set
the class and nothing read a sidebar variable, so the eleven lines carrying `dark:`
utilities could never fire. Dead code that reads as a feature is worse than no feature,
and the plan required a decision either way.

It ships, because the sidebar this milestone introduces is the first thing in the
repository that reads those sixteen variables, so half the dead code stopped being dead on
its own — and deleting the other half to re-add it later is two changes to avoid one.

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

`next-themes` does what §5 describes and was not installed: the whole of it here is one
string, three functions and a menu, and a dependency whose job is to set one class is a
dependency to justify rather than to reach for.

Worth recording because it nearly went in unnoticed: running the component generator to
add the sidebar, sheet, menu, skeleton and tooltip primitives also **rewrote three
existing files' imports from `@/lib/utils` to a package called `cn`, and added that package
to `package.json`**. It was removed and the three files are byte-identical to what they
were. Generated source is still source, and the diff is the review.

## 7. What is tested, and one measurement worth knowing

The shell had no test from the day it was written, which is how it kept a header of four
links long after there were five places to go. `AppShell.test.tsx` covers the property the
milestone exists for — every section reachable from every other, at 1280 px and at 375 px
— plus `aria-current` on the current section, the sheet opening and closing on a phone, and
the claim the shell has made in a comment since it was written and nothing had checked:
that it renders its navigation while the session lookup is still in flight.

Two bugs were found by writing it and fixed here:

- **Two "Sign in" controls**, one in the rail's footer and one in the top bar. The rail's
  was removed; identity belongs to the top bar.
- **Focus was not returned when the mobile sheet closed.** A dialog restores focus to its
  own trigger, and this one is opened by a button outside it flipping a flag — so closing
  it dropped focus on `<body>` and returned a keyboard user to the top of the document.
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
noticing. **Anything that opens a popper in a test pays this**, and the frontend suite went
from 130 tests in about 2 s to 174 in 43–136 s across runs on a machine that was also
running Ollama and a virtual machine. The spread is that load; the floor is the popper, and
most of it is three menu openings. Worth a look if the suite
becomes something people stop running.
