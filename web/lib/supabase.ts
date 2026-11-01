import { cookies } from "next/headers";
import { createServerClient } from "@supabase/ssr";

/**
 * Server-side Supabase client bound to the existing session cookie, so the
 * Training page uses the same auth as the rest of Mission Control.
 *
 * This deliberately uses the ANON key. Every table has RLS with a
 * `user_id = auth.uid()` policy, so the anon key plus the session cookie is
 * what scopes the data to Shyan. The service key never reaches the browser or
 * a request-scoped client; it lives only in GitHub Actions.
 */
export async function supabaseServer() {
  const cookieStore = await cookies();
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => cookieStore.getAll(),
        setAll: (toSet) => {
          try {
            toSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options),
            );
          } catch {
            // Called from a Server Component, where cookies are read-only.
            // Session refresh is handled by middleware.
          }
        },
      },
    },
  );
}
