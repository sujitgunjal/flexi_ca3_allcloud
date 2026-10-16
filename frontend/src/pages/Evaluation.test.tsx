import type { ComponentProps } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Evaluation from "./Evaluation";
import { runEvaluation } from "../services/api";
import type { EvaluationReport, EvaluationResults } from "../types";

vi.mock("../services/api", () => ({ runEvaluation: vi.fn() }));

const report: EvaluationReport = {
	decision_model: "ollama/test-model",
	split: "test",
	count: 4,
	invalid_outputs: 1,
	calibration_rows: 12,
	calibration_applied: true,
	dataset: { rows: 20, splits: { calibration: 12, validation: 4, test: 4 } },
	tasks: {
		complexity: {
			raw: { accuracy: 0.5, macro_f1: 0.45, brier_score: 0.6 },
			calibrated: { accuracy: 0.75, macro_f1: 0.7, brier_score: 0.4 },
		},
	},
	routing: {
		validation_selected_threshold: 0.5,
		deployed_threshold: 0.45,
		calibrated_at_selected_threshold: {
			routing_accuracy: 0.75,
			uncertain_rate: 0.25,
			selected_model_counts: { cheap: 2, strong: 2 },
		},
	},
	note: "Scores use only the test split.",
};

const savedResults: EvaluationResults = { available: true, report };

function renderEvaluation(overrides: Partial<ComponentProps<typeof Evaluation>> = {}) {
	return render(
		<Evaluation
			results={savedResults}
			isLoading={false}
			isRefreshing={false}
			error={null}
			onRefresh={() => undefined}
			onReport={() => undefined}
			{...overrides}
		/>,
	);
}

describe("Evaluation", () => {
	afterEach(cleanup);
	beforeEach(() => vi.mocked(runEvaluation).mockReset());

	it("shows the loading state before results are retrieved", () => {
		renderEvaluation({ results: null, isLoading: true });
		expect(screen.getByText("Loading evaluation results")).toBeTruthy();
	});

	it("explains when there is no persisted report", () => {
		renderEvaluation({ results: { available: false, report: null } });
		expect(screen.getByText("No saved evaluation report")).toBeTruthy();
		expect(screen.getAllByRole("button", { name: "Run evaluation" }).length).toBeGreaterThan(0);
	});

	it("displays actual saved test scores and surfaces load errors", () => {
		renderEvaluation({ error: "Report unavailable" });
		expect(screen.getByText("ollama/test-model")).toBeTruthy();
		expect(screen.getAllByText("75%").length).toBeGreaterThan(0);
		expect(screen.getByText(/Report unavailable/)).toBeTruthy();
	});

	it("runs once, disables duplicate submissions, and shows success", async () => {
		let finishRun: (value: EvaluationReport) => void = () => undefined;
		vi.mocked(runEvaluation).mockReturnValue(
			new Promise((resolve) => { finishRun = resolve; }),
		);
		const onReport = vi.fn();
		renderEvaluation({ onReport });

		const runButton = screen.getAllByRole("button", { name: "Run evaluation" })[0];
		fireEvent.click(runButton);
		fireEvent.click(runButton);
		expect(runEvaluation).toHaveBeenCalledOnce();
		expect(screen.getByRole("button", { name: "Running evaluation…" }).hasAttribute("disabled")).toBe(true);

		await act(async () => finishRun(report));
		expect(onReport).toHaveBeenCalledWith(report);
		expect(screen.getByText("Evaluation completed. The saved report has been updated.")).toBeTruthy();
	});

});
