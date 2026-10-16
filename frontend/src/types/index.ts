export interface GatewayMetrics {
	total_requests: number;
	cache_hits: number;
	cache_misses: number;
	llm_calls: number;
	tokens_input: number;
	tokens_output: number;
	estimated_cost: number;
	average_latency_ms: number;
	context_reduction_percent: number;
	escalations: number;
	fallbacks: number;
	context?: ContextMetrics;
}

export interface ContextMetrics {
	requests_with_metrics: number;
	total_original_tokens: number;
	total_optimized_tokens: number;
	total_tokens_saved: number;
	overall_reduction_percent: number | null;
}

export interface ModelInfo {
	id: string;
	tier: string;
	provider: string;
	available: boolean;
}

export interface AnalyticsTrendPoint {
	date: string;
	requests: number;
	successful_requests: number;
	failed_requests: number;
	tokens: number | null;
}

export interface AnalyticsData {
	total_requests: number;
	successful_requests: number;
	failed_requests: number;
	unknown_outcome_requests: number;
	cache_hits: number;
	cache_misses: number;
	cache_hit_rate: number | null;
	model_usage: Record<string, number>;
	tokens_input: number | null;
	tokens_output: number | null;
	tokens_total: number | null;
	average_latency_ms: number | null;
	estimated_cost_total: number | null;
	escalations: number;
	fallbacks: number;
	context_requests: number;
	context_tokens_before: number | null;
	context_tokens_after: number | null;
	context_tokens_saved: number | null;
	context_reduction_percent: number | null;
	trend: AnalyticsTrendPoint[];
}

export interface EvaluationScore {
	accuracy: number;
	macro_f1: number;
	brier_score: number;
}

export interface EvaluationTaskResult {
	raw: EvaluationScore;
	calibrated: EvaluationScore;
}

export interface EvaluationReport {
	decision_model: string;
	split: string;
	count: number;
	invalid_outputs: number;
	calibration_rows: number;
	calibration_applied: boolean;
	dataset: {
		rows: number;
		splits: Record<string, number>;
	};
	tasks: Record<string, EvaluationTaskResult>;
	routing: {
		validation_selected_threshold: number;
		deployed_threshold: number;
		calibrated_at_selected_threshold: {
			routing_accuracy: number;
			uncertain_rate: number;
			selected_model_counts: Record<string, number>;
		};
	};
	note: string;
}

export interface EvaluationResults {
	available: boolean;
	report: EvaluationReport | null;
}

export interface ChatDetails {
	model_tier?: string | null;
	actual_model?: string | null;
	complexity?: string | null;
	quality_score?: number | null;
	quality_status?: string | null;
	quality_relevant?: string | null;
	quality_complete?: string | null;
	quality_escalate?: string | null;
	latency_ms?: number | null;
	input_tokens?: number | null;
	output_tokens?: number | null;
	estimated_cost?: number | null;
	cache_hit?: boolean | null;
	escalated?: boolean | null;
	fallback_used?: boolean | null;
	routing_reason?: string | null;
}

export interface ConversationSummary {
	id: string;
	title: string;
	created_at: string;
	updated_at: string;
	preview?: string | null;
}

export interface ConversationMessage {
	id: string;
	role: "user" | "assistant";
	content: string;
	created_at: string;
	request_id?: string | null;
	details?: ChatDetails | null;
}

export interface Conversation extends ConversationSummary {
	messages: ConversationMessage[];
}

export interface RequestRecord {
	id: number | string;
	timestamp?: string | null;
	query?: string | null;
	complexity?: string | null;
	selected_model?: string | null;
	final_model?: string | null;
	input_tokens?: number | null;
	output_tokens?: number | null;
	total_tokens?: number | null;
	latency_ms?: number | null;
	estimated_cost?: number | null;
	cache_hit?: boolean | null;
	escalated?: boolean | null;
	quality_status?: string | null;
	quality_score?: number | null;
	completed?: boolean | null;
}
