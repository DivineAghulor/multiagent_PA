"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/cn";

const LINKS = [
  { href: "/week", label: "This week" },
  { href: "/tasks", label: "Tasks" },
  { href: "/planning", label: "Planning" },
  { href: "/projects", label: "Projects" },
  { href: "/reviews", label: "Reviews" },
];

export function Nav() {
  const pathname = usePathname();

  return (
    <nav className="flex flex-wrap gap-1">
      {LINKS.map((link) => {
        const active = pathname === link.href || pathname.startsWith(`${link.href}/`);
        return (
          <Link
            key={link.href}
            href={link.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
              active
                ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                : "text-neutral-600 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800",
            )}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
