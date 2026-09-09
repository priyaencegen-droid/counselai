import asyncio
import httpx
from app.core.config import get_settings
from app.prompts.prompts_user import get_system_prompt

async def post_json(url: str, payload: dict, headers: dict | None = None) -> dict:
    timeout = httpx.Timeout(300.0, connect=30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.is_error:
            detail = response.text.strip()
            raise RuntimeError(f"LLM request failed with HTTP {response.status_code}: {detail[:500]}")
        return response.json()

async def generate(prompt: str, model: str | None = None) -> str:
    settings = get_settings()
    provider = settings.llm_provider.lower().strip()
    if provider == "ollama":
        base_url = settings.ollama_base_url.strip().rstrip("/")
        model = (model or settings.ollama_model).strip()
        api_key = settings.ollama_api_key.strip()
        if not model:
            raise RuntimeError("OLLAMA_MODEL is empty")
        headers = None
        if api_key:
            headers = {"Authorization": f"Bearer {api_key}"}
        elif base_url == "https://ollama.com":
            raise RuntimeError("OLLAMA_API_KEY is required when OLLAMA_BASE_URL=https://ollama.com")
        data = await post_json(f"{base_url}/api/chat", {
            "model": model,
            "messages": [{"role": "system", "content": get_system_prompt()}, {"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.1},
        }, headers)
        content = data.get("message", {}).get("content", "").strip()
        if not content:
            raise RuntimeError("Ollama returned an empty response")
        return content
    if provider == "cloud":
        if not settings.cloud_api_key:
            raise RuntimeError("CLOUD_API_KEY is required when LLM_PROVIDER=cloud")
        data = await post_json(
            f"{settings.cloud_base_url.rstrip('/')}/chat/completions",
            {"model": settings.cloud_model,
             "messages": [{"role": "system", "content": get_system_prompt()}, {"role": "user", "content": prompt}],
             "temperature": 0.1},
            {"Authorization": f"Bearer {settings.cloud_api_key}"},
        )
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        if not content:
            raise RuntimeError("Cloud LLM returned an empty response")
        return content
    raise RuntimeError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")

async def generate_with_retry(prompt: str, model: str | None = None) -> str:
    for attempt in range(3):
        try:
            return await generate(prompt, model=model)
        except (httpx.ReadTimeout, asyncio.TimeoutError):
            if attempt == 2:
                raise
            await asyncio.sleep(2 ** attempt)

async def generate_map_memo(batch_no: int, source: str) -> str:
    settings = get_settings()
    return await generate_with_retry(f"""Prepare evidence memo batch {batch_no} from these source documents.
Extract parties, dates, identifiers, obligations, rights, representations, conditions, liabilities,
property/title signals, missing evidence and contradictions. Preserve exact values and cite each finding.

{source}""", model=settings.ollama_map_model if settings.llm_provider.lower() == "ollama" else None)

async def reduce_memos(memos: list[str]) -> str:
    settings = get_settings()
    reduced = memos
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
        if len(groups) == 1:
            break
        reduced = [await generate_with_retry(f"""Consolidate evidence memos group {index}.
Preserve every material fact, source citation, contradiction, missing document and legal risk.
Remove repetition, but do not invent or discard evidence.

{chr(10).join(groups[index - 1])}""") for index in range(1, len(groups) + 1)]
    final_source = "\n\n--- BATCH MEMO ---\n".join(reduced)
    return await generate_with_retry(f"""Create the final legal analysis report from the following evidence memos.
Cross-check all memos. Explicitly identify contradictions across files. Treat uncertain findings as uncertain.
Follow the exact five-section Markdown structure in your system instructions.

{final_source}""")

async def embed(text: str) -> list[float] | None:
    settings = get_settings()
    if not settings.enable_embeddings:
        return None
    if settings.llm_provider.lower() != "ollama":
        return None
    base_url = settings.ollama_base_url.strip().rstrip("/")
    api_key = settings.ollama_api_key.strip()
    data = await post_json(
        f"{base_url}/api/embed",
        {"model": settings.ollama_embed_model.strip(), "input": text},
        {"Authorization": f"Bearer {api_key}"} if api_key else None,
    )
    return data.get("embeddings", [None])[0]

async def analyze_map_reduce(documents: list[dict]) -> str:
    settings = get_settings()
    if not documents or not any(doc.get("chunks") for doc in documents):
        raise RuntimeError("No text was extracted from the uploaded documents")
    batches: list[list[dict]] = []
    current: dict[str, list[dict]] = {}
    chars = 0
    for doc in documents:
        for chunk in doc["chunks"]:
            chunk_chars = len(chunk["text"])
            if current and chars + chunk_chars > settings.max_context_chars_per_batch:
                batches.append([{"filename": filename, "chunks": chunks} for filename, chunks in current.items()])
                current = {}
                chars = 0
            current.setdefault(doc["filename"], []).append(chunk)
            chars += chunk_chars
    if current:
        batches.append([{"filename": filename, "chunks": chunks} for filename, chunks in current.items()])

    memos = []
    for batch_no, batch in enumerate(batches, start=1):
        source = "\n\n".join(
            f"SOURCE FILE: {d['filename']}\n" + "\n".join(f"[{c['location']}] {c['text']}" for c in d["chunks"])
            for d in batch
        )
        prompt = f"""Prepare evidence memo batch {batch_no} from these source documents.
Extract parties, dates, identifiers, obligations, rights, representations, conditions, liabilities,
property/title signals, missing evidence and contradictions. Preserve exact values and cite each finding.

{source}"""
        memos.append(await generate(prompt))

    reduced_memos = memos
    while len(reduced_memos) > 1:
        groups: list[list[str]] = []
        current: list[str] = []
        chars = 0
        for memo in reduced_memos:
            memo_size = len(memo)
            if current and chars + memo_size > settings.max_reduce_chars_per_batch:
                groups.append(current)
                current = []
                chars = 0
            current.append(memo)
            chars += memo_size
        if current:
            groups.append(current)

        if len(groups) == 1:
            break

        reduced_memos = []
        for group_no, group in enumerate(groups, start=1):
            source = "\n\n--- BATCH MEMO ---\n".join(group)
            reduced_memos.append(await generate(f"""Consolidate evidence memos group {group_no}.
Preserve every material fact, source citation, contradiction, missing document and legal risk.
Remove repetition, but do not invent or discard evidence.

{source}"""))

    final_source = "\n\n--- BATCH MEMO ---\n".join(reduced_memos)
    return await generate(f"""Create the final legal analysis report from the following evidence memos.
Cross-check all memos. Explicitly identify contradictions across files. Treat uncertain findings as uncertain.
Follow the exact five-section Markdown structure in your system instructions.

{final_source}""")
