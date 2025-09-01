#!/usr/bin/env python3
"""
Targeted test for authentication constraints fix
"""
import requests
import json

BASE_URL = "http://localhost:8003"

def test_auth_constraints_fix():
    """Test that AUTHENTICATION category properly blocks buttons"""
    
    session_id = "test-auth-fix"
    user_id = "test-user-auth-fix"
    
    print("Testing AUTHENTICATION constraints fix...")
    
    # Step 1: Create an initial template and add buttons first
    print("Step 1: Add buttons first...")
    response1 = requests.post(f"{BASE_URL}/chat", json={
        "session_id": session_id,
        "user_id": user_id,
        "message": "Add buttons: Verify Now, Resend Code"
    })
    
    print(f"Response 1 status: {response1.status_code}")
    if response1.status_code == 200:
        data1 = response1.json()
        has_buttons_before = any(comp.get("type") == "BUTTONS" for comp in data1.get("draft", {}).get("components", []))
        print(f"Has buttons before AUTH: {has_buttons_before}")
    
    # Step 2: Set category to AUTHENTICATION (this should remove buttons)
    print("Step 2: Set category to AUTHENTICATION...")
    response2 = requests.post(f"{BASE_URL}/chat", json={
        "session_id": session_id,
        "user_id": user_id,
        "message": "Set category to AUTHENTICATION"
    })
    
    print(f"Response 2 status: {response2.status_code}")
    if response2.status_code == 200:
        data2 = response2.json()
        category = data2.get("draft", {}).get("category")
        has_buttons_after = any(comp.get("type") == "BUTTONS" for comp in data2.get("draft", {}).get("components", []))
        print(f"Category: {category}")
        print(f"Has buttons after AUTH: {has_buttons_after}")
    
    # Step 3: Try to finalize to see if buttons are removed
    print("Step 3: Try to finalize...")
    response3 = requests.post(f"{BASE_URL}/chat", json={
        "session_id": session_id,
        "user_id": user_id,
        "message": "Finalize the template"
    })
    
    print(f"Response 3 status: {response3.status_code}")
    if response3.status_code == 200:
        data3 = response3.json()
        category = data3.get("draft", {}).get("category")
        has_buttons_final = any(comp.get("type") == "BUTTONS" for comp in data3.get("draft", {}).get("components", []))
        print(f"Final category: {category}")
        print(f"Has buttons in final: {has_buttons_final}")
        
        if category == "AUTHENTICATION" and not has_buttons_final:
            print("✅ SUCCESS: Buttons properly removed for AUTHENTICATION category")
            return True
        elif category == "AUTHENTICATION" and has_buttons_final:
            print("❌ FAIL: Buttons still present in AUTHENTICATION template")
            return False
        else:
            print(f"⚠️ Category not set to AUTHENTICATION: {category}")
            return False
    
    print("❌ FAIL: Could not complete the test")
    return False

if __name__ == "__main__":
    result = test_auth_constraints_fix()
    if result:
        print("\n🎉 Authentication constraints fix is working!")
    else:
        print("\n💥 Authentication constraints fix needs more work")
