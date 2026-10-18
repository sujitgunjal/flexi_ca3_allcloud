import logging

from app.context.embeddings import HashEmbedder, get_embedder
from app.context.selector import (
    context_budget,
    render_context,
    select_relevant_messages,
)
from app.orchestration.state import RequestState
from app.services.token_service import count_tokens

logger = logging.getLogger(__name__)


class ContextAgent:
    def __init__(self, embedder=None):
        self.embedder = embedder

    def run(self, state: RequestState) -> RequestState:
        query = state.get("query", "")
        history = list(state.get("conversation_history") or [])
        requirement = state.get("context_requirement") or "medium"
        token_limit, message_cap = context_budget(requirement)
        original_tokens = count_tokens(query) + sum(
            count_tokens(str(message.get("content", ""))) for message in history
        )

        embedder, embedding_source = self._embedder()
        selected = []
        if history:
            documents = [str(message.get("content", "")) for message in history]
            try:
                embeddings = embedder.embed([query], input_type="query") + embedder.embed(
                    documents,
                    input_type="document",
                )
            except Exception:
                logger.exception("Embeddings failed; using local hash similarity")
                embedder = HashEmbedder()
                embedding_source = "local_hash"
                embeddings = embedder.embed([query] + documents)
            selected = select_relevant_messages(
                query,
                history,
                embeddings,
                token_limit,
                message_cap,
            )

        optimized_tokens = count_tokens(query) + sum(
            count_tokens(message["content"]) for message in selected
        )
        reduction = (
            0.0
            if original_tokens == 0
            else round((original_tokens - optimized_tokens) / original_tokens * 100, 2)
        )

        state["optimized_history"] = [
            {"role": message["role"], "content": message["content"]}
            for message in selected
        ]
        state["optimized_context"] = (
            query if not selected else render_context(query, state["optimized_history"])
        )
        state["original_token_count"] = original_tokens
        state["optimized_token_count"] = optimized_tokens
        state["messages_selected"] = len(selected)
        state["context_reduction_percent"] = reduction
        state["embedding_source"] = embedding_source

        print(
            "[ContextAgent] "
            f"requirement={requirement} selected={len(selected)}/{len(history)} "
            f"tokens={original_tokens}->{optimized_tokens} "
            f"reduction={reduction}% source={embedding_source}"
        )
        _record_metrics(state)
        return state

    def _embedder(self):
        if self.embedder is not None:
            return self.embedder, "injected"
        embedder = get_embedder()
        return embedder, f"{embedder.provider}:{embedder.model}"


def _record_metrics(state: RequestState) -> None:
    request_id = state.get("metrics_request_id")
    if request_id is None:
        return
    try:
        from app.services.metrics_service import record_context_event

        record_context_event(
            request_id,
            state["original_token_count"],
            state["optimized_token_count"],
            state["context_reduction_percent"],
        )
    except Exception:
        logger.exception("Context metrics were not saved")
