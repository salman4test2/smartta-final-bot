#!/usr/bin/env python3
"""
Debug Multi-Turn Persistence
Test to debug why body content is lost between conversation turns.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from fastapi.testclient import TestClient
from app.main import app

def debug_persistence():
    """Debug why content is lost between turns."""
    client = TestClient(app)
    
    print("🔍 DEBUGGING MULTI-TURN PERSISTENCE")
    print("="*60)
    
    # Create user and session
    try:
        client.post("/users", json={"user_id": "persistence_test", "password": "test123"})
    except:
        pass
    
    session_response = client.post("/session/new", json={
        "user_id": "persistence_test",
        "session_name": "Persistence Test"
    })
    session_id = session_response.json()["session_id"]
    print(f"📱 Session: {session_id}")
    
    # Step 1: Provide explicit content
    print("\n--- Step 1: Provide explicit content ---")
    response1 = client.post("/chat", json={
        "message": "The message should say: Hi {{1}}! Special 20% off just for you! Use code SAVE20. Valid until {{2}}. Shop now!",
        "session_id": session_id,
        "user_id": "persistence_test"
    })
    
    result1 = response1.json()
    print(f"Step 1 response: {result1.get('reply', '')[:100]}...")
    print(f"Step 1 missing: {result1.get('missing', [])}")
    
    draft1 = result1.get('draft', {})
    components1 = draft1.get('components', [])
    body1 = next((c for c in components1 if c.get('type') == 'BODY'), None)
    print(f"Step 1 body component: {body1}")
    print(f"Step 1 draft structure: {list(draft1.keys())}")
    
    # Step 2: Simple continuation
    print("\n--- Step 2: Continue conversation ---")
    response2 = client.post("/chat", json={
        "message": "Yes, finalize this template",
        "session_id": session_id,
        "user_id": "persistence_test"
    })
    
    result2 = response2.json()
    print(f"Step 2 response: {result2.get('reply', '')[:100]}...")
    print(f"Step 2 missing: {result2.get('missing', [])}")
    
    draft2 = result2.get('draft', {})
    components2 = draft2.get('components', [])
    body2 = next((c for c in components2 if c.get('type') == 'BODY'), None)
    print(f"Step 2 body component: {body2}")
    print(f"Step 2 draft structure: {list(draft2.keys())}")
    
    # Check if template completed
    final_payload = result2.get('final_creation_payload')
    if final_payload:
        print("✅ Template completed successfully!")
        return True
    else:
        print("❌ Template not completed - body lost between turns")
        
        # Let's try one more explicit step
        print("\n--- Step 3: Re-provide content ---")
        response3 = client.post("/chat", json={
            "message": "Set the name to clothing_discount_offer, language to en_US, category to MARKETING, and message: Hi {{1}}! Special 20% off just for you! Use code SAVE20. Valid until {{2}}. Shop now!",
            "session_id": session_id,
            "user_id": "persistence_test"
        })
        
        result3 = response3.json()
        print(f"Step 3 response: {result3.get('reply', '')[:100]}...")
        print(f"Step 3 missing: {result3.get('missing', [])}")
        
        final_payload3 = result3.get('final_creation_payload')
        if final_payload3:
            print("✅ Template completed after re-provision!")
            return True
        
        return False

if __name__ == "__main__":
    debug_persistence()
