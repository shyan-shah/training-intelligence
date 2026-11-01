import { NextResponse } from "next/server";

import { supabaseServer } from "@/lib/supabase";

const MAX_BYTES = 10 * 1024 * 1024;

/**
 * Accepts an Evolt PDF, stores it in the private `evolt-scans` bucket under
 * the owner's uid, and queues it for parsing.
 *
 * Parsing itself happens in Python (ingest/evolt.py), because pdfplumber has
 * no JavaScript equivalent worth trusting and the validation rules must not
 * exist in two languages. This route stores the file and writes a placeholder
 * row; the nightly job fills in the values. That keeps one parser, one set of
 * range checks, and one definition of what a valid scan is.
 */
export async function POST(request: Request) {
  const sb = await supabaseServer();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) return NextResponse.json({ error: "Not signed in" }, { status: 401 });

  const form = await request.formData();
  const file = form.get("file");
  if (!(file instanceof File)) {
    return NextResponse.json({ error: "No file supplied" }, { status: 400 });
  }
  if (file.type !== "application/pdf") {
    return NextResponse.json({ error: "Only PDF scans are accepted" }, { status: 415 });
  }
  if (file.size > MAX_BYTES) {
    return NextResponse.json({ error: "File is larger than 10MB" }, { status: 413 });
  }

  // First path segment must be the uid: the storage policy checks it.
  const path = `${user.id}/${Date.now()}-${file.name.replace(/[^\w.-]/g, "_")}`;

  const { error: upErr } = await sb.storage
    .from("evolt-scans")
    .upload(path, file, { contentType: "application/pdf", upsert: false });
  if (upErr) return NextResponse.json({ error: upErr.message }, { status: 500 });

  const { error: rowErr } = await sb.from("evolt_scans").insert({
    user_id: user.id,
    scanned_at: new Date().toISOString(),
    pdf_path: path,
    parse_method: "pending",
    needs_review: true,
    review_reason: "Uploaded, awaiting parse by the nightly job",
    conditions: Object.fromEntries(
      ["time_of_day", "fasted", "hydration"]
        .map((k) => [k, form.get(k)])
        .filter(([, v]) => v !== null),
    ),
  });
  if (rowErr) return NextResponse.json({ error: rowErr.message }, { status: 500 });

  return NextResponse.json({
    stored: true,
    path,
    needs_review: true,
    review_reason: "Uploaded, awaiting parse by the nightly job",
  });
}
