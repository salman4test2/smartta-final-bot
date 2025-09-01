#!/usr/bin/env python3
"""
Test the improvements: friendly messaging and business profile storage
"""

import requests
import json
import time

BASE_URL = "http://localhost:8003"

def test_improvements():
    print("🔍 Testing Improvements")
    print("=" * 60)
    
    # Test 1: Friendly messaging
    print("\n1️⃣ Testing Friendly Messaging")
    print("-" * 30)
    
    try:
        response = requests.post(f"{BASE_URL}/chat", json={
            "session_id": f"test_friendly_{int(time.time())}",
            "message": "hello",
            "user_id": "test_user_friendly"
        }, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            reply = data.get("reply", "")
            print(f"Reply: {reply}")
            
            # Check if response is friendly
            friendly_indicators = ["hello", "hi", "great", "wonderful", "help", "assist", "welcome"]
            is_friendly = any(word in reply.lower() for word in friendly_indicators)
            
            if is_friendly:
                print("✅ PASS - Response is friendly")
            else:
                print("❌ FAIL - Response doesn't seem friendly")
        else:
            print(f"❌ FAIL - HTTP {response.status_code}")
            
    except Exception as e:
        print(f"❌ FAIL - Exception: {e}")
    
    # Test 2: Business profile storage
    print("\n2️⃣ Testing Business Profile Storage")
    print("-" * 30)
    
    user_id = f"test_user_profile_{int(time.time())}"
    session_id = f"test_profile_{int(time.time())}"
    
    try:
        # First interaction - mention business
        response1 = requests.post(f"{BASE_URL}/chat", json={
            "session_id": session_id,
            "message": "I run a restaurant called Mario's Pizza",
            "user_id": user_id
        }, timeout=10)
        
        print("First response:", response1.json().get("reply", ""))
        
        # Second interaction - new session, should remember business
        time.sleep(1)
        response2 = requests.post(f"{BASE_URL}/chat", json={
            "session_id": f"test_profile_new_{int(time.time())}",
            "message": "I want to create a template",
            "user_id": user_id  # Same user, different session
        }, timeout=10)
        
        print("Second response:", response2.json().get("reply", ""))
        
        # Check if it remembers the business
        second_reply = response2.json().get("reply", "")
        remembers_business = "mario" in second_reply.lower() or "pizza" in second_reply.lower() or "restaurant" in second_reply.lower()
        
        if remembers_business:
            print("✅ PASS - Bot remembers business information")
        else:
            print("❌ PARTIAL - Bot may not be using stored business profile yet")
            
    except Exception as e:
        print(f"❌ FAIL - Exception: {e}")
    
    # Test 3: Test runner
    print("\n3️⃣ Testing Test Runner")
    print("-" * 30)
    
    import subprocess
    import os
    
    try:
        # Check if tests folder exists
        tests_dir = "tests"
        if os.path.exists(tests_dir):
            test_files = [f for f in os.listdir(tests_dir) if f.startswith("test_") and f.endswith(".py")]
            print(f"✅ PASS - Tests folder exists with {len(test_files)} test files")
        else:
            print("❌ FAIL - Tests folder doesn't exist")
        
        # Check if run_tests.py exists
        if os.path.exists("run_tests.py"):
            print("✅ PASS - Test runner exists")
        else:
            print("❌ FAIL - Test runner doesn't exist")
            
    except Exception as e:
        print(f"❌ FAIL - Exception: {e}")

if __name__ == "__main__":
    test_improvements()
