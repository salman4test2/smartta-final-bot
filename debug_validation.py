#!/usr/bin/env python3
"""
Debug Validation Issues
Test to identify what validation issues prevent template finalization.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from fastapi.testclient import TestClient
from app.main import app

def debug_validation():
    """Debug validation issues preventing finalization."""
    client = TestClient(app)
    
    print("🔍 DEBUGGING VALIDATION ISSUES")
    print("="*50)
    
    # Create user and session
    try:
        client.post("/users", json={"user_id": "debug_user", "password": "test123"})
    except:
        pass
    
    session_response = client.post("/session/new", json={
        "user_id": "debug_user",
        "session_name": "Debug Session"
    })
    session_id = session_response.json()["session_id"]
    print(f"📱 Session: {session_id}")
    
    # Send a very explicit finalization request
    response = client.post("/chat", json={
        "message": "Create a marketing template called test_template in English with this message: Hi {{1}}! Special offer for you. Valid until {{2}}. Thanks!",
        "session_id": session_id,
        "user_id": "debug_user"
    })
    
    result = response.json()
    print(f"Reply: {result.get('reply', '')[:200]}")
    print(f"Missing: {result.get('missing', [])}")
    
    draft = result.get('draft', {})
    print(f"Draft: {draft}")
    
    # Try explicit finalization
    final_response = client.post("/chat", json={
        "message": "Finalize this template now. All required fields are provided.",
        "session_id": session_id,
        "user_id": "debug_user"
    })
    
    final_result = final_response.json()
    print(f"\nFinal reply: {final_result.get('reply', '')[:200]}")
    print(f"Final missing: {final_result.get('missing', [])}")
    
    final_payload = final_result.get('final_creation_payload')
    if final_payload:
        print("✅ Template finalized!")
        print(f"Payload: {final_payload}")
        return True
    else:
        print("❌ Template not finalized")
        print(f"Final draft: {final_result.get('draft', {})}")
        return False

if __name__ == "__main__":
    debug_validation()
