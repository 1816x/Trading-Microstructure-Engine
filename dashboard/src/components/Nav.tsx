"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Metrics" },
  { href: "/journal", label: "Journal" },
] as const;

export function Nav() {
  const pathname = usePathname();
  return (
    <nav className="flex gap-4 text-sm">
      {LINKS.map(({ href, label }) => {
        const active = pathname === href;
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={active ? "font-medium text-ink" : "text-ink-2 hover:text-ink"}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
