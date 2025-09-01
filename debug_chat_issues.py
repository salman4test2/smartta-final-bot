#!/usr/bin/env python3
"""
Debug test for specific 500 error issues in /chat endpoint
"""
import requests
import json
import sys

BASE_URL = "http://localhost:8003"

def test_debug_500_error():
    """Debug the 500 error that occurs with business context detection"""
    
    print("=== DEBUGGING 500 ERROR ===")
    
    # First test - simple health check
    try:
        response = requests.get(f"{BASE_URL}/health")
        print(f"Health check: {response.status_code}")
        if response.status_code != 200:
            print("Server not healthy, aborting")
            return False
    except Exception as e:
        print(f"Health check failed: {e}")
        return False
    
    # Test case that previously caused 500 error
    test_payload = {
        "session_id": "test-session-debug-500",
        "user_id": "test-user-debug",
        "message": "I want to create a promotional message for my sweet shop called Sweet Dreams. We're having a 50% off sale on all mithai."
    }
    
    print(f"Testing payload: {test_payload}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/chat", 
            json=test_payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        print(f"Response Status: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        if response.status_code == 500:
            print("=== 500 ERROR DETAILS ===")
            try:
                error_data = response.json()
                print(f"Error JSON: {json.dumps(error_data, indent=2)}")
            except:
                print(f"Error Text: {response.text}")
            return False
        elif response.status_code == 200:
            print("=== SUCCESS - NO 500 ERROR ===")
            try:
                data = response.json()
                print(f"Success Response: {json.dumps(data, indent=2)}")
            except:
                print(f"Success Text: {response.text}")
            return True
        else:
            print(f"=== UNEXPECTED STATUS {response.status_code} ===")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("Request timed out")
        return False
    except Exception as e:
        print(f"Request failed: {e}")
        return False

def test_authentication_constraints():
    """Test authentication category constraints"""
    
    print("\n=== TESTING AUTHENTICATION CONSTRAINTS ===")
    
    # Test that should trigger AUTH category and enforce constraints
    test_payload = {
        "session_id": "test-session-auth-debug",
        "user_id": "test-user-auth",
        "message": "I need to send OTP verification codes to users for login authentication."
    }
    
    print(f"Testing AUTH payload: {test_payload}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/chat", 
            json=test_payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        print(f"AUTH Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"AUTH Response: {json.dumps(data, indent=2)}")
            
            # Check if category was detected
            draft = data.get("draft", {})
            category = draft.get("category")
            print(f"Detected category: {category}")
            
            # Check if buttons are present (should be restricted for AUTH)
            components = draft.get("components", [])
            has_buttons = any(c.get("type") == "BUTTONS" for c in components)
            print(f"Has buttons: {has_buttons}")
            
            return True
        else:
            print(f"AUTH test failed with status {response.status_code}: {response.text}")
            return False
            
    except Exception as e:
        print(f"AUTH request failed: {e}")
        return False

def test_simple_chat():
    """Test simple chat functionality"""
    
    print("\n=== TESTING SIMPLE CHAT ===")
    
    test_payload = {
        "session_id": "test-session-simple",
        "user_id": "test-user-simple", 
        "message": "Hello, I want to create a WhatsApp template."
    }
    
    print(f"Testing simple payload: {test_payload}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/chat", 
            json=test_payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        print(f"Simple Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Simple Response: {json.dumps(data, indent=2)}")
            return True
        else:
            print(f"Simple test failed with status {response.status_code}: {response.text}")
            return False
            
    except Exception as e:
        print(f"Simple request failed: {e}")
        return False

if __name__ == "__main__":
    print("Starting debug tests...")
    
    results = []
    results.append(("500 Error Debug", test_debug_500_error()))
    results.append(("Simple Chat", test_simple_chat()))
    results.append(("Auth Constraints", test_authentication_constraints()))
    
    print("\n=== TEST RESULTS SUMMARY ===")
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"{test_name}: {status}")
    
    total_passed = sum(1 for _, result in results if result)
    total_tests = len(results)
    print(f"\nOverall: {total_passed}/{total_tests} tests passed")
    
    if total_passed < total_tests:
        sys.exit(1)
    else:
        print("All tests passed!")
