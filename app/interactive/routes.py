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
FIELD_SYSTEM_PROMPT = """You are a smart assistant that generates contextually relevant WhatsApp template fields.

CONTEXT AWARENESS:
- Use the brand name, category, and existing content to create relevant fields
- For businesses like "sweet shop", "restaurant", "clinic" - create industry-specific content
- Avoid generic labels like "Learn more", "Shop now" unless they fit the context
- Make buttons actionable and specific to the business type

RULES:
- MARKETING/UTILITY: HEADER formats = TEXT, IMAGE, VIDEO, DOCUMENT, LOCATION
- AUTHENTICATION: HEADER format = TEXT only
- Header TEXT: ≤60 chars, ≤1 {{n}} placeholder
- Body: Keep contextual, friendly, use {{n}} placeholders appropriately 
- Buttons: 2-3 QUICK_REPLY options, specific to business context
- Footer: Short, brand-appropriate

BUSINESS-SPECIFIC EXAMPLES:
- Sweet shop: "Order sweets", "View menu", "Call store"
- Restaurant: "Book table", "View menu", "Order now"  
- Clinic: "Book appointment", "Call clinic", "Get directions"
- Fashion: "Shop collection", "Size guide", "Track order"
- Service: "Get quote", "Schedule visit", "Contact us"

BUTTON GENERATION STRATEGY:
1. Look at brand name and category to understand business type
2. Check existing body content for context clues
3. Create 2-3 relevant, actionable buttons
4. Avoid duplicate or generic labels
5. Make buttons feel natural for that business

JSON CONTEXT:
{
  "category": "...",
  "language": "...", 
  "brand": "...",           // Use this for context!
  "field_id": "...",        
  "current_payload": {...}, // Check existing content
  "config": {...},          
  "hints": "...",           // User guidance
  "business_context": "..." // Additional business info
}

OUTPUT (field JSON only, no wrapper):
- header TEXT: {"type":"HEADER","format":"TEXT","text":"Sweet deals just for you!"}
- header IMAGE: {"type":"HEADER","format":"IMAGE","example":"media-url"}
- body: {"type":"BODY","text":"Hi {{1}}, enjoy our special sweets offer!"}
- buttons: {"type":"BUTTONS","buttons":[{"type":"QUICK_REPLY","text":"Order sweets"},{"type":"QUICK_REPLY","text":"View menu"}]}
- footer: {"type":"FOOTER","text":"Thank you for choosing us!"}
- name: {"name": "sweet_shop_offer_jan2024"}"""


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


def _extract_business_context(draft: Dict[str, Any], brand: str, hints: str) -> str:
    """Extract business context from available information."""
    context_parts = []
    
    # From brand name
    if brand:
        brand_lower = brand.lower()
        if any(word in brand_lower for word in ["sweet", "candy", "dessert", "bakery"]):
            context_parts.append("sweet/dessert business")
        elif any(word in brand_lower for word in ["restaurant", "cafe", "food", "kitchen"]):
            context_parts.append("food/restaurant business")
        elif any(word in brand_lower for word in ["clinic", "doctor", "medical", "health"]):
            context_parts.append("healthcare business")
        elif any(word in brand_lower for word in ["salon", "beauty", "spa", "hair"]):
            context_parts.append("beauty/wellness business")
        elif any(word in brand_lower for word in ["shop", "store", "retail", "fashion"]):
            context_parts.append("retail business")
        else:
            context_parts.append(f"business: {brand}")
    
    # From existing body content
    components = draft.get("components", [])
    for comp in components:
        if comp.get("type") == "BODY":
            body_text = (comp.get("text") or "").lower()
            if "sweet" in body_text or "dessert" in body_text:
                context_parts.append("sweets/desserts focus")
            elif "appointment" in body_text:
                context_parts.append("appointment-based service")
            elif "order" in body_text:
                context_parts.append("order-based business")
            elif "offer" in body_text or "discount" in body_text:
                context_parts.append("promotional context")
    
    # From hints
    if hints:
        hints_lower = hints.lower()
        if "promotion" in hints_lower or "offer" in hints_lower:
            context_parts.append("promotional message")
        elif "reminder" in hints_lower:
            context_parts.append("reminder message")
        elif "welcome" in hints_lower:
            context_parts.append("welcome message")
    
    return "; ".join(context_parts) if context_parts else "general business"


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
    """Generate content for a specific field using LLM with business context."""
    cfg = get_config()
    s = await get_or_create_session(db, req.session_id)
    d = await db.get(Draft, s.active_draft_id)
    
    draft = dict(d.draft or {})

    # Enhanced context for business-aware generation
    business_context = _extract_business_context(draft, req.brand, req.hints)
    
    context = {
        "category": draft.get("category"),
        "language": draft.get("language") or "en_US",
        "brand": req.brand or "",
        "field_id": req.field_id,
        "current_payload": draft,
        "config": cfg.get("lint_rules", {}).get("components", {}),
        "hints": req.hints or "",
        "business_context": business_context
    }

    # Call LLM for field generation
    llm = LlmClient(
        model=cfg.get("model", "gpt-4o-mini"), 
        temperature=float(cfg.get("temperature", 0.3))  # Slightly higher for creativity
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
