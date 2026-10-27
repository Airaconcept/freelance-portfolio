"""Extraction backends.

* OpenAICompatibleBackend - any server that speaks the OpenAI Chat Completions API:
  OpenAI, Azure OpenAI, DeepSeek, OpenRouter, Groq, Together, Mistral, a local Ollama or LM Studio...
* RuleBackend - regular expressions, no AI and no network. Used for the offline demo and tests,
  and a useful fallback for very regular documents.

Every backend returns: {"doc_type": "...", "fields": {...}, "line_items": [...]}.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime

import requests

from schema import DOC_TYPES


# ---------------------------------------------------------------- prompt + JSON parsing
def build_prompt(text: str) -> list[dict]:
    spec = {}
    for name, t in DOC_TYPES.items():
        spec[name] = {
            "when": t["description"],
            "fields": {f: f"{typ} - {desc}" for f, (typ, desc) in t["fields"].items()},
        }
        if "line_items" in t:
            spec[name]["line_items"] = {f: f"{typ} - {desc}" for f, (typ, desc) in t["line_items"].items()}
    system = (
        "You extract structured data from business documents. "
        "Answer with ONE JSON object only, no prose, in this shape: "
        '{"doc_type": "<one of: ' + ", ".join(DOC_TYPES) + '>", "fields": {...}, "line_items": [...]}. '
        "Use exactly the field names below. Use null when a value is not in the text - never guess. "
        "Numbers without currency symbols or thousands separators. Dates as YYYY-MM-DD.\n"
        "Document types and fields:\n" + json.dumps(spec, indent=1)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": text}]


def parse_json_answer(content: str) -> dict:
    """Accept a bare JSON object, a ```json fenced block, or JSON surrounded by text."""
    s = content.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, re.S)
    if fence:
        s = fence.group(1)
    elif not s.startswith("{"):
        start, end = s.find("{"), s.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("no JSON object in model answer")
        s = s[start:end + 1]
    data = json.loads(s)
    if not isinstance(data, dict) or "doc_type" not in data:
        raise ValueError("answer is not an object with doc_type")
    data.setdefault("fields", {})
    data.setdefault("line_items", [])
    return data


# ---------------------------------------------------------------- OpenAI-compatible
class OpenAICompatibleBackend:
    name = "openai"

    def __init__(self, base_url: str | None = None, api_key: str | None = None, model: str | None = None,
                 timeout: float = 60, max_attempts: int = 3, json_mode: bool = True, session=None, sleep=time.sleep):
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key if api_key is not None else os.environ.get("LLM_API_KEY", "")
        self.model = model or os.environ.get("LLM_MODEL") or "gpt-4o-mini"
        self.timeout, self.max_attempts, self.json_mode = timeout, max_attempts, json_mode
        self.session = session or requests.Session()
        self.sleep = sleep

    def extract(self, text: str) -> dict:
        messages = build_prompt(text)
        last_err = None
        for attempt in range(1, self.max_attempts + 1):
            body = {"model": self.model, "messages": messages, "temperature": 0}
            if self.json_mode:
                body["response_format"] = {"type": "json_object"}
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            try:
                r = self.session.post(f"{self.base_url}/chat/completions", json=body, headers=headers, timeout=self.timeout)
            except requests.RequestException as e:
                last_err = e
            else:
                if r.status_code == 400 and self.json_mode and "response_format" in r.text:
                    self.json_mode = False                 # some servers do not support JSON mode
                    continue
                if r.status_code in (429, 500, 502, 503, 504):
                    last_err = RuntimeError(f"HTTP {r.status_code}")
                elif r.status_code >= 400:
                    raise RuntimeError(f"LLM API error {r.status_code}: {r.text[:300]}")
                else:
                    content = r.json()["choices"][0]["message"]["content"]
                    try:
                        return parse_json_answer(content)
                    except (ValueError, json.JSONDecodeError) as e:
                        last_err = e                       # ask again, telling the model what went wrong
                        messages = messages + [{"role": "assistant", "content": content},
                                               {"role": "user", "content": f"That was not valid JSON ({e}). Reply with the JSON object only."}]
                        continue
            if attempt < self.max_attempts:
                self.sleep(2 ** attempt)
        raise RuntimeError(f"LLM extraction failed after {self.max_attempts} attempts: {last_err}")


# ---------------------------------------------------------------- rules (offline)
MONEY = r"(?:[A-Z]{3}\s*|[$€£]\s*)?(-?[\d,]+\.\d{2})"
CURRENCY_HINTS = [("GBP", r"GBP|£"), ("EUR", r"EUR|€"), ("USD", r"USD|\$")]


def _find(pattern, text, flags=re.I | re.M):
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def _date(s):
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%m/%d/%Y", "%d.%m.%Y", "%B %d, %Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _company(line):
    if not line:
        return None
    line = re.sub(r"\(.*?\)|=+", "", line).strip(" -:")
    return line.title() if line.isupper() else line


class RuleBackend:
    name = "rules"

    def extract(self, text: str) -> dict:
        if re.search(r"\b(invoice|bill\s*#|amount payable)\b", text, re.I):
            return self._invoice(text)
        return self._email(text)

    def _invoice(self, text):
        first = next(l for l in text.splitlines() if l.strip())
        vendor = _find(r"^From:\s*(.+)$", text) or first
        currency = next((c for c, p in CURRENCY_HINTS if re.search(p, text)), None)
        f = {
            "vendor": _company(vendor),
            "customer": _find(r"^(?:Bill To|Customer|Sold To)\s*:?\s+(.+)$", text),
            "invoice_number": _find(r"(?:Invoice\s*(?:No|Number|#)|Bill\s*#)\s*:?\s*([A-Z0-9][\w-]+)", text),
            "invoice_date": _date(_find(r"(?:Invoice Date|Date of issue|^DATE)\s*:?\s+([\w /,.-]+?)(?:\s{2,}|$)", text)),
            "due_date": _date(_find(r"(?:Due Date|Payment due|due)\s*:?\s+([\w /,.-]+?)(?:\)|\s{2,}|$)", text)),
            "currency": currency,
            "subtotal": _find(r"(?:Subtotal|Net amount)\s*:?\s*" + MONEY, text),
            "tax": _find(r"(?:VAT[^:\n]*|Tax[^:\n]*?|SALES TAX)\s*:?\s*" + MONEY, text),
            "total": _find(r"(?:TOTAL DUE[^:\n]*|Amount payable|^TOTAL)\s*:?\s*" + MONEY, text),
        }
        items = []
        # table rows: "description   qty   price   amount"
        for m in re.finditer(r"^(\S.*?\S)\s{2,}(\d+)\s+" + MONEY + r"\s+" + MONEY + r"\s*$", text, re.M):
            items.append({"description": m.group(1), "quantity": m.group(2), "unit_price": m.group(3), "amount": m.group(4)})
        # bullet rows: "- 2 x Item @ EUR 45.00 = EUR 90.00"
        for m in re.finditer(r"^[-*]\s*(\d+)\s*x\s*(.+?)\s*@\s*" + MONEY + r"\s*=\s*" + MONEY, text, re.M):
            items.append({"description": m.group(2), "quantity": m.group(1), "unit_price": m.group(3), "amount": m.group(4)})
        return {"doc_type": "invoice", "fields": f, "line_items": items}

    def _email(self, text):
        body = text.split("\n\n", 1)[-1].lower()
        subject = _find(r"^Subject:\s*(.+)$", text)
        low = (subject or "").lower() + " " + body
        if re.search(r"damaged|crushed|broken|refund|complain|not happy", low):
            intent, urgency = "complaint", "high"
        elif re.search(r"\bquote\b|quotation", low) and re.search(r"\border\b", low):
            intent, urgency = "order", "normal"
        elif re.search(r"\bquote\b|pricing|discount", low):
            intent, urgency = "quote_request", "normal"
        elif "?" in body:
            intent, urgency = "question", "normal"
        else:
            intent, urgency = "other", "normal"
        if re.search(r"no rush|whenever|any time", low):
            urgency = "low"
        elif re.search(r"as soon as possible|asap|urgent", low):
            urgency = "high"
        items = re.findall(r"(\d+\+?\s+(?:[a-z-]+\s){0,3}?(?:mugs|boxes|sets|cups|bags|flyers|posters)(?:\s+of\s+[a-z]+(?:\s+[a-z]+)?)?)\b", body)
        items = [re.sub(r"\s+", " ", i).strip() for i in items]
        f = {
            "sender_name": _find(r"^From:\s*([^<\n]+?)\s*(?:<|$)", text),
            "company": _find(r"^Company:\s*(.+)$", text),
            "subject": subject,
            "intent": intent,
            "items_mentioned": ", ".join(dict.fromkeys(items)) or None,
            "reference": _find(r"\border\s+(?:no\.?\s*|#\s*)?(\d{4,})", text),
            "deadline": _date(_find(r"(?:before|by)\s+(\d{4}-\d{2}-\d{2})", text)),
            "urgency": urgency,
            "summary": None,   # summaries need a language model; the rules backend leaves this empty
        }
        return {"doc_type": "email", "fields": f, "line_items": []}


def get_backend(name: str, **kw):
    if name == "rules":
        return RuleBackend()
    if name == "openai":
        return OpenAICompatibleBackend(**kw)
    raise ValueError(f"unknown backend {name!r} (use 'openai' or 'rules')")
