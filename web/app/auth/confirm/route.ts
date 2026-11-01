import { type EmailOtpType } from "@supabase/supabase-js";
import { redirect } from "next/navigation";
import { type NextRequest } from "next/server";

import { supabaseServer } from "@/lib/supabase";

/**
 * Lands the magic link. Verifies the one-time token, which sets the session
 * cookie, then forwards to the page that was originally asked for.
 */
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const token_hash = searchParams.get("token_hash");
  const type = searchParams.get("type") as EmailOtpType | null;
  const next = searchParams.get("next") ?? "/training";

  // Only ever redirect within this app: an open redirect here would be a
  // phishing vector carried by a link we ourselves emailed.
  const safeNext = next.startsWith("/") && !next.startsWith("//") ? next : "/training";

  if (!token_hash || !type) {
    redirect("/login?error=missing_token");
  }

  const supabase = await supabaseServer();
  const { error } = await supabase.auth.verifyOtp({ type, token_hash });

  if (error) {
    redirect("/login?error=invalid_or_expired");
  }

  redirect(safeNext);
}
