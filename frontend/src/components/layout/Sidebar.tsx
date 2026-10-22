import { NavLink } from "react-router-dom";
import {
  BookMarked, Briefcase, Building2, CalendarClock, Calculator, ChevronsLeft, ChevronsRight, Files, Home, Landmark, LifeBuoy, ScanSearch, Search, StickyNote, Users,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { aagam } from "../../api/aagam";
import { usePreference } from "../../lib/theme";

type Link = { to: string; icon: typeof Home; label: string; end?: boolean; badge?: "work" | "due" };
const NAV: { heading: string; links: Link[] }[] = [
  {
    heading: "Desk",
    links: [
      { to: "/", icon: Home, label: "Home", end: true },
      { to: "/work", icon: Briefcase, label: "Work", badge: "work" },
      { to: "/due", icon: CalendarClock, label: "Due dates", badge: "due" },
      { to: "/notes", icon: StickyNote, label: "Notes" },
    ],
  },
  {
    heading: "Records",
    links: [
      { to: "/companies", icon: Building2, label: "Clients" },
      { to: "/library", icon: Files, label: "Library" },
      { to: "/search", icon: Search, label: "Search" },
      { to: "/precedents", icon: BookMarked, label: "Precedents" },
      { to: "/entities", icon: Users, label: "People & companies" },
    ],
  },
  {
    heading: "Analysis",
    links: [
      { to: "/insights", icon: ScanSearch, label: "Insights" },
      { to: "/financials", icon: Landmark, label: "Financials" },
      { to: "/calculators", icon: Calculator, label: "Calculators" },
    ],
  },
];

/** The scales, small: AAGAM's mark. */
export function Mark({ size = 28 }: { size?: number }) {
  return (
    <span className="rounded-lg bg-accent-brand text-on-accent flex items-center justify-center shadow-sm shrink-0" style={{ width: size, height: size }}>
      <svg viewBox="0 0 24 24" width={size * 0.66} height={size * 0.66} fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d="M12 4v15M8 20h8M5 7h14M12 4l.01 0" />
        <path d="M5 7l-2.5 6a2.5 2.5 0 0 0 5 0L5 7zM19 7l-2.5 6a2.5 2.5 0 0 0 5 0L19 7z" />
      </svg>
    </span>
  );
}

export default function Sidebar() {
  const [small, setSmall] = usePreference("aagam.sidebar.small", false);
  const { data } = useQuery({ queryKey: ["overview"], queryFn: aagam.overview, refetchInterval: 60_000 });
  const badges = {
    work: data?.works_open ? { n: data.works_open, alert: data.works.some((w) => w.due_on && w.due_on < new Date().toISOString().slice(0, 10)) } : null,
    due: data ? (() => { const late = data.due.filter((d) => d.state === "overdue").length; return late ? { n: late, alert: true } : null; })() : null,
  };

  return (
    <aside className={clsx("sidebar bg-bg-secondary/80 backdrop-blur border-r border-bg-border flex flex-col shrink-0 transition-[width] duration-300 relative z-20", small ? "w-[60px]" : "w-56")}>
      <div className={clsx("h-12 flex items-center gap-2.5 border-b border-bg-border", small ? "justify-center" : "px-4")}>
        <Mark />
        {!small && (
          <span className="leading-tight fade-in">
            <span className="block font-semibold tracking-[0.2em] text-[13px] text-text-primary">AAGAM</span>
            <span className="block text-[10px] text-text-muted tracking-wide">Company secretarial desk</span>
          </span>
        )}
      </div>

      <nav className="py-2 space-y-2 flex-1 overflow-auto">
        {NAV.map(({ heading, links }) => (
          <div key={heading}>
            {small ? <div className="mx-4 my-2 border-t border-bg-border" /> : <p className="px-4 pt-1.5 pb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-text-muted">{heading}</p>}
            {links.map(({ to, icon: Icon, label, end, badge }) => {
              const b = badge ? badges[badge] : null;
              return (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  title={small ? label : undefined}
                  className={({ isActive }) =>
                    clsx(
                      "relative mx-2 flex items-center gap-2.5 py-1.5 rounded-lg text-sm transition-colors group",
                      small ? "justify-center px-0" : "px-2.5",
                      isActive ? "bg-accent-brand/10 text-accent-brand font-medium" : "text-text-secondary hover:text-text-primary hover:bg-bg-hover"
                    )
                  }
                >
                  {({ isActive }) => (
                    <>
                      {isActive && <span className="absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-full bg-accent-brand grow-x" aria-hidden />}
                      <Icon size={16} className="shrink-0 transition-transform group-hover:scale-110" />
                      {!small && <span className="flex-1 truncate">{label}</span>}
                      {b && (small ? (
                        <span className={clsx("absolute top-1 right-2.5 w-2 h-2 rounded-full", b.alert ? "bg-accent-red" : "bg-accent-brand")} aria-label={`${b.n}`} />
                      ) : (
                        <span className={clsx("text-[10.5px] tabular rounded-full px-1.5 min-w-[18px] text-center font-semibold", b.alert ? "bg-accent-red/15 text-accent-red" : "bg-bg-hover text-text-secondary")}>{b.n}</span>
                      ))}
                    </>
                  )}
                </NavLink>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="border-t border-bg-border p-2 space-y-0.5">
        <NavLink
          to="/help"
          title={small ? "Help: what AAGAM does" : undefined}
          className={({ isActive }) => clsx("flex items-center gap-2.5 py-1.5 rounded-lg text-sm", small ? "justify-center" : "px-2.5",
            isActive ? "bg-accent-brand/10 text-accent-brand font-medium" : "text-text-secondary hover:text-text-primary hover:bg-bg-hover")}
        >
          <LifeBuoy size={16} /> {!small && "What AAGAM does"}
        </NavLink>
        <button
          onClick={() => setSmall(!small)}
          className={clsx("w-full flex items-center gap-2.5 py-1.5 rounded-lg text-xs text-text-muted hover:text-text-primary hover:bg-bg-hover", small ? "justify-center" : "px-2.5")}
          aria-label={small ? "Widen the sidebar" : "Narrow the sidebar"}
          title={small ? "Widen the sidebar" : undefined}
        >
          {small ? <ChevronsRight size={15} /> : <><ChevronsLeft size={15} /> Narrow</>}
        </button>
      </div>
    </aside>
  );
}
