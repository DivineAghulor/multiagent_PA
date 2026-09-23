import { redirect } from "next/navigation";

export default function Home() {
  // The week screen is the daily home; everything else is reached from it.
  redirect("/week");
}
