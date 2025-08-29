#!/usr/bin/env python3
"""
Test Complete Template Creation
Provides all required fields to ensure a template gets created successfully.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from fastapi.testclient import TestClient
from app.main import app

def test_complete_template_creation():
    """Test providing all required fields step by step to complete a template."""
    client = TestClient(app)
    
    print("🎯 COMPLETE TEMPLATE CREATION TEST")
    print("="*60)
    
    # Create user and session
    try:
        client.post("/users", json={"user_id": "complete_test_user", "password": "test123"})
        print("👤 User created")
    except:
        print("👤 User exists (continuing)")
    
    session_response = client.post("/session/new", json={
        "user_id": "complete_test_user",
        "session_name": "Complete Test"
    })
    session_id = session_response.json()["session_id"]
    print(f"📱 Session: {session_id}")
    
    # Step-by-step completion
    steps = [
        {
            "message": "I want to create a marketing template for discount offers",
            "description": "Set business context and category"
        },
        {
            "message": "I run a clothing boutique for young women, marketing template is perfect",
            "description": "Confirm category and business type"
        },
        {
            "message": "The template name should be boutique_discount_offer",
            "description": "Provide template name"
        },
        {
            "message": "The message content is: Hi {{1}}! Special 20% off just for you at our boutique! Use code SAVE20. Valid until {{2}}. Shop now!",
            "description": "Provide explicit body content"
        },
        {
            "message": "Language should be English, en_US",
            "description": "Set language"
        },
        {
            "message": "Let's finalize this template now",
            "description": "Request finalization"
        }
    ]
    
    for i, step in enumerate(steps, 1):
        print(f"\n--- Step {i}: {step['description']} ---")
        print(f"👤 USER: {step['message']}")
        
        response = client.post("/chat", json={
            "message": step["message"],
            "session_id": session_id,
            "user_id": "complete_test_user"
        })
        
        result = response.json()
        reply = result.get('reply', '')
        missing = result.get('missing', [])
        draft = result.get('draft', {})
        final_payload = result.get('final_creation_payload')
        
        print(f"🤖 AI: {reply[:100]}{'...' if len(reply) > 100 else ''}")
        print(f"📋 Missing: {missing}")
        
        # Show what's been captured
        if draft.get('category'):
            print(f"✅ Category: {draft['category']}")
        if draft.get('name'):
            print(f"✅ Name: {draft['name']}")
        if draft.get('language'):
            print(f"✅ Language: {draft['language']}")
        
        # Check for body component
        components = draft.get('components', [])
        body_comp = next((c for c in components if c.get('type') == 'BODY'), None)
        if body_comp:
            body_text = body_comp.get('text', '')
            print(f"✅ Body: {body_text[:50]}{'...' if len(body_text) > 50 else ''}")
        
        # Check if template is complete
        if final_payload:
            print("\n🎉 TEMPLATE COMPLETED!")
            print("="*40)
            print(f"Name: {final_payload.get('name')}")
            print(f"Category: {final_payload.get('category')}")
            print(f"Language: {final_payload.get('language')}")
            
            final_components = final_payload.get('components', [])
            for comp in final_components:
                comp_type = comp.get('type', '')
                if comp_type == 'BODY':
                    print(f"Message: {comp.get('text', '')}")
                elif comp_type == 'HEADER':
                    print(f"Header: {comp.get('text', '')}")
                elif comp_type == 'FOOTER':
                    print(f"Footer: {comp.get('text', '')}")
                elif comp_type == 'BUTTONS':
                    buttons = comp.get('buttons', [])
                    button_texts = [btn.get('text', '') for btn in buttons]
                    print(f"Buttons: {', '.join(button_texts)}")
            
            print("\n✅ Template creation SUCCESS!")
            return True
        
        # If no missing fields, expect completion soon
        if not missing:
            print("🚀 All fields provided, template should complete next")
    
    print("\n❌ Template was not completed within expected steps")
    return False

def main():
    """Run the complete template creation test."""
    print("🧪 Testing Complete Template Creation Journey")
    print("="*80)
    
    success = test_complete_template_creation()
    
    print("\n" + "="*80)
    print("📊 RESULTS")
    print("="*80)
    
    if success:
        print("🎉 SUCCESS! Complete template creation is working correctly.")
        print("✅ All required fields can be provided step by step")
        print("✅ Template gets finalized with proper payload")
        print("✅ User experience is smooth and predictable")
    else:
        print("❌ FAILED! Template creation needs attention.")
        print("⚠️ Review the conversation flow and field extraction logic")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
