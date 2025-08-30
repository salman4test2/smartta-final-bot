"""
Test for LLM field generation in interactive mode.
Validates that generated content respects category constraints.
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

async def test_field_generation():
    """Test LLM field generation respects constraints."""
    print("=== Testing Field Generation ===")
    
    async with SessionLocal() as db:
        # Test 1: Generate name field
        start_req = InteractiveStartRequest(
            intent="I want to send discount codes to my customers"
        )
        
        response = await start(start_req, db)
        session_id = response.session_id
        
        print(f"✓ Started session for generation test: {session_id}")
        
        # Generate a template name
        try:
            gen_req = FieldGenerateRequest(
                session_id=session_id,
                field_id="name",
                hints="This is for a holiday discount campaign",
                brand="MyStore"
            )
            
            response = await generate_field(gen_req, db)
            generated_name = response.draft.get("name")
            
            if generated_name:
                print(f"✓ Generated name: {generated_name}")
                # Validate name format (snake_case)
                if generated_name.islower() and "_" in generated_name and generated_name.replace("_", "").isalnum():
                    print("  ✓ Name follows snake_case format")
                else:
                    print(f"  ⚠ Name format issue: {generated_name}")
            else:
                print("❌ Name generation failed")
                
        except Exception as e:
            print(f"❌ Name generation error: {e}")
        
        # Test 2: Generate body for MARKETING
        try:
            body_gen_req = FieldGenerateRequest(
                session_id=session_id,
                field_id="body",
                hints="Holiday discount message with customer personalization",
                brand="MyStore"
            )
            
            response = await generate_field(body_gen_req, db)
            body_comp = next((c for c in response.draft.get("components", []) if c.get("type") == "BODY"), None)
            
            if body_comp and body_comp.get("text"):
                print(f"✓ Generated body: {body_comp['text'][:50]}...")
                # Check for placeholders
                if "{{1}}" in body_comp["text"]:
                    print("  ✓ Body includes placeholder {{1}}")
                else:
                    print("  ⚠ Body missing placeholders")
            else:
                print("❌ Body generation failed")
                
        except Exception as e:
            print(f"❌ Body generation error: {e}")
        
        # Test 3: Generate buttons for MARKETING (should work)
        try:
            buttons_gen_req = FieldGenerateRequest(
                session_id=session_id,
                field_id="buttons",
                hints="Quick action buttons for discount offer",
                brand="MyStore"
            )
            
            response = await generate_field(buttons_gen_req, db)
            buttons_comp = next((c for c in response.draft.get("components", []) if c.get("type") == "BUTTONS"), None)
            
            if buttons_comp and buttons_comp.get("buttons"):
                print(f"✓ Generated {len(buttons_comp['buttons'])} buttons")
                for btn in buttons_comp["buttons"]:
                    if btn.get("type") == "QUICK_REPLY":
                        print(f"  ✓ Button: {btn.get('text')}")
                    else:
                        print(f"  ⚠ Non-QUICK_REPLY button: {btn}")
            else:
                print("❌ Buttons generation failed")
                
        except Exception as e:
            print(f"❌ Buttons generation error: {e}")

async def test_auth_constraints():
    """Test that AUTH templates respect constraints."""
    print("\n=== Testing AUTH Constraints ===")
    
    async with SessionLocal() as db:
        # Start with AUTH category
        start_req = InteractiveStartRequest(
            intent="I need to send verification codes"
        )
        
        response = await start(start_req, db)
        session_id = response.session_id
        
        print(f"✓ Started AUTH session: {session_id}")
        print(f"  Category: {response.draft.get('category')}")
        
        # Check field constraints
        buttons_field = next((f for f in response.fields if f.id == "buttons"), None)
        footer_field = next((f for f in response.fields if f.id == "footer"), None)
        header_field = next((f for f in response.fields if f.id == "header"), None)
        
        if buttons_field:
            assert not buttons_field.can_generate, "AUTH buttons should not be generatable"
            assert not buttons_field.can_delete, "AUTH buttons should not be deletable"
            print("  ✓ Buttons field properly disabled for AUTH")
        
        if footer_field:
            assert not footer_field.can_generate, "AUTH footer should not be generatable"
            assert not footer_field.can_delete, "AUTH footer should not be deletable"
            print("  ✓ Footer field properly disabled for AUTH")
        
        if header_field:
            allowed_formats = header_field.meta.get("allowed_formats", [])
            assert allowed_formats == ["TEXT"], f"AUTH should only allow TEXT headers, got: {allowed_formats}"
            print("  ✓ Header formats properly restricted for AUTH")
        
        # Try to generate a header (should work for TEXT)
        try:
            header_gen_req = FieldGenerateRequest(
                session_id=session_id,
                field_id="header",
                hints="Security verification header",
                brand="SecureApp"
            )
            
            response = await generate_field(header_gen_req, db)
            header_comp = next((c for c in response.draft.get("components", []) if c.get("type") == "HEADER"), None)
            
            if header_comp:
                if header_comp.get("format") == "TEXT":
                    print(f"  ✓ Generated TEXT header: {header_comp.get('text')}")
                else:
                    print(f"  ⚠ Generated non-TEXT header: {header_comp}")
            else:
                print("  ❌ Header generation failed")
                
        except Exception as e:
            print(f"  ❌ Header generation error: {e}")

async def main():
    """Run field generation tests."""
    print("Interactive Mode Field Generation Tests")
    print("=" * 50)
    
    await setup_test_db()
    
    try:
        await test_field_generation()
        await test_auth_constraints()
        
        print("\n" + "=" * 50)
        print("✅ All field generation tests completed!")
        return 0
        
    except Exception as e:
        print(f"\n❌ Field generation test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
        
    finally:
        await cleanup_test_db()

if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(result)
