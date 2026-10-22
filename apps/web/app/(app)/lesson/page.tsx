import { redirect } from "next/navigation";

/** Lessons live on each topic's page now; old links land there. */
export default async function Page({ searchParams }: PageProps<"/lesson">) {
  const { skill } = await searchParams;
  redirect(typeof skill === "string" && skill ? `/topics/${encodeURIComponent(skill)}?tab=lesson` : "/dashboard");
}
