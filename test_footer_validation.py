#!/usr/bin/env python3
"""
Test FOOTER placeholder validation rule
"""

import requests
import json

BASE_URL = "http://localhost:8003"

def test_footer_placeholder_validation():
    print("🔍 Testing FOOTER placeholder validation")
    print("=" * 50)
    
    # Test 1: Create a template and try to finalize with footer containing placeholders
    print("\n1️⃣ Test: Footer with {{1}} placeholder (should be rejected)")
    
    session_id = "test_footer_validation"
    
    try:
        # Step 1: Set up basic template
        response1 = requests.post(f"{BASE_URL}/chat", json={
            "session_id": session_id,
            "message": "I run a shop, category MARKETING, language English, name test_footer"
        })
        
        # Step 2: Add body
        response2 = requests.post(f"{BASE_URL}/chat", json={
            "session_id": session_id,
            "message": "Body: Welcome to our store!"
        })
        
        # Step 3: Add footer with placeholder (should be invalid)
        response3 = requests.post(f"{BASE_URL}/chat", json={
            "session_id": session_id,
            "message": "Footer: Thank you {{1}} for shopping with us!"
        })
        
        # Step 4: Try to finalize (should fail validation)
        response4 = requests.post(f"{BASE_URL}/chat", json={
            "session_id": session_id,
            "message": "Finalize the template"
        })
        
        data4 = response4.json()
        reply = data4.get("reply", "")
        missing = data4.get("missing", [])
        final_payload = data4.get("final_creation_payload")
        
        # Check if validation caught the placeholder issue
        validation_failed = (
            "fix_validation_issues" in missing or
            "placeholder" in reply.lower() or
            "footer" in reply.lower() or
            final_payload is None
        )
        
        if validation_failed:
            print("✅ PASS - Footer with placeholder was rejected")
            print(f"   Reply: {reply}")
            print(f"   Missing: {missing}")
        else:
            print("❌ FAIL - Footer with placeholder was not rejected")
            print(f"   Reply: {reply}")
            print(f"   Final payload created: {final_payload is not None}")
        
    except Exception as e:
        print(f"❌ FAIL - Exception: {e}")
        validation_failed = False
    
    # Test 2: Footer without placeholders (should be accepted)
    print("\n2️⃣ Test: Footer without placeholders (should be accepted)")
    
    session_id2 = "test_footer_validation_good"
    
    try:
        # Set up template with valid footer
        response1 = requests.post(f"{BASE_URL}/chat", json={
            "session_id": session_id2,
            "message": "Shop, MARKETING, English, name test_good_footer"
        })
        
        response2 = requests.post(f"{BASE_URL}/chat", json={
            "session_id": session_id2,
            "message": "Body: Welcome to our store!"
        })
        
        response3 = requests.post(f"{BASE_URL}/chat", json={
            "session_id": session_id2,
            "message": "Footer: Thank you for shopping with us!"
        })
        
        response4 = requests.post(f"{BASE_URL}/chat", json={
            "session_id": session_id2,
            "message": "Finalize the template"
        })
        
        data4 = response4.json()
        reply = data4.get("reply", "")
        final_payload = data4.get("final_creation_payload")
        
        # Check if template was successfully created
        validation_passed = final_payload is not None
        
        if validation_passed:
            print("✅ PASS - Footer without placeholder was accepted")
            print(f"   Template successfully created")
        else:
            print("❌ FAIL - Footer without placeholder was rejected")
            print(f"   Reply: {reply}")
        
    except Exception as e:
        print(f"❌ FAIL - Exception: {e}")
        validation_passed = False
    
    print("\n" + "=" * 50)
    print("📊 FOOTER PLACEHOLDER VALIDATION SUMMARY")
    print("=" * 50)
    
    if validation_failed and validation_passed:
        print("🎉 SUCCESS! Footer placeholder validation working correctly!")
        print("✅ Rejects footers with {{n}} placeholders")
        print("✅ Accepts footers without placeholders")
    else:
        print("⚠️ Issues detected in validation logic")
    
    print("=" * 50)

if __name__ == "__main__":
    test_footer_placeholder_validation()
