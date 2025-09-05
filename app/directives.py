from __future__ import annotations
from typing import Dict, Any, List, Tuple
import re

URL_RE   = re.compile(r"(https?://[^\s]+|www\.[^\s]+\.[^\s]+|[^\s]+\.[^\s]*\.com[^\s]*)", re.I)
PHONE_RE = re.compile(r"(\+?[\d\-\s().]{10,})", re.I)

def _tok(s: str) -> List[str]:
    return re.findall(r"[A-Za-z0-9_+:/.-]+", (s or "").lower())

def _syn(cfg: Dict[str, Any], key: str) -> List[str]:
    return [x.lower() for x in (((cfg.get("nlp") or {}).get("synonyms") or {}).get(key) or [])]

def _extract_int(s: str) -> int | None:
    m = re.search(r"\b(\d{1,3})\b", s)
    return int(m.group(1)) if m else None

def _extract_brand(s: str) -> str | None:
    patterns = [
        r"\b(?:company|brand)\s+name\s+(?:is|as|=)\s+(.+?)(?=\s+(?:in|for|and|with|$))",
        r"\bmy\s+(?:company|brand)\s+(?:is|as|=)\s+(.+?)(?=\s+(?:in|for|and|with|$))",
        r"\b(?:include|add)\s+(.*)\s+as\s+(?:company|brand)\s+name\b",
        r"['\"]([^'\"]{2,60})['\"]",
    ]
    for p in patterns:
        m = re.search(p, s, re.I | re.S)
        if m:
            name = (m.group(1) or "").strip().strip('.,;:!\'" ')
            if name and not re.match(r'^(company|brand|name)$', name, re.I):
                return name[:60]
    return None

def ensure_brand_in_body(components: List[dict], brand: str, max_len: int = 1024) -> List[dict]:
    comps = list(components or [])
    for c in comps:
        if (c.get("type") or "").upper() == "BODY":
            text = c.get("text") or ""
            present = re.search(rf"\b{re.escape(brand)}\b", text, re.I) is not None
            if brand and not present:
                sep = " — " if not text.endswith(("!", ".", "…")) else " "
                c["text"] = (text + sep + brand)[:max_len]
            break
    return comps

def _defaults_by_category(cfg: Dict[str, Any], cat: str) -> List[str]:
    lr = (cfg.get("lint_rules") or {})
    comps = (lr.get("components") or {})
    btns = (comps.get("buttons") or {})
    mapping = (btns.get("defaults_by_category") or {})
    return mapping.get(cat, mapping.get("MARKETING", ["Shop now", "Learn more", "Contact us"]))

def _dedup_labels(labels: List[str]) -> List[str]:
    seen = set(); out = []
    for l in labels:
        k = l.strip().lower()
        if k and k not in seen:
            out.append(l)
            seen.add(k)
    return out

def parse_directives(cfg: Dict[str, Any], text: str) -> List[dict]:
    """Return normalized directives from user text (config-driven; no business hardcode)."""
    toks = _tok(text)
    s = text.lower()

    syn_add     = _syn(cfg, "add")
    syn_button  = _syn(cfg, "button")
    syn_brand   = _syn(cfg, "brand")
    syn_shorten = _syn(cfg, "shorten")
    syn_body    = _syn(cfg, "body")
    syn_name    = _syn(cfg, "name")
    syn_header  = _syn(cfg, "header")
    syn_footer  = _syn(cfg, "footer")
    syn_remove  = _syn(cfg, "remove")
    syn_replace = _syn(cfg, "replace")
    syn_modify  = _syn(cfg, "modify")

    directives: List[dict] = []

    # buttons
    wants_button = any(x in toks for x in syn_button) or ("button" in s or "buttons" in s)
    if wants_button:
        url = URL_RE.search(text)
        phone = PHONE_RE.search(text)
        # explicit count "one / 1 / 2 / 3"
        count = _extract_int(text)
        labels = []
        # quoted labels become exact quick replies - fixed regex pattern
        for m in re.findall(r'["\']([^"\']{1,30})["\']', text):
            labels.append(m.strip())
        if "quick reply" in s or "quick replies" in s:
            # treat as quick reply hint
            pass

        if url:
            url_text = url.group(0)
            # Ensure URL has protocol
            if not url_text.startswith(('http://', 'https://')):
                if url_text.startswith('www.'):
                    url_text = 'https://' + url_text
                else:
                    url_text = 'https://' + url_text
            directives.append({"type": "buttons.set", "mode": "replace", "buttons": [
                {"type": "URL", "text": labels[0] if labels else "Visit Website", "url": url_text}
            ]})
        elif phone:
            directives.append({"type": "buttons.set", "mode": "replace", "buttons": [
                {"type": "PHONE_NUMBER", "text": labels[0] if labels else "Call us", "phone_number": phone.group(0)}
            ]})
        else:
            # quick replies; respect count if specified; use labels if provided
            directives.append({"type": "buttons.set", "mode": "replace", "count": count, "labels": labels})

    # brand/company
    if any(x in toks for x in syn_brand) or "company name" in s or "brand name" in s:
        brand = _extract_brand(text)
        if brand:
            directives.append({"type": "brand.set", "name": brand})

    # shorten
    if any(x in toks for x in syn_shorten) or "make it short" in s:
        target = None
        m = re.search(r"\b(\d{2,4})\b", text)
        if m: 
            target = int(m.group(1))
        directives.append({"type": "body.shorten", "target": target})

    # set name
    if any(x in toks for x in syn_name):
        m = re.search(r'name\s*(?:is|=|as)?\s*["\']?([a-z0-9_]{1,64})["\']?', text, re.I)
        if m:
            directives.append({"type": "name.set", "name": m.group(1)})

    # set body
    if any(x in toks for x in syn_body):
        # Try multiple patterns for body content extraction
        patterns = [
            r'(?:body|message|text|content)\s*(?:is|=|:)\s*["\'](.+?)["\']',  # Original quoted pattern
            r'(?:message|text)\s+(?:should\s+)?(?:say|be|read):\s*(.+?)(?=\s+and\s+add\s+|\s+and\s+button|\s*$)',  # "message should say: content"
            r'(?:body|message|text|content)\s*(?:is|=|:)\s*(.+?)(?=\s+and\s+|\s*$)',  # Unquoted until "and" or end
        ]
        for pattern in patterns:
            q = re.search(pattern, text, re.I | re.S)
            if q:
                content = q.group(1).strip().strip('\'"')  # Remove quotes if present
                if content:  # Only add if not empty
                    directives.append({"type": "body.set", "text": content})
                    break

    # header/footer simple text set
    if any(x in toks for x in syn_header):
        h = re.search(r'header\s*(?:is|=|:)\s*["\'](.+?)["\']', text, re.I | re.S)
        if h:
            directives.append({"type": "header.set", "format": "TEXT", "text": h.group(1).strip()})
    if any(x in toks for x in syn_footer):
        f = re.search(r'footer\s*(?:is|=|:)\s*["\'](.+?)["\']', text, re.I | re.S)
        if f:
            directives.append({"type": "footer.set", "text": f.group(1).strip()})

    # delete operations (optional)
    if any(x in toks for x in syn_remove):
        if "header" in s: 
            directives.append({"type": "header.delete"})
        if "footer" in s: 
            directives.append({"type": "footer.delete"})
        if "button" in s or "buttons" in s: 
            directives.append({"type": "buttons.delete"})

    return directives

def _category(candidate: Dict[str, Any], memory: Dict[str, Any]) -> str:
    return (candidate.get("category") or memory.get("category") or "").upper()

def apply_directives(cfg: Dict[str, Any], directives: List[dict],
                     candidate: Dict[str, Any], memory: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    out = dict(candidate or {})
    comps = list(out.get("components") or [])
    msgs: List[str] = []

    def get_buttons() -> dict | None:
        return next((c for c in comps if (c.get("type") or "").upper()=="BUTTONS"), None)

    def set_buttons(buttons: List[dict], replace: bool = True):
        nonlocal comps
        if replace:
            comps = [c for c in comps if (c.get("type") or "").upper() != "BUTTONS"]
            comps.append({"type": "BUTTONS", "buttons": buttons})
        else:
            blk = get_buttons()
            if not blk:
                comps.append({"type": "BUTTONS", "buttons": buttons})
            else:
                blk["buttons"].extend(buttons)

    # global limits
    limits = (cfg.get("limits") or {})
    blim  = (limits.get("buttons") or {})
    max_visible = int(blim.get("max_visible", 3))

    cat = _category(out, memory)

    for d in directives:
        t = d.get("type")

        # --- BUTTONS ---
        if t == "buttons.set":
            # Auth: validator will enforce, we still set (can also skip if you prefer)
            labels = d.get("labels") or []
            count  = d.get("count")
            mode   = (d.get("mode") or "replace").lower()

            # labels → quick replies
            if labels:
                labels = _dedup_labels([str(x)[:25] for x in labels])
                btns = [{"type": "QUICK_REPLY", "text": lab} for lab in labels]
                set_buttons(btns, replace=(mode=="replace"))
                # Let LLM handle friendly acknowledgment
                pass
            # URL/PHONE already normalized in parse_directives
            elif d.get("buttons"):
                btns = d["buttons"]
                set_buttons(btns, replace=(mode=="replace"))
                # Don't generate technical messages - let LLM handle friendly responses
                pass
            else:
                # No labels provided → pick defaults by category/business
                defaults = _defaults_by_category(cfg, cat) or ["Shop now"]
                if count is None: 
                    count = 1  # respect "one button" intents by default
                defaults = defaults[:max_visible]
                labels = defaults[: max(1, min(max_visible, int(count)))]
                btns = [{"type": "QUICK_REPLY", "text": lab} for lab in labels]
                set_buttons(btns, replace=(mode=="replace"))
                # Let LLM provide friendly acknowledgment
                pass

            out["components"] = comps

        elif t == "buttons.delete":
            before = len([c for c in comps if (c.get("type") or "").upper()=="BUTTONS"])
            comps = [c for c in comps if (c.get("type") or "").upper()!="BUTTONS"]
            after = len([c for c in comps if (c.get("type") or "").upper()=="BUTTONS"])
            if before!=after:
                msgs.append("Removed buttons.")
            out["components"] = comps

        # --- BRAND ---
        elif t == "brand.set":
            name = (d.get("name") or "").strip()
            if not name: 
                continue
            memory["brand_name"] = name
            comps2 = ensure_brand_in_body(comps, name)
            if comps2 is comps:
                memory["brand_name_pending"] = name
                msgs.append(f'Captured brand "{name}" (will apply once BODY is set).')
            else:
                comps = comps2
                msgs.append(f'Added brand "{name}" to BODY.')
            out["components"] = comps

        # --- BODY ---
        elif t == "body.set":
            txt = (d.get("text") or "").strip()
            if not txt: 
                continue
            inserted = False
            for c in comps:
                if (c.get("type") or "").upper()=="BODY":
                    c["text"] = txt
                    inserted = True
                    break
            if not inserted:
                comps.insert(0, {"type": "BODY", "text": txt})
            if memory.get("brand_name_pending"):
                comps = ensure_brand_in_body(comps, memory.pop("brand_name_pending"))
            msgs.append("Updated BODY.")
            out["components"] = comps

        elif t == "body.shorten":
            target = d.get("target") or (((cfg.get("text") or {}).get("shorten") or {}).get("target_length", 140))
            for c in comps:
                if (c.get("type") or "").upper()=="BODY" and (c.get("text") or "").strip():
                    text = re.sub(r"\s+", " ", c["text"].strip())
                    if len(text) > target:
                        # naive sentence-aware trim
                        parts = re.split(r"(?<=[.!?])\s+", text)
                        acc = ""
                        for p in parts:
                            if len((acc + " " + p).strip()) <= target:
                                acc = (acc + " " + p).strip()
                            else:
                                break
                        if not acc:
                            cut = text[:target].rsplit(" ", 1)[0] or text[:target]
                            acc = cut + "…"
                        c["text"] = acc
                        msgs.append(f"Shortened BODY to ≈{target} chars.")
                    break
            out["components"] = comps

        # --- NAME ---
        elif t == "name.set":
            name = (d.get("name") or "").strip()
            if name:
                out["name"] = name
                msgs.append("Updated template name.")

        # --- HEADER ---
        elif t == "header.set":
            fmt = (d.get("format") or "TEXT").upper()
            txt = (d.get("text") or "").strip()
            comps = [c for c in comps if (c.get("type") or "").upper()!="HEADER"]
            h = {"type": "HEADER", "format": fmt}
            if fmt == "TEXT" and txt:
                h["text"] = txt[:60]
            comps.insert(0, h)
            msgs.append("Updated HEADER.")
            out["components"] = comps

        elif t == "header.delete":
            before = len([c for c in comps if (c.get("type") or "").upper()=="HEADER"])
            comps = [c for c in comps if (c.get("type") or "").upper()!="HEADER"]
            if before != len([c for c in comps if (c.get("type") or "").upper()=="HEADER"]):
                msgs.append("Removed HEADER.")
            out["components"] = comps

        # --- FOOTER ---
        elif t == "footer.set":
            txt = (d.get("text") or "").strip()
            seen = False
            for c in comps:
                if (c.get("type") or "").upper()=="FOOTER":
                    c["text"] = txt[:60]
                    seen = True
                    break
            if not seen and txt:
                comps.append({"type": "FOOTER", "text": txt[:60]})
            msgs.append("Updated FOOTER.")
            out["components"] = comps

        elif t == "footer.delete":
            before = len([c for c in comps if (c.get("type") or "").upper()=="FOOTER"])
            comps = [c for c in comps if (c.get("type") or "").upper()!="FOOTER"]
            if before != len([c for c in comps if (c.get("type") or "").upper()=="FOOTER"]):
                msgs.append("Removed FOOTER.")
            out["components"] = comps

    return out, msgs
