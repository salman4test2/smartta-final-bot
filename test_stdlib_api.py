#!/usr/bin/env python3
"""
API test using only standard library (urllib).
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
    
    # Step 1: Get welcome message
    welcome = get_welcome()
    print_response("Welcome Message", welcome)
    
    # Step 2: User expresses simple goal
    response = chat_message(
        session_id, 
        "I want to send discount offers to my customers",
        user_id
    )
    print_response("Initial Goal", response)
    
    # Step 3: Provide business context and category
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
    
    # Step 5: Confirm language and name
    response = chat_message(
        session_id,
        "Use English (en_US) and name it clothing_discount_offer"
    )
    print_response("Language and Name", response)
    
    # Step 6: Finalize
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
    
    # Step 1: Get welcome message
    welcome = get_welcome()
    print_response("Welcome Message", welcome)
    
    # Step 2: User is unsure
    response = chat_message(
        session_id,
        "I'm not sure what I need. I run a restaurant and want to send messages to customers",
        user_id
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
    
    # Step 6: Set language and name
    response = chat_message(
        session_id,
        "Use English (en_US) and name it restaurant_reservation_reminder"
    )
    print_response("Language and Name", response)
    
    # Step 7: Final review and confirmation
    response = chat_message(
        session_id,
        "Perfect! This looks exactly what I need. Please finalize it."
    )
    print_response("Final Review", response)
    
    return response

def run_both_tests():
    """Run both test journeys and compare results."""
    print("🧪 Starting API Journey Tests...")
    print("Testing integration of friendly_prompts.py and prompts.py")
    
    try:
        # Test simple journey
        simple_result = test_simple_journey()
        
        # Test complex journey  
        complex_result = test_complex_journey()
        
        # Summary
        print("\n" + "📊" * 20)
        print("TEST SUMMARY")
        print("📊" * 20)
        
        simple_success = (
            simple_result.get("status") == 200 and 
            simple_result.get("data", {}).get("final_creation_payload") is not None
        )
        
        complex_success = (
            complex_result.get("status") == 200 and 
            complex_result.get("data", {}).get("final_creation_payload") is not None
        )
        
        print(f"✅ Simple Journey: {'SUCCESS' if simple_success else 'FAILED'}")
        print(f"✅ Complex Journey: {'SUCCESS' if complex_success else 'FAILED'}")
        
        if simple_success and complex_success:
            print(f"🎉 ALL TESTS PASSED! Both friendly_prompts.py and prompts.py are working together perfectly!")
            
            # Show final templates
            print(f"\n📋 SIMPLE TEMPLATE FINAL PAYLOAD:")
            simple_payload = simple_result["data"]["final_creation_payload"]
            print(json.dumps(simple_payload, indent=2))
            
            print(f"\n📋 COMPLEX TEMPLATE FINAL PAYLOAD:")
            complex_payload = complex_result["data"]["final_creation_payload"]
            print(json.dumps(complex_payload, indent=2))
            
        else:
            print(f"❌ Some tests failed. Check the responses above.")
            
    except Exception as e:
        print(f"❌ Test execution failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_both_tests()
