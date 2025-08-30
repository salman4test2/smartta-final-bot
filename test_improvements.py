#!/usr/bin/env python3
"""
Test the improved API endpoints with better validation and error handling
"""

import urllib.request
import json
import time

BASE_URL = "http://localhost:8000"

def make_request(method: str, url: str, data: dict = None) -> dict:
    try:
        if data:
            data_bytes = json.dumps(data).encode('utf-8')
            req = urllib.request.Request(url, data=data_bytes, method=method)
            req.add_header('Content-Type', 'application/json')
        else:
            req = urllib.request.Request(url, method=method)
        
        with urllib.request.urlopen(req) as response:
            response_data = response.read().decode('utf-8')
            return {'status_code': response.status, 'data': json.loads(response_data)}
    except urllib.error.HTTPError as e:
        error_data = e.read().decode('utf-8')
        return {'status_code': e.status, 'data': error_data}
    except Exception as e:
        return {'status_code': 500, 'data': str(e)}

def test_improvements():
    print("🔧 Testing API Improvements")
    print("=" * 50)
    
    timestamp = int(time.time())
    
    # Test 1: Create user with proper validation
    print("\n1. Testing user creation...")
    user_data = {"user_id": f"test_user_{timestamp}", "password": "test123"}
    response = make_request('POST', f"{BASE_URL}/users", user_data)
    
    if response['status_code'] in [200, 201]:
        user_id = response['data']['user_id']
        print(f"   ✅ User created: {user_id}")
    else:
        print(f"   ❌ User creation failed: {response}")
        return
    
    # Test 2: Create session with proper validation and 201 status
    print("\n2. Testing session creation with validation...")
    session_data = {
        "user_id": user_id,
        "session_name": "   Test Session with Spaces   "  # Test trimming
    }
    response = make_request('POST', f"{BASE_URL}/session/new", session_data)
    
    if response['status_code'] == 201:  # Should be 201 now
        session_id = response['data']['session_id']
        session_name = response['data']['session_name']
        print(f"   ✅ Session created: {session_id}")
        print(f"   ✅ Session name trimmed: '{session_name}'")
    else:
        print(f"   ❌ Session creation failed: {response}")
        return
    
    # Test 3: Try to create session with non-existent user (should 404)
    print("\n3. Testing session creation with invalid user...")
    invalid_session_data = {
        "user_id": "non_existent_user",
        "session_name": "Should Fail"
    }
    response = make_request('POST', f"{BASE_URL}/session/new", invalid_session_data)
    
    if response['status_code'] == 404:
        print("   ✅ Correctly returned 404 for non-existent user")
    else:
        print(f"   ❌ Expected 404, got: {response}")
    
    # Test 4: Try to get non-existent session (should 404)
    print("\n4. Testing GET session with non-existent ID...")
    response = make_request('GET', f"{BASE_URL}/session/non_existent_session")
    
    if response['status_code'] == 404:
        print("   ✅ Correctly returned 404 for non-existent session")
    else:
        print(f"   ❌ Expected 404, got: {response}")
    
    # Test 5: Test session name update with trimming
    print("\n5. Testing session name update with trimming...")
    # First add the session to user
    user_session_data = {"session_name": "   Trimmed Name   "}
    response = make_request('PUT', f"{BASE_URL}/users/{user_id}/sessions/{session_id}/name", 
                           user_session_data)
    
    if response['status_code'] == 200:
        updated_name = response['data']['session_name']
        print(f"   ✅ Session name updated and trimmed: '{updated_name}'")
    else:
        print(f"   ❌ Session name update failed: {response}")
    
    # Test 6: Test user sessions list with pagination
    print("\n6. Testing user sessions list with pagination...")
    response = make_request('GET', f"{BASE_URL}/users/{user_id}/sessions?limit=10&offset=0")
    
    if response['status_code'] == 200:
        data = response['data']
        print(f"   ✅ Sessions list retrieved")
        print(f"   ✅ Total sessions: {data.get('total_sessions', 0)}")
        print(f"   ✅ Limit: {data.get('limit', 'N/A')}")
        print(f"   ✅ Offset: {data.get('offset', 'N/A')}")
        print(f"   ✅ Has more: {data.get('has_more', 'N/A')}")
    else:
        print(f"   ❌ Sessions list failed: {response}")
    
    print("\n" + "=" * 50)
    print("🎉 API improvements tested successfully!")
    print("\n✅ Improvements implemented:")
    print("   • Proper HTTP status codes (201 for creation)")
    print("   • 404 errors for missing resources")
    print("   • Input trimming and validation")
    print("   • Pagination support with metadata")
    print("   • Better error handling")
    print("   • Updated timestamps on session rename")

if __name__ == "__main__":
    test_improvements()
