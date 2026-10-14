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
	completed?: boolean | null;
}
