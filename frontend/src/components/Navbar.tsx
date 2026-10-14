import {
	Activity,
	ChartNoAxesColumn,
	FlaskConical,
	LayoutDashboard,
	MessageSquare,
	RefreshCw,
	Server,
	Workflow,
} from "lucide-react";

export type PageKey = "Dashboard" | "Models" | "Requests" | "Analytics" | "Evaluation" | "Chat";

const navigation: { label: PageKey; icon: typeof LayoutDashboard }[] = [
	{ label: "Dashboard", icon: LayoutDashboard },
	{ label: "Models", icon: Server },
	{ label: "Requests", icon: Activity },
	{ label: "Analytics", icon: ChartNoAxesColumn },
	{ label: "Evaluation", icon: FlaskConical },
	{ label: "Chat", icon: MessageSquare },
];

interface NavbarProps {
	activePage: PageKey;
	onNavigate: (page: PageKey) => void;
	onRefresh: () => void;
	isRefreshing: boolean;
	endpoint: string;
}

export function Navbar({ activePage, onNavigate, onRefresh, isRefreshing, endpoint }: NavbarProps) {
	return (
		<>
			<aside className="sidebar">
				<a className="brand" href="#dashboard" onClick={() => onNavigate("Dashboard")}>
					<span className="brand__mark"><Workflow size={17} strokeWidth={2} /></span>
					<span className="brand__wordmark">
						<span className="brand__name">Switchboard<span>.</span></span>
						<span className="brand__descriptor">AI ROUTING GATEWAY</span>
					</span>
				</a>

				<div className="sidebar__section-label">WORKSPACE</div>
				<nav className="sidebar__nav" aria-label="Main navigation">
					{navigation.map(({ label, icon: Icon }) => (
						<button
							key={label}
							className={`nav-link${activePage === label ? " nav-link--active" : ""}`}
							onClick={() => onNavigate(label)}
							aria-current={activePage === label ? "page" : undefined}
						>
							<Icon size={18} strokeWidth={1.8} />
							<span>{label}</span>
							{activePage === label && <span className="nav-link__indicator" />}
						</button>
					))}
				</nav>

				<div className="sidebar__bottom">
					<span className="environment-dot" />
					<div>
						<span className="sidebar__environment">LOCAL GATEWAY</span>
						<span className="sidebar__endpoint">{endpoint.replace(/^https?:\/\//, "")}</span>
					</div>
				</div>
			</aside>

			<header className="topbar">
				<div className="topbar__crumb"><span>Switchboard AI</span><span>/</span><strong>{activePage}</strong></div>
				<button className="refresh-button" onClick={onRefresh} disabled={isRefreshing}>
					<RefreshCw size={15} className={isRefreshing ? "spin" : ""} />
					<span>{isRefreshing ? "Refreshing" : "Refresh data"}</span>
				</button>
			</header>
		</>
	);
}
