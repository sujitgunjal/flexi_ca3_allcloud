import type { ComponentProps } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import Analytics from "./Analytics";
import type { AnalyticsData } from "../types";

const sampleData: AnalyticsData = {
	total_requests: 3,
	successful_requests: 2,
	failed_requests: 1,
	unknown_outcome_requests: 0,
	cache_hits: 1,
	cache_misses: 1,
	cache_hit_rate: 0.5,
	model_usage: { cheap: 2 },
	tokens_input: 40,
	tokens_output: 60,
	tokens_total: 100,
	average_latency_ms: 125,
	estimated_cost_total: 0.0025,
	escalations: 1,
	fallbacks: 0,
	context_requests: 1,
	context_tokens_before: 100,
	context_tokens_after: 80,
	context_tokens_saved: 20,
	context_reduction_percent: 20,
	trend: [{
		date: "2026-10-16",
		requests: 3,
		successful_requests: 2,
		failed_requests: 1,
		tokens: 100,
	}],
};

function renderAnalytics(
	overrides: Partial<ComponentProps<typeof Analytics>> = {},
) {
	return render(
		<Analytics
			data={sampleData}
			isLoading={false}
			isRefreshing={false}
			error={null}
			onRefresh={() => undefined}
			{...overrides}
		/>,
	);
}

describe("Analytics", () => {
	afterEach(cleanup);

	it("shows loading values while request metrics are loading", () => {
		renderAnalytics({ data: null, isLoading: true });

		expect(screen.getByText("Loading model usage…")).toBeTruthy();
		expect(screen.getByLabelText("Request analytics").getAttribute("aria-busy")).toBe("true");
	});

	it("shows an honest empty state when there is no request history", () => {
		renderAnalytics({
			data: {
				...sampleData,
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
				context_requests: 0,
				context_tokens_before: null,
				context_tokens_after: null,
				context_tokens_saved: null,
				context_reduction_percent: null,
				trend: [],
			},
		});

		expect(screen.getByText("No request history yet")).toBeTruthy();
		expect(screen.getByText("No requests in the last 30 days.")).toBeTruthy();
		expect(screen.getAllByText("Not reported").length).toBeGreaterThan(0);
	});

	it("renders actual summary, routing, and trend values", () => {
		renderAnalytics();

		expect(screen.getAllByText("3").length).toBeGreaterThan(0);
		expect(screen.getByText("50%")).toBeTruthy();
		expect(screen.getByText("cheap")).toBeTruthy();
		expect(screen.getByText("Oct 16")).toBeTruthy();
		expect(screen.getByText("Context tokens saved")).toBeTruthy();
	});

	it("shows recoverable load errors and a retry action", () => {
		const onRefresh = vi.fn();
		renderAnalytics({ data: null, error: "Gateway unavailable", onRefresh });

		expect(screen.getByText(/Analytics could not be loaded: Gateway unavailable/)).toBeTruthy();
		screen.getByRole("button", { name: "Retry" }).click();
		expect(onRefresh).toHaveBeenCalledOnce();
	});
});
