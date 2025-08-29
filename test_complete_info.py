#!/usr/bin/env python3
"""
Test Complete Info Provision
Test what happens when user provides all info at once.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from fastapi.testclient import TestClient
from app.main import app

def test_complete_info():
    """Test providing all info at once."""
    client = TestClient(app)
    
    print("🔍 TESTING COMPLETE INFO PROVISION")
    print("="*50)
    
    # Create user and session
    try:
        client.post("/users", json={"user_id": "complete_info_test", "password": "test123"})
    except:
        pass
    
    session_response = client.post("/session/new", json={
        "user_id": "complete_info_test",
        "session_name": "Complete Info Test"
    })
    session_id = session_response.json()["session_id"]
    print(f"📱 Session: {session_id}")
    
    # Provide everything at once
    print("\n--- Providing complete information ---")
    response = client.post("/chat", json={
        "message": "Create a MARKETING template called clothing_special_offer in English (en_US) with this message: Hi {{1}}! Special 20% off just for you! Use code SAVE20. Shop now!",
        "session_id": session_id,
        "user_id": "complete_info_test"
    })
    
    result = response.json()
    print(f"Response: {result.get('reply', '')[:150]}...")
    print(f"Missing: {result.get('missing', [])}")
    
    draft = result.get('draft', {})
    print(f"Draft keys: {list(draft.keys())}")
    print(f"Category: {draft.get('category')}")
    print(f"Name: {draft.get('name')}")
    print(f"Language: {draft.get('language')}")
    
    components = draft.get('components', [])
    body_comp = next((c for c in components if c.get('type') == 'BODY'), None)
    print(f"Body component: {body_comp}")
    
    final_payload = result.get('final_creation_payload')
    if final_payload:
        print("✅ Template completed in one step!")
        return True
    else:
        print("❌ Template not completed, trying finalization...")
        
        # Try explicit finalization
        final_response = client.post("/chat", json={
            "message": "Finalize this template",
            "session_id": session_id,
            "user_id": "complete_info_test"
        })
        
        final_result = final_response.json()
        print(f"Final response: {final_result.get('reply', '')[:150]}...")
        print(f"Final missing: {final_result.get('missing', [])}")
        
        final_payload2 = final_result.get('final_creation_payload')
        if final_payload2:
            print("✅ Template completed after finalization!")
            return True
        else:
            print("❌ Still not completed")
            return False

if __name__ == "__main__":
    test_complete_info()
