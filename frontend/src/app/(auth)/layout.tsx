/**
 * The frame both auth screens share.
 *
 * `(auth)` is a route group: the parentheses keep it out of the URL, so these render at
 * `/login` and `/register` rather than `/auth/login`. The group exists for this layout —
 * a centred single column that the rest of the application will not have once there is a
 * navigation shell to sit inside.
 */

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-6 py-12">
      <div className="w-full max-w-sm">{children}</div>
    </main>
  );
}
