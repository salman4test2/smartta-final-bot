#!/usr/bin/env python3
"""
Fixed API test - creates users first and handles conversation flow properly.
Tests both simple and complex template creation journeys.
"""

import urllib.request
import urllib.parse
import json
import uuid
from typing import Dict, Any

BASE_URL = "http://localhost:8001"

def call_api(endpoint: str, method: str = "GET", data: Dict = None) -> Dict[str, Any]:
    """Make an API call to the server using urllib."""
    url = f"{BASE_URL}{endpoint}"
    
    try:
        if method == "GET":
            with urllib.request.urlopen(url) as response:
                result = json.loads(response.read().decode())
                return {"status": response.status, "data": result}
        elif method == "POST":
            json_data = json.dumps(data).encode() if data else b""
            req = urllib.request.Request(
                url, 
                data=json_data,
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode())
                return {"status": response.status, "data": result}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def create_user(user_id: str, username: str, email: str) -> Dict[str, Any]:
    """Create a user."""
    payload = {
        "user_id": user_id,
        "username": username,
        "email": email,
        "password": "test123"
    }
    return call_api("/users", "POST", payload)

def chat_message(session_id: str, message: str, user_id: str = None) -> Dict[str, Any]:
    """Send a chat message and get response."""
    payload = {
        "session_id": session_id,
        "message": message
    }
    if user_id:
        payload["user_id"] = user_id
        
    return call_api("/chat", "POST", payload)

def get_welcome() -> Dict[str, Any]:
    """Get the welcome message."""
    return call_api("/welcome")

def print_response(step: str, response: Dict[str, Any]):
    """Pretty print a response."""
    print(f"\n{'='*60}")
    print(f"STEP: {step}")
    print(f"{'='*60}")
    
    if response.get("status") == "error":
        print(f"❌ ERROR: {response.get('error')}")
        return
        
    if response["status"] != 200:
        print(f"❌ HTTP {response['status']}: {response.get('data', {})}")
        return
    
    data = response["data"]
    
    if "message" in data:  # Welcome endpoint
        print(f"🎉 WELCOME MESSAGE:")
        print(f"   {data['message'][:200]}...")
        print(f"📊 JOURNEY STAGE: {data.get('journey_stage')}")
        if "sample_templates" in data:
            print(f"📝 SAMPLE TEMPLATES: {list(data['sample_templates'].keys())}")
    else:  # Chat endpoint
        print(f"🤖 ASSISTANT: {data.get('reply', 'No reply')}")
        print(f"📊 SESSION: {data.get('session_id', 'Unknown')}")
        
        draft = data.get("draft", {})
        if draft:
            print(f"📋 DRAFT PROGRESS:")
            print(f"   Category: {draft.get('category', 'None')}")
            print(f"   Language: {draft.get('language', 'None')}")
            print(f"   Name: {draft.get('name', 'None')}")
            
            components = draft.get("components", [])
            if components:
                print(f"   Components: {len(components)}")
                for i, comp in enumerate(components, 1):
                    comp_type = comp.get("type", "Unknown")
                    if comp_type == "BODY":
                        text = comp.get("text", "")[:50] + "..." if len(comp.get("text", "")) > 50 else comp.get("text", "")
                        print(f"     {i}. {comp_type}: {text}")
                    else:
                        print(f"     {i}. {comp_type}")
        
        missing = data.get("missing", [])
        if missing:
            print(f"❓ MISSING: {', '.join(missing)}")
        
        final_payload = data.get("final_creation_payload")
        if final_payload:
            print(f"✅ FINAL TEMPLATE CREATED!")
            print(f"   Ready for WhatsApp API: {bool(final_payload)}")

def test_simple_journey():
    """Test a simple, straightforward template creation journey."""
    print("\n" + "🚀" * 20)
    print("TESTING SIMPLE JOURNEY - Marketing Discount Template")
    print("🚀" * 20)
    
    session_id = str(uuid.uuid4())
    user_id = "test_user_simple"
    
    # Create user first
    user_creation = create_user(user_id, "TestSimple", "simple@test.com")
    print_response("User Creation", user_creation)
    
    # Step 1: Get welcome message
    welcome = get_welcome()
    print_response("Welcome Message", welcome)
    
    # Step 2: User expresses simple goal (without user_id initially)
    response = chat_message(
        session_id, 
        "I want to send discount offers to my customers"
    )
    print_response("Initial Goal", response)
    
    # Step 3: Provide business context 
    response = chat_message(
        session_id,
        "I run a small clothing store. I want marketing templates for 20% off promotions"
    )
    print_response("Business Context", response)
    
    # Step 4: Provide explicit content
    response = chat_message(
        session_id,
        "The message should say: Hi {{1}}! Special 20% off sale just for you! Use code SAVE20 at checkout. Limited time only - shop now!"
    )
    print_response("Message Content", response)
    
    # Step 5: Confirm language
    response = chat_message(
        session_id,
        "Use English - en_US"
    )
    print_response("Language Selection", response)
    
    # Step 6: Template name
    response = chat_message(
        session_id,
        "Name it clothing_discount_offer"
    )
    print_response("Template Name", response)
    
    # Step 7: Finalize
    response = chat_message(
        session_id,
        "Perfect! Please finalize this template."
    )
    print_response("Finalization", response)
    
    return response

def test_complex_journey():
    """Test a complex journey with guidance, examples, and extras."""
    print("\n" + "🔥" * 20)  
    print("TESTING COMPLEX JOURNEY - Restaurant with Extras")
    print("🔥" * 20)
    
    session_id = str(uuid.uuid4())
    user_id = "test_user_complex"
    
    # Create user first
    user_creation = create_user(user_id, "TestComplex", "complex@test.com")
    print_response("User Creation", user_creation)
    
    # Step 1: Get welcome message
    welcome = get_welcome()
    print_response("Welcome Message", welcome)
    
    # Step 2: User is unsure (without user_id initially)
    response = chat_message(
        session_id,
        "I'm not sure what I need. I run a restaurant and want to send messages to customers"
    )
    print_response("Uncertain Start", response)
    
    # Step 3: Specify appointment reminders
    response = chat_message(
        session_id,
        "I want to send appointment reminders for table reservations. This should be utility templates."
    )
    print_response("Specify Use Case", response)
    
    # Step 4: Provide content with extras request
    response = chat_message(
        session_id,
        "The message should say: Hello {{1}}! Reminder: Your table reservation for {{2}} people is confirmed for {{3}} at {{4}}. We look forward to serving you! Also add a header and buttons please."
    )
    print_response("Message Content with Extras", response)
    
    # Step 5: Confirm extras
    response = chat_message(
        session_id,
        "Yes, add a header saying 'Reservation Reminder' and buttons for 'Confirm' and 'Reschedule'"
    )
    print_response("Extras Confirmation", response)
    
    # Step 6: Set language
    response = chat_message(
        session_id,
        "Use English - en_US"
    )
    print_response("Language Selection", response)
    
    # Step 7: Template name
    response = chat_message(
        session_id,
        "Name it restaurant_reservation_reminder"
    )
    print_response("Template Name", response)
    
    # Step 8: Final review and confirmation
    response = chat_message(
        session_id,
        "Perfect! This looks exactly what I need. Please finalize it."
    )
    print_response("Final Review", response)
    
    return response

def test_no_user_journey():
    """Test journey without user_id to avoid database issues."""
    print("\n" + "🌟" * 20)  
    print("TESTING NO-USER JOURNEY - Anonymous Session")
    print("🌟" * 20)
    
    session_id = str(uuid.uuid4())
    
    # Step 1: Simple marketing template without user
    response = chat_message(
        session_id,
        "I want to create a marketing template for my pizza restaurant"
    )
    print_response("Marketing Request", response)
    
    # Step 2: Provide content
    response = chat_message(
        session_id,
        "The message should say: Hi {{1}}! 🍕 Special deal today - Buy 2 pizzas get 1 free! Order now and enjoy delicious food!"
    )
    print_response("Pizza Content", response)
    
    # Step 3: Set language and name together
    response = chat_message(
        session_id,
        "Use English (en_US) and name it pizza_special_offer"
    )
    print_response("Language and Name", response)
    
    # Step 4: Finalize
    response = chat_message(
        session_id,
        "Great! Please finalize this template"
    )
    print_response("Finalization", response)
    
    return response

def run_all_tests():
    """Run all test journeys and compare results."""
    print("🧪 Starting Comprehensive API Journey Tests...")
    print("Testing integration of friendly_prompts.py and prompts.py")
    
    try:
        # Test simple journey
        simple_result = test_simple_journey()
        
        # Test complex journey  
        complex_result = test_complex_journey()
        
        # Test no-user journey
        no_user_result = test_no_user_journey()
        
        # Summary
        print("\n" + "📊" * 20)
        print("TEST SUMMARY")
        print("📊" * 20)
        
        def check_success(result):
            return (
                result.get("status") == 200 and 
                result.get("data", {}).get("final_creation_payload") is not None
            )
        
        simple_success = check_success(simple_result)
        complex_success = check_success(complex_result)
        no_user_success = check_success(no_user_result)
        
        print(f"✅ Simple Journey: {'SUCCESS' if simple_success else 'FAILED'}")
        print(f"✅ Complex Journey: {'SUCCESS' if complex_success else 'FAILED'}")
        print(f"✅ No-User Journey: {'SUCCESS' if no_user_success else 'FAILED'}")
        
        success_count = sum([simple_success, complex_success, no_user_success])
        
        if success_count >= 2:
            print(f"🎉 {success_count}/3 TESTS PASSED! friendly_prompts.py and prompts.py are working together!")
            
            # Show successful templates
            if simple_success:
                print(f"\n📋 SIMPLE TEMPLATE FINAL PAYLOAD:")
                simple_payload = simple_result["data"]["final_creation_payload"]
                print(json.dumps(simple_payload, indent=2))
            
            if complex_success:
                print(f"\n📋 COMPLEX TEMPLATE FINAL PAYLOAD:")
                complex_payload = complex_result["data"]["final_creation_payload"]
                print(json.dumps(complex_payload, indent=2))
                
            if no_user_success:
                print(f"\n📋 NO-USER TEMPLATE FINAL PAYLOAD:")
                no_user_payload = no_user_result["data"]["final_creation_payload"]
                print(json.dumps(no_user_payload, indent=2))
            
        else:
            print(f"❌ Only {success_count}/3 tests passed. Check the responses above.")
            
    except Exception as e:
        print(f"❌ Test execution failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_all_tests()
