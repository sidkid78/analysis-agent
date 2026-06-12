"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Quick Data" },
  { href: "/dev", label: "Smart Dev" },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <nav className="flex items-center gap-1 border-b border-black/10 px-6 py-2 dark:border-white/10">
      <span className="mr-3 text-sm font-semibold tracking-tight">⚡ Workbench</span>
      {LINKS.map((l) => {
        const active = pathname === l.href;
        return (
          <Link
            key={l.href}
            href={l.href}
            className={`rounded-md px-3 py-1.5 text-sm transition ${
              active
                ? "bg-indigo-600 text-white"
                : "text-zinc-600 hover:bg-black/[.04] dark:text-zinc-300 dark:hover:bg-white/5"
            }`}
          >
            {l.label}
          </Link>
        );
      })}
    </nav>
  );
}
