import type {
	AnalyticsData,
	Conversation,
	ConversationSummary,
	EvaluationReport,
	EvaluationResults,
	GatewayMetrics,
	ModelInfo,
	RequestRecord,
} from "../types";

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000")
	.replace(/\/$/, "");

async function requestJson<T>(
	path: string,
	init?: RequestInit,
	timeoutMs = 15000,
): Promise<T> {
	const controller = new AbortController();
	const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
	let response: Response;
	try {
		response = await fetch(`${API_BASE_URL}${path}`, {
			...init,
			signal: controller.signal,
		});
	} catch (error) {
		window.clearTimeout(timeout);
		if (controller.signal.aborted) {
			throw new Error(`${path} timed out after ${timeoutMs / 1000} seconds.`, { cause: error });
		}
		throw new Error(`Can't reach the gateway at ${API_BASE_URL}.`, { cause: error });
	}

	try {
		const body = response.status === 204 ? "" : await response.text();
		if (!response.ok) {
			let detail = `${path} returned ${response.status} ${response.statusText}.`;
			try {
				const payload: unknown = JSON.parse(body);
				if (payload && typeof payload === "object" && "detail" in payload
					&& typeof payload.detail === "string" && payload.detail) {
					detail = payload.detail;
				}
			} catch {
				// The status line remains useful when the error body is not JSON.
			}
			throw new GatewayResponseError(detail);
		}
		if (response.status === 204) {
			return undefined as T;
		}
		try {
			return JSON.parse(body) as T;
		} catch (error) {
			throw new Error(`${path} returned invalid JSON.`, { cause: error });
		}
	} catch (error) {
		if (controller.signal.aborted) {
			throw new Error(`${path} timed out after ${timeoutMs / 1000} seconds.`, { cause: error });
		}
		if (error instanceof GatewayResponseError) {
			throw error;
		}
		if (error instanceof Error && error.message.startsWith(`${path} returned `)) {
			throw error;
		}
		throw new Error(`${path} response could not be read.`, { cause: error });
	} finally {
		window.clearTimeout(timeout);
	}
}

class GatewayResponseError extends Error {}

function getJson<T>(path: string): Promise<T> {
	return requestJson<T>(path);
}

function postJson<T>(path: string): Promise<T> {
	return requestJson<T>(path, { method: "POST" }, 60000);
}

const metricFields: (keyof GatewayMetrics)[] = [
	"total_requests",
	"cache_hits",
	"cache_misses",
	"llm_calls",
	"tokens_input",
	"tokens_output",
	"estimated_cost",
	"average_latency_ms",
	"context_reduction_percent",
	"escalations",
	"fallbacks",
];

function isGatewayMetrics(value: unknown): value is GatewayMetrics {
	return typeof value === "object"
		&& value !== null
		&& metricFields.every((field) => typeof (value as Record<string, unknown>)[field] === "number");
}

function isRequestRecord(value: unknown): value is RequestRecord {
	return typeof value === "object"
		&& value !== null
		&& ("id" in value)
		&& (typeof value.id === "number" || typeof value.id === "string");
}

export async function getMetrics(): Promise<GatewayMetrics> {
	const payload: unknown = await getJson<unknown>("/metrics");
	if (isGatewayMetrics(payload)) {
		return payload;
	}
	if (isMetricsSummary(payload)) {
		return {
			total_requests: payload.total_requests,
			cache_hits: payload.cache.hits,
			cache_misses: payload.cache.misses,
			llm_calls: payload.cache.misses,
			tokens_input: payload.tokens.input,
			tokens_output: payload.tokens.output,
			estimated_cost: payload.cost.total,
			average_latency_ms: payload.latency.average_ms,
			context_reduction_percent: payload.context.overall_reduction_percent ?? 0,
			escalations: payload.escalation_count,
			fallbacks: payload.fallback_count,
			context: payload.context,
		};
	}
	throw new Error("/metrics returned an unsupported response format.");
}

interface MetricsSummaryPayload {
	total_requests: number;
	cache: { hits: number; misses: number };
	tokens: { input: number; output: number };
	cost: { total: number };
	latency: { average_ms: number };
	escalation_count: number;
	fallback_count: number;
	context: {
		requests_with_metrics: number;
		total_original_tokens: number;
		total_optimized_tokens: number;
		total_tokens_saved: number;
		overall_reduction_percent: number | null;
	};
}

function isMetricsSummary(value: unknown): value is MetricsSummaryPayload {
	if (!value || typeof value !== "object") return false;
	const summary = value as Record<string, unknown>;
	const cache = summary.cache as Record<string, unknown> | undefined;
	const tokens = summary.tokens as Record<string, unknown> | undefined;
	const cost = summary.cost as Record<string, unknown> | undefined;
	const latency = summary.latency as Record<string, unknown> | undefined;
	const context = summary.context as Record<string, unknown> | undefined;
	return typeof summary.total_requests === "number"
		&& typeof summary.escalation_count === "number"
		&& typeof summary.fallback_count === "number"
		&& typeof cache?.hits === "number"
		&& typeof cache?.misses === "number"
		&& typeof tokens?.input === "number"
		&& typeof tokens?.output === "number"
		&& typeof cost?.total === "number"
		&& typeof latency?.average_ms === "number"
		&& typeof context?.requests_with_metrics === "number"
		&& typeof context?.total_original_tokens === "number"
		&& typeof context?.total_optimized_tokens === "number"
		&& typeof context?.total_tokens_saved === "number"
		&& (typeof context?.overall_reduction_percent === "number"
			|| context?.overall_reduction_percent === null);
}

export function getModels(): Promise<ModelInfo[]> {
	return getJson<ModelInfo[]>("/models");
}

export async function getAnalytics(): Promise<AnalyticsData> {
	const payload: unknown = await getJson<unknown>("/metrics/analytics");
	if (isAnalyticsData(payload)) {
		return payload;
	}
	throw new Error("/metrics/analytics returned an unsupported response format.");
}

export async function getEvaluationResults(): Promise<EvaluationResults> {
	const payload: unknown = await getJson<unknown>("/evaluation/results");
	if (!isEvaluationResults(payload)) {
		throw new Error("/evaluation/results returned an unsupported response format.");
	}
	return payload;
}

export async function runEvaluation(): Promise<EvaluationReport> {
	const payload: unknown = await postJson<unknown>("/evaluation/run");
	if (!isEvaluationReport(payload)) {
		throw new Error("/evaluation/run returned an unsupported response format.");
	}
	return payload;
}

export async function getRequests(): Promise<RequestRecord[]> {
	const payload: unknown = await getJson<unknown>("/metrics/recent");

	if (Array.isArray(payload)) {
		if (payload.every(isRequestRecord)) {
			return payload;
		}
	}

	if (payload && typeof payload === "object") {
		const response = payload as { items?: unknown; requests?: unknown };
		const records = response.items ?? response.requests;
		if (Array.isArray(records) && records.every(isRequestRecord)) {
			return records;
		}
	}

	throw new Error("/requests returned an unsupported response format.");
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNumberOrNull(value: unknown): value is number | null {
	return value === null || isFiniteNumber(value);
}

function isFiniteNumber(value: unknown): value is number {
	return typeof value === "number" && Number.isFinite(value);
}

function isAnalyticsData(value: unknown): value is AnalyticsData {
	if (!isRecord(value) || !isRecord(value.model_usage) || !Array.isArray(value.trend)) {
		return false;
	}
	const counts = [
		"total_requests", "successful_requests", "failed_requests",
		"unknown_outcome_requests", "cache_hits", "cache_misses", "escalations",
		"fallbacks", "context_requests",
	];
	return counts.every((key) => typeof value[key] === "number" && Number.isFinite(value[key]))
		&& Object.values(value.model_usage).every((count) => typeof count === "number" && Number.isFinite(count))
		&& ["cache_hit_rate", "tokens_input", "tokens_output", "tokens_total",
			"average_latency_ms", "estimated_cost_total", "context_tokens_before",
			"context_tokens_after", "context_tokens_saved", "context_reduction_percent",
		].every((key) => isNumberOrNull(value[key]))
		&& value.trend.every((point) => isRecord(point)
			&& typeof point.date === "string"
			&& ["requests", "successful_requests", "failed_requests"].every(
				(key) => typeof point[key] === "number" && Number.isFinite(point[key]),
			)
			&& isNumberOrNull(point.tokens));
}

function isEvaluationResults(value: unknown): value is EvaluationResults {
	return isRecord(value)
		&& typeof value.available === "boolean"
		&& (value.report === null || isEvaluationReport(value.report))
		&& (value.available ? value.report !== null : value.report === null);
}

function isEvaluationReport(value: unknown): value is EvaluationReport {
	if (!isRecord(value) || !isRecord(value.dataset) || !isRecord(value.dataset.splits)
		|| !isRecord(value.tasks) || !isRecord(value.routing)
		|| !isRecord(value.routing.calibrated_at_selected_threshold)) {
		return false;
	}
	const routing = value.routing.calibrated_at_selected_threshold;
	const validTask = (task: unknown) => isRecord(task)
		&& ["raw", "calibrated"].every((key) => {
			const score = task[key];
			return isRecord(score)
				&& ["accuracy", "macro_f1", "brier_score"].every((metric) => isFiniteNumber(score[metric]));
		});
	return typeof value.decision_model === "string"
		&& typeof value.split === "string"
		&& isFiniteNumber(value.count)
		&& isFiniteNumber(value.invalid_outputs)
		&& isFiniteNumber(value.calibration_rows)
		&& typeof value.calibration_applied === "boolean"
		&& isFiniteNumber(value.dataset.rows)
		&& isFiniteNumber(value.dataset.splits.test)
		&& Object.values(value.dataset.splits).every(isFiniteNumber)
		&& Object.keys(value.tasks).length > 0
		&& Object.values(value.tasks).every(validTask)
		&& isFiniteNumber(routing.routing_accuracy)
		&& isFiniteNumber(routing.uncertain_rate)
		&& isRecord(routing.selected_model_counts)
		&& Object.values(routing.selected_model_counts).every(isFiniteNumber)
		&& isFiniteNumber(value.routing.validation_selected_threshold)
		&& isFiniteNumber(value.routing.deployed_threshold)
		&& typeof value.note === "string";
}

async function sendJson<T>(
	path: string,
	method: string,
	body?: unknown,
	timeoutMs = 15000,
): Promise<T> {
	return requestJson<T>(path, {
		method,
		headers: body === undefined ? undefined : { "Content-Type": "application/json" },
		body: body === undefined ? undefined : JSON.stringify(body),
	}, timeoutMs);
}

export function listConversations(): Promise<ConversationSummary[]> {
	return getJson<ConversationSummary[]>("/conversations");
}

export function createConversation(): Promise<Conversation> {
	return sendJson<Conversation>("/conversations", "POST");
}

export function getConversation(id: string): Promise<Conversation> {
	return getJson<Conversation>(`/conversations/${id}`);
}

export function renameConversation(id: string, title: string): Promise<Conversation> {
	return sendJson<Conversation>(`/conversations/${id}`, "PATCH", { title });
}

export function deleteConversation(id: string): Promise<void> {
	return sendJson<void>(`/conversations/${id}`, "DELETE");
}

export function sendConversationMessage(id: string, message: string): Promise<{
	request_id: string;
	status: string;
	conversation: Conversation;
}> {
	return sendJson(`/conversations/${id}/messages`, "POST", { message }, 600000);
}
