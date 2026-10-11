import type { GatewayMetrics, ModelInfo, RequestRecord } from "../types";

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000")
	.replace(/\/$/, "");

async function getJson<T>(path: string): Promise<T> {
	let response: Response;
	try {
		response = await fetch(`${API_BASE_URL}${path}`);
	} catch (error) {
		throw new Error(`Can't reach the gateway at ${API_BASE_URL}.`, { cause: error });
	}

	if (!response.ok) {
		throw new Error(`${path} returned ${response.status} ${response.statusText}.`);
	}

	try {
		return await response.json() as T;
	} catch (error) {
		throw new Error(`${path} returned invalid JSON.`, { cause: error });
	}
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

export async function getRequests(): Promise<RequestRecord[]> {
	const payload: unknown = await getJson<unknown>("/metrics/recent");;

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
