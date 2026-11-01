import { redirect } from "next/navigation";

import { supabaseServer } from "@/lib/supabase";

export async function POST() {
  const supabase = await supabaseServer();
  await supabase.auth.signOut();
  redirect("/login");
}
