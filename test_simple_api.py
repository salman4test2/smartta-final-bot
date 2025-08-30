#!/usr/bin/env python3
"""
Simplified API test using requests library.
Tests both simple and complex template creation journeys.
"""

import requests
import json
import uuid
from typing import Dict, Any

BASE_URL = "http://localhost:8001"

def call_api(endpoint: str, method: str = "GET", data: Dict = None) -> Dict[str, Any]:
    """Make an API call to the server."""
    url = f"{BASE_URL}{endpoint}"
    
    try:
        if method == "GET":
            response = requests.get(url)
            return {"status": response.status_code, "data": response.json()}
        elif method == "POST":
            response = requests.post(url, json=data)
            return {"status": response.status_code, "data": response.json()}
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
    
    # Step 3: Provide business context
    response = chat_message(
        session_id,
        "I run a small clothing store and want to send 20% off promotions to my customers"
    )
    print_response("Business Context", response)
    
    # Step 4: Confirm category suggestion
    response = chat_message(
        session_id,
        "Yes, marketing sounds perfect for my discount offers"
    )
    print_response("Category Confirmation", response)
    
    # Step 5: Provide explicit content
    response = chat_message(
        session_id,
        "The message should say: Hi {{1}}! Special 20% off sale just for you! Use code SAVE20 at checkout. Limited time only - shop now!"
    )
    print_response("Message Content", response)
    
    # Step 6: Confirm language
    response = chat_message(
        session_id,
        "Use English please - en_US"
    )
    print_response("Language Selection", response)
    
    # Step 7: Template name
    response = chat_message(
        session_id,
        "Name it clothing_store_discount_v1"
    )
    print_response("Template Name", response)
    
    # Step 8: Skip extras and finalize
    response = chat_message(
        session_id,
        "Looks good as is, please finalize"
    )
    print_response("Finalization", response)
    
    return response

def test_complex_journey():
    """Test a complex journey with guidance, examples, and extras."""
    print("\n" + "🔥" * 20)
    print("TESTING COMPLEX JOURNEY - Restaurant Appointment with Extras")
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
    
    # Step 3: Ask for examples
    response = chat_message(
        session_id,
        "Can you show me some examples of what I can create?"
    )
    print_response("Request Examples", response)
    
    # Step 4: Specify appointment reminders
    response = chat_message(
        session_id,
        "I want to send appointment reminders for table reservations"
    )
    print_response("Specify Use Case", response)
    
    # Step 5: Confirm utility category
    response = chat_message(
        session_id,
        "Yes, utility for notifications sounds right"
    )
    print_response("Category Confirmation", response)
    
    # Step 6: Provide content
    response = chat_message(
        session_id,
        "The message should say: Hello {{1}}! Reminder: Your table reservation for {{2}} people is confirmed for {{3}} at {{4}}. We look forward to serving you!"
    )
    print_response("Message Content", response)
    
    # Step 7: Request extras
    response = chat_message(
        session_id,
        "I'd like to add a header and buttons to make it look more professional"
    )
    print_response("Request Extras", response)
    
    # Step 8: Confirm header
    response = chat_message(
        session_id,
        "Yes, add a nice header about the reservation reminder"
    )
    print_response("Header Addition", response)
    
    # Step 9: Confirm buttons
    response = chat_message(
        session_id,
        "Yes, add quick reply buttons for confirm and reschedule"
    )
    print_response("Buttons Addition", response)
    
    # Step 10: Set language
    response = chat_message(
        session_id,
        "English is fine - en_US"
    )
    print_response("Language Selection", response)
    
    # Step 11: Template name
    response = chat_message(
        session_id,
        "Name it restaurant_reservation_reminder"
    )
    print_response("Template Name", response)
    
    # Step 12: Final review and confirmation
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
