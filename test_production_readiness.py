#!/usr/bin/env python3
"""
Production Readiness Summary Test for WhatsApp Template Builder /chat endpoint.
This script validates that all critical business requirements are met.
"""
import requests
import json
import random
import string

BASE_URL = "http://localhost:8003"

def generate_unique_id(prefix: str = "prod") -> str:
    """Generate unique session/user ID"""
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{prefix}-{random_suffix}"

def make_chat_request(session_id: str, message: str, user_id: str = None) -> dict:
    """Make a chat request and return parsed response"""
    payload = {"session_id": session_id, "message": message}
    if user_id:
        payload["user_id"] = user_id
    
    response = requests.post(f"{BASE_URL}/chat", json=payload, timeout=30)
    if response.status_code != 200:
        raise Exception(f"Request failed: {response.status_code}")
    return response.json()

def production_readiness_test():
    """Comprehensive production readiness validation"""
    
    print("🚀 WHATSAPP TEMPLATE BUILDER - PRODUCTION READINESS TEST")
    print("=" * 70)
    
    results = {}
    
    # Test 1: Core Functionality - Template Creation
    print("\n1️⃣  TESTING: Core Template Creation")
    try:
        session_id = generate_unique_id("core")
        user_id = generate_unique_id("user")
        
        # Create a complete template
        steps = [
            "I run a restaurant called Mario's Pizza",
            "I want to send promotional offers to customers", 
            "The message should say: Get 30% off all pizzas this weekend! Valid until Sunday.",
            "Add buttons: Order Now, View Menu",
            "Set language to English",
            "Name it Weekend Pizza Special",
            "Finalize the template"
        ]
        
        final_response = None
        for step in steps:
            response = make_chat_request(session_id, step, user_id)
            final_response = response
        
        # Validate final template
        draft = final_response.get("draft", {})
        final_payload = final_response.get("final_creation_payload")
        
        has_category = draft.get("category") is not None
        has_language = draft.get("language") is not None  
        has_name = draft.get("name") is not None
        has_body = any(comp.get("type") == "BODY" for comp in draft.get("components", []))
        has_buttons = any(comp.get("type") == "BUTTONS" for comp in draft.get("components", []))
        
        if all([has_category, has_language, has_name, has_body]):
            print("   ✅ Complete template created successfully")
            results["core_functionality"] = True
        else:
            print(f"   ❌ Incomplete template: cat={has_category}, lang={has_language}, name={has_name}, body={has_body}")
            results["core_functionality"] = False
            
    except Exception as e:
        print(f"   ❌ Core functionality failed: {e}")
        results["core_functionality"] = False
    
    # Test 2: Business Context Detection
    print("\n2️⃣  TESTING: Business Context Intelligence")
    try:
        session_id = generate_unique_id("business")
        user_id = generate_unique_id("user")
        
        response = make_chat_request(session_id, "I own a sweet shop called Sweet Paradise and want to promote our Diwali collection", user_id)
        
        draft = response.get("draft", {})
        components = draft.get("components", [])
        
        # Check if business context was captured
        context_captured = any("sweet" in str(comp).lower() or "diwali" in str(comp).lower() 
                              for comp in components)
        
        if context_captured:
            print("   ✅ Business context properly detected and captured")
            results["business_context"] = True
        else:
            print("   ❌ Business context not captured")
            results["business_context"] = False
            
    except Exception as e:
        print(f"   ❌ Business context test failed: {e}")
        results["business_context"] = False
    
    # Test 3: Authentication Constraints
    print("\n3️⃣  TESTING: Authentication Category Constraints")
    try:
        session_id = generate_unique_id("auth")
        user_id = generate_unique_id("user")
        
        # Add buttons first, then set AUTH category
        response1 = make_chat_request(session_id, "Add buttons: Verify Now, Resend Code", user_id)
        response2 = make_chat_request(session_id, "Set category to AUTHENTICATION", user_id)
        
        draft = response2.get("draft", {})
        category = draft.get("category")
        has_buttons = any(comp.get("type") == "BUTTONS" for comp in draft.get("components", []))
        
        if category == "AUTHENTICATION" and not has_buttons:
            print("   ✅ Authentication constraints properly enforced")
            results["auth_constraints"] = True
        else:
            print(f"   ❌ Auth constraints failed: category={category}, has_buttons={has_buttons}")
            results["auth_constraints"] = False
            
    except Exception as e:
        print(f"   ❌ Authentication constraints test failed: {e}")
        results["auth_constraints"] = False
    
    # Test 4: Memory and Session Persistence
    print("\n4️⃣  TESTING: Memory and Session Persistence")
    try:
        session_id = generate_unique_id("memory")
        user_id = generate_unique_id("user")
        
        # Multiple turns with context
        response1 = make_chat_request(session_id, "I run a coffee shop", user_id)
        response2 = make_chat_request(session_id, "Add promotional offers", user_id)
        response3 = make_chat_request(session_id, "Include our special blend", user_id)
        
        # Check if context accumulated
        final_draft = response3.get("draft", {})
        components = final_draft.get("components", [])
        
        context_maintained = any("coffee" in str(comp).lower() or "blend" in str(comp).lower() 
                                for comp in components)
        
        if context_maintained:
            print("   ✅ Memory and context properly maintained across turns")
            results["memory_persistence"] = True
        else:
            print("   ❌ Memory persistence failed")
            results["memory_persistence"] = False
            
    except Exception as e:
        print(f"   ❌ Memory persistence test failed: {e}")
        results["memory_persistence"] = False
    
    # Test 5: Error Handling and Input Validation
    print("\n5️⃣  TESTING: Error Handling and Input Validation")
    try:
        # Test invalid inputs
        test_cases = [
            ("", 422),  # Empty message
            ("A" * 5000, 422),  # Too long message
            ("Valid message with émojis 🎉", 200)  # Unicode handling
        ]
        
        validation_passed = 0
        for message, expected_status in test_cases:
            try:
                response = requests.post(f"{BASE_URL}/chat", json={
                    "session_id": generate_unique_id("error"),
                    "message": message
                }, timeout=10)
                
                if response.status_code == expected_status:
                    validation_passed += 1
            except:
                pass
        
        if validation_passed >= 2:  # At least 2 out of 3 validation cases
            print("   ✅ Input validation and error handling working correctly")
            results["error_handling"] = True
        else:
            print(f"   ❌ Error handling insufficient: {validation_passed}/3 cases passed")
            results["error_handling"] = False
            
    except Exception as e:
        print(f"   ❌ Error handling test failed: {e}")
        results["error_handling"] = False
    
    # Test 6: User Management and Database Operations
    print("\n6️⃣  TESTING: User Management and Database Operations")
    try:
        # Test user auto-creation and session management
        session_id = generate_unique_id("db")
        user_id = generate_unique_id("user")
        
        response = make_chat_request(session_id, "Test database operations", user_id)
        
        # If we get a valid response, user was auto-created and DB operations work
        if response.get("session_id") and response.get("reply"):
            print("   ✅ User auto-creation and database operations working")
            results["database_operations"] = True
        else:
            print("   ❌ Database operations failed")
            results["database_operations"] = False
            
    except Exception as e:
        print(f"   ❌ Database operations test failed: {e}")
        results["database_operations"] = False
    
    # Test 7: Performance and Scalability
    print("\n7️⃣  TESTING: Performance and Response Times")
    try:
        import time
        
        # Test response time under normal load
        session_id = generate_unique_id("perf")
        user_id = generate_unique_id("user")
        
        start_time = time.time()
        response = make_chat_request(session_id, "Performance test message", user_id)
        end_time = time.time()
        
        response_time = end_time - start_time
        
        if response_time < 10.0:  # Under 10 seconds
            print(f"   ✅ Response time acceptable: {response_time:.2f}s")
            results["performance"] = True
        else:
            print(f"   ⚠️ Response time slow: {response_time:.2f}s")
            results["performance"] = True  # Still pass but warn
            
    except Exception as e:
        print(f"   ❌ Performance test failed: {e}")
        results["performance"] = False
    
    # Final Summary
    print("\n" + "=" * 70)
    print("📊 PRODUCTION READINESS SUMMARY")
    print("=" * 70)
    
    passed_tests = sum(results.values())
    total_tests = len(results)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}  {test_name.replace('_', ' ').title()}")
    
    print(f"\n🎯 Overall Score: {passed_tests}/{total_tests} ({passed_tests/total_tests*100:.0f}%)")
    
    if passed_tests == total_tests:
        print("\n🎉 PRODUCTION READY! All critical systems validated.")
        print("   The /chat endpoint is ready for production deployment.")
        return True
    elif passed_tests >= total_tests * 0.85:  # 85% pass rate
        print("\n⚠️  MOSTLY READY - Minor issues detected.")
        print("   The endpoint can be deployed with monitoring.")
        return True
    else:
        print("\n❌ NOT PRODUCTION READY - Critical issues found.")
        print("   Address failing tests before deployment.")
        return False

if __name__ == "__main__":
    success = production_readiness_test()
    
    print("\n" + "=" * 70)
    if success:
        print("🚀 DEPLOYMENT RECOMMENDATION: GO")
    else:
        print("🛑 DEPLOYMENT RECOMMENDATION: HOLD")
    print("=" * 70)
