#!/usr/bin/env python3
"""
Final validation script - quick validation of all fixed issues
"""

import requests
import json

BASE_URL = "http://localhost:8003"

def test_quick_validation():
    print("🔍 Final Quick Validation Tests")
    print("=" * 50)
    
    tests_passed = 0
    total_tests = 0
    
    # Test 1: Authentication category auto-detection
    print("\n1️⃣ Testing authentication auto-detection...")
    total_tests += 1
    try:
        response = requests.post(f"{BASE_URL}/chat", json={
            "session_id": "test_auth_auto",
            "message": "I need to send OTP verification codes"
        })
        data = response.json()
        auth_detected = data.get("draft", {}).get("category") == "AUTHENTICATION"
        
        if auth_detected:
            print("✅ PASS - Authentication category auto-detected")
            tests_passed += 1
        else:
            print(f"❌ FAIL - Expected AUTH, got: {data.get('draft', {}).get('category')}")
    except Exception as e:
        print(f"❌ FAIL - Exception: {e}")
    
    # Test 2: Missing field is always a list
    print("\n2️⃣ Testing missing field consistency...")
    total_tests += 1
    try:
        # Test incomplete template
        response1 = requests.post(f"{BASE_URL}/chat", json={
            "session_id": "test_missing_incomplete",
            "message": "Create a marketing template"
        })
        data1 = response1.json()
        missing1_is_list = isinstance(data1.get("missing"), list)
        
        # Test finalized template
        response2 = requests.post(f"{BASE_URL}/chat", json={
            "session_id": "test_missing_complete",
            "message": "I run a pizza place"
        })
        requests.post(f"{BASE_URL}/chat", json={
            "session_id": "test_missing_complete",
            "message": "Category is MARKETING"
        })
        requests.post(f"{BASE_URL}/chat", json={
            "session_id": "test_missing_complete",
            "message": "Language is English"
        })
        requests.post(f"{BASE_URL}/chat", json={
            "session_id": "test_missing_complete",
            "message": "Name it pizza_promo"
        })
        requests.post(f"{BASE_URL}/chat", json={
            "session_id": "test_missing_complete",
            "message": "Message: Get 20% off pizza!"
        })
        response3 = requests.post(f"{BASE_URL}/chat", json={
            "session_id": "test_missing_complete",
            "message": "Finalize the template"
        })
        data3 = response3.json()
        missing3_is_list = isinstance(data3.get("missing"), list)
        
        if missing1_is_list and missing3_is_list:
            print("✅ PASS - Missing field is always a list")
            tests_passed += 1
        else:
            print(f"❌ FAIL - Missing field types: incomplete={type(data1.get('missing'))}, complete={type(data3.get('missing'))}")
    except Exception as e:
        print(f"❌ FAIL - Exception: {e}")
    
    # Test 3: Authentication constraints (no buttons)
    print("\n3️⃣ Testing authentication constraints...")
    total_tests += 1
    try:
        response = requests.post(f"{BASE_URL}/chat", json={
            "session_id": "test_auth_constraints",
            "message": "Create authentication template with verification code"
        })
        requests.post(f"{BASE_URL}/chat", json={
            "session_id": "test_auth_constraints",
            "message": "Add quick reply buttons"
        })
        final_response = requests.post(f"{BASE_URL}/chat", json={
            "session_id": "test_auth_constraints",
            "message": "Finalize the template"
        })
        
        data = final_response.json()
        category = data.get("draft", {}).get("category")
        components = data.get("draft", {}).get("components", [])
        has_buttons = any(c.get("type") == "BUTTONS" for c in components)
        
        if category == "AUTHENTICATION" and not has_buttons:
            print("✅ PASS - Authentication constraints enforced")
            tests_passed += 1
        else:
            print(f"❌ FAIL - Category: {category}, Has buttons: {has_buttons}")
    except Exception as e:
        print(f"❌ FAIL - Exception: {e}")
    
    # Test 4: Input validation
    print("\n4️⃣ Testing input validation...")
    total_tests += 1
    try:
        # Test empty message
        response = requests.post(f"{BASE_URL}/chat", json={
            "session_id": "test_validation",
            "message": ""
        })
        
        if response.status_code == 422:
            print("✅ PASS - Input validation working (422 for empty message)")
            tests_passed += 1
        else:
            print(f"❌ FAIL - Expected 422, got {response.status_code}")
    except Exception as e:
        print(f"❌ FAIL - Exception: {e}")
    
    # Test 5: Core functionality 
    print("\n5️⃣ Testing core functionality...")
    total_tests += 1
    try:
        response = requests.post(f"{BASE_URL}/chat", json={
            "session_id": "test_core",
            "message": "Create a promotional template for my restaurant"
        })
        
        data = response.json()
        has_required_fields = all(field in data for field in ["session_id", "reply", "draft", "missing"])
        
        if response.status_code == 200 and has_required_fields:
            print("✅ PASS - Core functionality working")
            tests_passed += 1
        else:
            print(f"❌ FAIL - Status: {response.status_code}, Fields: {list(data.keys())}")
    except Exception as e:
        print(f"❌ FAIL - Exception: {e}")
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 FINAL VALIDATION SUMMARY")
    print("=" * 50)
    print(f"Tests Passed: {tests_passed}/{total_tests}")
    print(f"Success Rate: {(tests_passed/total_tests)*100:.1f}%")
    
    if tests_passed == total_tests:
        print("\n🎉 ALL TESTS PASSED!")
        print("🚀 The /chat endpoint is fully validated and production-ready!")
    else:
        print(f"\n⚠️ {total_tests - tests_passed} tests failed. Review issues above.")
    
    print("=" * 50)

if __name__ == "__main__":
    test_quick_validation()
