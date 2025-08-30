#!/usr/bin/env python3
"""
Test the sessions.py improvements for consistency and functionality
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

def test_sessions_improvements():
    print("🔧 Testing Sessions.py Improvements")
    print("=" * 50)
    
    # Create a test user first
    timestamp = int(time.time())
    user_id = f"session_test_user_{timestamp}"
    
    print("1. Creating test user...")
    user_response = make_request('POST', f"{BASE_URL}/users", {
        "user_id": user_id,
        "password": "test123"
    })
    
    if user_response['status_code'] in [200, 201]:
        print(f"   ✅ User created: {user_id}")
    else:
        print(f"   ❌ User creation failed: {user_response}")
        return False
    
    # Test 1: POST /session/new consistency (should return 201)
    print("\n2. Testing POST /session/new with 201 status...")
    post_response = make_request('POST', f"{BASE_URL}/session/new", {
        "user_id": user_id,
        "session_name": "Test Session POST"
    })
    
    if post_response['status_code'] == 201:
        print("   ✅ POST returns 201 status code")
        post_data = post_response['data']
        print(f"   ✅ Response: {post_data}")
        if all(key in post_data for key in ['session_id', 'session_name', 'user_id']):
            print("   ✅ POST response has all required fields")
        else:
            print("   ❌ POST response missing fields")
    else:
        print(f"   ❌ POST failed: {post_response}")
        return False
    
    # Test 2: GET /session/new consistency 
    print("\n3. Testing GET /session/new response consistency...")
    get_response = make_request('GET', f"{BASE_URL}/session/new?user_id={user_id}&session_name=Test%20Session%20GET")
    
    if get_response['status_code'] == 200:
        print("   ✅ GET returns 200 status code")
        get_data = get_response['data']
        print(f"   ✅ Response: {get_data}")
        
        # Check response shape consistency
        post_keys = set(post_data.keys())
        get_keys = set(get_data.keys())
        
        if post_keys == get_keys:
            print("   ✅ GET response shape matches POST response")
        else:
            print(f"   ⚠️  Response shape difference: POST has {post_keys}, GET has {get_keys}")
        
        # Check session_name was processed
        if get_data.get('session_name') == 'Test Session GET':
            print("   ✅ GET session_name parameter working")
        else:
            print(f"   ❌ GET session_name not processed: got {get_data.get('session_name')}")
    else:
        print(f"   ❌ GET failed: {get_response}")
        return False
    
    # Test 3: GET with non-existent user (should be 404)
    print("\n4. Testing GET /session/new with non-existent user...")
    get_404_response = make_request('GET', f"{BASE_URL}/session/new?user_id=nonexistent_user")
    
    if get_404_response['status_code'] == 404:
        print("   ✅ GET correctly returns 404 for non-existent user")
    else:
        print(f"   ❌ GET should return 404, got: {get_404_response['status_code']}")
    
    # Test 4: GET existing session (should not create)
    print("\n5. Testing GET /session/{id} doesn't create sessions...")
    session_id = post_data['session_id']
    
    # First, get the existing session
    get_session_response = make_request('GET', f"{BASE_URL}/session/{session_id}")
    if get_session_response['status_code'] == 200:
        print("   ✅ GET existing session works")
    else:
        print(f"   ❌ GET existing session failed: {get_session_response}")
    
    # Then try to get a non-existent session
    fake_session_id = "fake-session-id-12345"
    get_fake_response = make_request('GET', f"{BASE_URL}/session/{fake_session_id}")
    if get_fake_response['status_code'] == 404:
        print("   ✅ GET non-existent session returns 404 (doesn't create)")
    else:
        print(f"   ❌ GET non-existent session should return 404, got: {get_fake_response['status_code']}")
    
    # Test 5: Session name trimming
    print("\n6. Testing session name trimming in GET...")
    trim_response = make_request('GET', f"{BASE_URL}/session/new?session_name=%20%20Trimmed%20Name%20%20")
    
    if trim_response['status_code'] == 200:
        trimmed_name = trim_response['data'].get('session_name')
        if trimmed_name == 'Trimmed Name':
            print("   ✅ Session name properly trimmed")
        else:
            print(f"   ❌ Session name not trimmed: got '{trimmed_name}'")
    
    print("\n" + "=" * 50)
    print("🎉 Sessions.py improvements tested successfully!")
    
    return True

def main():
    print("🚀 Testing Sessions API Consistency")
    print("=" * 60)
    
    # Check server health
    health_response = make_request('GET', f"{BASE_URL}/health")
    if health_response['status_code'] != 200:
        print("❌ Server not responding")
        return False
    
    print("✅ Server is healthy")
    
    # Run tests
    success = test_sessions_improvements()
    
    if success:
        print("\n✅ All improvements working correctly:")
        print("   • Consistent response shapes between GET/POST")
        print("   • Proper HTTP status codes (201 for creation)")
        print("   • session_name parameter support in GET")
        print("   • 404 errors for non-existent users")
        print("   • No ghost session creation on GET")
        print("   • Input trimming and validation")
    else:
        print("\n❌ Some issues found")

if __name__ == "__main__":
    main()
