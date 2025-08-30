"""
Interactive mode router for WhatsApp template builder.
Provides a field-by-field editing interface driven by backend logic.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..db import SessionLocal
from ..models import User, Draft
from ..repo import get_or_create_session, upsert_session, create_draft
from ..schemas import (
    InteractiveStartRequest, InteractiveStateResponse,
    InteractiveSetCategoryRequest, FieldDescriptor,
    FieldUpsertRequest, FieldGenerateRequest, FieldDeleteRequest,
    FinalizeResponse
)
from ..config import get_config
from ..llm import LlmClient
from ..utils import merge_deep
from ..validator import validate_schema, lint_rules
from ..prompts import build_system_prompt, build_context_block

router = APIRouter(prefix="/interactive", tags=["interactive"])

# Database dependency
async def get_db():
    async with SessionLocal() as s:
        yield s

# Field generation system prompt
FIELD_SYSTEM_PROMPT = """You are an assistant that generates ONE field for a WhatsApp template payload that must be valid for Meta's Cloud API.

Rules:
- Obey the category rules:
  - MARKETING/UTILITY: HEADER formats allowed = TEXT, IMAGE, VIDEO, DOCUMENT, LOCATION
  - AUTHENTICATION: HEADER format allowed = TEXT only
- If generating Header TEXT:
  - <= 60 characters, <= 1 {{n}} placeholder. Provide a concise title.
- If generating Body:
  - Keep it short, friendly, and brand-safe; use {{n}} placeholders if needed.
- If generating Buttons:
  - Use QUICK_REPLY texts only (no URL/phone here). Keep 1–3 short options.
- If generating Footer:
  - Keep it short.
- Never invent disallowed fields for the category.
- Respect the provided config constraints and examples in the context.
- Return STRICT JSON with only the requested field shape (do not wrap or add commentary).

You will receive JSON context:
{
  "category": "...",
  "language": "...",
  "brand": "...",
  "field_id": "...",        // which field to produce
  "current_payload": {...}, // partial template
  "config": {...},          // allowed formats, limits
  "hints": "...",           // optional guidance from user
}

Output:
- JSON object for that field ONLY.
  Examples:
  - For header TEXT: {"type":"HEADER","format":"TEXT","text":"<≤60 chars>"}
  - For header IMAGE: {"type":"HEADER","format":"IMAGE","example":"<media-id-or-url>"}
  - For body: {"type":"BODY","text":"Hi {{1}}, ..."}
  - For buttons: {"type":"BUTTONS","buttons":[{"type":"QUICK_REPLY","text":"..."}]}
  - For footer: {"type":"FOOTER","text":"..."}
  - For name: {"name": "snake_case_name"}"""


def _fields_from_draft(draft: Dict[str, Any], cfg: Dict[str, Any]) -> List[FieldDescriptor]:
    """Compute field descriptors from draft + config."""
    cat = (draft.get("category") or "").upper()
    
    # Get header formats allowed for this category
    lint_rules = cfg.get("lint_rules", {})
    category_constraints = lint_rules.get("category_constraints", {})
    category_config = category_constraints.get(cat, category_constraints.get("MARKETING", {}))
    header_allowed = category_config.get("allowed_header_formats", ["TEXT","IMAGE","VIDEO","DOCUMENT","LOCATION"])

    # Find components
    comps = draft.get("components") or []
    def get_comp(kind: str) -> Optional[Dict[str, Any]]:
        for c in comps:
            if (c.get("type") or "").upper() == kind:
                return c
        return None

    header = get_comp("HEADER")
    body   = get_comp("BODY")
    footer = get_comp("FOOTER")
    buttons= get_comp("BUTTONS")

    fields: List[FieldDescriptor] = []
    
    # Core required fields
    fields.append(FieldDescriptor(
        id="category", 
        label="Category", 
        required=True, 
        can_delete=False, 
        can_generate=False,
        value=draft.get("category"), 
        meta={"enum":["MARKETING","UTILITY","AUTHENTICATION"]}
    ))
    
    fields.append(FieldDescriptor(
        id="language", 
        label="Language", 
        required=True, 
        can_delete=False, 
        can_generate=False,
        value=draft.get("language") or "en_US", 
        meta={"hint":"e.g., en_US, hi_IN"}
    ))
    
    fields.append(FieldDescriptor(
        id="name", 
        label="Template Name", 
        required=True, 
        can_delete=False, 
        can_generate=True,
        value=draft.get("name"), 
        meta={"pattern":"^[a-z0-9_]{1,64}$","hint":"snake_case"}
    ))
    
    # Header (optional, but with category restrictions)
    fields.append(FieldDescriptor(
        id="header", 
        label="Header", 
        required=False, 
        can_delete=True, 
        can_generate=True,
        value=header, 
        meta={"allowed_formats": header_allowed, "max_length": 60}
    ))
    
    # Body (always required)
    fields.append(FieldDescriptor(
        id="body", 
        label="Body", 
        required=True, 
        can_delete=False, 
        can_generate=True,
        value=body, 
        meta={"placeholders":"{{n}}"}
    ))
    
    # Footer (disabled for AUTH)
    footer_allowed = category_config.get("allow_footer", True)
    fields.append(FieldDescriptor(
        id="footer", 
        label="Footer", 
        required=False, 
        can_delete=footer_allowed, 
        can_generate=footer_allowed,
        value=footer, 
        meta={}
    ))
    
    # Buttons (disabled for AUTH)
    buttons_allowed = category_config.get("allow_buttons", True)
    fields.append(FieldDescriptor(
        id="buttons", 
        label="Buttons", 
        required=False, 
        can_delete=buttons_allowed, 
        can_generate=buttons_allowed,
        value=buttons, 
        meta={"kind":"QUICK_REPLY_ONLY"}
    ))
    
    return fields


def _apply_field(draft: Dict[str, Any], field_id: str, value: Any) -> Dict[str, Any]:
    """Apply a field update to the draft."""
    d = dict(draft)
    comps = list(d.get("components") or [])
    
    def upsert_comp(comp: Dict[str, Any]):
        nonlocal comps
        t = (comp.get("type") or "").upper()
        for i, c in enumerate(comps):
            if (c.get("type") or "").upper() == t:
                comps[i] = comp
                break
        else:
            comps.append(comp)

    if field_id == "name":
        d["name"] = value.get("name") if isinstance(value, dict) else value
    elif field_id == "language":
        d["language"] = value
    elif field_id == "category":
        d["category"] = value
    elif field_id == "header":
        if value is None:
            comps = [c for c in comps if (c.get("type") or "").upper() != "HEADER"]
        else:
            upsert_comp(value)
    elif field_id == "body":
        if isinstance(value, dict) and (value.get("type") or "").upper() == "BODY":
            upsert_comp(value)
        elif isinstance(value, str):
            upsert_comp({"type":"BODY","text":value})
    elif field_id == "footer":
        if value is None:
            comps = [c for c in comps if (c.get("type") or "").upper() != "FOOTER"]
        else:
            upsert_comp(value if isinstance(value, dict) else {"type":"FOOTER","text":value})
    elif field_id == "buttons":
        if value is None:
            comps = [c for c in comps if (c.get("type") or "").upper() != "BUTTONS"]
        else:
            upsert_comp(value)
    
    d["components"] = comps
    return d


def _issues_for(draft: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Get validation issues and missing required fields."""
    # Validate using existing schema + lint
    schema = cfg.get("creation_payload_schema", {}) or {}
    issues = validate_schema(draft, schema) + lint_rules(draft, cfg.get("lint_rules", {}) or {})
    
    missing = []
    if not draft.get("category"): 
        missing.append("category")
    if not draft.get("language"): 
        missing.append("language")
    if not draft.get("name"):     
        missing.append("name")
    
    # Check if body exists and has content
    has_body = any(
        (c.get("type") or "").upper() == "BODY" and (c.get("text") or "").strip() 
        for c in (draft.get("components") or [])
    )
    if not has_body: 
        missing.append("body")
    
    return {"issues": issues, "missing": missing}


@router.post("/start", response_model=InteractiveStateResponse)
async def start(req: InteractiveStartRequest, db: AsyncSession = Depends(get_db)):
    """Start interactive template creation with intent analysis."""
    cfg = get_config()
    s = await get_or_create_session(db, req.session_id)
    
    if not s.active_draft_id:
        d = await create_draft(db, s.id, draft={}, version=1)
        s.active_draft_id = d.id
        await db.flush()
    else:
        d = await db.get(Draft, s.active_draft_id)

    # Naive intent→category hint (backend decides, UI never guesses)
    intent = (req.intent or "").lower()
    cat = None
    if any(k in intent for k in ["offer","promo","greeting","festival","campaign","discount","sale"]):
        cat = "MARKETING"
    elif any(k in intent for k in ["update","reminder","notification","status","confirmation","appointment"]):
        cat = "UTILITY" 
    elif any(k in intent for k in ["otp","verify","verification","code","login","security"]):
        cat = "AUTHENTICATION"

    draft = dict(d.draft or {})
    if cat:
        draft["category"] = cat

    # Seed minimal scaffold if category known
    if cat and not any((c.get("type") or "").upper() == "BODY" for c in (draft.get("components") or [])):
        body = "Hi {{1}}, ..."
        draft["components"] = [{"type":"BODY","text":body}]
    
    # Always ensure language is set
    if not draft.get("language"):
        draft["language"] = "en_US"

    d.draft = draft
    await upsert_session(db, s)
    await db.commit()

    needs_category = not bool(draft.get("category"))
    fields = _fields_from_draft(draft, cfg)
    errs = _issues_for(draft, cfg)
    
    return InteractiveStateResponse(
        session_id=s.id,
        needs_category=needs_category,
        fields=fields,
        draft=draft,
        **errs
    )


@router.post("/set-category", response_model=InteractiveStateResponse)
async def set_category(req: InteractiveSetCategoryRequest, db: AsyncSession = Depends(get_db)):
    """Set the template category and update field descriptors."""
    cfg = get_config()
    s = await get_or_create_session(db, req.session_id)
    d = await db.get(Draft, s.active_draft_id)
    
    draft = dict(d.draft or {})
    draft["category"] = req.category.upper()
    
    d.draft = draft
    await upsert_session(db, s)
    await db.commit()
    
    fields = _fields_from_draft(draft, cfg)
    errs = _issues_for(draft, cfg)
    
    return InteractiveStateResponse(
        session_id=s.id, 
        needs_category=False, 
        fields=fields, 
        draft=draft, 
        **errs
    )


@router.put("/field", response_model=InteractiveStateResponse)
async def upsert_field(req: FieldUpsertRequest, db: AsyncSession = Depends(get_db)):
    """Update a field value in the draft."""
    cfg = get_config()
    s = await get_or_create_session(db, req.session_id)
    d = await db.get(Draft, s.active_draft_id)
    
    draft = _apply_field(dict(d.draft or {}), req.field_id, req.value)
    
    d.draft = draft
    await upsert_session(db, s)
    await db.commit()
    
    fields = _fields_from_draft(draft, cfg)
    errs = _issues_for(draft, cfg)
    
    return InteractiveStateResponse(
        session_id=s.id, 
        needs_category=not bool(draft.get("category")), 
        fields=fields, 
        draft=draft, 
        **errs
    )


@router.post("/field/generate", response_model=InteractiveStateResponse)
async def generate_field(req: FieldGenerateRequest, db: AsyncSession = Depends(get_db)):
    """Generate content for a specific field using LLM."""
    cfg = get_config()
    s = await get_or_create_session(db, req.session_id)
    d = await db.get(Draft, s.active_draft_id)
    
    draft = dict(d.draft or {})

    # Prepare context for LLM
    context = {
        "category": draft.get("category"),
        "language": draft.get("language") or "en_US",
        "brand": req.brand or "",
        "field_id": req.field_id,
        "current_payload": draft,
        "config": cfg.get("components", {}),
        "hints": req.hints or ""
    }

    # Call LLM for field generation
    llm = LlmClient(
        model=cfg.get("model", "gpt-4o-mini"), 
        temperature=float(cfg.get("temperature", 0.2))
    )
    
    try:
        out = llm.respond(FIELD_SYSTEM_PROMPT, str(context), [], f"Generate {req.field_id} field")
        
        if not isinstance(out, dict):
            raise HTTPException(400, f"Generation failed: invalid response format")

        # Apply the generated field
        draft = _apply_field(draft, req.field_id, out)
        
        d.draft = draft
        await upsert_session(db, s)
        await db.commit()
        
    except Exception as e:
        raise HTTPException(400, f"Generation failed: {str(e)}")

    fields = _fields_from_draft(draft, cfg)
    errs = _issues_for(draft, cfg)
    
    return InteractiveStateResponse(
        session_id=s.id, 
        needs_category=not bool(draft.get("category")), 
        fields=fields, 
        draft=draft, 
        **errs
    )


@router.delete("/field", response_model=InteractiveStateResponse)
async def delete_field(req: FieldDeleteRequest, db: AsyncSession = Depends(get_db)):
    """Delete an optional field from the draft."""
    cfg = get_config()
    s = await get_or_create_session(db, req.session_id)
    d = await db.get(Draft, s.active_draft_id)
    
    # Apply deletion (value = None)
    draft = _apply_field(dict(d.draft or {}), req.field_id, None)
    
    d.draft = draft
    await upsert_session(db, s)
    await db.commit()
    
    fields = _fields_from_draft(draft, cfg)
    errs = _issues_for(draft, cfg)
    
    return InteractiveStateResponse(
        session_id=s.id, 
        needs_category=not bool(draft.get("category")), 
        fields=fields, 
        draft=draft, 
        **errs
    )


@router.post("/finalize", response_model=FinalizeResponse)
async def finalize(session_id: str, db: AsyncSession = Depends(get_db)):
    """Finalize the template after full validation."""
    cfg = get_config()
    s = await get_or_create_session(db, session_id)
    d = await db.get(Draft, s.active_draft_id)
    
    draft = dict(d.draft or {})

    # Run full validation
    schema = cfg.get("creation_payload_schema", {}) or {}
    issues = validate_schema(draft, schema) + lint_rules(draft, cfg.get("lint_rules", {}) or {})
    
    if issues:
        return FinalizeResponse(ok=False, issues=issues, payload=None)

    # All good - return final payload
    return FinalizeResponse(ok=True, issues=[], payload=draft)
