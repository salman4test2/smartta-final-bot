# app/llm.py
from __future__ import annotations
import json, time, os, re
from typing import List, Dict, Any

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

class LlmClient:
    def __init__(self, model: str, temperature: float = 0.2, timeout: int = 40):
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.client = OpenAI() if (OpenAI and os.getenv("OPENAI_API_KEY")) else None

    def _mock(self, system: str, context: str, history: List[Dict[str, str]], user: str) -> Dict[str, Any]:
        # deterministic safe mock so /chat works without a key
        is_create = bool(re.search(r"\b(create|make|draft|template)\b", user, re.I))
        out = {
            "agent_action": "ASK" if not is_create else "DRAFT",
            "message_to_user": "Mock: I prepared a draft. Tell me the category, name, language, body.",
            "draft": {
                "category": "MARKETING",
                "name": "auto_template",
                "language": "en_US",
                "components": [{"type": "BODY", "text": "Hi {{1}}, special offer! Enjoy {{2}}."}]
            },
            "missing": ["category","name","language","body"],
            "final_creation_payload": None,
            "memory": {"category": "MARKETING", "event_label": "offer", "buttons_request": {"count": 2, "types": ["QUICK_REPLY"]}}
        }
        return out

    def respond(self, system: str, context: str, history: List[Dict[str, str]], user: str) -> Dict[str, Any]:
        if not self.client:
            return self._mock(system, context, history, user)

        messages = [{"role": "system", "content": system},
                    {"role": "system", "content": context}] + history + [{"role": "user", "content": user}]
        t0 = time.time()
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                response_format={"type": "json_object"},
                messages=messages,
                timeout=self.timeout,
            )
            content = resp.choices[0].message.content or "{}"
            out = json.loads(content)
        except Exception as e:
            # salvage JSON object from any text
            try:
                m = re.search(r"\{[\s\S]*\}$", content or "")
                if m: out = json.loads(m.group(0))
                else: raise
            except Exception:
                # fall back to a single question so convo keeps moving
                out = {"agent_action": "ASK",
                       "message_to_user": "I couldn’t parse that. What template category should I use — MARKETING, UTILITY, or AUTHENTICATION?",
                       "draft": None, "missing": ["category"], "final_creation_payload": None, "memory": None}
        out["_latency_ms"] = int(1000 * (time.time() - t0))
        return out
