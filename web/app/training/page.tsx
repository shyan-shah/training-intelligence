import { redirect } from "next/navigation";

import TrainingTabs from "@/components/TrainingTabs";
import { loadTrainingData } from "@/lib/queries";
import { supabaseServer } from "@/lib/supabase";

// Health data is per-user and changes nightly: never statically rendered and
// never cached.
export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function TrainingPage() {
  const sb = await supabaseServer();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) redirect("/login?next=/training");

  // 90 days is the default window; the in-page control widens it without a
  // refetch because the queries already pull the longer baseline history the
  // charts need.
  const data = await loadTrainingData(90);

  return (
    <main style={{ background: "var(--plane)", minHeight: "100dvh" }}>
      <TrainingTabs data={data} />
    </main>
  );
}
