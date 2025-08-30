#!/usr/bin/env python3
"""
Integration test to verify that the improved schemas work with the existing API
"""

import asyncio
import urllib.request
import urllib.parse
import json
import time

BASE_URL = "http://localhost:8000"

def make_request(endpoint, method="GET", data=None):
    """Make HTTP request to the API"""
    url = f"{BASE_URL}{endpoint}"
    
    if method == "GET":
        if data:
            query_string = urllib.parse.urlencode(data)
            url = f"{url}?{query_string}"
        req = urllib.request.Request(url)
    else:
        json_data = json.dumps(data).encode('utf-8') if data else b''
        req = urllib.request.Request(url, data=json_data, method=method)
        req.add_header('Content-Type', 'application/json')
    
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Request failed: {e}")
        return None

def test_schema_integration():
    """Test that the new schemas work with the API"""
    print("Testing Schema Integration with Live API")
    print("=" * 50)
    
    # Test 1: Create user with validation
    print("\n1. Testing user creation with new validation...")
    user_data = {
        "user_id": "  test_schema_user  ",  # Test whitespace stripping
        "password": "securepassword123"
    }
    
    result = make_request("/users", "POST", user_data)
    if result:
        print(f"✓ User created successfully: {result.get('user_id')}")
        user_id = result.get('user_id')
        # Verify whitespace was stripped
        if user_id == "test_schema_user":
            print("✓ Whitespace stripping works in API")
        else:
            print(f"✗ Expected 'test_schema_user', got '{user_id}'")
    else:
        print("✗ User creation failed")
        return False
    
    # Test 2: Test user login
    print("\n2. Testing user login...")
    login_data = {
        "user_id": "  test_schema_user  ",  # Test whitespace stripping
        "password": "securepassword123"
    }
    
    result = make_request("/users/login", "POST", login_data)
    if result and result.get('message') == 'Login successful':
        print("✓ User login successful with new schemas")
    else:
        print("✗ User login failed")
    
    # Test 3: Create session with validation
    print("\n3. Testing session creation...")
    session_data = {
        "user_id": "test_schema_user",
        "session_name": "  Schema Test Session  "  # Test whitespace stripping
    }
    
    result = make_request("/session/new", "POST", session_data)
    if result:
        session_id = result.get('session_id')
        session_name = result.get('session_name')
        print(f"✓ Session created: {session_id}")
        if session_name == "Schema Test Session":
            print("✓ Session name whitespace stripping works")
        else:
            print(f"✗ Expected 'Schema Test Session', got '{session_name}'")
    else:
        print("✗ Session creation failed")
        return False
    
    # Test 4: Test chat input validation
    print("\n4. Testing chat with message validation...")
    chat_data = {
        "message": "  Hello, this is a test message with whitespace  ",  # Test stripping
        "session_id": session_id,
        "user_id": "test_schema_user"
    }
    
    result = make_request("/chat", "POST", chat_data)
    if result:
        print("✓ Chat message processed successfully")
        print(f"  Reply preview: {result.get('reply', '')[:50]}...")
    else:
        print("✗ Chat message failed")
    
    # Test 5: Get user sessions with pagination
    print("\n5. Testing user sessions endpoint...")
    result = make_request(f"/users/test_schema_user/sessions", "GET", {"limit": 10, "offset": 0})
    if result:
        print(f"✓ Retrieved {len(result.get('sessions', []))} sessions")
        print(f"  Total sessions: {result.get('total_sessions', 0)}")
        print(f"  Has more: {result.get('has_more', False)}")
    else:
        print("✗ Failed to retrieve user sessions")
    
    # Test 6: Test validation errors
    print("\n6. Testing validation error handling...")
    
    # Test empty message
    invalid_chat = {
        "message": "",  # Should fail validation
        "session_id": session_id
    }
    
    result = make_request("/chat", "POST", invalid_chat)
    if not result:  # Expect this to fail
        print("✓ Empty message correctly rejected")
    else:
        print("✗ Empty message was accepted (should have failed)")
    
    # Test too long session name
    invalid_session = {
        "user_id": "test_schema_user",
        "session_name": "x" * 121  # Should fail validation (max 120)
    }
    
    result = make_request("/session/new", "POST", invalid_session)
    if not result:  # Expect this to fail
        print("✓ Too long session name correctly rejected")
    else:
        print("✗ Too long session name was accepted (should have failed)")
    
    print("\n" + "=" * 50)
    print("Schema integration test completed!")
    return True

if __name__ == "__main__":
    # First check if the server is running
    try:
        health_check = make_request("/")
        if health_check:
            print("Server is running, starting integration test...")
            test_schema_integration()
        else:
            print("Server is not running. Please start the server first with: uvicorn app.main:app --reload")
    except:
        print("Could not connect to server. Please start the server first with: uvicorn app.main:app --reload")
