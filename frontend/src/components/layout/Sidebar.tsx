import { NavLink } from "react-router";
import { MaterialIcon } from "../shared/MaterialIcon";

interface NavItem {
  to: string;
  icon: string;
  label: string;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", icon: "sensors", label: "INTERCEPT_FEED" },
  { to: "/infrastructure", icon: "router", label: "INFRASTRUCTURE" },
{ to: "/labelling", icon: "label_important", label: "LABELLING" },
  { to: "/attribution", icon: "hub", label: "ATTRIBUTION" },
  { to: "/graph", icon: "account_tree", label: "AFFILIATION_GRAPH" },
  { to: "/archive", icon: "inventory_2", label: "SIGNAL_ARCHIVE" },
  { to: "/terminal", icon: "terminal", label: "TERMINAL_LOG" },
];

const BASE_NAV_CLASS =
  "flex items-center gap-3 px-4 py-3 text-sm font-label text-on-surface/40 border-l-4 border-transparent hover:text-primary-container/80 hover:bg-surface-container hover:translate-x-1 transition-all";

const ACTIVE_NAV_CLASS =
  "bg-surface-container-high text-primary-container border-l-4 border-primary-container";

export function Sidebar() {
  return (
    <aside className="fixed left-0 top-16 bottom-0 w-64 z-40 bg-surface-container-low flex flex-col">
      {/* Node identity block */}
      <div className="px-4 py-4 border-b border-outline-variant/20">
        <p className="font-mono text-[10px] text-outline uppercase">NODE_01_DASHBOARD</p>
        <p className="font-mono text-[9px] text-outline/50 mt-0.5">
          LAT: 51.4902 // LNG: -0.0146
        </p>
      </div>

      {/* Primary navigation */}
      <nav className="flex-1 py-2">
        {NAV_ITEMS.map(({ to, icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              isActive ? `${BASE_NAV_CLASS} ${ACTIVE_NAV_CLASS}` : BASE_NAV_CLASS
            }
          >
            <MaterialIcon name={icon} />
            {label}
          </NavLink>
        ))}

        <div className="px-4 mt-4">
          <button className="w-full bg-primary text-on-primary font-label uppercase tracking-widest text-xs py-3 hover:glow-primary transition-all active:scale-95">
            EXECUTE_SCAN
          </button>
        </div>
      </nav>

      {/* Bottom system actions */}
      <div className="px-4 py-4 border-t border-outline-variant/20 flex items-center gap-4">
        <button className="flex items-center gap-1.5 font-mono text-[10px] text-outline/40 hover:text-on-surface transition-colors">
          <MaterialIcon name="logout" className="text-sm" />
          LOG_OFF
        </button>
        <button className="flex items-center gap-1.5 font-mono text-[10px] text-outline/40 hover:text-on-surface transition-colors">
          <MaterialIcon name="restart_alt" className="text-sm" />
          REBOOT_SYSTEM
        </button>
      </div>
    </aside>
  );
}
