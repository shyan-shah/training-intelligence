import { notFound } from "next/navigation";

import TrainingTabs from "@/components/TrainingTabs";

import { FIXTURES } from "./fixtures";

/**
 * Design preview. Renders the real page against fixture data so the layout can
 * be reviewed without a database or a signed-in session.
 *
 * Disabled in production: health data aside, this route would otherwise show
 * invented numbers that look real.
 */
export const dynamic = "force-dynamic";

export default function PreviewPage() {
  if (process.env.NODE_ENV === "production" && process.env.ENABLE_PREVIEW !== "1") {
    notFound();
  }
  return (
    <main style={{ background: "var(--plane)", minHeight: "100dvh" }}>
      <TrainingTabs data={FIXTURES} />
    </main>
  );
}
