import { ArrowRight, BrainCircuit, CircleHelp, Clock3, Coins, Database, Hash, Layers3, Network, Route, ShieldCheck } from "lucide-react";
import { ContextReduction } from "../components/ContextReduction";
import { MetricCard } from "../components/MetricCard";
import type { GatewayMetrics, ModelInfo, RequestRecord } from "../types";

interface DashboardProps {
	metrics: GatewayMetrics | null;
	models: ModelInfo[];
	requests: RequestRecord[];
	isLoading: boolean;
	metricsError: string | null;
	requestsError: string | null;
	onOpenRequests: () => void;
}

const integer = new Intl.NumberFormat("en-US");
const currency = new Intl.NumberFormat("en-US", {
	style: "currency",
	currency: "USD",
	minimumFractionDigits: 2,
	maximumFractionDigits: 4,
});

const pipelineStages = [
	{ label: "Cache", detail: "Check for a match", icon: Database, tone: "green" },
	{ label: "Complexity", detail: "Assess the request", icon: BrainCircuit, tone: "blue" },
	{ label: "Context", detail: "Select relevant history", icon: Layers3, tone: "amber" },
	{ label: "Model router", detail: "Choose a model tier", icon: Route, tone: "rose" },
	{ label: "Quality", detail: "Review the response", icon: ShieldCheck, tone: "green" },
];

function tokenTotal(metrics: GatewayMetrics | null): number {
	return (metrics?.tokens_input ?? 0) + (metrics?.tokens_output ?? 0);
}

function metricNote(value: number, total: number): string {
	if (!total) return "No requests recorded";
	return `${((value / total) * 100).toFixed(1)}% of total requests`;
}

export default function Dashboard({
	metrics,
	models,
	requests,
	isLoading,
	metricsError,
	requestsError,
	onOpenRequests,
}: DashboardProps) {
	const total = metrics?.total_requests ?? 0;
	const cacheHits = metrics?.cache_hits ?? 0;
	const modelUsage = getModelUsage(requests, models);
	const knownModelRequests = modelUsage.reduce((sum, item) => sum + item.count, 0);
	const qualitySummary = getQualitySummary(requests, models);

	return (
		<div className="page-content">
			<div className="page-heading">
				<div>
					<div className="eyebrow"><span className="eyebrow__line" />INTELLIGENT MODEL ROUTING</div>
					<h1>Gateway overview</h1>
					<p className="page-subtitle">One considered path from prompt to response.</p>
				</div>
				<div className={`live-badge${metricsError ? " live-badge--offline" : isLoading ? " live-badge--loading" : ""}`}>
					<span />{metricsError ? "API OFFLINE" : isLoading ? "CONNECTING" : "LIVE DATA"}
				</div>
			</div>

			{metricsError && (
				<div className="notice notice--error" role="alert">
					<CircleHelp size={17} />
					<span>Metrics unavailable: {metricsError}</span>
				</div>
			)}

			<section className="metrics-grid" aria-label="Gateway metrics" aria-busy={isLoading}>
				<MetricCard
					label="Total requests"
					value={metrics ? integer.format(total) : isLoading ? "—" : "Unavailable"}
					note={metrics ? `${integer.format(metrics.llm_calls)} sent to models` : "GET /metrics"}
					icon={Network}
					accent="green"
				/>
				<MetricCard
					label="Cache hits"
					value={metrics ? integer.format(cacheHits) : isLoading ? "—" : "Unavailable"}
					note={metrics ? metricNote(cacheHits, total) : "GET /metrics"}
					icon={Database}
					accent="blue"
				/>
				<MetricCard
					label="Tokens used"
					value={metrics ? integer.format(tokenTotal(metrics)) : isLoading ? "—" : "Unavailable"}
					note={metrics ? `${integer.format(metrics.tokens_input)} in · ${integer.format(metrics.tokens_output)} out` : "GET /metrics"}
					icon={Hash}
					accent="amber"
				/>
				<MetricCard
					label="Estimated cost"
					value={metrics ? currency.format(metrics.estimated_cost) : isLoading ? "—" : "Unavailable"}
					note="USD · reported by gateway"
					icon={Coins}
					accent="rose"
				/>
				<MetricCard
					label="Average latency"
					value={metrics ? `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(metrics.average_latency_ms)} ms` : isLoading ? "—" : "Unavailable"}
					note="average response time"
					icon={Clock3}
					accent="teal"
				/>
			</section>

			<section className="dashboard-summary-grid" aria-label="Usage, cost, and request summary">
				<article className="summary-panel">
					<div className="summary-panel__heading">
						<div><div className="eyebrow">ROUTING MIX</div><h2>Model usage</h2></div>
						<span className="summary-panel__meta">{integer.format(knownModelRequests)} routed</span>
					</div>
					{knownModelRequests ? (
						<div className="usage-list">
							{modelUsage.map(({ tier, count, tone }) => {
								const percentage = (count / knownModelRequests) * 100;
								return (
									<div className="usage-row" key={tier}>
										<div className="usage-row__label"><span>{tier}</span><strong>{percentage.toFixed(0)}%</strong></div>
										<div className="usage-bar" role="progressbar" aria-label={`${tier} model usage`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(percentage)}>
											<span className={`usage-bar__fill usage-bar__fill--${tone}`} style={{ width: `${percentage}%` }} />
										</div>
									</div>
								);
							})}
						</div>
					) : (
						<div className="summary-empty">{isLoading ? "Loading request usage…" : "No model usage data recorded yet."}</div>
					)}
					{knownModelRequests > 0 && knownModelRequests < requests.length && (
						<p className="summary-panel__note">Percentages include requests matched to a configured model tier.</p>
					)}
				</article>

				<article className="summary-panel">
					<div className="summary-panel__heading">
						<div><div className="eyebrow">SPEND</div><h2>Cost</h2></div>
						<span className="summary-panel__meta">USD</span>
					</div>
					<div className="cost-comparison">
						<div className="cost-comparison__row">
							<span>Baseline</span>
							<strong>{metrics ? "Not reported" : isLoading ? "—" : "Unavailable"}</strong>
						</div>
						<div className="cost-comparison__row cost-comparison__row--gateway">
							<span>Your Gateway</span>
							<strong>{metrics ? currency.format(metrics.estimated_cost) : isLoading ? "—" : "Unavailable"}</strong>
						</div>
					</div>
					<p className="summary-panel__note">Gateway cost is reported by the API. A baseline cost is not currently available.</p>
				</article>

				<article className="summary-panel">
					<div className="summary-panel__heading">
						<div><div className="eyebrow">TRAFFIC</div><h2>Requests</h2></div>
						<span className="summary-panel__meta">ALL TIME</span>
					</div>
					<dl className="request-summary">
						<div><dt>Total</dt><dd>{metrics ? integer.format(total) : isLoading ? "—" : "Unavailable"}</dd></div>
						<div><dt>Cache Hits</dt><dd>{metrics ? integer.format(cacheHits) : isLoading ? "—" : "Unavailable"}</dd></div>
						<div><dt>Escalations</dt><dd>{metrics ? integer.format(metrics.escalations) : isLoading ? "—" : "Unavailable"}</dd></div>
					</dl>
				</article>
			</section>

			<section className="quality-cascade" aria-label="Quality and model cascade">
				<article className="summary-panel quality-panel">
					<div className="summary-panel__heading">
						<div><div className="eyebrow">QUALITY</div><h2>Response quality</h2></div>
						<span className="summary-panel__meta">{qualitySummary.evaluatedCount ? `${integer.format(qualitySummary.evaluatedCount)} REVIEWED` : "RECENT DATA"}</span>
					</div>
					{qualitySummary.evaluatedCount ? (
						<>
							<div className="quality-stats">
								<div className="quality-stat">
									<span>Passed</span>
									<strong className="quality-stat__pass">{qualitySummary.passPercent}%</strong>
								</div>
								<div className="quality-stat">
									<span>Escalated</span>
									<strong className="quality-stat__escalated">{qualitySummary.escalationPercent}%</strong>
								</div>
							</div>
							<div className="quality-bar" role="img" aria-label={`${qualitySummary.passPercent}% passed, ${qualitySummary.failPercent}% failed`}>
								<span className="quality-bar__pass" style={{ width: `${qualitySummary.passPercent}%` }} />
								<span className="quality-bar__fail" style={{ width: `${qualitySummary.failPercent}%` }} />
							</div>
							<p className="summary-panel__note">Based on completed, evaluated requests in recent history.</p>
						</>
					) : (
						<div className="quality-empty">{isLoading ? "Loading quality results…" : "Quality results will appear after evaluated requests are recorded."}</div>
					)}
				</article>

				<article className="summary-panel cascade-panel">
					<div className="summary-panel__heading">
						<div><div className="eyebrow">MODEL CASCADE</div><h2>Quality-gated routing</h2></div>
						<span className="summary-panel__meta">{qualitySummary.evaluatedCount ? "RECENT RESULTS" : "LIVE DATA"}</span>
					</div>
					{qualitySummary.evaluatedCount ? (
						<div className="cascade-flow">
							<div className="cascade-model">
								<span className="cascade-model__dot" />
								<strong>{qualitySummary.initialTier}</strong>
								<span className="cascade-model__caption">initial model</span>
							</div>
							<div className="cascade-branches">
								<div className="cascade-branch cascade-branch--pass">
									<span className="cascade-branch__line" aria-hidden="true" />
									<span className="cascade-branch__label">PASS</span>
									<strong>{qualitySummary.passPercent}%</strong>
								</div>
								<div className="cascade-branch cascade-branch--fail">
									<span className="cascade-branch__line" aria-hidden="true" />
									<span className="cascade-branch__label">FAIL</span>
									<strong>{qualitySummary.failPercent}%</strong>
									<span className="cascade-branch__arrow" aria-hidden="true">↓</span>
								</div>
							</div>
							<div className="cascade-model cascade-model--strong">
								<span className="cascade-model__dot" />
								<strong>{qualitySummary.escalationTier}</strong>
								<span className="cascade-model__caption">{qualitySummary.escalatedCount} escalated</span>
							</div>
						</div>
					) : (
						<div className="quality-empty">{isLoading ? "Loading model outcomes…" : "The cascade will appear when quality outcomes are available."}</div>
					)}
					<p className="summary-panel__note">Quality failures trigger escalation when another model tier is available.</p>
				</article>
			</section>

			<section className="section-block" aria-label="Context optimization">
				<ContextReduction context={metrics?.context ?? null} isLoading={isLoading} />
			</section>

			<section className="flow-section" aria-labelledby="flow-title">
				<div className="flow-heading">
					<div>
						<div className="eyebrow">MULTI-AGENT ORCHESTRATION</div>
						<h2 id="flow-title">How a request moves</h2>
					</div>
					<span className="flow-count">5 STAGES</span>
				</div>
				<div className="flow-track-viewport">
					<div className="flow-track">
						{pipelineStages.map(({ label, detail, icon: Icon, tone }, index) => (
							<div className="flow-unit" key={label}>
								<div className="flow-stage">
									<div className={`flow-stage__icon flow-stage__icon--${tone}`}><Icon size={18} strokeWidth={1.8} /></div>
									<div className="flow-stage__title"><span>0{index + 1}</span><strong>{label}</strong></div>
									<p>{detail}</p>
								</div>
								{index < pipelineStages.length - 1 && <ArrowRight className="flow-arrow" size={16} aria-hidden="true" />}
							</div>
						))}
					</div>
				</div>
			</section>

			<section className="section-block">
				<div className="section-heading">
					<div>
						<div className="eyebrow">ACTIVITY</div>
						<h2>Recent requests</h2>
					</div>
					<button className="text-button" onClick={onOpenRequests}>View all <span aria-hidden="true">↗</span></button>
				</div>
				{requestsError ? (
					<div className="empty-state empty-state--warning">
						<div className="empty-state__icon"><CircleHelp size={20} /></div>
						<div><strong>Request history is unavailable</strong><p>{requestsError}</p></div>
					</div>
				) : requests.length === 0 ? (
					<div className="empty-state">
						<div className="empty-state__icon"><ActivityIcon /></div>
						<div><strong>{isLoading ? "Loading request history" : "No requests to show"}</strong><p>{isLoading ? "Waiting for gateway data." : "Request records will appear here when available."}</p></div>
					</div>
				) : (
					<RequestRows requests={requests.slice(0, 5)} />
				)}
			</section>

			<div className="dashboard-footnote">
				<span className="footnote-dot" />
				<span>Metrics are reported by the gateway. No sample data is shown.</span>
			</div>
		</div>
	);
}

function getModelUsage(requests: RequestRecord[], models: ModelInfo[]) {
	const tiers = [
		{ tier: "Local", tone: "green" },
		{ tier: "Cheap", tone: "blue" },
		{ tier: "Strong", tone: "amber" },
	] as const;
	const counts = new Map(tiers.map(({ tier }) => [tier.toLowerCase(), 0]));

	for (const request of requests) {
		const recordedModel = request.final_model || request.selected_model;
		if (!recordedModel) continue;
		const configuredModel = models.find((model) => model.id.toLowerCase() === recordedModel.toLowerCase());
		const tier = (configuredModel?.tier || recordedModel).toLowerCase();
		if (counts.has(tier)) counts.set(tier, (counts.get(tier) ?? 0) + 1);
	}

	return tiers.map(({ tier, tone }) => ({ tier, tone, count: counts.get(tier.toLowerCase()) ?? 0 }));
}

function getQualitySummary(requests: RequestRecord[], models: ModelInfo[]) {
	const reviewed = requests.filter(
		(request) => request.completed === true
			&& (request.quality_status === "pass" || request.quality_status === "fail"),
	);
	const passed = reviewed.filter((request) => request.quality_status === "pass");
	const failed = reviewed.filter((request) => request.quality_status === "fail");
	const escalated = reviewed.filter((request) => request.escalated === true);
	const tierLabel = (modelId?: string | null) => {
		if (!modelId) return null;
		const model = models.find((item) =>
			item.id.toLowerCase() === modelId.toLowerCase()
				|| item.tier.toLowerCase() === modelId.toLowerCase(),
		);
		const tier = model?.tier ?? modelId;
		return tier.charAt(0).toUpperCase() + tier.slice(1);
	};
	const mostCommonTier = (records: RequestRecord[], field: "selected_model" | "final_model") => {
		const counts = new Map<string, number>();
		for (const request of records) {
			const tier = tierLabel(request[field]);
			if (tier) counts.set(tier, (counts.get(tier) ?? 0) + 1);
		}
		return [...counts].sort((left, right) => right[1] - left[1])[0]?.[0] ?? null;
	};
	const percentage = (count: number) => reviewed.length
		? Math.round((count / reviewed.length) * 100)
		: 0;

	return {
		evaluatedCount: reviewed.length,
		passPercent: percentage(passed.length),
		failPercent: percentage(failed.length),
		escalationPercent: percentage(escalated.length),
		escalatedCount: escalated.length,
		initialTier: mostCommonTier(reviewed, "selected_model") ?? "Initial model",
		escalationTier: mostCommonTier(escalated, "final_model") ?? "Strong",
	};
}

function ActivityIcon() {
	return <Network size={19} strokeWidth={1.7} />;
}

function RequestRows({ requests }: { requests: RequestRecord[] }) {
	return (
		<div className="table-wrap">
			<table className="data-table">
				<thead><tr><th>Request</th><th>Model</th><th>Tokens</th><th>Latency</th><th>Cost</th></tr></thead>
				<tbody>
					{requests.map((request) => (
						<tr key={request.id}>
							<td><span className="request-query">{request.query || `Request #${request.id}`}</span><span className="request-time">{formatTimestamp(request.timestamp)}</span></td>
							<td>{request.final_model || request.selected_model || "—"}</td>
							<td>{integer.format(request.total_tokens ?? ((request.input_tokens ?? 0) + (request.output_tokens ?? 0)))}</td>
							<td>{request.latency_ms == null ? "—" : `${Math.round(request.latency_ms)} ms`}</td>
							<td>{request.estimated_cost == null ? "—" : currency.format(request.estimated_cost)}</td>
						</tr>
					))}
				</tbody>
			</table>
		</div>
	);
}

export function formatTimestamp(timestamp?: string | null): string {
	if (!timestamp) return "Time not recorded";
	const date = new Date(timestamp);
	return Number.isNaN(date.getTime())
		? timestamp
		: date.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}
