import { redirect } from "next/navigation";

/** Practice lives on each topic's page now. */
export default function PracticePage() {
  redirect("/dashboard");
}
