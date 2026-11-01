"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";

import { supabaseBrowser } from "@/lib/supabase-browser";

/**
 * Magic-link sign in. No password, because there is one user and a password
 * is one more thing to leak.
 *
 * `shouldCreateUser: false` is the access control: a stranger who guesses the
 * URL and submits their own address gets nothing, because Supabase will not
 * create an account for them. RLS is the second line, not the only one.
 */
function LoginForm() {
  const params = useSearchParams();
  const next = params.get("next") ?? "/training";

  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setStatus("sending");
    setMessage(null);

    const supabase = supabaseBrowser();
    const redirectTo =
      `${window.location.origin}/auth/confirm?next=${encodeURIComponent(next)}`;

    const { error } = await supabase.auth.signInWithOtp({
      email: email.trim(),
      options: { emailRedirectTo: redirectTo, shouldCreateUser: false },
    });

    if (error) {
      setStatus("error");
      setMessage(error.message);
      return;
    }
    setStatus("sent");
  }

  return (
    <main
      className="flex min-h-[100dvh] items-center justify-center px-5"
      style={{ background: "var(--plane)" }}
    >
      <div className="panel w-full max-w-sm p-6">
        <div className="eyebrow">Training Intelligence</div>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Sign in</h1>

        {status === "sent" ? (
          <p className="mt-4 text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
            Check your email. The link signs you in on this device and lasts long
            enough that an installed app rarely asks again.
          </p>
        ) : (
          <form onSubmit={submit} className="mt-5 space-y-3">
            <label className="block">
              <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
                Email
              </span>
              <input
                type="email"
                required
                autoComplete="email"
                inputMode="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1.5 w-full rounded-xl px-3 py-2.5 text-sm outline-none"
                style={{
                  background: "var(--surface-sunken)",
                  border: "1px solid var(--border-hairline)",
                  color: "var(--text-primary)",
                }}
              />
            </label>

            <button
              type="submit"
              disabled={status === "sending"}
              className="press w-full rounded-xl px-3 py-2.5 text-sm font-semibold text-white disabled:opacity-60"
              style={{ background: "var(--accent)" }}
            >
              {status === "sending" ? "Sending" : "Email me a link"}
            </button>

            {message && (
              <p className="text-[11px]" style={{ color: "var(--status-critical)" }}>
                {message}
              </p>
            )}
          </form>
        )}
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
