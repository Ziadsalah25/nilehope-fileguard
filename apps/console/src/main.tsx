import React, {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  useRef,
  type FormEvent,
  type ReactNode,
} from "react";
import { createRoot } from "react-dom/client";
import {
  BrowserRouter,
  NavLink,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Bell,
  Check,
  CheckCheck,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Circle,
  CircleHelp,
  ClipboardCheck,
  Clock3,
  Database,
  ExternalLink,
  Eye,
  FileCheck2,
  FileClock,
  FileText,
  Folder,
  FolderOpen,
  Globe2,
  HardDrive,
  HeartPulse,
  LayoutDashboard,
  Loader2,
  LogOut,
  Menu,
  Monitor,
  Moon,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Search,
  Server,
  Settings2,
  Shield,
  ShieldCheck,
  SlidersHorizontal,
  Sun,
  Terminal,
  Trash2,
  Wifi,
  X,
  XCircle,
} from "lucide-react";
import "@fontsource-variable/inter";
import "./style.css";
import { api, clock, relative, type Row } from "./api";
import Recovery from "./Recovery";

const Language = createContext({
  lang: "en",
  t: (en: string, _ar?: string) => en,
  toggle: () => {},
});
const useLang = () => useContext(Language);
const ToastContext = createContext<(message: string, bad?: boolean) => void>(
  () => {},
);
const useToast = () => useContext(ToastContext);
function Icon({
  icon: IconComponent,
  size = 18,
}: {
  icon: any;
  size?: number;
}) {
  return <IconComponent size={size} strokeWidth={1.75} />;
}
function Status({ online, label }: { online: boolean; label?: string }) {
  const { t } = useLang();
  return (
    <span className={`badge ${online ? "green" : "muted"}`}>
      <span className="status-dot" />
      {label || (online ? t("Online", "متصل") : t("Offline", "غير متصل"))}
    </span>
  );
}
function Result({ value }: { value: string }) {
  const { t } = useLang();
  const denied = value === "blocked",
    observed = value === "observed";
  return (
    <span className={`badge ${observed ? "blue" : denied ? "rose" : "green"}`}>
      {observed ? (
        <Eye size={12} />
      ) : denied ? (
        <XCircle size={12} />
      ) : (
        <CheckCircle2 size={12} />
      )}{" "}
      {observed
        ? t("Observed change", "تغيير ملحوظ")
        : denied
          ? t("Denied check", "فحص مرفوض")
          : t("Allowed check", "فحص مسموح")}
    </span>
  );
}
function OSBadge({ device }: { device: Row }) {
  return (
    <Badge
      tone={
        device.os_family === "linux"
          ? "purple"
          : device.os_family === "windows"
            ? "blue"
            : "muted"
      }
    >
      {device.os_family === "linux" ? (
        <Terminal size={11} />
      ) : (
        <Monitor size={11} />
      )}{" "}
      {device.os_family === "linux"
        ? "Linux"
        : device.os_family === "windows"
          ? "Windows"
          : "Unknown OS"}
    </Badge>
  );
}
function formatCapacity(used: any, total: any) {
  return total
    ? `${(Number(used || 0) / 1024).toFixed(1)} / ${(Number(total) / 1024).toFixed(1)} GB`
    : "Not reported";
}
function uptime(value: any) {
  if (value === null || value === undefined) return "Not reported";
  const seconds = Number(value);
  return `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}
function Badge({
  children,
  tone = "muted",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
function Empty({
  title,
  description,
  icon: EmptyIcon = FolderOpen,
  action,
}: {
  title: string;
  description: string;
  icon?: any;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <EmptyIcon size={25} />
      </div>
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}
function Loading() {
  return (
    <div className="loading">
      <Loader2 className="spin" size={24} />
      <span>Loading your workspace…</span>
    </div>
  );
}
function ErrorBox({ message, retry }: { message: string; retry: () => void }) {
  return (
    <div className="error-box">
      <XCircle size={20} />
      <div>
        <strong>We couldn’t load this view</strong>
        <p>{message}</p>
      </div>
      <button className="btn secondary" onClick={retry}>
        Try again
      </button>
    </div>
  );
}
function useData(path: string, interval = 10000) {
  const [data, setData] = useState<any>(null),
    [error, setError] = useState(""),
    [refreshing, setRefreshing] = useState(false);
  const sequence = useRef(0);
  const load = useCallback(async () => {
    const request = ++sequence.current;
    setRefreshing(true);
    try {
      const result = await api(path);
      if (request === sequence.current) {
        setData(result);
        setError("");
      }
    } catch (e) {
      if (request === sequence.current) setError((e as Error).message);
    } finally {
      if (request === sequence.current) setRefreshing(false);
    }
  }, [path]);
  useEffect(() => {
    void load();
    const id = window.setInterval(load, interval);
    return () => {
      clearInterval(id);
      sequence.current++;
    };
  }, [load, interval]);
  return { data, error, load, refreshing };
}
function PageHeader({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="heading-actions">{children}</div>
    </div>
  );
}
function Panel({
  title,
  description,
  action,
  children,
  className = "",
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-heading">
        <div>
          <h2>{title}</h2>
          {description && <p>{description}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
function Modal({
  title,
  description,
  children,
  onClose,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLElement>(null),
    close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    if (!dialog.current?.contains(document.activeElement))
      dialog.current
        ?.querySelector<HTMLElement>("button,input,select,textarea")
        ?.focus();
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") close.current();
      if (e.key === "Tab") {
        const elements = Array.from(
          dialog.current?.querySelectorAll<HTMLElement>(
            'button:not(:disabled),a[href],input,select,textarea,[tabindex="0"]',
          ) || [],
        ).filter((el) => el.offsetParent !== null);
        const first = elements[0],
          last = elements[elements.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => {
      window.removeEventListener("keydown", handler);
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, []);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <section
        ref={dialog}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="modal-head">
          <div>
            <h2>{title}</h2>
            {description && <p>{description}</p>}
          </div>
          <button
            className="icon-btn"
            aria-label="Close dialog"
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}

function Login({ onLogin }: { onLogin: (value: any) => void }) {
  const { t, toggle, lang } = useLang();
  const [username, setUsername] = useState(""),
    [password, setPassword] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const result = await api("/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      onLogin(result);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login-page">
      <div className="login-art">
        <div className="login-brand">
          <div className="brand-icon">
            <HeartPulse size={25} />
          </div>
          <span>
            NILE OF HOPE<small>FILEGUARD</small>
          </span>
        </div>
        <div className="login-art-body">
          <Badge tone="glass">
            <span className="status-dot" /> HOSPITAL SECURITY WORKSPACE
          </Badge>
          <h1>
            A clearer view.
            <br />A stronger connection.
          </h1>
          <p>
            Your endpoints, shared files, and access activity.
            <br />
            One focused workspace for your hospital IT team.
          </p>
          <div className="orbital">
            <div className="orbit orbit-one" />
            <div className="orbit orbit-two" />
            <div className="orbit orbit-three" />
            <div className="orbit-center">
              <ShieldCheck size={54} />
            </div>
            <div className="orbit-node node-one">
              <Monitor size={22} />
            </div>
            <div className="orbit-node node-two">
              <Database size={22} />
            </div>
            <div className="orbit-node node-three">
              <Folder size={22} />
            </div>
            <div className="orbit-label">
              <span className="status-dot" /> Visibility starts with connection
            </div>
          </div>
        </div>
        <div className="login-art-foot">
          <ShieldCheck size={15} /> Built for hospital IT operations
        </div>
      </div>
      <div className="login-form-side">
        <button className="btn text login-language" onClick={toggle}>
          <Globe2 size={16} />
          {lang === "en" ? "العربية" : "English"}
        </button>
        <div className="login-content">
          <div className="login-symbol">
            <ShieldCheck size={27} />
          </div>
          <div className="eyebrow">
            {t("YOUR SECURITY WORKSPACE", "مساحة عمل الأمان")}
          </div>
          <h2>{t("Welcome back.", "مرحباً بعودتك.")}</h2>
          <p>
            {t(
              "Sign in to your FileGuard console.",
              "سجل الدخول إلى وحدة إدارة الملفات.",
            )}
          </p>
          <form onSubmit={submit}>
            <label>
              {t("Username", "اسم المستخدم")}
              <input
                autoComplete="username"
                name="username"
                autoFocus
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                placeholder="Enter your username"
              />
            </label>
            <label>
              {t("Password", "كلمة المرور")}
              <input
                type="password"
                autoComplete="current-password"
                name="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder="Enter your password"
              />
            </label>
            {error && (
              <div className="form-error" role="alert">
                {error}
              </div>
            )}
            <button className="btn primary login-submit" disabled={busy}>
              {busy ? (
                <Loader2 className="spin" size={17} />
              ) : (
                <>
                  {t("Sign in to workspace", "تسجيل الدخول")}
                  <ArrowRight size={17} />
                </>
              )}
            </button>
          </form>
          <div className="login-note">
            <Shield size={15} />
            <span>
              {t(
                "For authorized hospital personnel. Sign-in activity is recorded.",
                "للموظفين المصرح لهم. يتم تسجيل نشاط الدخول.",
              )}
            </span>
          </div>
        </div>
        <div className="login-copyright">
          © {new Date().getFullYear()} Nile of Hope Hospital{" "}
          <span>FileGuard</span>
        </div>
      </div>
    </div>
  );
}

const navItems = [
  { path: "/", icon: LayoutDashboard, en: "Overview", ar: "نظرة عامة" },
  { path: "/recovery", icon: FileClock, en: "Recovery & versions", ar: "الاستعادة والإصدارات" },
  { path: "/devices", icon: Monitor, en: "Devices", ar: "الأجهزة" },
  {
    path: "/activity",
    icon: Activity,
    en: "File activity",
    ar: "نشاط الملفات",
  },
  {
    path: "/shares",
    icon: FolderOpen,
    en: "Shared folders",
    ar: "المجلدات المشتركة",
  },
  {
    path: "/approvals",
    icon: ClipboardCheck,
    en: "Access requests",
    ar: "طلبات الوصول",
  },
  { path: "/audit", icon: FileCheck2, en: "Audit trail", ar: "سجل التدقيق" },
];
function Shell({ session, onLogout }: { session: any; onLogout: () => void }) {
  const { t, lang, toggle } = useLang(),
    location = useLocation(),
    navigate = useNavigate();
  const [connectionLost, setConnectionLost] = useState(false);
  useEffect(() => {
    const offline = () => setConnectionLost(true),
      online = () => setConnectionLost(false);
    window.addEventListener("backend-offline", offline);
    window.addEventListener("backend-online", online);
    return () => {
      window.removeEventListener("backend-offline", offline);
      window.removeEventListener("backend-online", online);
    };
  }, []);
  const [open, setOpen] = useState(false),
    [query, setQuery] = useState(""),
    [help, setHelp] = useState(false);
  const [dark, setDark] = useState(
    () => localStorage.getItem("nile-theme") === "dark",
  );
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("nile-theme", dark ? "dark" : "light");
  }, [dark]);
  useEffect(() => setOpen(false), [location.pathname]);
  const current = navItems.find((i) => i.path === location.pathname);
  const section = current
    ? t(current.en, current.ar)
    : t("System & database", "النظام وقاعدة البيانات");
  const monitoring = !session.remote_commands && !session.directory_writes;
  return (
    <div className="app-layout">
      <button
        className={`sidebar-scrim ${open ? "visible" : ""}`}
        aria-label="Close navigation"
        onClick={() => setOpen(false)}
      />
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <NavLink to="/" className="brand">
          <div className="brand-icon">
            <HeartPulse size={23} />
          </div>
          <span>
            NileHope<small>FILEGUARD</small>
          </span>
        </NavLink>
        <div className="workspace-picker">
          <div className="workspace-mark">NH</div>
          <div>
            <b>{t("Hospital workspace", "مساحة عمل المستشفى")}</b>
            <small>File protection & recovery</small>
          </div>
          <ShieldCheck size={16} />
        </div>
        <div className="nav-label">{t("WORKSPACE", "مساحة العمل")}</div>
        <nav>
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === "/"}
              className={({ isActive }) =>
                isActive ? "nav-item active" : "nav-item"
              }
            >
              <Icon icon={item.icon} />
              <span>{t(item.en, item.ar)}</span>
              {item.path === "/devices" && <span className="nav-chip">IT</span>}
            </NavLink>
          ))}
        </nav>
        <div className="nav-label system-label">
          {t("ADMINISTRATION", "الإدارة")}
        </div>
        <NavLink
          to="/system"
          className={({ isActive }) =>
            isActive ? "nav-item active" : "nav-item"
          }
        >
          <Settings2 size={19} />
          <span>{t("System & database", "النظام وقاعدة البيانات")}</span>
        </NavLink>
        <div className="sidebar-bottom">
          <div className="mode-card">
            <div className="mode-icon">
              <Eye size={18} />
            </div>
            <b>
              {monitoring
                ? t("Observe first.", "المراقبة أولاً.")
                : t("Controls available", "التحكم متاح")}
            </b>
            <p>
              {monitoring
                ? t(
                    "Monitoring is active. Endpoint restrictions are not applied.",
                    "المراقبة نشطة دون تطبيق قيود على الأجهزة.",
                  )
                : t(
                    "Review changes before sending endpoint commands.",
                    "راجع التغييرات قبل إرسال الأوامر.",
                  )}
            </p>
            <NavLink to="/system">
              {t("View configuration", "عرض الإعدادات")}
              <ArrowUpRight size={14} />
            </NavLink>
          </div>
          <button className="sidebar-help" onClick={() => setHelp(true)}>
            <CircleHelp size={17} />
            {t("Deployment guide", "دليل النشر")}
            <ArrowUpRight size={14} />
          </button>
          <div className="sidebar-user">
            <div className="avatar">
              {session.user.slice(0, 2).toUpperCase()}
            </div>
            <div>
              <b>{session.user}</b>
              <small>{t("Administrator", "مسؤول النظام")}</small>
            </div>
            <button
              className="icon-btn"
              title={t("Sign out", "خروج")}
              aria-label="Sign out"
              onClick={onLogout}
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-wrap">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-btn mobile-menu"
              aria-label="Open navigation"
              onClick={() => setOpen(true)}
            >
              <Menu size={21} />
            </button>
            <span className="breadcrumb-root">
              {t("Workspace", "مساحة العمل")}
            </span>
            <ChevronRight size={14} />
            <b>{section}</b>
          </div>
          <div className="topbar-right">
            <form
              className="global-search"
              onSubmit={(e) => {
                e.preventDefault();
                navigate(`/devices?q=${encodeURIComponent(query)}`);
              }}
            >
              <Search size={16} />
              <input
                aria-label="Search devices"
                placeholder={t("Search endpoints…", "ابحث عن جهاز…")}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              <kbd>↵</kbd>
            </form>
            <button
              className="icon-btn"
              aria-label={dark ? "Use light theme" : "Use dark theme"}
              onClick={() => setDark(!dark)}
            >
              {dark ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <button className="language-button" onClick={toggle}>
              {lang === "en" ? "عربي" : "EN"}
            </button>
            <NavLink
              className="icon-btn notification-button"
              aria-label="View access requests"
              to="/approvals"
            >
              <Bell size={18} />
            </NavLink>
            <div className="topbar-avatar">
              {session.user.slice(0, 1).toUpperCase()}
            </div>
          </div>
        </header>
        {session.environment === "test" && (
          <div className="test-strip">
            <span className="test-label">TEST WORKSPACE</span>
            <span>
              {t(
                "Synthetic lab devices are clearly labeled. No live hospital connection is implied.",
                "الأجهزة التجريبية محددة بوضوح. لا يعني ذلك الاتصال الفعلي بالمستشفى.",
              )}
            </span>
          </div>
        )}
        <main className="main-content">
          {connectionLost && (
            <div className="form-error connection-alert" role="alert">
              <Wifi size={16} />
              {t(
                "Connection interrupted. Last received data is shown while we reconnect.",
                "انقطع الاتصال. تُعرض آخر بيانات مستلمة حتى إعادة الاتصال.",
              )}
            </div>
          )}
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/recovery" element={<Recovery />} />
            <Route path="/devices" element={<Devices session={session} />} />
            <Route path="/activity" element={<FileActivity />} />
            <Route path="/shares" element={<Shares />} />
            <Route
              path="/approvals"
              element={<Approvals session={session} />}
            />
            <Route path="/audit" element={<Audit />} />
            <Route path="/system" element={<System />} />
            <Route
              path="*"
              element={
                <Empty
                  title="Page not found"
                  description="Choose a page from the workspace navigation."
                />
              }
            />
          </Routes>
          <footer className="workspace-footer">
            <span>
              Nile of Hope <span className="footer-dot">·</span>{" "}
              {t("FileGuard", "مركز إدارة الملفات")}
            </span>
            <span>
              <span className="tiny-dot" />
              {t(
                "Console metadata. Recovery copies stay with the agent.",
                "تعرض الوحدة بيانات الأحداث وتبقى نسخ الاستعادة لدى الوكيل.",
              )}
            </span>
          </footer>
        </main>
      </div>
      {help && (
        <Modal
          title={t("Connect your hospital", "ربط المستشفى")}
          description="Deployment overview"
          onClose={() => setHelp(false)}
        >
          <div className="guide-steps">
            {[
              [
                "01",
                "Prepare the server",
                "Run the container stack on a Linux VM or a Linux VM hosted by Hyper-V on Windows Server.",
              ],
              [
                "02",
                "Establish trust",
                "Configure the hospital DNS name and a trusted HTTPS certificate.",
              ],
              [
                "03",
                "Enroll an agent",
                "Install the Windows agent on one pilot PC and on EXAMPLE-FILE01 in file-server mode.",
              ],
              [
                "04",
                "Validate the feed",
                "Confirm real heartbeats and events from \\EXAMPLE-FILE01\\E before extending the deployment.",
              ],
            ].map(([number, title, text]) => (
              <div key={number}>
                <span>{number}</span>
                <section>
                  <h3>{title}</h3>
                  <p>{text}</p>
                </section>
              </div>
            ))}
          </div>
          <div className="modal-foot">
            <button
              className="btn primary"
              onClick={() => {
                setHelp(false);
                navigate("/system");
              }}
            >
              View connection status
              <ArrowRight size={16} />
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function ActivityChart({ week }: { week: Row[] }) {
  const { t } = useLang();
  const [hover, setHover] = useState<number | null>(null);
  const width = 640,
    height = 185,
    pad = 14;
  const maximum = Math.max(
    4,
    ...week.map(
      (x) => Number(x.allowed) + Number(x.blocked) + Number(x.observed || 0),
    ),
  );
  function points(key: string) {
    return week.map((d, i) => [
      pad + (i * (width - 2 * pad)) / 6,
      150 - (Number(d[key] || 0) / maximum) * 122,
    ]);
  }
  const allowed = points("allowed"),
    denied = points("blocked"),
    observed = points("observed");
  const path = (values: number[][]) =>
    values.map((p, i) => `${i === 0 ? "M" : "L"}${p[0]},${p[1]}`).join(" ");
  return (
    <div className="activity-chart">
      <div className="chart-y">
        <span>{maximum}</span>
        <span>{Math.round(maximum / 2)}</span>
        <span>0</span>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={t(
          "Access checks and observed file changes during the last seven days",
          "فحوص الوصول المسموحة والمرفوضة خلال الأسبوع",
        )}
      >
        <defs>
          <linearGradient id="activity-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#1d9b82" stopOpacity=".18" />
            <stop offset="100%" stopColor="#1d9b82" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[28, 89, 150].map((y) => (
          <line
            key={y}
            x1="0"
            x2={width}
            y1={y}
            y2={y}
            className="chart-grid"
          />
        ))}
        <path
          d={`${path(allowed)} L${width - pad},150 L${pad},150 Z`}
          fill="url(#activity-fill)"
        />
        <path
          d={path(allowed)}
          fill="none"
          stroke="#269d87"
          strokeWidth="2.5"
          strokeLinejoin="round"
        />
        <path
          d={path(denied)}
          fill="none"
          stroke="#a495d0"
          strokeWidth="2"
          strokeDasharray="5 4"
          strokeLinejoin="round"
        />
        <path
          d={path(observed)}
          fill="none"
          stroke="#6d99c1"
          strokeWidth="2"
          strokeLinejoin="round"
        />
        {week.map((d, i) => (
          <g
            key={i}
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
          >
            <rect
              x={pad + (i * (width - 2 * pad)) / 6 - 25}
              y="0"
              width="50"
              height="160"
              fill="transparent"
            />
            <text
              x={allowed[i][0]}
              y="177"
              textAnchor="middle"
              className="chart-day"
            >
              {d.label}
            </text>
            {hover === i && (
              <>
                <line
                  x1={allowed[i][0]}
                  x2={allowed[i][0]}
                  y1="0"
                  y2="150"
                  stroke="#a7bdb4"
                  strokeDasharray="3 4"
                />
                <circle
                  cx={allowed[i][0]}
                  cy={allowed[i][1]}
                  r="4"
                  fill="#269d87"
                  stroke="white"
                  strokeWidth="2"
                />
              </>
            )}
          </g>
        ))}
      </svg>
      {hover !== null && (
        <div className="chart-tooltip">
          {week[hover].label}: {week[hover].allowed} allowed ·{" "}
          {week[hover].blocked} denied · {week[hover].observed || 0} file
          changes
        </div>
      )}
    </div>
  );
}
function Overview() {
  const { t } = useLang(),
    { data, error, load, refreshing } = useData("/overview");
  if (!data)
    return error ? <ErrorBox message={error} retry={load} /> : <Loading />;
  const s = data.stats;
  const metrics = [
    {
      label: t("Enrolled endpoints", "الأجهزة المسجلة"),
      value: s.total,
      icon: Monitor,
      note: `${s.online} ${t("online right now", "متصل الآن")}`,
      tone: "teal",
      extra: t("Fleet visibility", "رؤية الأجهزة"),
    },
    {
      label: t("Monitored shares", "المشاركات المراقبة"),
      value: s.shares,
      icon: FolderOpen,
      note: t("Explicitly registered paths", "مسارات مسجلة للمراقبة"),
      tone: "blue",
      extra: t("Metadata only", "بيانات الأحداث فقط"),
    },
    {
      label: t("File events logged", "أحداث الملفات المسجلة"),
      value: s.events,
      icon: Activity,
      note: t(
        "Access checks and observed changes",
        "فحوص الوصول وتغييرات الملفات",
      ),
      tone: "purple",
      extra: t("Agent-reported", "تقارير العملاء"),
    },
    {
      label: t("Pending requests", "الطلبات المعلقة"),
      value: s.pending,
      icon: ClipboardCheck,
      note: t("Awaiting administrator review", "بانتظار مراجعة المسؤول"),
      tone: "orange",
      extra: s.pending
        ? t("Needs attention", "يتطلب المراجعة")
        : t("All caught up", "لا طلبات معلقة"),
    },
  ];
  return (
    <>
      <PageHeader
        eyebrow={t("YOUR HOSPITAL, AT A GLANCE", "المستشفى في لمحة")}
        title={t("Security overview", "نظرة عامة على الأمان")}
        description={t(
          "A clear picture of your endpoints and shared-file activity.",
          "صورة واضحة لأجهزتك ونشاط الملفات المشتركة.",
        )}
      >
        <button className="btn secondary" onClick={load}>
          <RefreshCw size={15} className={refreshing ? "spin" : ""} />
          {t("Refresh", "تحديث")}
        </button>
        <NavLink to="/devices" className="btn primary">
          <Plus size={16} />
          {t("Connect an endpoint", "ربط جهاز")}
        </NavLink>
      </PageHeader>
      <div className="overview-banner">
        <div className="overview-banner-icon">
          <Eye size={21} />
        </div>
        <div>
          <b>
            {t(
              "Visibility first. Your monitoring workspace is ready.",
              "المراقبة أولاً. مساحة العمل جاهزة.",
            )}
          </b>
          <p>
            {t(
              "Review connections and access checks before enabling endpoint controls.",
              "راجع الاتصالات وفحوص الوصول قبل تفعيل التحكم بالأجهزة.",
            )}
          </p>
        </div>
        <NavLink to="/system">
          {t("View system status", "حالة النظام")}
          <ArrowRight size={16} />
        </NavLink>
      </div>
      <div className="metrics-grid">
        {metrics.map((m) => (
          <div className="metric-card" key={m.label}>
            <div className="metric-label">
              {m.label}
              <span className={`metric-icon ${m.tone}`}>
                <m.icon size={18} />
              </span>
            </div>
            <div className="metric-value">
              {Number(m.value).toLocaleString()}
              <span>{m.extra}</span>
            </div>
            <p>
              <span className={`tiny-dot ${m.tone}`} />
              {m.note}
            </p>
          </div>
        ))}
      </div>
      <div className="dashboard-row">
        <Panel
          title={t("File access activity", "نشاط الوصول للملفات")}
          description={t(
            "Access checks and file changes over the last 7 days",
            "فحوص الوصول المبلغ عنها خلال ٧ أيام",
          )}
          action={
            <Badge>
              <Clock3 size={12} />
              {t("Last 7 days", "آخر ٧ أيام")}
            </Badge>
          }
          className="chart-panel"
        >
          <div className="chart-summary">
            <div>
              <strong>
                {data.week
                  .reduce(
                    (sum: number, d: Row) =>
                      sum +
                      Number(d.allowed) +
                      Number(d.blocked) +
                      Number(d.observed || 0),
                    0,
                  )
                  .toLocaleString()}
              </strong>
              <span>{t("total observations", "إجمالي الملاحظات")}</span>
            </div>
            <div className="chart-legend">
              <span>
                <i className="legend-dot allowed" />
                {t("Allowed", "مسموح")}
              </span>
              <span>
                <i className="legend-dot denied" />
                {t("Denied", "مرفوض")}
              </span>
            </div>
          </div>
          <ActivityChart week={data.week} />
          <div className="chart-foot">
            <CircleHelp size={13} />
            {t(
              "Access checks describe permissions evaluated, not confirmed file deletion.",
              "فحص الوصول لا يثبت حدوث حذف فعلي للملف.",
            )}
          </div>
        </Panel>
        <Panel
          title={t("Fleet health", "حالة الأجهزة")}
          description={t(
            "Connection status across your workspace",
            "حالة الاتصال في مساحة العمل",
          )}
          action={
            <span className="small-icon">
              <HeartPulse size={17} />
            </span>
          }
          className="fleet-panel"
        >
          <div className="fleet-ring">
            <svg viewBox="0 0 148 148">
              <circle
                cx="74"
                cy="74"
                r="61"
                fill="none"
                stroke="var(--border)"
                strokeWidth="10"
              />
              <circle
                cx="74"
                cy="74"
                r="61"
                fill="none"
                stroke="#269d87"
                strokeWidth="10"
                strokeLinecap="round"
                strokeDasharray={`${s.total ? (s.online / s.total) * 383 : 0} 383`}
                transform="rotate(-90 74 74)"
              />
            </svg>
            <div>
              <strong>
                {s.total ? Math.round((s.online / s.total) * 100) : 0}
                <small>%</small>
              </strong>
              <span>{t("online", "متصل")}</span>
            </div>
          </div>
          <div className="fleet-stat">
            <span>
              <i className="legend-dot allowed" />
              {t("Online endpoints", "أجهزة متصلة")}
            </span>
            <b>{s.online}</b>
          </div>
          <div className="fleet-stat">
            <span>
              <i className="legend-dot offline" />
              {t("Offline endpoints", "أجهزة غير متصلة")}
            </span>
            <b>{s.offline}</b>
          </div>
          <NavLink to="/devices" className="panel-bottom-link">
            {t("View all endpoints", "عرض جميع الأجهزة")}
            <ArrowRight size={15} />
          </NavLink>
        </Panel>
      </div>
      <div className="dashboard-lower">
        <Panel
          title={t("Recent endpoints", "أحدث الأجهزة")}
          description={t(
            "A live view of your enrolled devices",
            "عرض الأجهزة المسجلة",
          )}
          action={
            <NavLink to="/devices" className="text-link">
              {t("View all", "عرض الكل")}
              <ArrowUpRight size={14} />
            </NavLink>
          }
        >
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t("ENDPOINT", "الجهاز")}</th>
                  <th>{t("ADDRESS", "العنوان")}</th>
                  <th>{t("STATUS", "الحالة")}</th>
                  <th>{t("LAST SEEN", "آخر ظهور")}</th>
                </tr>
              </thead>
              <tbody>
                {data.devices.map((d: Row) => (
                  <tr key={d.id}>
                    <td>
                      <NavLink
                        to={`/devices?device=${d.id}`}
                        className="device-cell"
                      >
                        <span className="device-icon">
                          <Monitor size={17} />
                        </span>
                        <span>
                          <b>{d.hostname}</b>
                          <small>
                            {d.department || t("Unassigned", "غير محدد")}
                            {d.simulated && " · Synthetic"}
                          </small>
                        </span>
                      </NavLink>
                    </td>
                    <td>
                      <code>{d.ip || "—"}</code>
                    </td>
                    <td>
                      <Status online={d.online} />
                    </td>
                    <td className="text-muted">{relative(d.last_seen)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!data.devices.length && (
            <Empty
              title={t("Your fleet starts here", "ابدأ ربط أجهزتك")}
              description={t(
                "Enroll a Windows or Linux agent to see its connection and heartbeat.",
                "سجل عميلاً على Windows لعرض حالة اتصاله.",
              )}
              icon={Monitor}
            />
          )}
        </Panel>
        <Panel
          title={t("Latest activity", "أحدث النشاطات")}
          description={t(
            "The latest observations from your agents",
            "آخر ملاحظات العملاء",
          )}
          action={
            <NavLink to="/activity" className="text-link">
              {t("View feed", "عرض النشاط")}
              <ArrowUpRight size={14} />
            </NavLink>
          }
        >
          <div className="activity-feed">
            {data.activity.map((event: Row) => (
              <div className="feed-item" key={event.id}>
                <span
                  className={`feed-icon ${event.result === "blocked" ? "rose" : "teal"}`}
                >
                  {event.result === "blocked" ? (
                    <FileClock size={17} />
                  ) : (
                    <FileCheck2 size={17} />
                  )}
                </span>
                <div>
                  <b>{event.device}</b>
                  <p>
                    {event.file?.split(/[\\/]/).pop() || "File access check"}
                  </p>
                  <small>
                    {event.result === "blocked"
                      ? t("Denied access check", "فحص وصول مرفوض")
                      : event.result === "observed"
                        ? t("Observed file change", "تغيير ملف ملحوظ")
                        : t("Allowed access check", "فحص وصول مسموح")}
                  </small>
                </div>
                <time>{relative(event.ts)}</time>
              </div>
            ))}
          </div>
          {!data.activity.length && (
            <Empty
              title={t("Listening for activity", "بانتظار النشاط")}
              description={t(
                "File-server agents will send observed access checks here.",
                "ستظهر فحوص الوصول من عملاء خوادم الملفات هنا.",
              )}
              icon={Activity}
            />
          )}
        </Panel>
      </div>
      <div className="bottom-status">
        <span>
          <span className="tiny-dot" />
          {t("Updated", "آخر تحديث")}{" "}
          {new Date(data.updated_at).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </span>
        <span>
          {t("Refreshes every 10 seconds", "تحديث كل ١٠ ثوانٍ")}
          <RefreshCw size={12} />
        </span>
      </div>
    </>
  );
}
function Devices({ session }: { session: any }) {
  const { t } = useLang(),
    toast = useToast(),
    location = useLocation();
  const { data, error, load, refreshing } = useData("/devices");
  const [query, setQuery] = useState(
      new URLSearchParams(location.search).get("q") || "",
    ),
    [filter, setFilter] = useState("all"),
    [ring, setRing] = useState("all"),
    [platformFilter, setPlatformFilter] = useState("all"),
    [agentPlatform, setAgentPlatform] = useState("windows"),
    [selected, setSelected] = useState<Row | null>(null),
    [enroll, setEnroll] = useState(false),
    [cmd, setCmd] = useState("collect_logs"),
    [sending, setSending] = useState(false);
  useEffect(() => {
    setQuery(new URLSearchParams(location.search).get("q") || "");
  }, [location.search]);
  const openedDevice = useRef("");
  useEffect(() => {
    const id = new URLSearchParams(location.search).get("device");
    if (data && id && openedDevice.current !== id) {
      setSelected(data.items.find((d: Row) => String(d.id) === id) || null);
      openedDevice.current = id;
    }
    if (!id) openedDevice.current = "";
  }, [data, location.search]);
  useEffect(() => {
    if (data)
      setSelected((current) =>
        current
          ? data.items.find((d: Row) => d.id === current.id) || null
          : null,
      );
  }, [data]);
  if (!data)
    return error ? <ErrorBox message={error} retry={load} /> : <Loading />;
  const rows = data.items.filter(
    (d: Row) =>
      (filter === "all" || (filter === "online" ? d.online : !d.online)) &&
      (ring === "all" || d.ring === ring) &&
      (platformFilter === "all" ||
        (d.os_family || "unknown") === platformFilter) &&
      [d.hostname, d.ip, d.win_user, d.department, d.os_family, d.os_version]
        .join(" ")
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const online = data.items.filter((d: Row) => d.online).length;
  async function changeRing(value: string) {
    if (!selected) return;
    try {
      await api(`/devices/${selected.id}/ring`, {
        method: "POST",
        body: JSON.stringify({ ring: value }),
      });
      setSelected((current) =>
        current?.id === selected.id ? { ...current, ring: value } : current,
      );
      toast(t("Deployment ring updated.", "تم تحديث مجموعة النشر."));
      void load();
    } catch (e) {
      toast((e as Error).message, true);
    }
  }
  async function sendCommand() {
    if (!selected) return;
    const warnings: Record<string, string> = {
      isolate_smb:
        "This closes ALL active SMB sessions on this server and may interrupt open files. Clients can reconnect. Continue?",
      lock_usb:
        "Disable USB storage startup on this device? Already-connected devices may remain usable.",
      restore_usb:
        "Restore the USB storage setting previously saved by this agent?",
    };
    if (warnings[cmd] && !window.confirm(warnings[cmd])) return;
    setSending(true);
    try {
      await api(`/devices/${selected.id}/commands`, {
        method: "POST",
        body: JSON.stringify({ command: cmd }),
      });
      toast("Command queued for the next heartbeat.");
      void load();
    } catch (e) {
      toast((e as Error).message, true);
    } finally {
      setSending(false);
    }
  }
  return (
    <>
      <PageHeader
        eyebrow={t("ENDPOINT VISIBILITY", "متابعة الأجهزة")}
        title={t("Your connected fleet", "أجهزة مساحة العمل")}
        description={t(
          "Monitor device connections, agent health, and deployment rings.",
          "راقب اتصال الأجهزة وحالة العملاء ومجموعات النشر.",
        )}
      >
        <button className="btn secondary" onClick={load}>
          <RefreshCw size={15} className={refreshing ? "spin" : ""} />
          {t("Refresh", "تحديث")}
        </button>
        <button className="btn primary" onClick={() => setEnroll(true)}>
          <Plus size={16} />
          {t("Connect endpoint", "ربط جهاز")}
        </button>
      </PageHeader>
      <div className="summary-strip">
        <div>
          <Monitor size={18} />
          <span>{t("All endpoints", "جميع الأجهزة")}</span>
          <b>{data.items.length}</b>
        </div>
        <div>
          <span className="tiny-dot" />
          <span>{t("Online", "متصل")}</span>
          <b>{online}</b>
        </div>
        <div>
          <span className="tiny-dot gray" />
          <span>{t("Offline", "غير متصل")}</span>
          <b>{data.items.length - online}</b>
        </div>
        <div>
          <Eye size={17} />
          <span>{t("Mode", "الوضع")}</span>
          <Badge tone="green">
            {session.remote_commands
              ? t("Controls enabled", "التحكم مفعل")
              : t("Monitoring", "مراقبة")}
          </Badge>
        </div>
      </div>
      <section className="panel">
        <div className="list-toolbar">
          <div className="tabs">
            {[
              ["all", t("All endpoints", "جميع الأجهزة")],
              ["online", t("Online", "متصل")],
              ["offline", t("Offline", "غير متصل")],
            ].map(([value, label]) => (
              <button
                key={value}
                className={filter === value ? "active" : ""}
                onClick={() => setFilter(value)}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="filter-group">
            <label className="search-input">
              <Search size={16} />
              <input
                aria-label="Filter endpoints"
                placeholder={t(
                  "Search by device, user, or IP…",
                  "ابحث بالجهاز أو المستخدم أو العنوان…",
                )}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
            <select
              aria-label="Filter operating system"
              value={platformFilter}
              onChange={(e) => setPlatformFilter(e.target.value)}
            >
              <option value="all">All systems</option>
              <option value="windows">Windows</option>
              <option value="linux">Linux</option>
              <option value="unknown">Unknown OS</option>
            </select>
            <select
              aria-label="Filter deployment ring"
              value={ring}
              onChange={(e) => setRing(e.target.value)}
            >
              <option value="all">{t("All rings", "جميع المجموعات")}</option>
              {["pilot", "ring20", "ring50", "all"].map((r) => (
                <option key={r} value={r}>
                  {r === "all" ? "Full rollout" : r}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="table-scroll">
          <table className="devices-table">
            <thead>
              <tr>
                <th>{t("DEVICE", "الجهاز")}</th>
                <th>{t("SYSTEM / USER", "النظام / المستخدم")}</th>
                <th>{t("IP ADDRESS", "عنوان IP")}</th>
                <th>{t("STATUS", "الحالة")}</th>
                <th>{t("AGENT", "العميل")}</th>
                <th>{t("RING", "المجموعة")}</th>
                <th>{t("LAST SEEN", "آخر ظهور")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((d: Row) => (
                <tr key={d.id}>
                  <td>
                    <button
                      className="device-cell"
                      onClick={() => setSelected(d)}
                    >
                      <span
                        className={`device-icon ${d.hostname.includes("FILE") ? "server" : ""}`}
                      >
                        {d.hostname.includes("FILE") ? (
                          <Server size={18} />
                        ) : (
                          <Monitor size={18} />
                        )}
                      </span>
                      <span>
                        <b>{d.hostname}</b>
                        <small>
                          {d.department || t("Unassigned", "غير محدد")}
                          {d.simulated && " · Synthetic"}
                        </small>
                      </span>
                    </button>
                  </td>
                  <td>
                    <div className="platform-cell">
                      <OSBadge device={d} />
                      <small>{d.win_user || "—"}</small>
                    </div>
                  </td>
                  <td>
                    <code>{d.ip || "—"}</code>
                  </td>
                  <td>
                    <Status online={d.online} />
                  </td>
                  <td>
                    <Badge>{d.agent_version || "Awaiting data"}</Badge>
                  </td>
                  <td>
                    <span className="ring-tag">{d.ring}</span>
                  </td>
                  <td className="text-muted">{relative(d.last_seen)}</td>
                  <td>
                    <button
                      className="icon-btn"
                      aria-label={`View ${d.hostname}`}
                      onClick={() => setSelected(d)}
                    >
                      <MoreHorizontal size={20} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!rows.length && (
          <Empty
            title={t("No matching endpoints", "لا توجد أجهزة مطابقة")}
            description={
              data.items.length
                ? t(
                    "Try a different search or filter.",
                    "جرّب بحثاً أو تصفية مختلفة.",
                  )
                : t(
                    "Install and enroll a Windows agent to start receiving device data.",
                    "ثبّت عميل Windows وسجله لعرض بيانات الأجهزة.",
                  )
            }
            icon={Monitor}
          />
        )}
        <div className="table-footer">
          <span>
            {rows.length} {t("endpoints shown", "جهاز معروض")}
          </span>
          <span>
            <span className="tiny-dot" />
            {t("Heartbeat window: 90 seconds", "نافذة الاتصال: ٩٠ ثانية")}
          </span>
        </div>
      </section>
      {selected && (
        <Modal
          title={selected.hostname}
          description={t(
            "Endpoint details and control history",
            "تفاصيل الجهاز وسجل التحكم",
          )}
          onClose={() => setSelected(null)}
        >
          <div className="device-detail-header">
            <div className="detail-device-icon">
              <Monitor size={28} />
            </div>
            <div>
              <Status
                online={
                  data.items.find((d: Row) => d.id === selected.id)?.online ||
                  false
                }
              />
              {selected.simulated && (
                <Badge tone="purple">Synthetic lab device</Badge>
              )}
            </div>
          </div>
          <dl className="detail-grid">
            {[
              ["IP address", selected.ip],
              ["MAC address", selected.mac],
              ["Reported user", selected.win_user],
              ["Department", selected.department],
              ["Agent version", selected.agent_version],
              ["Operating system", selected.os_version || selected.os_family],
              ["Architecture", selected.architecture],
              [
                "CPU utilization",
                selected.cpu_percent === null ||
                selected.cpu_percent === undefined
                  ? "Not reported"
                  : `${Number(selected.cpu_percent).toFixed(1)}%`,
              ],
              [
                "Memory usage",
                formatCapacity(
                  selected.memory_used_mb,
                  selected.memory_total_mb,
                ),
              ],
              [
                "System volume",
                formatCapacity(selected.disk_used_mb, selected.disk_total_mb),
              ],
              ["Uptime", uptime(selected.uptime_seconds)],
              [
                "Metrics sampled",
                selected.telemetry_at
                  ? relative(selected.telemetry_at)
                  : "Not reported",
              ],
              [
                "Last heartbeat",
                selected.last_seen ? clock(selected.last_seen) : "Not yet seen",
              ],
            ].map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value || "—"}</dd>
              </div>
            ))}
          </dl>
          <div className="detail-section">
            <OSBadge device={selected} />
            <p className="helper" style={{ marginTop: 10 }}>
              {selected.monitoring_message ||
                "Monitoring coverage has not been reported yet."}
            </p>
            {selected.monitoring_status === "partial" && (
              <Badge tone="orange">Partial coverage</Badge>
            )}
          </div>
          <div className="detail-section">
            <label>
              Deployment ring
              <select
                value={selected.ring}
                onChange={(e) => void changeRing(e.target.value)}
              >
                {["pilot", "ring20", "ring50", "all"].map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="detail-section">
            <h3>
              <Terminal size={16} /> {t("Endpoint commands", "أوامر الأجهزة")}
            </h3>
            {!session.remote_commands ? (
              <div className="notice">
                <Eye size={17} />
                <p>
                  {t(
                    "This connection test is monitoring-only. No restriction commands will be sent.",
                    "اختبار الاتصال للمراقبة فقط. لن تُرسل أوامر تقييد.",
                  )}
                </p>
              </div>
            ) : (
              <div className="command-row">
                <select value={cmd} onChange={(e) => setCmd(e.target.value)}>
                  <option value="collect_logs">Collect audit metadata</option>
                  <option value="sync_policy">Refresh Group Policy</option>
                  <option value="lock_usb">Block USB storage startup</option>
                  <option value="restore_usb">Restore saved USB setting</option>
                  <option value="isolate_smb">
                    Disconnect all SMB sessions
                  </option>
                </select>
                <button
                  className="btn primary"
                  onClick={sendCommand}
                  disabled={sending}
                >
                  Send
                </button>
              </div>
            )}
            <div className="command-history">
              {data.commands
                .filter((c: Row) => c.device_id === selected.id)
                .map((c: Row) => (
                  <div key={c.id}>
                    <b>{c.command}</b>
                    <Badge
                      tone={
                        c.status === "failed"
                          ? "rose"
                          : c.status === "completed"
                            ? "green"
                            : "muted"
                      }
                    >
                      {c.status}
                    </Badge>
                    <p>{c.output || "Waiting for the device."}</p>
                  </div>
                ))}
            </div>
          </div>
        </Modal>
      )}
      {enroll && (
        <Modal
          title={t("Connect an endpoint", "ربط جهاز")}
          description={t(
            "Start with one pilot PC and the file-server agent.",
            "ابدأ بجهاز تجريبي وعميل خادم الملفات.",
          )}
          onClose={() => setEnroll(false)}
        >
          <div className="enroll-guide">
            <div className="tabs agent-tabs">
              <button
                onClick={() => setAgentPlatform("windows")}
                className={agentPlatform === "windows" ? "active" : ""}
              >
                <Monitor size={14} />
                Windows
              </button>
              <button
                onClick={() => setAgentPlatform("linux")}
                className={agentPlatform === "linux" ? "active" : ""}
              >
                <Terminal size={14} />
                Linux
              </button>
            </div>
            <a
              className="btn primary agent-download"
              href={`/agents/${agentPlatform}-agent.zip`}
            >
              <ArrowDownToLine size={15} />
              Download {agentPlatform === "linux" ? "Linux" : "Windows"} agent
            </a>
            {agentPlatform === "linux" ? (
              <>
                <p className="helper">
                  Python 3.10+ is required. The read-only agent reports Linux
                  inventory, CPU, memory, disk and uptime. It observes file
                  metadata in the directories you assign to its hostname.
                </p>
                <pre>
                  {
                    "sudo python3 install_linux.py --server https://YOUR-WINDOWS-PC:8443 --ca-file console-root-ca.crt"
                  }
                </pre>
                <p className="helper">
                  Enter the enrollment token locally. Then register a Linux
                  folder in Shared folders, selecting this enrolled hostname. No
                  file contents or permission changes are sent.
                </p>
              </>
            ) : (
              <>
                <div className="notice">
                  <ShieldCheck size={18} />
                  <p>
                    {t(
                      "Use a trusted HTTPS console address on your hospital network. The enrollment token is entered locally.",
                      "استخدم عنوان HTTPS موثوقاً وأدخل رمز التسجيل محلياً.",
                    )}
                  </p>
                </div>
                <ol>
                  <li>
                    Copy the supplied <code>agent</code> folder to the Windows
                    computer.
                  </li>
                  <li>Open an elevated PowerShell window.</li>
                  <li>
                    Run the installer with your console URL and enrollment
                    token.
                  </li>
                </ol>
                <pre>
                  {
                    '.\\Install-LocalAgent.ps1 `\n  -ServerUrl "https://fileguard.example.local" `\n  -EnrollToken $token -Ring pilot'
                  }
                </pre>
                <p className="helper">
                  For EXAMPLE-FILE01, add <code>-Role fileserver</code> to
                  forward share audit metadata. Once enrolled, its heartbeat
                  should appear within 90 seconds.
                </p>
              </>
            )}
            <p className="helper">
              Demo devices are labeled. Real Windows and Linux devices appear
              after their own agents enroll against a reachable console.
            </p>
          </div>
        </Modal>
      )}
    </>
  );
}

function FileActivity() {
  const { t } = useLang();
  const [query, setQuery] = useState(""),
    [result, setResult] = useState(""),
    [page, setPage] = useState(1);
  const params = new URLSearchParams({ q: query, result, page: String(page) });
  const { data, error, load, refreshing } = useData("/events?" + params);
  if (!data)
    return error ? <ErrorBox message={error} retry={load} /> : <Loading />;
  return (
    <>
      <PageHeader
        eyebrow={t("SHARED-FILE OBSERVATIONS", "ملاحظات الملفات المشتركة")}
        title={t("File activity", "نشاط الملفات")}
        description={t(
          "Explore Windows access checks and Linux file-change observations.",
          "استعرض فحوص الوصول المبلغ عنها من خوادم الملفات.",
        )}
      >
        <button className="btn secondary" onClick={load}>
          <RefreshCw size={15} className={refreshing ? "spin" : ""} />
          {t("Refresh", "تحديث")}
        </button>
        <a
          className="btn primary"
          href={`/api/console/events/export?q=${encodeURIComponent(query)}&result=${result}`}
        >
          <ArrowDownToLine size={16} />
          {t("Export CSV", "تصدير CSV")}
        </a>
      </PageHeader>
      <div className="notice activity-notice">
        <Eye size={18} />
        <p>
          {t(
            "Observation, not enforcement. An allowed check is not proof that a file was deleted. Denied checks describe results reported by Windows.",
            "الملاحظات لا تطبق قيوداً. الفحص المسموح لا يثبت حذف ملف، والمرفوض يعكس نتيجة Windows.",
          )}
        </p>
      </div>
      <section className="panel">
        <div className="list-toolbar">
          <div className="tabs">
            {[
              ["", t("All activity", "جميع النشاطات")],
              ["allowed", t("Allowed", "مسموح")],
              ["blocked", t("Denied", "مرفوض")],
              ["observed", t("File changes", "تغييرات الملفات")],
            ].map(([value, label]) => (
              <button
                key={value}
                className={result === value ? "active" : ""}
                onClick={() => {
                  setResult(value);
                  setPage(1);
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <label className="search-input">
            <Search size={16} />
            <input
              aria-label="Search activity"
              placeholder={t(
                "Search device, user, or file…",
                "ابحث بالجهاز أو المستخدم أو الملف…",
              )}
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(1);
              }}
            />
          </label>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>{t("TIME", "الوقت")}</th>
                <th>{t("DEVICE / USER", "الجهاز / المستخدم")}</th>
                <th>{t("FILE PATH", "مسار الملف")}</th>
                <th>{t("ACTION", "الإجراء")}</th>
                <th>{t("RESULT", "النتيجة")}</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((e: Row) => (
                <tr key={e.id}>
                  <td className="nowrap text-muted">{clock(e.ts)}</td>
                  <td>
                    <div className="stack-cell">
                      <b>{e.device}</b>
                      <small>{e.win_user || "—"}</small>
                    </div>
                  </td>
                  <td>
                    <div className="file-cell">
                      <FileText size={16} />
                      <div>
                        <b>{e.file?.split(/[\\/]/).pop() || "—"}</b>
                        <code title={e.file}>{e.file}</code>
                      </div>
                    </div>
                  </td>
                  <td>
                    <Badge>{e.action}</Badge>
                  </td>
                  <td>
                    <Result value={e.result} />
                    {e.process === "SIMULATOR" && (
                      <small className="synthetic-label">Synthetic</small>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!data.items.length && (
          <Empty
            title={t("No access checks to display", "لا توجد فحوص وصول")}
            description={t(
              "Try another filter, or connect a file-server agent to start the feed.",
              "جرّب تصفية أخرى أو اربط عميل خادم الملفات.",
            )}
            icon={Activity}
          />
        )}
        <div className="table-footer">
          <span>
            {data.total.toLocaleString()} {t("observations", "ملاحظة")}
          </span>
          <div className="pagination">
            <button
              className="icon-btn"
              aria-label="Previous page"
              disabled={page === 1}
              onClick={() => setPage(page - 1)}
            >
              <ChevronLeft size={16} />
            </button>
            <span>
              {t("Page", "صفحة")} {page} /{" "}
              {Math.max(1, Math.ceil(data.total / 25))}
            </span>
            <button
              className="icon-btn"
              aria-label="Next page"
              disabled={page * 25 >= data.total}
              onClick={() => setPage(page + 1)}
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      </section>
    </>
  );
}

function Shares() {
  const { t } = useLang(),
    toast = useToast();
  const { data, error, load } = useData("/shares");
  const fleet = useData("/devices", 30000);
  const [targetOS, setTargetOS] = useState("windows"),
    [targetHost, setTargetHost] = useState("");
  const [adding, setAdding] = useState(false),
    [path, setPath] = useState(""),
    [busy, setBusy] = useState(false),
    [formError, setFormError] = useState("");
  async function add(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/shares", {
        method: "POST",
        body: JSON.stringify({
          path,
          target_os: targetOS,
          target_host: targetHost,
        }),
      });
      setAdding(false);
      setPath("");
      toast("Monitoring target registered.");
      void load();
    } catch (e) {
      setFormError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function remove(row: Row) {
    if (
      !window.confirm(
        `Remove ${row.path} from monitoring? This does not change its Windows permissions.`,
      )
    )
      return;
    try {
      await api(`/shares/${row.id}`, { method: "DELETE" });
      toast("Monitoring target removed.");
      void load();
    } catch (e) {
      toast((e as Error).message, true);
    }
  }
  if (!data)
    return error ? <ErrorBox message={error} retry={load} /> : <Loading />;
  return (
    <>
      <PageHeader
        eyebrow={t("SHARE VISIBILITY", "متابعة المشاركات")}
        title={t("Shared folders", "المجلدات المشتركة")}
        description={t(
          "Define the exact paths your file-server agents should observe.",
          "حدد المسارات التي يجب أن يراقبها عملاء خوادم الملفات.",
        )}
      >
        <button className="btn secondary" onClick={load}>
          <RefreshCw size={15} />
          {t("Refresh", "تحديث")}
        </button>
        <button
          className="btn primary"
          onClick={() => {
            setAdding(true);
            setFormError("");
          }}
        >
          <Plus size={16} />
          {t("Register share", "تسجيل مشاركة")}
        </button>
      </PageHeader>
      <div className="notice activity-notice">
        <FolderOpen size={18} />
        <p>
          {t(
            "Choose Windows UNC shares or Linux directories. Registration changes monitoring scope, not file permissions.",
            "تسجيل المسار يحدد نطاق المراقبة ولا يغير صلاحيات NTFS أو يثبت حماية المشاركة.",
          )}
        </p>
      </div>
      <div className="shares-grid">
        {data.items.map((f: Row) => (
          <section className="panel share-card" key={f.id}>
            <div className="share-card-top">
              <div className="share-folder-icon">
                <FolderOpen size={25} />
              </div>
              <button
                className="icon-btn"
                aria-label={`Remove ${f.path}${f.target_host ? " on " + f.target_host : ""}`}
                onClick={() => void remove(f)}
              >
                <Trash2 size={17} />
              </button>
            </div>
            <Badge tone={f.path.startsWith("\\\\SIM-") ? "purple" : "blue"}>
              {f.path.startsWith("\\\\SIM-")
                ? "Synthetic lab share"
                : t("Monitoring target", "هدف مراقبة")}
            </Badge>
            <h2>
              {f.target_os === "linux"
                ? f.path.split("/").filter(Boolean).pop() || f.path
                : f.path.split("\\").filter(Boolean).slice(1).join(" / ") ||
                  f.path}
            </h2>
            <code>{f.path}</code>
            {f.target_os === "linux" && (
              <p className="helper">Linux · {f.target_host}</p>
            )}
            <div className="share-card-info">
              <div>
                <span>{t("Observation", "الملاحظة")}</span>
                <b>
                  {f.probe
                    ? f.probe.result.replaceAll("_", " ")
                    : f.target_os === "linux"
                      ? t("Metadata changes", "تغييرات البيانات الوصفية")
                      : t("Awaiting agent", "بانتظار العميل")}
                </b>
              </div>
              <div>
                <span>
                  {t(
                    f.target_os === "linux"
                      ? "Agent last seen"
                      : "Last ACL review",
                    f.target_os === "linux"
                      ? "آخر ظهور للعميل"
                      : "آخر مراجعة ACL",
                  )}
                </span>
                <b>
                  {f.target_os === "linux"
                    ? relative(
                        (fleet.data?.items || []).find(
                          (d: Row) =>
                            d.hostname.toLowerCase() ===
                            String(f.target_host).toLowerCase(),
                        )?.last_seen,
                      )
                    : f.probe
                      ? relative(f.probe.ts)
                      : "—"}
                </b>
              </div>
            </div>
            <div className="share-card-foot">
              <CircleHelp size={14} />
              {t(
                f.target_os === "linux"
                  ? "Read-only observation; file contents are not collected"
                  : "Effective protection is unverified",
                "الحماية الفعلية غير مثبتة",
              )}
            </div>
          </section>
        ))}
      </div>
      {!data.items.length && (
        <section className="panel">
          <Empty
            title={t("Bring your shares into view", "أضف مشاركاتك للمراقبة")}
            description={t(
              "Register a UNC path and connect its file-server agent.",
              "سجل مسار UNC واربط عميل خادم الملفات.",
            )}
            action={
              <button className="btn primary" onClick={() => setAdding(true)}>
                <Plus size={15} />
                Register share
              </button>
            }
          />
        </section>
      )}
      {adding && (
        <Modal
          title={t("Register a monitoring target", "تسجيل هدف للمراقبة")}
          description={t(
            "Use an exact UNC share or subfolder path.",
            "استخدم مسار UNC محدداً للمشاركة أو المجلد.",
          )}
          onClose={() => setAdding(false)}
        >
          <form className="modal-form" onSubmit={add}>
            <label>
              Platform
              <select
                aria-label="Folder platform"
                value={targetOS}
                onChange={(e) => {
                  setTargetOS(e.target.value);
                  setPath("");
                  setTargetHost("");
                }}
              >
                <option value="windows">Windows / SMB</option>
                <option value="linux">Linux directory</option>
              </select>
            </label>
            {targetOS === "linux" && (
              <label>
                Linux device
                <select
                  aria-label="Linux target device"
                  value={targetHost}
                  onChange={(e) => setTargetHost(e.target.value)}
                  required
                >
                  <option value="">Select an enrolled Linux device</option>
                  {(fleet.data?.items || [])
                    .filter((d: Row) => d.os_family === "linux")
                    .map((d: Row) => (
                      <option key={d.id} value={d.hostname}>
                        {d.hostname}
                      </option>
                    ))}
                </select>
              </label>
            )}
            <label>
              {t("Share path", "مسار المشاركة")}
              <input
                autoFocus
                value={path}
                onChange={(e) => setPath(e.target.value)}
                placeholder={
                  targetOS === "linux" ? "/srv/shared" : "\\\\EXAMPLE-FILE01\\E"
                }
                required
              />
            </label>
            <p className="helper">
              The matching file-server agent receives this path on its next
              configuration refresh. Wildcards and administrative share
              discovery are not automatic.
            </p>
            {formError && (
              <div className="form-error" role="alert">
                {formError}
              </div>
            )}
            <div className="modal-foot">
              <button
                type="button"
                className="btn secondary"
                onClick={() => setAdding(false)}
              >
                Cancel
              </button>
              <button
                className="btn primary"
                disabled={busy || (targetOS === "linux" && !targetHost)}
              >
                {busy ? (
                  <Loader2 size={16} className="spin" />
                ) : (
                  <Plus size={16} />
                )}
                Register share
              </button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}

function Approvals({ session }: { session: any }) {
  const { t } = useLang(),
    toast = useToast();
  const { data, error, load } = useData("/requests");
  const [filter, setFilter] = useState("all"),
    [adding, setAdding] = useState(false),
    [form, setForm] = useState({
      requester: "",
      action: "Delete",
      path: "",
      reason: "",
    }),
    [formError, setFormError] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/requests", { method: "POST", body: JSON.stringify(form) });
      setAdding(false);
      setForm({ requester: "", action: "Delete", path: "", reason: "" });
      toast("Request recorded for review.");
      void load();
    } catch (e) {
      setFormError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function decide(r: Row, action: string) {
    if (
      !window.confirm(
        `${action} request #${r.id}? AD grants apply to the action-wide approval group, not just this file path.`,
      )
    )
      return;
    try {
      await api(`/requests/${r.id}/${action}`, { method: "POST", body: "{}" });
      toast("Request updated.");
      void load();
    } catch (e) {
      toast((e as Error).message, true);
    }
  }
  if (!data)
    return error ? <ErrorBox message={error} retry={load} /> : <Loading />;
  const rows = data.items.filter(
    (r: Row) => filter === "all" || r.status === filter,
  );
  return (
    <>
      <PageHeader
        eyebrow={t("ACCESS GOVERNANCE", "إدارة الوصول")}
        title={t("Access requests", "طلبات الوصول")}
        description={t(
          "Review documented requests for temporary file-operation permissions.",
          "راجع الطلبات الموثقة لصلاحيات عمليات الملفات المؤقتة.",
        )}
      >
        <button
          className="btn primary"
          onClick={() => {
            setAdding(true);
            setFormError("");
          }}
        >
          <Plus size={16} />
          {t("Record a request", "تسجيل طلب")}
        </button>
      </PageHeader>
      {!session.directory_writes && (
        <div className="notice activity-notice">
          <Eye size={18} />
          <p>
            {t(
              "Monitoring mode: requests can be recorded, but approvals will not change Active Directory membership.",
              "وضع المراقبة: يمكنك تسجيل الطلبات دون تغيير عضوية Active Directory.",
            )}
          </p>
        </div>
      )}
      <section className="panel">
        <div className="list-toolbar">
          <div className="tabs">
            {["all", "pending", "approved", "rejected"].map((value) => (
              <button
                key={value}
                className={filter === value ? "active" : ""}
                onClick={() => setFilter(value)}
              >
                {value[0].toUpperCase() + value.slice(1)}
                {value === "pending" && (
                  <span className="tab-count">{data.counts.pending}</span>
                )}
              </button>
            ))}
          </div>
          <span className="text-muted small">{data.items.length} requests</span>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>REQUEST</th>
                <th>REQUESTER</th>
                <th>FILE / REASON</th>
                <th>STATUS</th>
                <th>CREATED</th>
                <th>DECISION</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r: Row) => (
                <tr key={r.id}>
                  <td>
                    <b>#{r.id}</b>
                    <small className="block text-muted">{r.action}</small>
                  </td>
                  <td>{r.requester}</td>
                  <td>
                    <div className="stack-cell">
                      <code>{r.path}</code>
                      <small>{r.reason}</small>
                    </div>
                  </td>
                  <td>
                    <Badge
                      tone={
                        r.status === "approved"
                          ? "green"
                          : r.status === "pending"
                            ? "orange"
                            : "muted"
                      }
                    >
                      {r.status}
                    </Badge>
                  </td>
                  <td className="nowrap text-muted">{clock(r.created_at)}</td>
                  <td>
                    {r.status === "pending" ? (
                      <div className="button-pair">
                        <button
                          className="btn small-btn secondary"
                          disabled={!session.directory_writes}
                          onClick={() => void decide(r, "approve")}
                        >
                          Approve
                        </button>
                        <button
                          className="btn small-btn text"
                          onClick={() => void decide(r, "reject")}
                        >
                          Reject
                        </button>
                      </div>
                    ) : r.status === "approved" ? (
                      <button
                        className="btn small-btn secondary"
                        disabled={!session.directory_writes}
                        onClick={() => void decide(r, "revoke")}
                      >
                        Revoke
                      </button>
                    ) : (
                      <span className="text-muted">Reviewed</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!rows.length && (
          <Empty
            title={t("Nothing waiting here", "لا توجد طلبات هنا")}
            description={t(
              "Documented access requests will appear in this queue.",
              "ستظهر طلبات الوصول الموثقة في هذه القائمة.",
            )}
            icon={ClipboardCheck}
          />
        )}
      </section>
      {adding && (
        <Modal
          title={t("Record an access request", "تسجيل طلب وصول")}
          description="Administrator-entered request. Staff SSO is not configured."
          onClose={() => setAdding(false)}
        >
          <form className="modal-form" onSubmit={submit}>
            <div className="form-grid">
              <label>
                Windows username
                <input
                  autoFocus
                  required
                  value={form.requester}
                  onChange={(e) =>
                    setForm({ ...form, requester: e.target.value })
                  }
                  placeholder="username"
                />
              </label>
              <label>
                Requested operation
                <select
                  value={form.action}
                  onChange={(e) => setForm({ ...form, action: e.target.value })}
                >
                  {["Delete", "Upload", "Send"].map((x) => (
                    <option key={x}>{x}</option>
                  ))}
                </select>
              </label>
            </div>
            <label>
              File path
              <input
                required
                value={form.path}
                onChange={(e) => setForm({ ...form, path: e.target.value })}
                placeholder="\\EXAMPLE-FILE01\E\folder\file.pdf"
              />
            </label>
            <label>
              Reason
              <textarea
                required
                minLength={3}
                maxLength={300}
                value={form.reason}
                onChange={(e) => setForm({ ...form, reason: e.target.value })}
                placeholder="Explain the operation and the business reason."
              />
            </label>
            {formError && <div className="form-error">{formError}</div>}
            <div className="modal-foot">
              <button
                type="button"
                className="btn secondary"
                onClick={() => setAdding(false)}
              >
                Cancel
              </button>
              <button className="btn primary" disabled={busy}>
                Record request
                <ArrowRight size={15} />
              </button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}

function Audit() {
  const { t } = useLang();
  const { data, error, load } = useData("/audit", 15000);
  const [query, setQuery] = useState("");
  if (!data)
    return error ? <ErrorBox message={error} retry={load} /> : <Loading />;
  const rows = data.items.filter((r: Row) =>
    [r.actor, r.action, r.target]
      .join(" ")
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  return (
    <>
      <PageHeader
        eyebrow={t("ACCOUNTABILITY & TRACEABILITY", "التتبع والمساءلة")}
        title={t("Audit trail", "سجل التدقيق")}
        description={t(
          "A hash-chained record of console and administrator activity.",
          "سجل مترابط بالبصمات لنشاط المسؤولين ووحدة التحكم.",
        )}
      >
        <button className="btn secondary" onClick={load}>
          <RefreshCw size={15} />
          Verify & refresh
        </button>
      </PageHeader>
      <div className={`integrity-banner ${data.integrity ? "" : "bad"}`}>
        <ShieldCheck size={24} />
        <div>
          <b>
            {data.integrity
              ? t("Audit chain verified", "تم التحقق من سلسلة التدقيق")
              : t(
                  "Audit integrity requires review",
                  "تتطلب سلامة السجل المراجعة",
                )}
          </b>
          <p>
            {data.integrity
              ? t(
                  "Stored entries match their recorded hash links.",
                  "السجلات متطابقة مع روابط البصمات المخزنة.",
                )
              : `First broken entry: #${data.broken_at}`}
          </p>
        </div>
        <Badge tone={data.integrity ? "green" : "rose"}>
          {data.integrity ? "Intact" : "Review required"}
        </Badge>
      </div>
      <section className="panel">
        <div className="list-toolbar">
          <h2>Recent entries</h2>
          <label className="search-input">
            <Search size={16} />
            <input
              aria-label="Search audit trail"
              placeholder="Search actor, action, or target…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>TIME</th>
                <th>ACTOR</th>
                <th>ACTION</th>
                <th>TARGET</th>
                <th>OUTCOME</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r: Row) => (
                <tr key={r.id}>
                  <td className="text-muted nowrap">{clock(r.ts)}</td>
                  <td>
                    <div className="audit-actor">
                      <span className="mini-avatar">
                        {(r.actor || "?").slice(0, 1).toUpperCase()}
                      </span>
                      {r.actor || "Anonymous"}
                    </div>
                  </td>
                  <td>
                    <code className="audit-code">{r.action}</code>
                  </td>
                  <td className="audit-target">{r.target}</td>
                  <td>
                    <Badge
                      tone={
                        ["success", "completed"].includes(r.outcome)
                          ? "green"
                          : ["failed", "error", "denied"].includes(r.outcome)
                            ? "rose"
                            : "muted"
                      }
                    >
                      {r.outcome}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!rows.length && (
          <Empty
            title="No matching audit entries"
            description="Try another search term."
            icon={FileCheck2}
          />
        )}
        <div className="table-footer">
          Showing up to 200 recent entries · Hash verification covers the
          complete stored chain.
        </div>
      </section>
    </>
  );
}

function System() {
  const { t } = useLang(),
    toast = useToast();
  const { data, error, load, refreshing } = useData("/system", 15000);
  const settings = useData("/settings", 60000);
  const [minutes, setMinutes] = useState(30),
    [saving, setSaving] = useState(false);
  useEffect(() => {
    if (settings.data)
      setMinutes(Number(settings.data.values.approval_minutes));
  }, [settings.data]);
  if (!data)
    return error ? <ErrorBox message={error} retry={load} /> : <Loading />;
  async function save(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await api("/settings", {
        method: "POST",
        body: JSON.stringify({ approval_minutes: minutes }),
      });
      toast("Approval duration saved.");
      void settings.load();
    } catch (e) {
      toast((e as Error).message, true);
    } finally {
      setSaving(false);
    }
  }
  return (
    <>
      <PageHeader
        eyebrow={t("WORKSPACE OPERATIONS", "عمليات مساحة العمل")}
        title={t("System & database", "النظام وقاعدة البيانات")}
        description={t(
          "Check your services, inspect stored data, and review configuration.",
          "تحقق من الخدمات والبيانات المخزنة وإعدادات مساحة العمل.",
        )}
      >
        <button className="btn secondary" onClick={load}>
          <RefreshCw size={15} className={refreshing ? "spin" : ""} />
          {t("Test connections", "اختبار الاتصالات")}
        </button>
      </PageHeader>
      <div className="service-grid">
        {[
          {
            name: "Backend API",
            sub: "Authenticated console and agent endpoints",
            ok: true,
            icon: Server,
          },
          {
            name: "Agent ingestion",
            sub: "Dedicated Windows-agent API",
            ok: data.agent.connected,
            icon: Wifi,
          },
          {
            name:
              data.database.engine === "mysql" ? "MySQL database" : "Database",
            sub: data.database.version,
            ok: data.database.connected,
            icon: Database,
          },
          {
            name: "Background worker",
            sub: data.worker.last_seen
              ? `Heartbeat ${relative(data.worker.last_seen)}`
              : "Waiting for a worker heartbeat",
            ok: data.worker.online,
            icon: Activity,
          },
        ].map((s) => (
          <div className="panel service-card" key={s.name}>
            <div className="service-icon">
              <s.icon size={23} />
            </div>
            <Status
              online={s.ok}
              label={s.ok ? "Connected" : "Awaiting heartbeat"}
            />
            <h2>{s.name}</h2>
            <p>{s.sub}</p>
          </div>
        ))}
      </div>
      <div className="dashboard-row system-row">
        <Panel
          title={t("Database explorer", "مستعرض قاعدة البيانات")}
          description={t(
            "Row counts queried from the connected database",
            "أعداد السجلات من قاعدة البيانات المتصلة",
          )}
          action={
            <a
              className="btn secondary small-btn"
              href="/api/console/system/schema"
            >
              <ArrowDownToLine size={14} />
              SQL schema
            </a>
          }
        >
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>TABLE</th>
                  <th>RECORDS</th>
                  <th>CONTENT</th>
                </tr>
              </thead>
              <tbody>
                {data.database.tables.map((table: Row) => (
                  <tr key={table.name}>
                    <td>
                      <span className="table-name">
                        <Database size={14} />
                        <code>{table.name}</code>
                      </span>
                    </td>
                    <td>
                      <b>{table.rows.toLocaleString()}</b>
                    </td>
                    <td className="text-muted small">
                      {
                        (
                          {
                            devices: "Enrolled agent identities",
                            file_events: "Reported access checks",
                            folders: "Registered share paths",
                            probes: "ACL observations",
                            requests: "Access request history",
                            device_commands: "Command queue and results",
                            audit: "Hash-chained audit entries",
                            admins: "Administrator accounts",
                            settings: "Preferences and worker heartbeat",
                          } as Record<string, string>
                        )[table.name]
                      }
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="table-footer">
            <ShieldCheck size={14} />
            Credentials, password hashes, and device keys are not displayed.
          </div>
        </Panel>
        <div className="system-right">
          <Panel
            title={t("Operating mode", "وضع التشغيل")}
            description={t(
              "Current runtime configuration",
              "إعدادات التشغيل الحالية",
            )}
          >
            <div className="config-list">
              {[
                ["Endpoint restrictions", data.configuration.remote_commands],
                ["AD membership changes", data.configuration.directory_writes],
                ["Device enrollment", data.configuration.enrollment],
              ].map(([label, enabled]) => (
                <div key={String(label)}>
                  <span>{String(label)}</span>
                  <Badge tone={enabled ? "green" : "muted"}>
                    {enabled ? "Enabled" : "Off"}
                  </Badge>
                </div>
              ))}
            </div>
            <div className="mode-description">
              <Eye size={17} />
              <p>
                {data.configuration.monitoring_only
                  ? "Connection testing and monitoring only. No blocking or permission changes are applied."
                  : "Controls are enabled by the server configuration. Review every command before sending."}
              </p>
            </div>
          </Panel>
          <Panel
            title={t("Approval preferences", "تفضيلات الموافقات")}
            description="Applies when directory approvals are enabled"
          >
            <form className="preferences-form" onSubmit={save}>
              <label>
                Default grant duration
                <div className="duration-input">
                  <input
                    type="number"
                    aria-label="Approval duration in minutes"
                    min="5"
                    max="120"
                    value={minutes}
                    onChange={(e) => setMinutes(Number(e.target.value))}
                  />
                  <span>minutes</span>
                </div>
              </label>
              <button className="btn secondary" disabled={saving}>
                {saving ? (
                  <Loader2 className="spin" size={14} />
                ) : (
                  <Check size={14} />
                )}
                Save preference
              </button>
            </form>
          </Panel>
        </div>
      </div>
      <Panel
        title={t(
          "Connect with MySQL Workbench",
          "الاتصال باستخدام MYSQL WORKBENCH",
        )}
        description={t(
          "Use the published MySQL port from your container environment.",
          "استخدم منفذ MySQL المنشور في بيئة الحاويات.",
        )}
      >
        <div className="workbench-layout">
          <div className="workbench-instructions">
            <div className="workbench-icon">
              <Database size={26} />
            </div>
            <div>
              <h3>Inspect the same database behind your console.</h3>
              <p>
                For this local test: Standard TCP/IP, host{" "}
                <code>127.0.0.1</code>, port <code>13306</code>, schema{" "}
                <code>nilehope_fileguard</code>. Use the application database account
                from the generated environment file.
              </p>
              <p className="helper">
                When deployed to your VM, publish the database to the intended
                hospital interface and use the VM address from your PC. The
                cloud lab has no connection to your hospital network.
              </p>
            </div>
          </div>
          <pre className="sql-preview">
            {
              "USE nilehope_fileguard;\n\nSELECT hostname, ip, agent_version, last_seen\nFROM devices\nORDER BY hostname;"
            }
          </pre>
        </div>
      </Panel>
    </>
  );
}

function App() {
  const [lang, setLang] = useState(
      localStorage.getItem("nile-language") || "en",
    ),
    [session, setSession] = useState<any>(null),
    [ready, setReady] = useState(false),
    [startupError, setStartupError] = useState(""),
    [toast, setToast] = useState<{ message: string; bad: boolean } | null>(
      null,
    );
  const notify = useCallback((message: string, bad = false) => {
    setToast({ message, bad });
  }, []);
  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 5000);
    return () => clearTimeout(id);
  }, [toast]);
  const bootstrap = useCallback(async () => {
    try {
      const data = await api("/session");
      setSession(data);
      setStartupError("");
    } catch (e) {
      setStartupError((e as Error).message);
    } finally {
      setReady(true);
    }
  }, []);
  useEffect(() => {
    void bootstrap();
    const handler = () => {
      setSession((s: any) => ({ ...s, user: null }));
      void bootstrap();
    };
    window.addEventListener("session-expired", handler);
    return () => window.removeEventListener("session-expired", handler);
  }, [bootstrap]);
  useEffect(() => {
    localStorage.setItem("nile-language", lang);
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  }, [lang]);
  async function logout() {
    try {
      await api("/logout", { method: "POST", body: "{}" });
      await bootstrap();
    } catch (e) {
      notify((e as Error).message, true);
    }
  }
  return (
    <Language.Provider
      value={{
        lang,
        t: (en, ar) => (lang === "ar" && ar ? ar : en),
        toggle: () => setLang(lang === "en" ? "ar" : "en"),
      }}
    >
      <ToastContext.Provider value={notify}>
        {!ready ? (
          <Loading />
        ) : startupError ? (
          <div className="startup-error">
            <ErrorBox message={startupError} retry={bootstrap} />
          </div>
        ) : session?.user ? (
          <BrowserRouter>
            <Shell session={session} onLogout={logout} />
          </BrowserRouter>
        ) : (
          <Login onLogin={(value) => setSession({ ...session, ...value })} />
        )}{" "}
        {toast && (
          <div className={`toast ${toast.bad ? "bad" : ""}`} role="status">
            {toast.bad ? <XCircle size={19} /> : <CheckCircle2 size={19} />}
            <span>{toast.message}</span>
            <button
              className="icon-btn"
              onClick={() => setToast(null)}
              aria-label="Dismiss notification"
            >
              <X size={15} />
            </button>
          </div>
        )}
      </ToastContext.Provider>
    </Language.Provider>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
