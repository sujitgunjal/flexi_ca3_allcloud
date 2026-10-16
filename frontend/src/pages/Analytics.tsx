import {
	Activity,
	ChartNoAxesColumn,
	CircleHelp,
	Coins,
	Database,
	Hash,
	RefreshCw,
	Timer,
} from "lucide-react";
import { MetricCard } from "../components/MetricCard";
import type { AnalyticsData } from "../types";

interface AnalyticsProps {
	data: AnalyticsData | null;
	isLoading: boolean;
	isRefreshing: boolean;
	error: string | null;
	onRefresh: () => void;
}

const integer = new Intl.NumberFormat("en-US");
const decimal = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });
const currency = new Intl.NumberFormat("en-US", {
	style: "currency",
	currency: "USD",
	minimumFractionDigits: 2,
	maximumFractionDigits: 4,
});
const tones = ["green", "blue", "amber"] as const;

function formatOptional(value: number | null, formatter: Intl.NumberFormat, suffix = ""): string {
	return value === null ? "Not reported" : `${formatter.format(value)}${suffix}`;
}

export default function Analytics({
	data,
	isLoading,
	isRefreshing,
	error,
	onRefresh,
}: AnalyticsProps) {
	const modelRows = Object.entries(data?.model_usage ?? {}).sort((left, right) => right[1] - left[1]);
	const routedRequests = modelRows.reduce((total, [, count]) => total + count, 0);
	const maximumTrendRequests = Math.max(1, ...(data?.trend.map((point) => point.requests) ?? []));

	return (
		<div className="page-content">
			<div className="page-heading">
				<div>
					<div className="eyebrow"><span className="eyebrow__line" />TRAFFIC INSIGHTS</div>
					<h1>Analytics</h1>
					<p className="page-subtitle">Persisted gateway activity and request outcomes.</p>
				</div>
				<button className="refresh-button page-refresh" type="button" onClick={onRefresh} disabled={isRefreshing}>
					<RefreshCw size={14} className={isRefreshing ? "spin" : ""} />
					<span>{isRefreshing ? "Refreshing" : "Refresh data"}</span>
				</button>
			</div>

			{error && (
				<div className="notice notice--error" role="alert">
					<CircleHelp size={17} />
					<span>Analytics could not be loaded: {error}</span>
					<button className="text-button" type="button" onClick={onRefresh}>Retry</button>
				</div>
			)}

			{data?.total_requests === 0 && !isLoading && !error && (
				<div className="empty-state analytics-empty" role="status">
					<div className="empty-state__icon"><Activity size={19} /></div>
					<div><strong>No request history yet</strong><p>Analytics will update here after the gateway records requests.</p></div>
				</div>
			)}

			<section className="metrics-grid analytics-metrics" aria-label="Request analytics" aria-busy={isLoading}>
				<MetricCard label="Total requests" value={data ? integer.format(data.total_requests) : isLoading ? "—" : "Unavailable"} note={data ? `${integer.format(data.successful_requests)} successful · ${integer.format(data.failed_requests)} failed` : "Persisted request records"} icon={Activity} accent="green" />
				<MetricCard label="Cache hit rate" value={data ? formatOptional(data.cache_hit_rate === null ? null : data.cache_hit_rate * 100, decimal, "%") : isLoading ? "—" : "Unavailable"} note={data ? `${integer.format(data.cache_hits)} hits · ${integer.format(data.cache_misses)} misses` : "Known cache outcomes"} icon={Database} accent="blue" />
				<MetricCard label="Tokens consumed" value={data ? formatOptional(data.tokens_total, integer) : isLoading ? "—" : "Unavailable"} note={data ? `${formatOptional(data.tokens_input, integer)} input · ${formatOptional(data.tokens_output, integer)} output` : "Measured token usage"} icon={Hash} accent="amber" />
				<MetricCard label="Average latency" value={data ? formatOptional(data.average_latency_ms, decimal, " ms") : isLoading ? "—" : "Unavailable"} note="Across requests with a latency measurement" icon={Timer} accent="teal" />
				<MetricCard label="Estimated cost" value={data ? formatOptional(data.estimated_cost_total, currency) : isLoading ? "—" : "Unavailable"} note="Sum of costs reported by the gateway · USD" icon={Coins} accent="rose" />
			</section>

			<section className="dashboard-summary-grid analytics-panels" aria-label="Routing and request trends">
				<article className="summary-panel">
					<div className="summary-panel__heading">
						<div><div className="eyebrow">ROUTING MIX</div><h2>Model usage</h2></div>
						<span className="summary-panel__meta">{integer.format(routedRequests)} routed</span>
					</div>
					{modelRows.length ? (
						<div className="usage-list">
							{modelRows.map(([model, count], index) => {
								const percentage = routedRequests ? (count / routedRequests) * 100 : 0;
								return (
									<div className="usage-row" key={model}>
										<div className="usage-row__label"><span>{model}</span><strong>{integer.format(count)} · {percentage.toFixed(1)}%</strong></div>
										<div className="usage-bar" role="progressbar" aria-label={`${model} request share`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percentage}>
											<span className={`usage-bar__fill usage-bar__fill--${tones[index % tones.length]}`} style={{ width: `${percentage}%` }} />
										</div>
									</div>
								);
							})}
						</div>
					) : <div className="summary-empty">{isLoading ? "Loading model usage…" : "No model usage has been recorded."}</div>}
					<p className="summary-panel__note">Based on the final model when available, otherwise the selected model. Requests without model metadata are omitted.</p>
				</article>

				<article className="summary-panel">
					<div className="summary-panel__heading">
						<div><div className="eyebrow">REQUEST TREND</div><h2>Daily activity</h2></div>
						<span className="summary-panel__meta">LAST 30 DAYS</span>
					</div>
					{data?.trend.length ? (
						<div className="analytics-trend">
							{data.trend.map((point) => (
								<div className="analytics-trend__row" key={point.date}>
									<time dateTime={point.date}>{new Date(`${point.date}T00:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" })}</time>
									<div className="usage-bar" role="img" aria-label={`${point.date}: ${point.requests} requests`}>
										<span className="usage-bar__fill usage-bar__fill--green" style={{ width: `${(point.requests / maximumTrendRequests) * 100}%` }} />
									</div>
									<strong>{integer.format(point.requests)}</strong>
								</div>
							))}
						</div>
					) : <div className="summary-empty">{isLoading ? "Loading request trends…" : "No requests in the last 30 days."}</div>}
					<p className="summary-panel__note">Only dates with persisted requests are shown; token totals remain unavailable when no token measurements were recorded.</p>
				</article>

				<article className="summary-panel">
					<div className="summary-panel__heading">
						<div><div className="eyebrow">OPTIMIZATION</div><h2>Gateway outcomes</h2></div>
						<span className="summary-panel__meta">ALL TIME</span>
					</div>
					<dl className="request-summary analytics-summary">
						<div><dt>Successful</dt><dd>{data ? integer.format(data.successful_requests) : isLoading ? "—" : "Unavailable"}</dd></div>
						<div><dt>Failed</dt><dd>{data ? integer.format(data.failed_requests) : isLoading ? "—" : "Unavailable"}</dd></div>
						<div><dt>Outcome unknown</dt><dd>{data ? integer.format(data.unknown_outcome_requests) : isLoading ? "—" : "Unavailable"}</dd></div>
						<div><dt>Escalations · fallbacks</dt><dd>{data ? `${integer.format(data.escalations)} · ${integer.format(data.fallbacks)}` : isLoading ? "—" : "Unavailable"}</dd></div>
						<div><dt>Context tokens saved</dt><dd>{data ? formatOptional(data.context_tokens_saved, integer) : isLoading ? "—" : "Unavailable"}</dd></div>
						<div><dt>Context reduction</dt><dd>{data ? formatOptional(data.context_reduction_percent, decimal, "%") : isLoading ? "—" : "Unavailable"}</dd></div>
					</dl>
					<p className="summary-panel__note">{data?.context_requests ? `Context measurements from ${integer.format(data.context_requests)} requests.` : "Context optimization measurements have not been reported."}</p>
				</article>
			</section>

			{!data && !isLoading && !error && (
				<div className="empty-state empty-state--warning analytics-error" role="alert">
					<div className="empty-state__icon"><ChartNoAxesColumn size={19} /></div>
					<div><strong>Analytics data is unavailable</strong><p>Refresh the page to retry loading persisted request metrics.</p></div>
				</div>
			)}
		</div>
	);
}
