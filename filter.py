"""Keyword-based topic filtering. No AI/LLM anywhere in the pipeline.

An entry is kept only if it matches at least one allowed category.
Everything else is noise and gets marked as seen (never posted).

Categories:
  security - exploits, vulnerabilities, CVEs, network/infosec news
  ai       - models, pricing, capability/benchmarks, releases

Matching is strict: bare generic words ("price", "model", "hack") are not
enough on their own; they must combine with a strong AI/security signal.
"""

from __future__ import annotations

import re

from fetcher import Entry

CVE_RE = re.compile(r"CVE-\d{4}-\d{4,7}", re.IGNORECASE)


def _word(term: str) -> str:
    return rf"\b{re.escape(term)}\b"


def _compile(patterns: list[str]) -> list[re.Pattern]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


SECURITY_PATTERNS = _compile(
    [
        _word("exploit"), _word("exploits"), _word("exploited"), _word("exploitation"),
        _word("zero-day"), _word("zeroday"), _word("0-day"), _word("0day"),
        _word("vulnerability"), _word("vulnerabilities"), _word("vulnerable"),
        _word("vuln"), _word("vulns"), _word("cve"),
        _word("remote code execution"), _word("rce"),
        _word("privilege escalation"), _word("arbitrary code"),
        _word("buffer overflow"), _word("memory corruption"),
        _word("sandbox escape"), _word("authentication bypass"),
        _word("sql injection"), _word("command injection"), _word("injection"),
        _word("backdoor"), _word("reverse shell"), _word("malware"),
        _word("ransomware"), _word("botnet"), _word("trojan"), _word("spyware"),
        _word("rootkit"), _word("keylogger"), _word("phishing"),
        _word("credential stuffing"), _word("brute force"),
        _word("data breach"), _word("breach"), _word("compromised"),
        _word("hacked"), _word("hacking"), _word("threat actor"),
        _word("security advisory"), _word("security researcher"),
        _word("security flaw"), _word("security vulnerability"),
        _word("security update"), _word("infosec"), _word("cybersecurity"),
        _word("exploit chain"), _word("side channel"), _word("side-channel"),
        r"\bsupply chain attack",
        _word("red team"), _word("penetration test"),
        _word("pentest"), _word("command and control"), _word("exfiltrat"),
        _word("cisa"), _word("nist"), _word("owasp"), _word("payload"),
        _word("ddos"),
        r"\bcve-\d{4}-\d{4,7}\b",
    ]
)

AI_STRONG = _compile(
    [
        _word("openai"), _word("chatgpt"), _word("gpt"), _word("gpt-4"),
        _word("gpt-4o"), _word("gpt-5"), _word("claude"), _word("anthropic"),
        _word("gemini"), _word("deepmind"), _word("llama"), _word("mistral"),
        _word("deepseek"), _word("qwen"), _word("grok"), _word("xai"),
        _word("copilot"), _word("sora"), _word("midjourney"), _word("perplexity"),
        _word("ollama"), _word("hugging face"), _word("huggingface"),
        _word("cerebras"), _word("gemma"), _word("minimax"),
        _word("stable diffusion"), _word("whisper"),
        _word("large language model"), _word("llm"), _word("multimodal"),
        _word("foundation model"), _word("open weights"), _word("fine-tun"),
        _word("fine tuning"), _word("pre-training"), _word("pretrain"),
        _word("inference"), _word("diffusion model"), _word("text-to-video"),
        _word("text-to-image"), _word("image generation"), _word("ai agent"),
        _word("ai agents"), _word("reasoning model"), _word("agi"),
        _word("machine learning"), _word("deep learning"), _word("neural network"),
        _word("transformer"), _word("benchmark"), _word("benchmarks"),
        _word("mmlu"), _word("gpqa"), _word("humaneval"), _word("swe-bench"),
        _word("leaderboard"), _word("context window"), _word("context length"),
        _word("h100"), _word("b200"), _word("nvidia"),
        _word("artificial intelligence"), _word("ai model"), _word("ai models"),
        _word("open-source model"), _word("open source model"),
        _word("model weights"), _word("inference cost"), _word("training run"),
        _word("reasoning"), _word("agentic"),
        r"\bpretrain",
    ]
)

AI_CONTEXT = _compile(
    [
        _word("pricing"), _word("price"), _word("prices"), _word("subscription"),
        _word("api cost"), _word("token cost"), _word("per token"),
        _word("capabilit"), _word("performance"),
    ]
)

AI_WORD = re.compile(_word("ai"), re.IGNORECASE)


def _matches_security(text: str) -> bool:
    if CVE_RE.search(text):
        return True
    return any(p.search(text) for p in SECURITY_PATTERNS)


def _matches_ai(text: str) -> bool:
    return (
        any(p.search(text) for p in AI_STRONG)
        or (AI_WORD.search(text) and any(p.search(text) for p in AI_CONTEXT))
    )


MATCHERS = {"security": _matches_security, "ai": _matches_ai}


def matches_categories(entry: Entry, categories: list[str]) -> bool:
    """Return True if the entry matches at least one allowed category."""
    text = f"{entry.title} {entry.summary} {entry.link}".lower()
    return any(matcher(text) for name, matcher in MATCHERS.items() if name in categories)


def matching_keywords(entry: Entry, categories: list[str]) -> dict[str, list[str]]:
    """Return a dict of {category: [matched_pattern, ...]} for the entry."""
    text = f"{entry.title} {entry.summary} {entry.link}".lower()
    result: dict[str, list[str]] = {}
    for name in categories:
        if name not in MATCHERS:
            continue
        patterns: list[re.Pattern] = []
        if name == "security":
            patterns = SECURITY_PATTERNS
        elif name == "ai":
            patterns = AI_STRONG
        hits: list[str] = []
        if name == "security" and CVE_RE.search(text):
            hits.append("CVE regex match")
        for p in patterns:
            m = p.search(text)
            if m:
                hits.append(m.group(0))
        if name == "ai" and not hits and AI_WORD.search(text):
            for p in AI_CONTEXT:
                m = p.search(text)
                if m:
                    hits.append(f"(ai context) {m.group(0)}")
        if hits:
            result[name] = hits
    return result
