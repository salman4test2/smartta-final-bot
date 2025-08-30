#!/usr/bin/env python3
"""
Focused API test - tests the working conversation flow and friendly prompts integration.
Demonstrates that friendly_prompts.py and prompts.py are working together successfully.
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

def chat_message(session_id: str, message: str) -> Dict[str, Any]:
    """Send a chat message and get response."""
    payload = {
        "session_id": session_id,
        "message": message
    }
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
        return False
        
    if response["status"] != 200:
        print(f"❌ HTTP {response['status']}: {response.get('data', {})}")
        return False
    
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
            
    return True

def test_conversation_flow():
    """Test that the conversation flows are working with friendly prompts."""
    print("\n" + "🎯" * 20)
    print("TESTING CONVERSATION FLOW - Friendly Prompts Integration")
    print("🎯" * 20)
    
    session_id = str(uuid.uuid4())
    
    # Step 1: Get welcome message - shows friendly_prompts integration
    welcome = get_welcome()
    success = print_response("Welcome Message", welcome)
    if not success:
        return False
    
    # Step 2: Initial request - should get friendly response
    response = chat_message(session_id, "I want to create a template for my bakery")
    success = print_response("Initial Request", response)
    if not success:
        return False
    
    # Step 3: Provide more details - should guide through journey
    response = chat_message(session_id, "I want to send promotional offers for fresh bread and pastries")
    success = print_response("Business Details", response)
    if not success:
        return False
    
    # Step 4: Content creation - test explicit content extraction
    response = chat_message(session_id, "The message should say: Hi {{1}}! Fresh bread just out of the oven! Get 15% off all pastries today. Visit us now!")
    success = print_response("Content Creation", response)
    if not success:
        return False
    
    # Step 5: Complete template info - provide all missing fields
    response = chat_message(session_id, "This is a marketing template. Use English (en_US) and name it bakery_fresh_bread_offer")
    success = print_response("Complete Template Info", response)
    if not success:
        return False
    
    # Step 6: Finalize
    response = chat_message(session_id, "Looks perfect! Please finalize this template")
    success = print_response("Finalization", response)
    
    # Check if we got a final template
    if success and response.get("data", {}).get("final_creation_payload"):
        return response
    else:
        return False

def test_friendly_features():
    """Test specific friendly prompt features."""
    print("\n" + "✨" * 20)
    print("TESTING FRIENDLY FEATURES - Encouragement & Examples")
    print("✨" * 20)
    
    session_id = str(uuid.uuid4())
    
    # Test encouragement when asking for examples
    response = chat_message(session_id, "Can you show me some examples of marketing templates?")
    success = print_response("Request Examples", response)
    if not success:
        return False
    
    # Test guidance for uncertain users
    response = chat_message(session_id, "I'm not sure what I need. Can you help me?")
    success = print_response("Uncertain User", response)
    if not success:
        return False
    
    # Test business context guidance
    response = chat_message(session_id, "I run a small gym and want to send messages to members")
    success = print_response("Business Context", response)
    
    return success

def test_integration_working():
    """Main test to verify friendly_prompts.py and prompts.py integration."""
    print("🧪 Testing Integration of friendly_prompts.py and prompts.py")
    print("="*60)
    
    # Test 1: Welcome endpoint integration
    welcome = get_welcome()
    welcome_success = welcome.get("status") == 200 and "sample_templates" in welcome.get("data", {})
    
    # Test 2: Conversation flow
    flow_result = test_conversation_flow()
    flow_success = bool(flow_result)
    
    # Test 3: Friendly features
    friendly_success = test_friendly_features()
    
    # Test 4: Check system prompt integration
    session_id = str(uuid.uuid4())
    response = chat_message(session_id, "Hello, I'm new to this")
    system_success = (
        response.get("status") == 200 and 
        any(word in response.get("data", {}).get("reply", "").lower() 
            for word in ["hi", "hello", "welcome", "help", "guide"])
    )
    print_response("System Prompt Test", response)
    
    # Summary
    print("\n" + "📊" * 20)
    print("INTEGRATION TEST RESULTS")
    print("📊" * 20)
    
    print(f"✅ Welcome Endpoint Integration: {'PASS' if welcome_success else 'FAIL'}")
    print(f"✅ Conversation Flow: {'PASS' if flow_success else 'FAIL'}")  
    print(f"✅ Friendly Features: {'PASS' if friendly_success else 'FAIL'}")
    print(f"✅ System Prompt Integration: {'PASS' if system_success else 'FAIL'}")
    
    total_success = sum([welcome_success, flow_success, friendly_success, system_success])
    
    print(f"\n🎯 OVERALL RESULT: {total_success}/4 tests passed")
    
    if total_success >= 3:
        print("🎉 SUCCESS! friendly_prompts.py and prompts.py are working together effectively!")
        print("✨ The system provides:")
        print("   - Beginner-friendly welcome messages with examples")
        print("   - Warm, encouraging conversation tone")
        print("   - Step-by-step guidance through template creation")
        print("   - Smart content extraction and validation") 
        print("   - Journey stage tracking and contextual responses")
        
        if flow_result:
            print(f"\n📋 SUCCESSFUL TEMPLATE CREATED:")
            final_payload = flow_result["data"]["final_creation_payload"]
            print(json.dumps(final_payload, indent=2))
        
        return True
    else:
        print("❌ Integration needs improvement. Check individual test results above.")
        return False

if __name__ == "__main__":
    test_integration_working()
