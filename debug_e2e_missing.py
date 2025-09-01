#!/usr/bin/env python3
"""
Debug the E2E missing field issue
"""

import requests
import json
import time
import random

BASE_URL = "http://localhost:8003"

def test_e2e_finalize():
    """Debug the E2E finalize step specifically"""
    
    session_id = f"debug_e2e_{int(time.time())}_{random.randint(1000, 9999)}"
    user_id = f"test_user_{random.randint(10000, 99999)}"
    
    print(f"🔍 Testing E2E flow with session: {session_id}")
    
    steps = [
        ("Business context", "I run a pizza restaurant called Mario's Pizza"),
        ("Category", "I want to send promotional offers"),
        ("Content", "Add message: Get 30% off on all pizzas this weekend!"),
        ("Extras", "Add buttons: Order Now, View Menu"),
        ("Language", "Set language to English"),
        ("Name", "Name it Pizza Weekend Sale"),
        ("Finalize", "Please finalize the template")
    ]
    
    for i, (step_name, message) in enumerate(steps):
        print(f"\n📝 Step {i+1}: {step_name}")
        print(f"   Message: {message}")
        
        payload = {
            "session_id": session_id,
            "message": message
        }
        if user_id:
            payload["user_id"] = user_id
        
        try:
            response = requests.post(f"{BASE_URL}/chat", json=payload, timeout=30)
            
            print(f"   Status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"   ❌ Error: {response.text}")
                continue
                
            data = response.json()
            
            # Check missing field specifically
            missing = data.get("missing")
            print(f"   Missing type: {type(missing)}")
            print(f"   Missing value: {missing}")
            
            # Check if it's a list
            if isinstance(missing, list):
                print(f"   ✅ Missing is list: {missing}")
            else:
                print(f"   ❌ Missing is NOT list: {missing} ({type(missing)})")
                
            # Show key parts of response
            print(f"   Draft category: {data.get('draft', {}).get('category')}")
            print(f"   Draft components count: {len(data.get('draft', {}).get('components', []))}")
            print(f"   Final payload: {data.get('final_creation_payload') is not None}")
            
            # If it's the finalize step and missing is not a list, show full response
            if step_name == "Finalize" and not isinstance(missing, list):
                print(f"   🚨 FULL RESPONSE FOR DEBUGGING:")
                print(json.dumps(data, indent=2))
                
        except Exception as e:
            print(f"   ❌ Exception: {e}")

if __name__ == "__main__":
    test_e2e_finalize()
