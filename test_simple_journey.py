#!/usr/bin/env python3
"""
Simple Journey Test - Focus on core functionality
Tests the basic template creation flow with minimal complexity.
"""

from fastapi.testclient import TestClient
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.main import app

def test_basic_journey():
    """Test basic template creation journey."""
    client = TestClient(app)
    
    print("🧪 BASIC JOURNEY TEST")
    print("="*50)
    
    # Create user
    try:
        user_response = client.post("/users", json={
            "user_id": "simple_test_user", 
            "password": "test123"
        })
        print("👤 Created user")
    except:
        print("👤 User exists or creation failed (continuing)")
    
    # Create session
    session_response = client.post("/session/new", json={
        "user_id": "simple_test_user",
        "session_name": "Simple Test"
    })
    session_id = session_response.json()["session_id"]
    print(f"📱 Session: {session_id}")
    
    # Test messages in sequence
    messages = [
        "I want to create a discount offer template",
        "I run a clothing store for young women",
        "Yes, marketing template sounds perfect",
        "The message should say: Hi {{1}}! Special 20% off just for you! Use code SAVE20. Valid until {{2}}. Shop now!",
        "Call the template clothing_discount_promo",
        "Yes, finalize this template"
    ]
    
    for i, message in enumerate(messages, 1):
        print(f"\n--- Step {i} ---")
        print(f"👤 USER: {message}")
        
        response = client.post("/chat", json={
            "message": message,
            "session_id": session_id,
            "user_id": "simple_test_user"
        })
        
        result = response.json()
        print(f"🤖 AI: {result.get('reply', '')[:100]}...")
        
        if result.get('missing'):
            print(f"📋 Missing: {result['missing']}")
        
        if result.get('final_creation_payload'):
            print("🎉 TEMPLATE COMPLETED!")
            template = result['final_creation_payload']
            print(f"   Name: {template.get('name')}")
            print(f"   Category: {template.get('category')}")
            print(f"   Language: {template.get('language')}")
            
            body = next((c.get('text') for c in template.get('components', []) if c.get('type') == 'BODY'), None)
            if body:
                print(f"   Message: {body}")
            
            return True
    
    print("❌ Template not completed in expected steps")
    return False

def test_welcome_endpoint():
    """Test the welcome endpoint."""
    client = TestClient(app)
    
    print("\n🎬 WELCOME ENDPOINT TEST")
    print("="*30)
    
    response = client.get("/welcome")
    data = response.json()
    
    print("✅ Welcome message retrieved")
    print(f"✅ Journey stage: {data.get('journey_stage')}")
    print(f"✅ Examples provided: {len(data.get('examples', []))}")
    
    return True

def test_user_management():
    """Test user creation and management."""
    client = TestClient(app)
    
    print("\n👥 USER MANAGEMENT TEST")
    print("="*25)
    
    # Create user
    user_data = {"user_id": "test_mgmt_user", "password": "secure123"}
    response = client.post("/users", json=user_data)
    
    if response.status_code == 200:
        print("✅ User created successfully")
    elif response.status_code == 400:
        print("✅ User already exists (expected)")
    else:
        print(f"❌ Unexpected response: {response.status_code}")
        return False
    
    # Test login
    login_response = client.post("/users/login", json=user_data)
    if login_response.status_code == 200:
        print("✅ User login successful")
    else:
        print(f"❌ Login failed: {login_response.status_code}")
        return False
    
    return True

if __name__ == "__main__":
    print("🚀 WhatsApp Template Builder - Core Functionality Test")
    print("="*60)
    
    tests = [
        ("Welcome Endpoint", test_welcome_endpoint),
        ("User Management", test_user_management),
        ("Basic Template Journey", test_basic_journey)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
            print(f"✅ {test_name}: {'PASSED' if result else 'FAILED'}")
        except Exception as e:
            results.append((test_name, False))
            print(f"❌ {test_name}: ERROR - {e}")
    
    print("\n" + "="*60)
    print("📊 TEST RESULTS SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED - System is working correctly!")
    else:
        print("⚠️ Some tests failed - Check the issues above")
    
    sys.exit(0 if passed == total else 1)
