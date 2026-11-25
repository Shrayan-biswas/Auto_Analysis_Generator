import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from openai import OpenAI


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_NEMOTRON_MODEL = "nemotron-3-nano:4b"
NVIDIA_NEMOTRON_MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
NVIDIA_API_BASE_URL = "https://integrate.api.nvidia.com/v1"

SYSTEM_PROMPT = """You are a senior business and data analyst. Analyze only evidence
in the supplied dataset profile and document text. Do not invent facts, values,
causes, targets, or forecasts. Distinguish observed facts from hypotheses. Explain
what each important chart or visual communicates, call out missing or unreliable
data, and give concrete recommendations tied to the evidence. Use the exact
section headings requested by the user."""

REPORT_PROMPT = """Write a complete, decision-ready analysis report in Markdown.
Prioritize this focus: {focus}

Required sections:
# Executive Summary
# Dataset and Scope
# Key Findings
# Trends and Comparisons
# Chart and Visual Interpretation
# Risks, Anomalies, and Data Quality
# Recommendations
# Limitations and Assumptions

Use specific numbers and table/sheet/page/slide names from the evidence. Explain
the meaning of each major comparison and its business implication. Clearly state
when the input does not contain enough evidence for a conclusion. For PBIX
layout-only metadata, do not claim access to underlying figures.

Evidence:
{context}
"""


def _request_json(url, payload, timeout=180):
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            response_data = response.read().decode("utf-8")
    except HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"AI provider returned HTTP {error.code}: {details[:1200]}"
        ) from error
    except URLError as error:
        raise RuntimeError(
            f"Could not connect to the AI provider at {url}: {error.reason}"
        ) from error
    try:
        return json.loads(response_data)
    except json.JSONDecodeError as error:
        raise RuntimeError("AI provider returned invalid JSON.") from error


def list_ollama_models(base_url=OLLAMA_URL):
    request = Request(
        f"{base_url.rstrip('/')}/api/tags",
        headers={"Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=3) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, json.JSONDecodeError) as error:
        raise RuntimeError(
            "Ollama is not reachable. Install/start Ollama and run "
            f"`ollama pull {OLLAMA_NEMOTRON_MODEL}`."
        ) from error
    return sorted(
        item["name"]
        for item in result.get("models", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    )


def _generate_nvidia_stream(prompt, api_key):
    client = OpenAI(
        base_url=NVIDIA_API_BASE_URL,
        api_key=api_key,
    )
    completion = client.chat.completions.create(
        model=NVIDIA_NEMOTRON_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=1,
        top_p=0.95,
        max_tokens=16384,
        parallel_tool_calls=True,
        seed=42,
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
        stream=True,
    )
    answer_parts = []
    for chunk in completion:
        if not chunk.choices:
            continue
        content = chunk.choices[0].delta.content
        if content:
            answer_parts.append(content)
    answer = "".join(answer_parts)
    if not answer.strip():
        raise RuntimeError("Nemotron returned an empty analysis.")
    return answer.strip()


def generate_report(
    context,
    focus="General business overview",
    provider="Ollama (local Nemotron)",
    model=OLLAMA_NEMOTRON_MODEL,
    api_key=None,
):
    prompt = REPORT_PROMPT.format(focus=focus, context=context)

    if provider == "NVIDIA hosted Nemotron":
        api_key = api_key or os.getenv("NVIDIA_API_KEY")
        if not api_key:
            raise RuntimeError(
                "NVIDIA API key is missing. Add one in the sidebar or set "
                "NVIDIA_API_KEY in Streamlit secrets or the environment."
            )
        # Always target the configured live model; ignore stale widget/session values.
        return _generate_nvidia_stream(
            prompt,
            api_key,
        )

    if provider == "Ollama (local Nemotron)":
        result = _request_json(
            f"{OLLAMA_URL.rstrip('/')}/api/chat",
            {
                "model": model or OLLAMA_NEMOTRON_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_predict": 3500,
                },
            },
        )
        answer = result.get("message", {}).get("content")
    else:
        raise ValueError(f"Unsupported AI provider: {provider}")

    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("Nemotron returned an empty analysis.")
    return answer.strip()
