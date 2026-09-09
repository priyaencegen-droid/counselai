import asyncio
import logging
import re
import httpx
from app.core.config import get_settings
from app.prompts.prompts_user import get_system_prompt

logger = logging.getLogger("counselai.llm")

def clean_llm_response(text: str) -> str:
    """Clean model output, stripping outermost markdown fence if wrapped."""
    trimmed = text.strip()
    # Strip ```markdown ... ``` or ``` ... ``` if the entire response is enclosed in it
    match = re.match(r"^```(?:markdown|md)?\s*\n([\s\S]*?)\n```$", trimmed, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return trimmed

async def post_json(url: str, payload: dict, headers: dict | None = None, timeout_seconds: float = 300.0) -> dict:
    timeout = httpx.Timeout(timeout_seconds, connect=30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.is_error:
            detail = response.text.strip()
            raise RuntimeError(f"LLM request to {url} failed with HTTP {response.status_code}: {detail[:500]}")
        return response.json()

async def generate(prompt: str, model: str | None = None) -> str:
    settings = get_settings()
    provider = settings.llm_provider.lower().strip()

    if provider == "ollama":
        base_url = settings.ollama_base_url.strip().rstrip("/")
        primary_model = settings.ollama_model.strip()
        requested_model = (model or primary_model).strip()
        api_key = settings.ollama_api_key.strip()

        if not primary_model and not requested_model:
            raise RuntimeError("OLLAMA_MODEL is empty in configuration")

        headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
        if not api_key and base_url.startswith("https://ollama.com"):
            raise RuntimeError("OLLAMA_API_KEY is required when using Ollama Cloud (https://ollama.com)")

        payload = {
            "model": requested_model,
            "messages": [
                {"role": "system", "content": get_system_prompt()},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {"temperature": 0.1},
        }

        try:
            data = await post_json(f"{base_url}/api/chat", payload, headers)
            content = data.get("message", {}).get("content", "").strip()
            if not content:
                raise RuntimeError(f"Ollama model '{requested_model}' returned an empty response")
            return clean_llm_response(content)
        except Exception as exc:
            # If a secondary model (e.g. map model) failed, fallback to primary model
            if model and model != primary_model and primary_model:
                logger.warning("Requested model '%s' failed (%s). Retrying with primary model '%s'...", model, exc, primary_model)
                payload["model"] = primary_model
                data = await post_json(f"{base_url}/api/chat", payload, headers)
                content = data.get("message", {}).get("content", "").strip()
                if not content:
                    raise RuntimeError(f"Ollama primary model '{primary_model}' returned an empty response")
                return clean_llm_response(content)
            raise

    if provider == "cloud":
        if not settings.cloud_api_key:
            raise RuntimeError("CLOUD_API_KEY is required when LLM_PROVIDER=cloud")
        headers = {"Authorization": f"Bearer {settings.cloud_api_key}"}
        payload = {
            "model": settings.cloud_model,
            "messages": [
                {"role": "system", "content": get_system_prompt()},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        }
        data = await post_json(
            f"{settings.cloud_base_url.rstrip('/')}/chat/completions",
            payload,
            headers,
        )
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        if not content:
            raise RuntimeError("Cloud LLM returned an empty response")
        return clean_llm_response(content)

    raise RuntimeError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")

async def generate_with_retry(prompt: str, model: str | None = None, max_attempts: int = 3) -> str:
    last_error = None
    for attempt in range(max_attempts):
        try:
            return await generate(prompt, model=model)
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError, asyncio.TimeoutError) as exc:
            last_error = exc
            if attempt == max_attempts - 1:
                raise RuntimeError(f"LLM request timed out after {max_attempts} attempts: {exc}") from exc
            await asyncio.sleep(2 ** attempt)
        except Exception as exc:
            # If error is non-retryable 4xx (except timeout), raise immediately
            last_error = exc
            if "404" in str(exc) or "401" in str(exc) or "403" in str(exc):
                raise
            if attempt == max_attempts - 1:
                raise
            await asyncio.sleep(2 ** attempt)
    raise RuntimeError(f"LLM generation failed: {last_error}")

async def generate_map_memo(batch_no: int, source: str) -> str:
    settings = get_settings()
    map_model = settings.ollama_map_model.strip() if settings.llm_provider.lower() == "ollama" and settings.ollama_map_model else None
    prompt = f"""Prepare evidence memo batch {batch_no} from these source documents.
Extract parties, dates, identifiers, obligations, rights, representations, conditions, liabilities,
property/title signals, missing evidence and contradictions. Preserve exact values and cite each finding.

{source}"""
    return await generate_with_retry(prompt, model=map_model)

async def generate_title_search_report(source: str) -> str:
    """Generate the complete Title Search Report directly in a single pass from extracted document text."""
    prompt = f"""Using all the extracted facts from the provided input documents below, generate the complete, exhaustive Title Search Report according to the exact structured template in your system instructions.

Follow the exact template structure with all headings, sections 1 to 14, Property and boundaries, Chronological Flow of Title for each Gat Number / M.E. No., 14-point Checklist, Conclusion/Observation, and Final Certificate/Opinion with Advocate signoff.

INPUT DOCUMENTS:
{source}"""
    return await generate_with_retry(prompt)

async def reduce_memos(memos: list[str]) -> str:
    settings = get_settings()
    valid_memos = [m.strip() for m in memos if m and m.strip()]
    if not valid_memos:
        raise RuntimeError("No evidence memos were available to generate the final report")

    if len(valid_memos) == 1:
        return await generate_title_search_report(valid_memos[0])

    reduced = valid_memos
    while len(reduced) > 1:
        groups: list[list[str]] = []
        current: list[str] = []
        chars = 0
        for memo in reduced:
            if current and chars + len(memo) > settings.max_reduce_chars_per_batch:
                groups.append(current)
                current = []
                chars = 0
            current.append(memo)
            chars += len(memo)
        if current:
            groups.append(current)
        if len(groups) <= 1:
            break

        reduced = []
        for index, group in enumerate(groups, start=1):
            group_source = "\n\n--- BATCH MEMO ---\n".join(group)
            prompt = f"""Consolidate evidence memos group {index}.
Preserve every material fact, source citation, contradiction, missing document and legal risk.
Remove repetition, but do not invent or discard evidence.

{group_source}"""
            consolidated = await generate_with_retry(prompt)
            reduced.append(consolidated)

    final_source = "\n\n--- BATCH MEMO ---\n".join(reduced)
    report_prompt = f"""Using all the consolidated evidence from all examined documents below, generate the complete, exhaustive Title Search Report according to the exact structured template in your system instructions.

Follow the exact template structure with all headings, sections 1 to 14, Property and boundaries, Chronological Flow of Title for each Gat Number / M.E. No., 14-point Checklist, Conclusion/Observation, and Final Certificate/Opinion with Advocate signoff.

EVIDENCE:
{final_source}"""
    return await generate_with_retry(report_prompt)

async def embed(text: str) -> list[float] | None:
    settings = get_settings()
    if not settings.enable_embeddings:
        return None
    if settings.llm_provider.lower() != "ollama":
        return None
    base_url = settings.ollama_base_url.strip().rstrip("/")
    api_key = settings.ollama_api_key.strip()
    try:
        data = await post_json(
            f"{base_url}/api/embed",
            {"model": settings.ollama_embed_model.strip(), "input": text},
            {"Authorization": f"Bearer {api_key}"} if api_key else None,
            timeout_seconds=30.0,
        )
        embeddings = data.get("embeddings")
        if embeddings and len(embeddings) > 0:
            return embeddings[0]
    except Exception as exc:
        logger.warning("Embedding generation failed: %s. Continuing without embedding vector.", exc)
    return None

