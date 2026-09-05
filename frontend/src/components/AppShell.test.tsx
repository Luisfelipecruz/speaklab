/**
 * The frame, and the one property the whole milestone is about: you can get anywhere from
 * anywhere without typing an address.
 *
 * The shell went untested from the day it was written, which is how it kept a header of
 * four text links long after there were five places to go. The tests below are short
 * because most of them are that one property said at different widths and in different
 * session states.
 *
 * **The session states matter more than they look.** The shell renders around the thing
 * that knows who is signed in, so it is the component most able to blank a page while a
 * check is in flight — and "checking" is the state a returning visitor is in for the first
 * few hundred milliseconds of every single load.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AppShell } from "@/components/AppShell";
import type { ShellFacts } from "@/components/AppSidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthContext, type AuthStatus, type UseAuth } from "@/hooks/useAuth";
import { makeProfile } from "@/test/fixtures";

const push = jest.fn();
const refresh = jest.fn();
let pathname = "/home";

jest.mock("next/navigation", () => ({
  usePathname: () => pathname,
  useRouter: () => ({ push, refresh }),
}));

const SECTIONS = ["Home", "Scenarios", "Read aloud", "History", "Progress"];

function auth(status: AuthStatus, signOut = jest.fn()): UseAuth {
  return {
    user: status === "authenticated" ? makeProfile() : null,
    status,
    error: null,
    pending: false,
    signIn: jest.fn(),
    signUp: jest.fn(),
    signOut,
  };
}

function renderShell({
  status = "authenticated" as AuthStatus,
  facts = null as ShellFacts | null,
  signOut = jest.fn(),
} = {}) {
  return render(
    <AuthContext.Provider value={auth(status, signOut)}>
      <TooltipProvider>
        <AppShell facts={facts}>
          <p>page body</p>
        </AppShell>
      </TooltipProvider>
    </AuthContext.Provider>,
  );
}

beforeEach(() => {
  pathname = "/home";
  push.mockClear();
  refresh.mockClear();
  // The permanent rail is the desktop case. `useIsMobile` reads innerWidth, and jsdom
  // defaults to 1024, but stating it here stops one test's resize leaking into the next.
  window.innerWidth = 1280;
});

test("every section is one click away, whichever one you are on", () => {
  pathname = "/sessions/12";
  renderShell();

  const nav = screen.getByRole("navigation");
  for (const label of SECTIONS) {
    expect(within(nav).getByRole("link", { name: label })).toBeInTheDocument();
  }
});

test("the page is one main region, not two", () => {
  // The vendored `SidebarInset` is itself a `<main>`, so wrapping the page in another one
  // inside it is the easy mistake — nothing looks wrong and a screen reader is offered two
  // main regions to skip to.
  renderShell();

  expect(screen.getAllByRole("main")).toHaveLength(1);
});

test("the section you are in is marked for a screen reader, not only in colour", () => {
  pathname = "/sessions/12";
  renderShell();

  expect(screen.getByRole("link", { name: "History" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(screen.getByRole("link", { name: "Progress" })).not.toHaveAttribute(
    "aria-current",
  );
});

test("a deeper path still marks its section", () => {
  pathname = "/read/third-street-theatre";
  renderShell();

  expect(screen.getByRole("link", { name: "Read aloud" })).toHaveAttribute(
    "aria-current",
    "page",
  );
});

test("the navigation is there while the session check is still in flight", () => {
  // The claim the shell has made in a comment since it was written, and which nothing
  // checked: blanking the frame during the check would empty the page on every
  // navigation for somebody who is already signed in.
  renderShell({ status: "checking" });

  const nav = screen.getByRole("navigation");
  for (const label of SECTIONS) {
    expect(within(nav).getByRole("link", { name: label })).toBeInTheDocument();
  }
  expect(screen.getByText("page body")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /sign out/i })).not.toBeInTheDocument();
});

test("signing out clears the server-rendered pages behind it", async () => {
  const signOut = jest.fn().mockResolvedValue(undefined);
  renderShell({ signOut });

  await userEvent.click(screen.getByRole("button", { name: /sign out/i }));

  await waitFor(() => expect(signOut).toHaveBeenCalled());
  expect(push).toHaveBeenCalledWith("/login");
  // Without this the previous account's history stays on screen: those pages were
  // rendered on the server with the cookie that has just been thrown away.
  expect(refresh).toHaveBeenCalled();
});

test("a signed-out reader is offered the way in rather than a sign-out", () => {
  renderShell({ status: "anonymous" });

  expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  expect(screen.queryByRole("button", { name: /sign out/i })).not.toBeInTheDocument();
});

describe("on a phone", () => {
  beforeEach(() => {
    window.innerWidth = 375;
  });

  test("the navigation opens in a sheet, closes, and hands focus back", async () => {
    renderShell();

    // Off-canvas to start: practice happens on the device the microphone is in, and a
    // permanent rail at this width is most of the screen.
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();

    const trigger = screen.getByRole("button", { name: "Toggle navigation" });
    await userEvent.click(trigger);

    const sheet = await screen.findByRole("dialog");
    for (const label of SECTIONS) {
      expect(within(sheet).getByRole("link", { name: label })).toBeInTheDocument();
    }

    await userEvent.keyboard("{Escape}");

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    // Focus back on the control that opened it. Without this a keyboard user is returned
    // to the top of the document and has to walk the page again.
    expect(trigger).toHaveFocus();
  });

  test("following a link closes the sheet it was in", async () => {
    renderShell();

    await userEvent.click(screen.getByRole("button", { name: "Toggle navigation" }));
    const sheet = await screen.findByRole("dialog");
    await userEvent.click(within(sheet).getByRole("link", { name: "Progress" }));

    // Otherwise the sheet still covers the page the person has just navigated to.
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});

describe("what the rail says about each section", () => {
  const facts: ShellFacts = { sessions: 7, attempts: 3, periods: 2, stale: false };

  test("counts come from the practice, not from a second request", () => {
    renderShell({ facts });

    const nav = screen.getByRole("navigation");
    expect(within(nav).getByText("7")).toBeInTheDocument();
    expect(within(nav).getByText("3")).toBeInTheDocument();
    expect(
      screen.getByText(/2 weeks with practice in them, 7 conversations/),
    ).toBeInTheDocument();
  });

  test("figures known to be behind the practice are said to be", () => {
    renderShell({ facts: { ...facts, stale: true } });

    expect(screen.getByText("Progress figures are behind")).toBeInTheDocument();
  });

  test("a reader nobody has identified gets no counts at all", () => {
    // Not zeroes. "0 conversations" beside a sign-in prompt states something false about
    // an account that has not been looked up.
    renderShell({ status: "anonymous", facts: null });

    expect(screen.queryByText(/conversations/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "History" })).toBeInTheDocument();
  });
});
