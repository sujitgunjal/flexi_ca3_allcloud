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
	completed?: boolean | null;
}
