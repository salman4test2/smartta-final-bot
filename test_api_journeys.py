#!/usr/bin/env python3
"""
Test API calls for both simple and complex template creation journeys.
Tests the integration of friendly_prompts.py and prompts.py working together.
"""

import asyncio
import aiohttp
import json
import uuid
from typing import Dict, Any, List

BASE_URL = "http://localhost:8001"

class TemplateJourneyTester:
    def __init__(self):
        self.session = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def call_api(self, endpoint: str, method: str = "GET", data: Dict = None) -> Dict[str, Any]:
        """Make an API call to the server."""
        url = f"{BASE_URL}{endpoint}"
        
        try:
            if method == "GET":
                async with self.session.get(url) as response:
                    result = await response.json()
                    return {"status": response.status, "data": result}
            elif method == "POST":
                async with self.session.post(url, json=data) as response:
                    result = await response.json()
                    return {"status": response.status, "data": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def chat_message(self, session_id: str, message: str, user_id: str = None) -> Dict[str, Any]:
        """Send a chat message and get response."""
        payload = {
            "session_id": session_id,
            "message": message
        }
        if user_id:
            payload["user_id"] = user_id
            
        return await self.call_api("/chat", "POST", payload)
    
    async def get_welcome(self) -> Dict[str, Any]:
        """Get the welcome message."""
        return await self.call_api("/welcome")
    
    def print_response(self, step: str, response: Dict[str, Any]):
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

async def test_simple_journey():
    """Test a simple, straightforward template creation journey."""
    print("\n" + "🚀" * 20)
    print("TESTING SIMPLE JOURNEY - Marketing Discount Template")
    print("🚀" * 20)
    
    session_id = str(uuid.uuid4())
    user_id = "test_user_simple"
    
    async with TemplateJourneyTester() as tester:
        # Step 1: Get welcome message
        welcome = await tester.get_welcome()
        tester.print_response("Welcome Message", welcome)
        
        # Step 2: User expresses simple goal
        response = await tester.chat_message(
            session_id, 
            "I want to send discount offers to my customers",
            user_id
        )
        tester.print_response("Initial Goal", response)
        
        # Step 3: Provide business context
        response = await tester.chat_message(
            session_id,
            "I run a small clothing store and want to send 20% off promotions to my customers"
        )
        tester.print_response("Business Context", response)
        
        # Step 4: Confirm category suggestion
        response = await tester.chat_message(
            session_id,
            "Yes, marketing sounds perfect for my discount offers"
        )
        tester.print_response("Category Confirmation", response)
        
        # Step 5: Provide explicit content
        response = await tester.chat_message(
            session_id,
            "The message should say: Hi {{1}}! Special 20% off sale just for you! Use code SAVE20 at checkout. Limited time only - shop now!"
        )
        tester.print_response("Message Content", response)
        
        # Step 6: Confirm language
        response = await tester.chat_message(
            session_id,
            "Use English please - en_US"
        )
        tester.print_response("Language Selection", response)
        
        # Step 7: Template name
        response = await tester.chat_message(
            session_id,
            "Name it clothing_store_discount_v1"
        )
        tester.print_response("Template Name", response)
        
        # Step 8: Skip extras and finalize
        response = await tester.chat_message(
            session_id,
            "Looks good as is, please finalize"
        )
        tester.print_response("Finalization", response)
        
        return response

async def test_complex_journey():
    """Test a complex journey with guidance, examples, and extras."""
    print("\n" + "🔥" * 20)
    print("TESTING COMPLEX JOURNEY - Restaurant Appointment with Extras")
    print("🔥" * 20)
    
    session_id = str(uuid.uuid4())
    user_id = "test_user_complex"
    
    async with TemplateJourneyTester() as tester:
        # Step 1: Get welcome message
        welcome = await tester.get_welcome()
        tester.print_response("Welcome Message", welcome)
        
        # Step 2: User is unsure
        response = await tester.chat_message(
            session_id,
            "I'm not sure what I need. I run a restaurant and want to send messages to customers",
            user_id
        )
        tester.print_response("Uncertain Start", response)
        
        # Step 3: Ask for examples
        response = await tester.chat_message(
            session_id,
            "Can you show me some examples of what I can create?"
        )
        tester.print_response("Request Examples", response)
        
        # Step 4: Specify appointment reminders
        response = await tester.chat_message(
            session_id,
            "I want to send appointment reminders for table reservations"
        )
        tester.print_response("Specify Use Case", response)
        
        # Step 5: Confirm utility category
        response = await tester.chat_message(
            session_id,
            "Yes, utility for notifications sounds right"
        )
        tester.print_response("Category Confirmation", response)
        
        # Step 6: Ask AI to write content
        response = await tester.chat_message(
            session_id,
            "Can you write the message for me? I want it professional but friendly"
        )
        tester.print_response("AI Content Request", response)
        
        # Step 7: Approve the content
        response = await tester.chat_message(
            session_id,
            "That looks perfect! Please use that message"
        )
        tester.print_response("Content Approval", response)
        
        # Step 8: Request extras
        response = await tester.chat_message(
            session_id,
            "I'd like to add a header and buttons to make it look more professional"
        )
        tester.print_response("Request Extras", response)
        
        # Step 9: Confirm header
        response = await tester.chat_message(
            session_id,
            "Yes, add a nice header about the reservation reminder"
        )
        tester.print_response("Header Addition", response)
        
        # Step 10: Confirm buttons
        response = await tester.chat_message(
            session_id,
            "Yes, add quick reply buttons for confirm and reschedule"
        )
        tester.print_response("Buttons Addition", response)
        
        # Step 11: Set language
        response = await tester.chat_message(
            session_id,
            "English is fine - en_US"
        )
        tester.print_response("Language Selection", response)
        
        # Step 12: Template name
        response = await tester.chat_message(
            session_id,
            "Name it restaurant_reservation_reminder"
        )
        tester.print_response("Template Name", response)
        
        # Step 13: Final review and confirmation
        response = await tester.chat_message(
            session_id,
            "Perfect! This looks exactly what I need. Please finalize it."
        )
        tester.print_response("Final Review", response)
        
        return response

async def run_both_tests():
    """Run both test journeys and compare results."""
    print("🧪 Starting API Journey Tests...")
    print("Testing integration of friendly_prompts.py and prompts.py")
    
    try:
        # Test simple journey
        simple_result = await test_simple_journey()
        
        # Test complex journey  
        complex_result = await test_complex_journey()
        
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
    asyncio.run(run_both_tests())
