/**
 * One session for the whole application.
 *
 * The provider exists because several components have to agree on one copy of the
 * session, and the failure it prevents is quiet: two consumers each with their own copy
 * means two `GET /auth/me` calls on load and a sign-out that empties one of them while the
 * other still renders an email address. Neither shows up as an exception, which is exactly
 * why it is worth a test.
 *
 * The other half is the throw. `useAuth` outside a provider raises rather than falling
 * back to a private copy, because a silent fallback rebuilds the bug the provider removed.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AuthProvider } from "@/components/AuthProvider";
import { useAuth } from "@/hooks/useAuth";
import { makeProfile } from "@/test/fixtures";

jest.mock("@/lib/auth", () => ({
  ApiError: class extends Error {},
  fetchMe: jest.fn(),
  login: jest.fn(),
  logout: jest.fn(),
  register: jest.fn(),
}));

import { fetchMe, logout } from "@/lib/auth";

const mockFetchMe = fetchMe as jest.MockedFunction<typeof fetchMe>;
const mockLogout = logout as jest.MockedFunction<typeof logout>;

function Consumer({ name }: { name: string }) {
  const { user, status, signOut } = useAuth();
  return (
    <div>
      <span data-testid={`${name}-status`}>{status}</span>
      <span data-testid={`${name}-user`}>{user?.email ?? "nobody"}</span>
      <button onClick={() => void signOut()}>sign out from {name}</button>
    </div>
  );
}

beforeEach(() => {
  jest.clearAllMocks();
  mockFetchMe.mockResolvedValue(makeProfile());
  mockLogout.mockResolvedValue(undefined);
});

test("two consumers share one session and one lookup", async () => {
  render(
    <AuthProvider>
      <Consumer name="header" />
      <Consumer name="page" />
    </AuthProvider>,
  );

  await waitFor(() =>
    expect(screen.getByTestId("header-status")).toHaveTextContent("authenticated"),
  );
  expect(screen.getByTestId("page-user")).toHaveTextContent("someone@example.com");

  // The count is the point. A hook-per-consumer version asks the API once per consumer,
  // on every screen.
  expect(mockFetchMe).toHaveBeenCalledTimes(1);
});

test("signing out from one consumer empties the other", async () => {
  render(
    <AuthProvider>
      <Consumer name="header" />
      <Consumer name="page" />
    </AuthProvider>,
  );

  await waitFor(() =>
    expect(screen.getByTestId("page-user")).toHaveTextContent("someone@example.com"),
  );

  await userEvent.click(screen.getByRole("button", { name: "sign out from header" }));

  await waitFor(() => expect(screen.getByTestId("page-user")).toHaveTextContent("nobody"));
  expect(screen.getByTestId("header-user")).toHaveTextContent("nobody");
});

test("a session check that fails is reported as anonymous, not as signed in", async () => {
  mockFetchMe.mockRejectedValue(new Error("the API is down"));

  render(
    <AuthProvider>
      <Consumer name="page" />
    </AuthProvider>,
  );

  await waitFor(() =>
    expect(screen.getByTestId("page-status")).toHaveTextContent("anonymous"),
  );
  expect(screen.getByTestId("page-user")).toHaveTextContent("nobody");
});

test("using the session outside a provider throws instead of inventing one", () => {
  // React logs the error it is about to rethrow; the console is silenced so a passing
  // test does not print a stack trace that looks like a failure.
  const errors = jest.spyOn(console, "error").mockImplementation(() => {});

  expect(() => render(<Consumer name="orphan" />)).toThrow(
    "useAuth must be used inside <AuthProvider>",
  );

  errors.mockRestore();
});
