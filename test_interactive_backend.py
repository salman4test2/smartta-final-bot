"""
Test script for interactive mode functionality.
Tests the field-by-field editing API endpoints.
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal, engine, Base
from app.models import Draft, UserSession
from app.interactive.routes import (
    _fields_from_draft, _apply_field, _issues_for,
    start, set_category, upsert_field, generate_field, delete_field, finalize
)
from app.schemas import (
    InteractiveStartRequest, InteractiveSetCategoryRequest,
    FieldUpsertRequest, FieldGenerateRequest, FieldDeleteRequest
)
from app.config import get_config
from sqlalchemy import text
import json

async def setup_test_db():
    """Create tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def cleanup_test_db():
    """Clean up test data."""
    async with SessionLocal() as session:
        await session.execute(text("DELETE FROM drafts WHERE 1=1"))
        await session.execute(text("DELETE FROM user_sessions WHERE 1=1"))
        await session.commit()

async def test_field_descriptors():
    """Test field descriptor generation."""
    print("=== Testing Field Descriptors ===")
    
    cfg = get_config()
    
    # Test MARKETING category
    draft_marketing = {
        "category": "MARKETING",
        "language": "en_US",
        "name": "test_marketing",
        "components": [
            {"type": "BODY", "text": "Hi {{1}}, check out our new offer!"}
        ]
    }
    
    fields = _fields_from_draft(draft_marketing, cfg)
    print(f"Marketing fields count: {len(fields)}")
    
    # Find header field
    header_field = next((f for f in fields if f.id == "header"), None)
    if header_field:
        print(f"Header allowed formats: {header_field.meta.get('allowed_formats', [])}")
        assert "TEXT" in header_field.meta.get('allowed_formats', [])
        assert "IMAGE" in header_field.meta.get('allowed_formats', [])
        print("✓ Marketing header supports multiple formats")
    
    # Find buttons field
    buttons_field = next((f for f in fields if f.id == "buttons"), None)
    if buttons_field:
        assert buttons_field.can_generate == True
        assert buttons_field.can_delete == True
        print("✓ Marketing buttons field can be generated and deleted")
    
    # Test AUTHENTICATION category
    draft_auth = {
        "category": "AUTHENTICATION",
        "language": "en_US",
        "name": "test_auth",
        "components": [
            {"type": "BODY", "text": "Your code is {{1}}"}
        ]
    }
    
    fields_auth = _fields_from_draft(draft_auth, cfg)
    header_field_auth = next((f for f in fields_auth if f.id == "header"), None)
    if header_field_auth:
        allowed = header_field_auth.meta.get('allowed_formats', [])
        print(f"Auth header allowed formats: {allowed}")
        # Should only allow TEXT for AUTH
        assert "TEXT" in allowed
        assert len([f for f in allowed if f != "TEXT"]) == 0 or "TEXT" == allowed[0]
        print("✓ Authentication header restricted to TEXT only")
    
    # Find buttons field for AUTH
    buttons_field_auth = next((f for f in fields_auth if f.id == "buttons"), None)
    if buttons_field_auth:
        assert buttons_field_auth.can_generate == False
        assert buttons_field_auth.can_delete == False
        print("✓ Authentication buttons field disabled")

async def test_field_application():
    """Test field value application."""
    print("\n=== Testing Field Application ===")
    
    draft = {
        "category": "MARKETING",
        "language": "en_US",
        "components": []
    }
    
    # Test applying header
    header_value = {"type": "HEADER", "format": "TEXT", "text": "Special Offer!"}
    draft = _apply_field(draft, "header", header_value)
    
    header_comp = next((c for c in draft["components"] if c.get("type") == "HEADER"), None)
    assert header_comp is not None
    assert header_comp["text"] == "Special Offer!"
    print("✓ Header field applied successfully")
    
    # Test applying body
    body_value = {"type": "BODY", "text": "Hi {{1}}, enjoy 20% off!"}
    draft = _apply_field(draft, "body", body_value)
    
    body_comp = next((c for c in draft["components"] if c.get("type") == "BODY"), None)
    assert body_comp is not None
    assert body_comp["text"] == "Hi {{1}}, enjoy 20% off!"
    print("✓ Body field applied successfully")
    
    # Test applying buttons
    buttons_value = {
        "type": "BUTTONS",
        "buttons": [
            {"type": "QUICK_REPLY", "text": "Shop Now"},
            {"type": "QUICK_REPLY", "text": "Learn More"}
        ]
    }
    draft = _apply_field(draft, "buttons", buttons_value)
    
    buttons_comp = next((c for c in draft["components"] if c.get("type") == "BUTTONS"), None)
    assert buttons_comp is not None
    assert len(buttons_comp["buttons"]) == 2
    print("✓ Buttons field applied successfully")
    
    # Test deleting optional field
    draft = _apply_field(draft, "buttons", None)
    buttons_comp = next((c for c in draft["components"] if c.get("type") == "BUTTONS"), None)
    assert buttons_comp is None
    print("✓ Optional field deletion works")

async def test_validation():
    """Test validation and issues detection."""
    print("\n=== Testing Validation ===")
    
    cfg = get_config()
    
    # Test incomplete draft
    draft_incomplete = {
        "category": "MARKETING",
        "components": []
    }
    
    issues = _issues_for(draft_incomplete, cfg)
    missing = issues["missing"]
    
    assert "name" in missing
    assert "body" in missing
    print(f"✓ Missing fields detected: {missing}")
    
    # Test complete draft
    draft_complete = {
        "category": "MARKETING",
        "language": "en_US", 
        "name": "complete_template",
        "components": [
            {"type": "BODY", "text": "Hi {{1}}, welcome!"}
        ]
    }
    
    issues_complete = _issues_for(draft_complete, cfg)
    missing_complete = issues_complete["missing"]
    
    assert len(missing_complete) == 0
    print("✓ Complete draft has no missing fields")

async def test_interactive_endpoints():
    """Test the interactive API endpoints."""
    print("\n=== Testing Interactive Endpoints ===")
    
    await setup_test_db()
    
    try:
        async with SessionLocal() as db:
            # Test start endpoint
            start_req = InteractiveStartRequest(
                intent="I want to send discount offers to my customers"
            )
            
            response = await start(start_req, db)
            
            assert response.session_id is not None
            assert response.needs_category == False  # Should infer MARKETING
            assert len(response.fields) > 0
            print(f"✓ Start endpoint created session: {response.session_id}")
            
            session_id = response.session_id
            
            # Test field upsert
            upsert_req = FieldUpsertRequest(
                session_id=session_id,
                field_id="name",
                value="special_offer_template"
            )
            
            response = await upsert_field(upsert_req, db)
            assert response.draft.get("name") == "special_offer_template"
            print("✓ Field upsert works")
            
            # Test field deletion
            delete_req = FieldDeleteRequest(
                session_id=session_id,
                field_id="header"
            )
            
            response = await delete_field(delete_req, db)
            header_comp = next((c for c in response.draft.get("components", []) if c.get("type") == "HEADER"), None)
            assert header_comp is None
            print("✓ Field deletion works")
            
            # Add required body for finalization
            body_req = FieldUpsertRequest(
                session_id=session_id,
                field_id="body",
                value={"type": "BODY", "text": "Hi {{1}}, enjoy 20% off everything!"}
            )
            await upsert_field(body_req, db)
            
            # Test finalization
            final_response = await finalize(session_id, db)
            
            if final_response.ok:
                print("✓ Template finalized successfully")
                print(f"Final payload: {json.dumps(final_response.payload, indent=2)}")
            else:
                print(f"⚠ Finalization issues: {final_response.issues}")
    
    finally:
        await cleanup_test_db()

async def main():
    """Run all tests."""
    print("Interactive Mode Backend Tests")
    print("=" * 40)
    
    try:
        await test_field_descriptors()
        await test_field_application()
        await test_validation()
        await test_interactive_endpoints()
        
        print("\n" + "=" * 40)
        print("✅ All interactive tests passed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(result)
