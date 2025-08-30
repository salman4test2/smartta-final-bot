"""
Integration test for the interactive mode API.
Tests the complete user journey from intent to finalized template.
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal, engine, Base
from app.interactive.routes import (
    start, set_category, upsert_field, generate_field, delete_field, finalize
)
from app.schemas import (
    InteractiveStartRequest, InteractiveSetCategoryRequest,
    FieldUpsertRequest, FieldGenerateRequest, FieldDeleteRequest
)
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

async def test_marketing_journey():
    """Test complete marketing template creation journey."""
    print("=== Marketing Template Journey ===")
    
    async with SessionLocal() as db:
        # Step 1: Start with marketing intent
        start_req = InteractiveStartRequest(
            intent="I want to send a special discount offer to my customers"
        )
        
        response = await start(start_req, db)
        session_id = response.session_id
        
        print(f"✓ Started session: {session_id}")
        print(f"  Category auto-detected: {response.draft.get('category')}")
        print(f"  Needs category selection: {response.needs_category}")
        
        # Step 2: Set template name
        name_req = FieldUpsertRequest(
            session_id=session_id,
            field_id="name",
            value="holiday_discount_2024"
        )
        
        response = await upsert_field(name_req, db)
        print(f"✓ Set template name: {response.draft.get('name')}")
        
        # Step 3: Update body content
        body_req = FieldUpsertRequest(
            session_id=session_id,
            field_id="body",
            value={
                "type": "BODY",
                "text": "Hi {{1}}! 🎉 Enjoy 25% off everything in our holiday sale. Use code HOLIDAY25. Valid until {{2}}. Shop now!"
            }
        )
        
        response = await upsert_field(body_req, db)
        body_comp = next((c for c in response.draft.get("components", []) if c.get("type") == "BODY"), None)
        print(f"✓ Updated body: {body_comp['text'][:50]}...")
        
        # Step 4: Add header
        header_req = FieldUpsertRequest(
            session_id=session_id,
            field_id="header",
            value={
                "type": "HEADER",
                "format": "TEXT",
                "text": "🎄 Holiday Sale Alert!"
            }
        )
        
        response = await upsert_field(header_req, db)
        header_comp = next((c for c in response.draft.get("components", []) if c.get("type") == "HEADER"), None)
        print(f"✓ Added header: {header_comp['text']}")
        
        # Step 5: Add buttons
        buttons_req = FieldUpsertRequest(
            session_id=session_id,
            field_id="buttons",
            value={
                "type": "BUTTONS",
                "buttons": [
                    {"type": "QUICK_REPLY", "text": "Shop Now"},
                    {"type": "QUICK_REPLY", "text": "View Catalog"},
                    {"type": "QUICK_REPLY", "text": "Contact Us"}
                ]
            }
        )
        
        response = await upsert_field(buttons_req, db)
        buttons_comp = next((c for c in response.draft.get("components", []) if c.get("type") == "BUTTONS"), None)
        print(f"✓ Added {len(buttons_comp['buttons'])} buttons")
        
        # Step 6: Add footer
        footer_req = FieldUpsertRequest(
            session_id=session_id,
            field_id="footer",
            value={
                "type": "FOOTER",
                "text": "Terms apply. Visit our store for details."
            }
        )
        
        response = await upsert_field(footer_req, db)
        footer_comp = next((c for c in response.draft.get("components", []) if c.get("type") == "FOOTER"), None)
        print(f"✓ Added footer: {footer_comp['text']}")
        
        # Step 7: Validate current state
        print(f"  Missing fields: {response.missing}")
        print(f"  Validation issues: {response.issues}")
        
        # Step 8: Finalize
        final_response = await finalize(session_id, db)
        
        if final_response.ok:
            print("✅ Template finalized successfully!")
            payload = final_response.payload
            print(f"  Final template name: {payload.get('name')}")
            print(f"  Category: {payload.get('category')}")
            print(f"  Language: {payload.get('language')}")
            print(f"  Components: {len(payload.get('components', []))}")
            return True
        else:
            print(f"❌ Finalization failed: {final_response.issues}")
            return False

async def test_auth_template():
    """Test authentication template with restrictions."""
    print("\n=== Authentication Template Journey ===")
    
    async with SessionLocal() as db:
        # Step 1: Start with auth intent
        start_req = InteractiveStartRequest(
            intent="I need to send verification codes to users"
        )
        
        response = await start(start_req, db)
        session_id = response.session_id
        
        print(f"✓ Started session: {session_id}")
        print(f"  Category auto-detected: {response.draft.get('category')}")
        
        # Check field restrictions for AUTH
        buttons_field = next((f for f in response.fields if f.id == "buttons"), None)
        footer_field = next((f for f in response.fields if f.id == "footer"), None)
        header_field = next((f for f in response.fields if f.id == "header"), None)
        
        if buttons_field:
            print(f"  Buttons can_generate: {buttons_field.can_generate} (should be False)")
            print(f"  Buttons can_delete: {buttons_field.can_delete} (should be False)")
        
        if header_field:
            allowed_formats = header_field.meta.get('allowed_formats', [])
            print(f"  Header allowed formats: {allowed_formats}")
        
        # Step 2: Set basic fields
        name_req = FieldUpsertRequest(
            session_id=session_id,
            field_id="name",
            value="verification_code"
        )
        await upsert_field(name_req, db)
        
        body_req = FieldUpsertRequest(
            session_id=session_id,
            field_id="body",
            value={
                "type": "BODY",
                "text": "Your verification code is {{1}}. This code expires in {{2}} minutes. Do not share this code with anyone."
            }
        )
        await upsert_field(body_req, db)
        
        # Step 3: Try to add header (should work with TEXT)
        header_req = FieldUpsertRequest(
            session_id=session_id,
            field_id="header",
            value={
                "type": "HEADER",
                "format": "TEXT",
                "text": "Security Code"
            }
        )
        response = await upsert_field(header_req, db)
        print("✓ Added TEXT header to AUTH template")
        
        # Step 4: Finalize
        final_response = await finalize(session_id, db)
        
        if final_response.ok:
            print("✅ AUTH template finalized successfully!")
            return True
        else:
            print(f"❌ AUTH finalization failed: {final_response.issues}")
            return False

async def test_category_override():
    """Test manual category selection."""
    print("\n=== Manual Category Selection ===")
    
    async with SessionLocal() as db:
        # Step 1: Start with ambiguous intent
        start_req = InteractiveStartRequest(
            intent="I want to send messages to my customers"
        )
        
        response = await start(start_req, db)
        session_id = response.session_id
        
        print(f"✓ Started with ambiguous intent")
        print(f"  Needs category: {response.needs_category}")
        
        if response.needs_category:
            # Step 2: Set category manually
            category_req = InteractiveSetCategoryRequest(
                session_id=session_id,
                category="UTILITY"
            )
            
            response = await set_category(category_req, db)
            print(f"✓ Set category to: {response.draft.get('category')}")
            print(f"  Needs category now: {response.needs_category}")
            
            return True
        else:
            print("  Category was auto-detected")
            return True

async def main():
    """Run all integration tests."""
    print("Interactive Mode Integration Tests")
    print("=" * 50)
    
    await setup_test_db()
    
    try:
        success_count = 0
        total_tests = 3
        
        if await test_marketing_journey():
            success_count += 1
        
        if await test_auth_template():
            success_count += 1
            
        if await test_category_override():
            success_count += 1
        
        print("\n" + "=" * 50)
        print(f"Integration Test Results: {success_count}/{total_tests} passed")
        
        if success_count == total_tests:
            print("✅ All integration tests passed!")
            return 0
        else:
            print("❌ Some tests failed")
            return 1
            
    except Exception as e:
        print(f"\n❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
        
    finally:
        await cleanup_test_db()

if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(result)
