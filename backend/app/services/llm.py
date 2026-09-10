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
    """Call Ollama Cloud API at https://ollama.com/api/chat."""
    settings = get_settings()
    base_url = settings.ollama_base_url.strip().rstrip("/")
    primary_model = settings.ollama_model.strip()
    requested_model = (model or primary_model).strip()
    api_key = settings.ollama_api_key.strip()

    if not requested_model:
        raise RuntimeError("OLLAMA_MODEL is empty in configuration")
    if not api_key:
        raise RuntimeError("OLLAMA_API_KEY is required for Ollama Cloud")

    api_url = f"{base_url}/api/chat"
    headers = {"Authorization": f"Bearer {api_key}"}
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
        logger.info("Calling Ollama Cloud model '%s' at %s", requested_model, api_url)
        data = await post_json(api_url, payload, headers)
        content = data.get("message", {}).get("content", "").strip()
        if not content:
            raise RuntimeError(f"Ollama Cloud model '{requested_model}' returned an empty response. Raw: {str(data)[:300]}")
        logger.info("Ollama Cloud model '%s' responded successfully (%d chars)", requested_model, len(content))
        return clean_llm_response(content)
    except Exception as exc:
        logger.error("Ollama Cloud call failed for model '%s': %s", requested_model, exc)
        # If a secondary model (e.g. map model) failed, fallback to primary model
        if model and model != primary_model and primary_model:
            is_rate_limit = "429" in str(exc) or "too many concurrent" in str(exc).lower()
            sleep_secs = 5.0 if is_rate_limit else 1.0
            logger.warning("Model '%s' failed (%s). Waiting %ds then retrying with primary model '%s'...", model, exc, sleep_secs, primary_model)
            await asyncio.sleep(sleep_secs)
            payload["model"] = primary_model
            data = await post_json(api_url, payload, headers)
            content = data.get("message", {}).get("content", "").strip()
            if not content:
                raise RuntimeError(f"Ollama Cloud primary model '{primary_model}' returned an empty response")
            return clean_llm_response(content)
        raise

async def generate_with_retry(prompt: str, model: str | None = None, max_attempts: int = 6) -> str:
    """Retry LLM calls with progressive backoff. Defaults to 6 attempts for rate-limited providers."""
    last_error = None
    for attempt in range(max_attempts):
        try:
            return await generate(prompt, model=model)
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError, asyncio.TimeoutError) as exc:
            last_error = exc
            if attempt == max_attempts - 1:
                raise RuntimeError(f"LLM request timed out after {max_attempts} attempts: {exc}") from exc
            sleep_time = min(2 ** attempt, 30)  # cap at 30s
            logger.info("LLM timeout on attempt %d/%d. Retrying in %ds...", attempt + 1, max_attempts, sleep_time)
            await asyncio.sleep(sleep_time)
        except Exception as exc:
            # Non-retryable auth/notfound errors — raise immediately
            last_error = exc
            is_rate_limit = "429" in str(exc) or "too many concurrent" in str(exc).lower()
            if not is_rate_limit and ("404" in str(exc) or "401" in str(exc) or "403" in str(exc)):
                raise
            if attempt == max_attempts - 1:
                raise
            # Progressive backoff: 5s, 10s, 15s, 20s, 25s for rate limits; exponential for others
            sleep_time = (5 * (attempt + 1)) if is_rate_limit else min(2 ** attempt, 30)
            logger.info("LLM attempt %d/%d failed (%s). Retrying in %ds...", attempt + 1, max_attempts, exc, sleep_time)
            await asyncio.sleep(sleep_time)
    raise RuntimeError(f"LLM generation failed after {max_attempts} attempts: {last_error}")

async def generate_map_memo(batch_no: int, source: str) -> str:
    settings = get_settings()
    map_model = settings.ollama_map_model.strip() if settings.ollama_map_model else None
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
    """Generate embeddings via Ollama Cloud."""
    settings = get_settings()
    if not settings.enable_embeddings:
        return None
    base_url = settings.ollama_base_url.strip().rstrip("/")
    api_key = settings.ollama_api_key.strip()
    if not api_key:
        return None
    try:
        data = await post_json(
            f"{base_url}/api/embed",
            {"model": settings.ollama_embed_model.strip(), "input": text},
            {"Authorization": f"Bearer {api_key}"},
            timeout_seconds=30.0,
        )
        embeddings = data.get("embeddings")
        if embeddings and len(embeddings) > 0:
            return embeddings[0]
    except Exception as exc:
        logger.warning("Embedding generation failed: %s. Continuing without embedding vector.", exc)
    return None
