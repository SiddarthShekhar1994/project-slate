import type { Metadata } from "next";

export const metadata: Metadata = { title: "Progress" };

export default function Page() {
  return (
    <div className="mx-auto max-w-3xl">
      <p className="text-sm font-semibold text-accent-tint-text">Progress</p>
      <h1 className="mt-1 text-2xl font-bold">Progress</h1>
      <p className="mt-2 text-text-2">This page is being built next.</p>
    </div>
  );
}
