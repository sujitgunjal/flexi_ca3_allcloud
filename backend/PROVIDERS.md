# Model providers

The chat generator routes between the local Ollama tier and the configured
NVIDIA NIM `cheap` and `strong` tiers. Set the model IDs, API base, and
`NVIDIA_API_KEY` in `backend/.env`; `backend/.env.example` lists the defaults.
The configured NVIDIA model IDs are catalog IDs, and the API base
`https://integrate.api.nvidia.com/v1` is NVIDIA's OpenAI-compatible NIM endpoint.
LiteLLM 1.104 recognizes that endpoint as `nvidia_nim` while keeping the
configured catalog model ID intact.

`PROVIDER_TIMEOUT_SECONDS` is the finite timeout for each NVIDIA generation
attempt. `OLLAMA_TIMEOUT_SECONDS` separately bounds local generation and
defaults to 30 seconds, allowing for model loading and local inference. A caller
may explicitly provide a timeout for a provider probe. Both paths disable
LiteLLM retries and streaming so retries do not multiply the configured
deadline. Quality checks remain enabled and each Ollama quality evaluation is
bounded by `QUALITY_TIMEOUT_SECONDS` (20 seconds by default); an unavailable
evaluator produces the existing invalid-quality result. The existing tier fallback remains first (`strong` to `cheap`,
`cheap` to `strong`, `local` to `cheap`). If the NVIDIA primary and its NVIDIA
fallback both fail, local Ollama is the final fallback. If all applicable
attempts fail, `/chat` returns HTTP 502 with a generic provider/orchestration
error.
