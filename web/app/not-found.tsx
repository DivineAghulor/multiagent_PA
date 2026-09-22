import Link from "next/link";

export default function NotFound() {
  return (
    <div className="py-16 text-center">
      <p className="text-sm font-medium">That page doesn&apos;t exist.</p>
      <Link href="/week" className="mt-2 inline-block text-sm text-blue-700 underline dark:text-blue-400">
        Back to this week
      </Link>
    </div>
  );
}
