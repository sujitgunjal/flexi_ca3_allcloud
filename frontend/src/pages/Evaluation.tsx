import { useRef, useState } from "react";
import { AlertCircle, CheckCircle2, FlaskConical, Play, RefreshCw } from "lucide-react";
import { runEvaluation } from "../services/api";
import type { EvaluationReport, EvaluationResults } from "../types";

interface EvaluationProps {
	results: EvaluationResults | null;
	isLoading: boolean;
	isRefreshing: boolean;
	error: string | null;
	onRefresh: () => void;
	onReport: (report: EvaluationReport) => void;
}

const percentage = new Intl.NumberFormat("en-US", {
	style: "percent",
	maximumFractionDigits: 1,
});

function displayPercent(value: number): string {
	return percentage.format(value);
}

export default function Evaluation({
	results,
	isLoading,
	isRefreshing,
	error,
	onRefresh,
	onReport,
}: EvaluationProps) {
	const [isRunning, setIsRunning] = useState(false);
	const [runError, setRunError] = useState<string | null>(null);
	const [runComplete, setRunComplete] = useState(false);
	const running = useRef(false);
	const report = results?.report ?? null;

	async function startEvaluation() {
		if (running.current) return;
		running.current = true;
		setIsRunning(true);
		setRunError(null);
		setRunComplete(false);
		try {
			const nextReport = await runEvaluation();
			onReport(nextReport);
			setRunComplete(true);
		} catch (runFailure) {
			setRunError(runFailure instanceof Error ? runFailure.message : "Evaluation could not be run.");
		} finally {
			running.current = false;
			setIsRunning(false);
		}
	}

	return (
		<div className="page-content">
			<div className="page-heading">
				<div>
					<div className="eyebrow"><span className="eyebrow__line" />QUALITY WORKSPACE</div>
					<h1>Evaluation</h1>
					<p className="page-subtitle">Stored decision-model evaluation results from the test split.</p>
				</div>
				<div className="evaluation-actions">
					<button className="refresh-button page-refresh" type="button" onClick={onRefresh} disabled={isRefreshing}>
						<RefreshCw size={14} className={isRefreshing ? "spin" : ""} />
						<span>{isRefreshing ? "Refreshing" : "Refresh data"}</span>
					</button>
					<button className="evaluation-run" type="button" onClick={() => void startEvaluation()} disabled={isRunning || isLoading}>
						<Play size={14} />
						<span>{isRunning ? "Running evaluation…" : "Run evaluation"}</span>
					</button>
				</div>
			</div>

			{error && (
				<div className="notice notice--error" role="alert">
					<AlertCircle size={17} />
					<span>Evaluation results could not be loaded: {error}</span>
					<button className="text-button" type="button" onClick={onRefresh}>Retry</button>
				</div>
			)}
			{runError && (
				<div className="notice notice--error" role="alert">
					<AlertCircle size={17} />
					<span>Evaluation failed: {runError}</span>
				</div>
			)}
			{runComplete && (
				<div className="notice evaluation-success" role="status">
					<CheckCircle2 size={17} />
					<span>Evaluation completed. The saved report has been updated.</span>
				</div>
			)}

			{isLoading && !report ? (
				<div className="empty-state empty-state--large" role="status">
					<div className="empty-state__icon"><RefreshCw size={19} className="spin" /></div>
					<div><strong>Loading evaluation results</strong><p>Retrieving the persisted report from the gateway.</p></div>
				</div>
			) : !report ? (
				<div className="empty-state empty-state--large">
					<div className="empty-state__icon"><FlaskConical size={21} /></div>
					<div>
						<strong>{error ? "Saved evaluation report unavailable" : "No saved evaluation report"}</strong>
						<p>{error ? "Retry loading the report, or run an evaluation if prediction data is available." : "Run the existing decision evaluator to score its persisted predictions. This does not call a model or run the separate gateway query dataset."}</p>
					</div>
				</div>
			) : (
				<>
					<section className="metrics-grid evaluation-metrics" aria-label="Evaluation summary">
						<article className="metric-card metric-card--green">
							<div className="metric-card__top"><span className="metric-card__label">Decision model</span><span className="metric-card__icon"><FlaskConical size={17} /></span></div>
							<strong className="metric-card__value evaluation-model">{report.decision_model}</strong>
							<span className="metric-card__note">Model named in the persisted evaluation report</span>
						</article>
						<article className="metric-card metric-card--blue">
							<div className="metric-card__top"><span className="metric-card__label">Scored test cases</span><span className="metric-card__icon"><FlaskConical size={17} /></span></div>
							<strong className="metric-card__value">{report.count}</strong>
							<span className="metric-card__note">{report.dataset.splits.test ?? report.count} test rows in dataset</span>
						</article>
						<article className="metric-card metric-card--amber">
							<div className="metric-card__top"><span className="metric-card__label">Invalid outputs</span><span className="metric-card__icon"><AlertCircle size={17} /></span></div>
							<strong className="metric-card__value">{report.invalid_outputs}</strong>
							<span className="metric-card__note">{report.invalid_outputs ? "Excluded from score calculations" : "No invalid outputs reported"}</span>
						</article>
						<article className="metric-card metric-card--teal">
							<div className="metric-card__top"><span className="metric-card__label">Calibration</span><span className="metric-card__icon"><CheckCircle2 size={17} /></span></div>
							<strong className="metric-card__value">{report.calibration_applied ? "Applied" : "Not applied"}</strong>
							<span className="metric-card__note">{report.calibration_rows} calibration rows</span>
						</article>
						<article className="metric-card metric-card--rose">
							<div className="metric-card__top"><span className="metric-card__label">Dataset size</span><span className="metric-card__icon"><FlaskConical size={17} /></span></div>
							<strong className="metric-card__value">{report.dataset.rows}</strong>
							<span className="metric-card__note">{report.split} split report</span>
						</article>
					</section>

					{!isLoading && !error && results?.available === false && (
						<div className="notice" role="status"><AlertCircle size={17} /><span>Showing a run result, but no saved report was returned by the latest refresh.</span></div>
					)}

					<section className="summary-panel evaluation-panel" aria-labelledby="evaluation-scores-title">
						<div className="summary-panel__heading">
							<div><div className="eyebrow">RAW VS CALIBRATED</div><h2 id="evaluation-scores-title">Test-set scores</h2></div>
							<span className="summary-panel__meta">SPLIT: {report.split.toUpperCase()}</span>
						</div>
						<div className="table-wrap">
							<table className="data-table evaluation-table">
								<thead><tr><th>Task</th><th>Raw accuracy</th><th>Calibrated accuracy</th><th>Raw macro-F1</th><th>Calibrated macro-F1</th><th>Raw Brier</th><th>Calibrated Brier</th></tr></thead>
								<tbody>{Object.entries(report.tasks).map(([task, scores]) => (
									<tr key={task}>
										<td>{task}</td>
										<td>{displayPercent(scores.raw.accuracy)}</td>
										<td>{displayPercent(scores.calibrated.accuracy)}</td>
										<td>{displayPercent(scores.raw.macro_f1)}</td>
										<td>{displayPercent(scores.calibrated.macro_f1)}</td>
										<td>{scores.raw.brier_score.toFixed(4)}</td>
										<td>{scores.calibrated.brier_score.toFixed(4)}</td>
									</tr>
								))}</tbody>
							</table>
						</div>
						<p className="summary-panel__note">The evaluator reports raw and calibrated metrics; Brier score is a calibration-loss measure where lower is better. This table reports measurements without declaring a universal winner.</p>
					</section>

					<section className="summary-panel evaluation-panel" aria-labelledby="routing-results-title">
						<div className="summary-panel__heading">
							<div><div className="eyebrow">ROUTING VALIDATION</div><h2 id="routing-results-title">Routing comparison</h2></div>
							<span className="summary-panel__meta">VALIDATION-SELECTED THRESHOLD</span>
						</div>
						<dl className="request-summary">
							<div><dt>Selected threshold</dt><dd>{report.routing.validation_selected_threshold.toFixed(2)}</dd></div>
							<div><dt>Deployed threshold</dt><dd>{report.routing.deployed_threshold.toFixed(2)}</dd></div>
							<div><dt>Test routing accuracy</dt><dd>{displayPercent(report.routing.calibrated_at_selected_threshold.routing_accuracy)}</dd></div>
							<div><dt>Uncertain fallback rate</dt><dd>{displayPercent(report.routing.calibrated_at_selected_threshold.uncertain_rate)}</dd></div>
						</dl>
						<p className="summary-panel__note">Selected tiers reported by the evaluator: {Object.entries(report.routing.calibrated_at_selected_threshold.selected_model_counts).map(([model, count]) => `${model} ${count}`).join(" · ") || "Not reported"}.</p>
					</section>

					<details className="evaluation-method">
						<summary>Evaluation scope and methodology</summary>
						<p>{report.note}</p>
						<p>This report scores persisted raw predictions. Running evaluation recalculates metrics and rewrites the evaluator’s JSON, Markdown, and reliability-chart artifacts; it does not call the model or change routing policy.</p>
					</details>
				</>
			)}
		</div>
	);
}
