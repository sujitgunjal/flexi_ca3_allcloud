import { afterEach, describe, expect, it, vi } from "vitest";
import { getAnalytics, getEvaluationResults, runEvaluation } from "./api";

afterEach(() => {
	vi.useRealTimers();
	vi.unstubAllGlobals();
});

describe("analytics API client", () => {
	it("uses the backend analytics response and validates its shape", async () => {
		const data = {
			total_requests: 0,
			successful_requests: 0,
			failed_requests: 0,
			unknown_outcome_requests: 0,
			cache_hits: 0,
			cache_misses: 0,
			cache_hit_rate: null,
			model_usage: {},
			tokens_input: null,
			tokens_output: null,
			tokens_total: null,
			average_latency_ms: null,
			estimated_cost_total: null,
			escalations: 0,
			fallbacks: 0,
			context_requests: 0,
			context_tokens_before: null,
			context_tokens_after: null,
			context_tokens_saved: null,
			context_reduction_percent: null,
			trend: [],
		};
		vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
			new Response(JSON.stringify(data), { status: 200 }),
		));

		await expect(getAnalytics()).resolves.toEqual(data);
	});

	it("reports network failures", async () => {
		vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
		await expect(getAnalytics()).rejects.toThrow("Can't reach the gateway");
	});

	it("surfaces backend error details", async () => {
		vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
			new Response(JSON.stringify({ detail: "Metrics database unavailable" }), {
				status: 503,
				statusText: "Service Unavailable",
			}),
		));
		await expect(getAnalytics()).rejects.toThrow("Metrics database unavailable");
	});

	it("rejects malformed JSON and unsupported analytics shapes", async () => {
		vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(
			new Response("{", { status: 200 }),
		).mockResolvedValueOnce(
			new Response(JSON.stringify({ unexpected: true }), { status: 200 }),
		));
		await expect(getAnalytics()).rejects.toThrow("/metrics/analytics returned invalid JSON.");
		await expect(getAnalytics()).rejects.toThrow("unsupported response format");
	});

	it("reports request timeouts", async () => {
		vi.useFakeTimers();
		vi.stubGlobal("fetch", vi.fn((_url: RequestInfo | URL, init?: RequestInit) => (
			new Promise<Response>((_resolve, reject) => {
				init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
			})
		)));
		const request = getAnalytics();
		const assertion = expect(request).rejects.toThrow("timed out after 15 seconds");
		await vi.advanceTimersByTimeAsync(15000);

		await assertion;
	});

	it("rejects malformed evaluation result envelopes", async () => {
		vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
			new Response(JSON.stringify({ available: true, report: null }), { status: 200 }),
		));
		await expect(getEvaluationResults()).rejects.toThrow("unsupported response format");
	});

	it("surfaces evaluation execution errors from the backend", async () => {
		vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
			new Response(JSON.stringify({ detail: "No raw predictions found." }), {
				status: 409,
				statusText: "Conflict",
			}),
		));
		await expect(runEvaluation()).rejects.toThrow("No raw predictions found.");
	});
});
