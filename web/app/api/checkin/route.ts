import { NextResponse } from "next/server";

import { supabaseServer } from "@/lib/supabase";

/** Ranges mirror the CHECK constraints in 0001_init.sql and the validation in
 *  the MCP tool, so a check-in cannot be written out of range by any path. */
const RANGES: Record<string, [number, number]> = {
  soreness: [1, 5],
  energy: [1, 5],
  mood: [1, 5],
  niggle_pain: [0, 10],
};

export async function POST(request: Request) {
  const sb = await supabaseServer();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) return NextResponse.json({ error: "Not signed in" }, { status: 401 });

  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Body must be JSON" }, { status: 400 });
  }

  const row: Record<string, unknown> = {
    user_id: user.id,
    day: typeof body.day === "string" ? body.day : new Date().toISOString().slice(0, 10),
  };

  for (const [field, [lo, hi]] of Object.entries(RANGES)) {
    const value = body[field];
    if (value === undefined || value === null) continue;
    const n = Number(value);
    if (!Number.isInteger(n) || n < lo || n > hi) {
      return NextResponse.json(
        { error: `${field} must be an integer between ${lo} and ${hi}` },
        { status: 400 },
      );
    }
    row[field] = n;
  }

  if (typeof body.niggle_area === "string") row.niggle_area = body.niggle_area.slice(0, 120);
  if (typeof body.notes === "string") row.notes = body.notes.slice(0, 2000);

  const { error } = await sb.from("daily_checkin").upsert(row, { onConflict: "user_id,day" });
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  return NextResponse.json({ written: true, day: row.day });
}
