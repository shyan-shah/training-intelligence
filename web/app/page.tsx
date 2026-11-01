import { redirect } from "next/navigation";

/** The app is the Training page. The manifest's start_url points straight at
 *  it, but a bare domain visit should land somewhere too. */
export default function Home() {
  redirect("/training");
}
