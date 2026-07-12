"""LLM abstraction. One interface, four backends:

  mock      — deterministic extractive engine, zero dependencies (default dev)
  ollama    — local models (Llama 3, Qwen, Phi-3) via Ollama
  openai    — GPT family
  anthropic — Claude family

The mock engine is genuinely grounded: it extracts and ranks sentences from the
retrieved context, so RAG demos show real citations without any model running."""
import logging
import re
import time

from app.core.config import settings

log = logging.getLogger("eaios.llm")
TOKEN = re.compile(r"[a-z0-9]+")


class MockLLM:
    name = "mock"

    def complete(self, system: str, prompt: str) -> str:
        context, question = _split_prompt(prompt)
        if "EMAIL" in system.upper():
            return self._email(question, context)
        if "REPORT" in system.upper():
            return self._report(question, context)
        if context:
            return self._grounded_answer(question, context)
        return (
            f"Here is my take on \"{question[:120]}\": this instance is running the built-in mock engine, "
            "so responses outside the knowledge base are limited. Connect Ollama or a cloud API key in "
            "Settings to enable full generative answers. Document-grounded questions, SQL, analytics and "
            "report generation are fully functional in mock mode."
        )

    def _grounded_answer(self, question: str, context: str) -> str:
        query_terms = set(TOKEN.findall(question.lower()))
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", context) if len(s.strip()) > 30]
        scored = sorted(
            sentences,
            key=lambda s: len(query_terms & set(TOKEN.findall(s.lower()))),
            reverse=True,
        )
        best = [s for s in scored[:4] if query_terms & set(TOKEN.findall(s.lower()))]
        if not best:
            return "The knowledge base does not contain a confident answer to that question. Try rephrasing, or upload the relevant document."
        return "Based on the indexed enterprise documents: " + " ".join(best)

    def _email(self, request: str, context: str) -> str:
        return (
            f"Subject: Regarding {request[:60].rstrip('.')}\n\n"
            "Hi [Name],\n\n"
            f"I hope you're doing well. I'm writing regarding {request.rstrip('.')}. "
            + (f"For context: {context[:220].strip()}… " if context else "")
            + "Please let me know if you need any further details, and I'd be happy to set up a quick call.\n\n"
            "Best regards,\n[Your name]"
        )

    def _report(self, request: str, context: str) -> str:
        body = context[:600].strip() or "No indexed material matched this topic yet — upload source documents to enrich this report."
        return (
            f"# Report: {request[:80]}\n\n"
            f"## Executive Summary\n{body}\n\n"
            "## Key Findings\nThe findings above are extracted verbatim from indexed enterprise sources; "
            "confidence scores and citations accompany each retrieval.\n\n"
            "## Recommended Next Steps\nReview the cited source documents and connect a full LLM provider "
            "for narrative synthesis."
        )


class OllamaLLM:
    name = "ollama"

    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.OLLAMA_MODEL

    def complete(self, system: str, prompt: str) -> str:
        import httpx

        r = httpx.post(
            f"{settings.OLLAMA_BASE_URL}/api/generate",
            json={"model": self.model, "system": system, "prompt": prompt, "stream": False,
                  "options": {"temperature": settings.TEMPERATURE}},
            timeout=120,
            trust_env=False,
        )
        r.raise_for_status()
        return r.json().get("response", "").strip()


class OpenAILLM:
    """OpenAI-compatible chat API. Works with any compatible endpoint via
    OPENAI_BASE_URL — e.g. **OpenRouter** (https://openrouter.ai/api/v1 — one
    key for GPT, Claude, Gemini, DeepSeek, Qwen, Llama, Phi…), Groq
    (https://api.groq.com/openai/v1), or a local vLLM/llama.cpp server."""

    def __init__(self) -> None:
        base = settings.OPENAI_BASE_URL.rstrip("/")
        self.base_url = base
        self.model = settings.OPENAI_MODEL
        if "openrouter.ai" in base:
            self.name = "openrouter"
        elif "groq.com" in base:
            self.name = "groq"
        elif "openai.com" in base:
            self.name = "openai"
        else:
            self.name = "openai-compatible"

    def complete(self, system: str, prompt: str) -> str:
        import httpx

        headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
        if self.name == "openrouter":  # attribution headers OpenRouter recommends
            headers["HTTP-Referer"] = "https://eaios.onrender.com"
            headers["X-Title"] = "EAIOS"
        r = httpx.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json={
                "model": self.model,
                "temperature": settings.TEMPERATURE,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()


class AnthropicLLM:
    name = "anthropic"

    def complete(self, system: str, prompt: str) -> str:
        import httpx

        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": settings.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"},
            json={
                "model": settings.ANTHROPIC_MODEL,
                "max_tokens": 1500,
                "temperature": settings.TEMPERATURE,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["content"][0]["text"].strip()


_llm = None
_tags_cache: list[str] | None = None


def reset_llm() -> None:
    """Drop the cached provider so the next call re-detects (hot model swap)."""
    global _llm
    _llm = None
_tags_checked_at = 0.0
TAGS_RETRY_SECONDS = 30  # unreachable Ollama is re-probed, so starting it later self-heals


def ollama_tags(force: bool = False) -> list[str]:
    """Models available on the local Ollama server ([] if unreachable).
    Successful probes are cached; empty results are retried every 30s."""
    global _tags_cache, _tags_checked_at
    stale = not _tags_cache and (time.time() - _tags_checked_at) > TAGS_RETRY_SECONDS
    if _tags_cache is None or force or stale:
        try:
            import httpx

            r = httpx.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=2.5, trust_env=False)
            r.raise_for_status()
            _tags_cache = [m["name"] for m in r.json().get("models", [])]
        except Exception:
            _tags_cache = []
        _tags_checked_at = time.time()
    return _tags_cache


_EMBED_PREFIXES = ("nomic-embed", "mxbai-embed", "bge-", "snowflake-arctic-embed", "all-minilm")
VISION_PREFIXES = ("llava", "moondream", "qwen2-vl", "qwen2.5vl", "qwen2.5-vl", "minicpm-v", "bakllava", "llama3.2-vision")


def _pick_chat_model(tags: list[str]) -> str | None:
    """Prefer the configured model; otherwise first non-embedding, non-vision model."""
    for t in tags:
        if t.split(":")[0] == settings.OLLAMA_MODEL.split(":")[0]:
            return t
    for t in tags:
        base = t.split(":")[0]
        if not base.startswith(_EMBED_PREFIXES) and not base.startswith(VISION_PREFIXES):
            return t
    return None


def caption_image(path: str) -> str:
    """Caption an image with a local vision model (LLaVA / Qwen-VL / moondream) if one is pulled."""
    try:
        vm = next((t for t in ollama_tags() if t.split(":")[0].startswith(VISION_PREFIXES)), None)
        if not vm:
            return ""
        import base64

        import httpx

        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        r = httpx.post(
            f"{settings.OLLAMA_BASE_URL}/api/generate",
            json={
                "model": vm,
                "prompt": "Describe this image for a searchable enterprise document index. Include any chart values, table contents, or text you can read.",
                "images": [b64],
                "stream": False,
            },
            timeout=180,
            trust_env=False,
        )
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except Exception:  # noqa: BLE001
        return ""


def get_llm():
    global _llm
    # Self-heal: if we fell back to mock in auto mode, upgrade as soon as Ollama appears.
    if _llm is not None and _llm.name == "mock" and settings.LLM_PROVIDER.lower() == "auto":
        model = _pick_chat_model(ollama_tags())
        if model:
            _llm = OllamaLLM(model)
            log.info("LLM provider upgraded: ollama (%s)", model)
    if _llm is None:
        provider = settings.LLM_PROVIDER.lower()
        if provider in ("auto", "ollama"):
            model = _pick_chat_model(ollama_tags())
            if model:
                _llm = OllamaLLM(model)
            elif provider == "ollama":
                log.warning("LLM_PROVIDER=ollama but no Ollama models found — using mock")
        if _llm is None and provider in ("auto", "openai") and settings.OPENAI_API_KEY:
            _llm = OpenAILLM()
        if _llm is None and provider in ("auto", "anthropic") and settings.ANTHROPIC_API_KEY:
            _llm = AnthropicLLM()
        if _llm is None:
            _llm = MockLLM()
        log.info("LLM provider: %s (%s)", _llm.name, getattr(_llm, "model", "n/a"))
    return _llm


def safe_complete(system: str, prompt: str) -> str:
    """Never let a provider outage break the request path — degrade to mock."""
    try:
        return get_llm().complete(system, prompt)
    except Exception as exc:  # noqa: BLE001
        log.warning("LLM call failed (%s) — falling back to mock", exc)
        return MockLLM().complete(system, prompt)


def complete_with(model: str, system: str, prompt: str) -> str:
    """One-off completion against a SPECIFIC model id (Model Arena).

    Uses the active OpenAI-compatible endpoint/key with a temporary model
    override; on the mock provider returns a deterministic per-model variant
    so comparisons stay demoable offline. Raises on provider errors — the
    caller reports them per-model instead of masking with mock text."""
    active = get_llm()
    if active.name == "mock" or not settings.OPENAI_API_KEY:
        base = MockLLM().complete(system, prompt)
        return f"[{model}] {base}"
    candidate = OpenAILLM()
    candidate.model = model
    return candidate.complete(system, prompt)


def _split_prompt(prompt: str) -> tuple[str, str]:
    """Extract CONTEXT/QUESTION segments from a RAG prompt (mock engine helper)."""
    context, question = "", prompt
    if "CONTEXT:" in prompt and "QUESTION:" in prompt:
        context = prompt.split("CONTEXT:", 1)[1].split("QUESTION:", 1)[0].strip()
        question = prompt.split("QUESTION:", 1)[1].strip()
    return context, question
