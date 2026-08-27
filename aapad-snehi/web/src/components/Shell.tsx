import {
  Activity,
  BellRing,
  BookOpen,
  Camera,
  ChevronRight,
  HandHeart,
  LayoutDashboard,
  Map,
  Menu,
  Radio,
  Search,
  ShieldCheck,
  X,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { APP_ROUTES } from "../routes";

const navItems = [
  { href: APP_ROUTES.operations, label: "Operations", icon: LayoutDashboard },
  { href: APP_ROUTES.map, label: "Risk map", icon: Map },
  { href: APP_ROUTES.users, label: "Users", icon: Camera },
  { href: APP_ROUTES.volunteers, label: "Volunteers", icon: HandHeart },
  { href: APP_ROUTES.safety, label: "Disaster Safety", icon: BookOpen },
  { href: APP_ROUTES.admin, label: "Admin", icon: ShieldCheck },
  { href: APP_ROUTES.blueskyHelpers, label: "Bluesky helpers", icon: Search },
  { href: APP_ROUTES.pipeline, label: "Pipeline", icon: Activity },
];

interface ShellProps {
  children: ReactNode;
  path: string;
  navigate: (path: string) => void;
  connection: "api" | "demo";
  loading: boolean;
}

export function Shell({ children, path, navigate, connection, loading }: ShellProps) {
  const [mobileOpen, setMobileOpen] = useState(false);

  const go = (href: string) => {
    navigate(href);
    setMobileOpen(false);
  };

  return (
    <div className="app-shell">
      <header className="site-header">
        <div className="header-inner">
          <button className="brand" type="button" onClick={() => go("/")} aria-label="AapadSnehi home">
            <span className="brand-mark"><Radio size={19} strokeWidth={2.3} /></span>
            <span className="brand-copy">
              <strong>Aapad<span>Snehi</span></strong>
              <small>Response intelligence</small>
            </span>
          </button>

          <nav className="desktop-nav" aria-label="Primary navigation">
            {navItems.map((item) => {
              const active = path === item.href;
              return (
                <button key={item.href} type="button" className={active ? "nav-link active" : "nav-link"} onClick={() => go(item.href)}>
                  <item.icon size={16} /> {item.label}
                </button>
              );
            })}
          </nav>

          <div className="header-actions flex items-center gap-3">
            <span className={`connection-chip ${connection}`}>
              <span className="pulse-dot" /> {loading ? "Connecting" : connection === "api" ? "API online" : "Demo data"}
            </span>

            <span className="demo-admin-badge">Quick demo</span>

            <button className="icon-button desktop-only" type="button" aria-label="Notifications">
              <BellRing size={18} />
            </button>
            <button className="icon-button mobile-menu" type="button" onClick={() => setMobileOpen((open) => !open)} aria-label="Open navigation" aria-expanded={mobileOpen}>
              {mobileOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>
        {mobileOpen && (
          <nav className="mobile-nav" aria-label="Mobile navigation">
            {navItems.map((item) => (
              <button key={item.href} type="button" className={path === item.href ? "active" : ""} onClick={() => go(item.href)}>
                <span><item.icon size={18} /> {item.label}</span><ChevronRight size={16} />
              </button>
            ))}
          </nav>
        )}
      </header>
      <main>{children}</main>
      <footer className="site-footer">
        <div>
          <span className="footer-brand"><Radio size={16} /> AapadSnehi</span>
          <p>Decision support for response teams. Recommendations require human review.</p>
        </div>
        <div className="footer-trust"><ShieldCheck size={16} /> Official, media, and community signals stay visibly distinct.</div>
      </footer>
    </div>
  );
}
