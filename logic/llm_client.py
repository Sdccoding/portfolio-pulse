"""
logic/llm_client.py — Portfolio Pulse: Provider-Agnostic LLM Client Factory
=============================================================================
Single source of truth for ALL LLM interaction in the project.

Supports two providers, toggled via the LLM_PROVIDER env var:
  - "gemini"  → Google Gemini 2.5 Flash via google-genai SDK
  - "ollama"  → Local Ollama via OpenAI-compatible /v1 endpoint

Usage (all consumers):
    from logic import llm_client

    response = llm_client.generate(prompt, use_grounding=True)
    print(response.text)
    print(response.grounding_sources)
"""
from loguru import logger

import config


# ── Unified Response Wrapper ──────────────────────────────────────────────────

class LLMResponse:
    """
    Unified response wrapper regardless of provider.

    Attributes:
        text:              Raw text output from the LLM.
        grounding_sources: List of URLs used for grounding (Gemini only; empty for Ollama).
        raw:               The original provider-specific response object (for advanced use).
    """

    def __init__(self, text: str, grounding_sources: list[str] | None = None, raw=None):
        self.text = text
        self.grounding_sources = grounding_sources or []
        self.raw = raw

    def __repr__(self) -> str:
        return (
            f"LLMResponse(text={self.text[:80]!r}..., "
            f"grounding_sources={len(self.grounding_sources)} URLs)"
        )


# ── Provider Implementations ─────────────────────────────────────────────────

def _generate_gemini(prompt: str, use_grounding: bool) -> LLMResponse:
    """Generate via Google Gemini SDK."""
    from google import genai
    from google.genai import types

    # Lazy-init the singleton client
    if not hasattr(_generate_gemini, "_client"):
        _generate_gemini._client = genai.Client(api_key=config.get_api_key())

    client = _generate_gemini._client

    model_id = "gemini-2.5-flash"

    if use_grounding:
        google_search_tool = types.Tool(google_search=types.GoogleSearch())
        gen_config = types.GenerateContentConfig(
            tools=[google_search_tool],
            response_modalities=["TEXT"],
        )
    else:
        gen_config = types.GenerateContentConfig(
            response_modalities=["TEXT"],
        )

    response = client.models.generate_content(
        model=model_id,
        contents=prompt,
        config=gen_config,
    )

    # Extract grounding URLs
    sources: list[str] = []
    if use_grounding:
        try:
            chunks = response.candidates[0].grounding_metadata.grounding_chunks
            sources = [c.web.uri for c in chunks if c.web and c.web.uri]
        except Exception:
            pass

    return LLMResponse(
        text=(response.text or "").strip(),
        grounding_sources=sources,
        raw=response,
    )


def _generate_ollama(prompt: str, use_grounding: bool) -> LLMResponse:
    """Generate via Ollama's OpenAI-compatible /v1 endpoint, simulating search grounding via DuckDuckGo."""
    from openai import OpenAI
    import json

    # Lazy-init the singleton client
    if not hasattr(_generate_ollama, "_client"):
        _generate_ollama._client = OpenAI(
            base_url=config.OLLAMA_BASE_URL,
            api_key="ollama",  # Ollama doesn't need a real key
        )

    client = _generate_ollama._client

    messages = [{"role": "user", "content": prompt}]
    tools = None

    if use_grounding:
        tools = [{
            "type": "function",
            "function": {
                "name": "web_search",
                "description": (
                    "Search the web using DuckDuckGo for real-time stock news, "
                    "earnings reports, analyst targets, and company updates."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query to execute (e.g. 'TCS Q3 results 2026')."
                        }
                    },
                    "required": ["query"]
                }
            }
        }]

    # Check if prompt requires JSON output
    is_json = "json" in prompt.lower()
    response_format = {"type": "json_object"} if is_json else None

    # Step 1: Initial call to the model
    response = client.chat.completions.create(
        model=config.OLLAMA_MODEL,
        messages=messages,
        tools=tools,
        response_format=response_format,
        temperature=0.7,
    )

    message = response.choices[0].message
    sources: list[str] = []

    # Step 2: Handle tool calls if requested by the model
    if message.tool_calls:
        from duckduckgo_search import DDGS

        # Add assistant's message with tool call request to history
        messages.append(message)

        for tool_call in message.tool_calls:
            if tool_call.function.name == "web_search":
                try:
                    args = json.loads(tool_call.function.arguments)
                    query = args.get("query")
                except Exception as e:
                    logger.warning(f"[LLM] Failed to parse search arguments: {e}")
                    continue

                logger.info(f"[LLM] Ollama requested web search for: '{query}'")
                
                # Run DuckDuckGo text search
                try:
                    with DDGS() as ddgs:
                        results = list(ddgs.text(query, backend="lite", max_results=5))
                    logger.info(f"[LLM] DDG search returned {len(results)} results")
                    search_contexts = []
                    for r in results:
                        title = r.get("title", "No Title")
                        href = r.get("href", "")
                        body = r.get("body", "")
                        if href:
                            sources.append(href)
                        search_contexts.append(f"[{title}]({href})\n{body}")
                    
                    search_text = "\n\n".join(search_contexts)
                except Exception as e:
                    logger.error(f"[LLM] DuckDuckGo search failed: {e}")
                    search_text = f"Search failed with error: {e}"

                # Append tool result to history
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": "web_search",
                    "content": search_text
                })

        # Step 3: Run second completion turn with the search results injected
        response = client.chat.completions.create(
            model=config.OLLAMA_MODEL,
            messages=messages,
            response_format=response_format,
            temperature=0.7,
        )
        text = (response.choices[0].message.content or "").strip()
    else:
        text = (message.content or "").strip()

    return LLMResponse(
        text=text,
        grounding_sources=sources,
        raw=response,
    )


def _generate_vllm(prompt: str, use_grounding: bool) -> LLMResponse:
    """Generate via vLLM's OpenAI-compatible /v1 endpoint, simulating search grounding via DuckDuckGo."""
    from openai import OpenAI
    import json

    # Lazy-init the singleton client
    if not hasattr(_generate_vllm, "_client"):
        _generate_vllm._client = OpenAI(
            base_url=config.VLLM_BASE_URL,
            api_key="vllm",  # vLLM doesn't need a real key by default
        )

    client = _generate_vllm._client

    messages = [{"role": "user", "content": prompt}]
    tools = None

    if use_grounding:
        tools = [{
            "type": "function",
            "function": {
                "name": "web_search",
                "description": (
                    "Search the web using DuckDuckGo for real-time stock news, "
                    "earnings reports, analyst targets, and company updates."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query to execute (e.g. 'TCS Q3 results 2026')."
                        }
                    },
                    "required": ["query"]
                }
            }
        }]

    # Check if prompt requires JSON output
    is_json = "json" in prompt.lower()
    response_format = {"type": "json_object"} if is_json else None

    # Step 1: Initial call to the model
    response = client.chat.completions.create(
        model=config.VLLM_MODEL,
        messages=messages,
        tools=tools,
        response_format=response_format,
        temperature=0.7,
    )

    message = response.choices[0].message
    sources: list[str] = []

    # Step 2: Handle tool calls if requested by the model
    if message.tool_calls:
        from duckduckgo_search import DDGS

        messages.append(message)

        for tool_call in message.tool_calls:
            if tool_call.function.name == "web_search":
                try:
                    args = json.loads(tool_call.function.arguments)
                    query = args.get("query")
                except Exception as e:
                    logger.warning(f"[LLM] Failed to parse search arguments: {e}")
                    continue

                logger.info(f"[LLM] vLLM requested web search for: '{query}'")
                
                try:
                    with DDGS() as ddgs:
                        results = list(ddgs.text(query, backend="lite", max_results=5))
                    logger.info(f"[LLM] DDG search returned {len(results)} results")
                    search_contexts = []
                    for r in results:
                        title = r.get("title", "No Title")
                        href = r.get("href", "")
                        body = r.get("body", "")
                        if href:
                            sources.append(href)
                        search_contexts.append(f"[{title}]({href})\n{body}")
                    
                    search_text = "\n\n".join(search_contexts)
                except Exception as e:
                    logger.error(f"[LLM] DuckDuckGo search failed: {e}")
                    search_text = f"Search failed with error: {e}"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": "web_search",
                    "content": search_text
                })

        # Step 3: Run second completion turn with the search results injected
        response = client.chat.completions.create(
            model=config.VLLM_MODEL,
            messages=messages,
            response_format=response_format,
            temperature=0.7,
        )
        text = (response.choices[0].message.content or "").strip()
    else:
        text = (message.content or "").strip()

    return LLMResponse(
        text=text,
        grounding_sources=sources,
        raw=response,
    )


# ── Provider Registry ────────────────────────────────────────────────────────

_PROVIDERS = {
    "gemini": _generate_gemini,
    "ollama": _generate_ollama,
    "vllm": _generate_vllm,
}


# ── Public API ────────────────────────────────────────────────────────────────

def get_provider() -> str:
    """Return the name of the currently configured LLM provider."""
    return config.LLM_PROVIDER


def generate(prompt: str, use_grounding: bool = True) -> LLMResponse:
    """
    Single entry point for all LLM calls across the project.

    Args:
        prompt:        The full text prompt to send to the LLM.
        use_grounding: If True and provider supports it (Gemini), enables
                       Google Search grounding for real-time web retrieval.
                       Silently ignored for providers that lack grounding.

    Returns:
        LLMResponse with .text and .grounding_sources.

    Raises:
        ValueError: If LLM_PROVIDER is not a recognised provider.
    """
    provider = config.LLM_PROVIDER
    generate_fn = _PROVIDERS.get(provider)

    if generate_fn is None:
        raise ValueError(
            f"Unknown LLM_PROVIDER: '{provider}'. "
            f"Valid options: {', '.join(_PROVIDERS.keys())}"
        )

    return generate_fn(prompt, use_grounding)
