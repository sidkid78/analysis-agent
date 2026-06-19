"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// The shared 62px icon rail used by every tab (Quick Data, Smart Dev, Infra).
export function Rail() {
  const pathname = usePathname();
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <div
      style={{
        width: 62,
        flex: "none",
        background: "var(--panel)",
        borderRight: "1px solid var(--line)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "14px 0",
      }}
    >
      <div
        style={{
          width: 30,
          height: 30,
          borderRadius: 9,
          background: "var(--accent)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          marginBottom: 24,
        }}
      >
        <div style={{ width: 11, height: 11, background: "var(--accent-ink)", transform: "rotate(45deg)", borderRadius: 2 }} />
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8, alignItems: "center" }}>
        <RailIcon href="/" title="Quick Data" active={isActive("/")}>
          {(c) => (
            <div style={{ display: "flex", alignItems: "flex-end", gap: 2.5 }}>
              <span style={{ width: 3, height: 8, background: c, borderRadius: 2 }} />
              <span style={{ width: 3, height: 14, background: c, borderRadius: 2 }} />
              <span style={{ width: 3, height: 11, background: c, borderRadius: 2 }} />
            </div>
          )}
        </RailIcon>
        <RailIcon href="/dev" title="Smart Dev" active={isActive("/dev")}>
          {(c) => (
            <span className="mono" style={{ color: c, fontSize: 14, fontWeight: 700 }}>
              &lt;/&gt;
            </span>
          )}
        </RailIcon>
        <RailIcon href="/infra" title="Infrastructure" active={isActive("/infra")}>
          {(c) => (
            <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
              <span style={{ width: 16, height: 4, background: c, borderRadius: 1.5 }} />
              <span style={{ width: 16, height: 4, background: c, borderRadius: 1.5 }} />
              <span style={{ width: 16, height: 4, background: c, borderRadius: 1.5 }} />
            </div>
          )}
        </RailIcon>
      </div>

      <div style={{ flex: 1 }} />
      <div
        style={{
          width: 30,
          height: 30,
          borderRadius: "50%",
          background: "var(--chip)",
          border: "1px solid var(--line)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 11,
          fontWeight: 600,
          color: "var(--ink-2)",
        }}
      >
        SK
      </div>
    </div>
  );
}

function RailIcon({
  href,
  title,
  active,
  children,
}: {
  href: string;
  title: string;
  active: boolean;
  children: (iconColor: string) => React.ReactNode;
}) {
  return (
    <Link
      href={href}
      title={title}
      style={{
        width: 40,
        height: 40,
        borderRadius: 11,
        background: active ? "var(--accent-tint)" : "transparent",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {children(active ? "var(--accent)" : "var(--ink-3)")}
    </Link>
  );
}
