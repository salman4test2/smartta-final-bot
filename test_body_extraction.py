#!/usr/bin/env python3
"""
Test Body Content Extraction
Tests that the LLM properly extracts explicit content into the body component.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from fastapi.testclient import TestClient
from app.main import app

def test_explicit_body_content():
    """Test that explicit message content gets properly extracted."""
    client = TestClient(app)
    
    print("🧪 TESTING EXPLICIT BODY CONTENT EXTRACTION")
    print("="*60)
    
    # Create user and session
    try:
        client.post("/users", json={"user_id": "body_test_user", "password": "test123"})
        print("👤 User created")
    except:
        print("👤 User exists (continuing)")
    
    session_response = client.post("/session/new", json={
        "user_id": "body_test_user",
        "session_name": "Body Test"
    })
    session_id = session_response.json()["session_id"]
    print(f"📱 Session created: {session_id}")
    
    # Step 1: Initial context
    print("\n--- Step 1: Set context ---")
    response1 = client.post("/chat", json={
        "message": "I want to create a discount offer for my clothing store",
        "session_id": session_id,
        "user_id": "body_test_user"
    })
    result1 = response1.json()
    print(f"Missing: {result1.get('missing', [])}")
    
    # Step 2: Set category 
    print("\n--- Step 2: Confirm category ---")
    response2 = client.post("/chat", json={
        "message": "Yes, marketing template is perfect",
        "session_id": session_id,
        "user_id": "body_test_user"
    })
    result2 = response2.json()
    print(f"Missing: {result2.get('missing', [])}")
    
    # Step 3: Provide explicit message content
    print("\n--- Step 3: Provide explicit content ---")
    explicit_message = "The message should say: Hi {{1}}! Special 20% off just for you! Use code SAVE20. Valid until {{2}}. Shop now!"
    response3 = client.post("/chat", json={
        "message": explicit_message,
        "session_id": session_id,
        "user_id": "body_test_user"
    })
    result3 = response3.json()
    
    print(f"User message: {explicit_message}")
    print(f"AI response: {result3.get('reply', '')}")
    print(f"Missing: {result3.get('missing', [])}")
    
    # Check if body was extracted
    draft = result3.get('draft', {})
    components = draft.get('components', [])
    body_component = next((c for c in components if c.get('type') == 'BODY'), None)
    
    if body_component:
        body_text = body_component.get('text', '')
        print(f"✅ Body extracted: {body_text}")
        
        # Check if the content matches what the user provided
        expected_content = "Hi {{1}}! Special 20% off just for you! Use code SAVE20. Valid until {{2}}. Shop now!"
        if expected_content in body_text or body_text in expected_content:
            print("✅ Content matches user input")
            return True
        else:
            print(f"❌ Content mismatch. Expected part of: {expected_content}")
            return False
    else:
        print("❌ No body component found")
        print(f"Draft structure: {draft}")
        return False

def test_direct_llm_extraction():
    """Test the LLM directly to see what it extracts from explicit content."""
    from app.llm import LlmClient
    from app.prompts import build_system_prompt, build_context_block
    from app.config import get_config
    from app.main import _sanitize_candidate
    
    print("\n🧪 TESTING DIRECT LLM EXTRACTION")
    print("="*50)
    
    cfg = get_config()
    llm = LlmClient(model=cfg.get("model", "gpt-4o-mini"))
    
    system = build_system_prompt(cfg)
    draft = {"category": "MARKETING"}
    memory = {"category": "MARKETING", "business_type": "clothing store"}
    context = build_context_block(draft, memory, cfg, [])
    
    explicit_message = "The message should say: Hi {{1}}! Special 20% off just for you! Use code SAVE20. Valid until {{2}}. Shop now!"
    
    print(f"Input: {explicit_message}")
    
    try:
        result = llm.respond(system, context, [], explicit_message)
        print(f"LLM action: {result.get('agent_action')}")
        print(f"LLM reply: {result.get('message_to_user', '')}")
        
        draft_result = result.get('draft', {})
        if draft_result:
            print(f"Raw LLM draft: {draft_result}")
            
            # Apply sanitization (this is what the main chat flow does)
            sanitized_draft = _sanitize_candidate(draft_result)
            print(f"Sanitized draft: {sanitized_draft}")
            
            components = sanitized_draft.get('components', [])
            body_comp = next((c for c in components if c.get('type') == 'BODY'), None)
            if body_comp:
                print(f"✅ LLM extracted body after sanitization: {body_comp.get('text')}")
                return True
            else:
                print(f"❌ No body component found even after sanitization")
                print(f"Components: {components}")
        else:
            print("❌ LLM didn't create draft")
            print(f"Full result: {result}")
        
    except Exception as e:
        print(f"❌ LLM error: {e}")
    
    return False

def main():
    """Run all body extraction tests."""
    print("🎯 BODY CONTENT EXTRACTION TESTS")
    print("="*80)
    
    test1_success = test_explicit_body_content()
    test2_success = test_direct_llm_extraction()
    
    print("\n" + "="*80)
    print("📊 RESULTS SUMMARY")
    print("="*80)
    print(f"Full journey test: {'✅ PASSED' if test1_success else '❌ FAILED'}")
    print(f"Direct LLM test: {'✅ PASSED' if test2_success else '❌ FAILED'}")
    
    if test1_success and test2_success:
        print("\n🎉 All tests passed! Body extraction is working correctly.")
        return True
    else:
        print("\n⚠️ Some tests failed. Body extraction needs attention.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
