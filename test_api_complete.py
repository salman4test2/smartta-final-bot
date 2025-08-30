#!/usr/bin/env python3
"""
Complete API test for WhatsApp Template Builder
Tests both simple and complex journeys end-to-end
"""

import requests
import json
import time
import sys
from typing import Dict, Any

BASE_URL = "http://localhost:8000"

def test_health():
    """Test if server is running"""
    try:
        response = requests.get(f"{BASE_URL}/health")
        return response.status_code == 200
    except:
        return False

def create_user(email: str, password: str) -> str:
    """Create a test user and return user_id"""
    response = requests.post(f"{BASE_URL}/users", json={
        "email": email,
        "password": password
    })
    if response.status_code == 201:
        return response.json()["user_id"]
    elif response.status_code == 400 and "already exists" in response.text:
        # User exists, try to login
        login_response = requests.post(f"{BASE_URL}/users/login", json={
            "email": email,
            "password": password
        })
        if login_response.status_code == 200:
            return login_response.json()["user_id"]
    raise Exception(f"Failed to create/login user: {response.text}")

def chat_message(user_id: str, session_id: str, message: str) -> Dict[str, Any]:
    """Send a chat message and return response"""
    response = requests.post(f"{BASE_URL}/chat", json={
        "user_id": user_id,
        "session_id": session_id,
        "message": message
    })
    if response.status_code != 200:
        raise Exception(f"Chat failed: {response.status_code} - {response.text}")
    return response.json()

def get_welcome() -> Dict[str, Any]:
    """Get welcome message"""
    response = requests.get(f"{BASE_URL}/welcome")
    if response.status_code != 200:
        raise Exception(f"Welcome failed: {response.status_code} - {response.text}")
    return response.json()

def print_separator(title: str):
    print(f"\n{'='*60}")
    print(f" {title}")
    print('='*60)

def print_chat_turn(turn: int, user_msg: str, bot_reply: str, draft: Dict = None):
    print(f"\n--- Turn {turn} ---")
    print(f"👤 User: {user_msg}")
    print(f"🤖 Bot:  {bot_reply}")
    if draft:
        print(f"📝 Draft: {json.dumps(draft, indent=2)}")

def test_simple_journey():
    """Test a simple, straightforward template creation journey"""
    print_separator("SIMPLE JOURNEY TEST")
    
    # Create user
    user_id = create_user("simple_test@example.com", "password123")
    session_id = f"simple_test_{int(time.time())}"
    
    print(f"Created user: {user_id}")
    print(f"Session: {session_id}")
    
    # Test welcome endpoint
    welcome = get_welcome()
    print(f"Welcome message: {welcome['message'][:100]}...")
    
    turn = 1
    
    # Turn 1: Start with clear intent
    response = chat_message(user_id, session_id, "I want to send discount offers to my clothing store customers")
    print_chat_turn(turn, "I want to send discount offers to my clothing store customers", 
                   response["reply"], response.get("draft"))
    turn += 1
    
    # Turn 2: Provide language
    response = chat_message(user_id, session_id, "Use English please")
    print_chat_turn(turn, "Use English please", response["reply"], response.get("draft"))
    turn += 1
    
    # Turn 3: Provide template name
    response = chat_message(user_id, session_id, "Call it clothing_store_discount")
    print_chat_turn(turn, "Call it clothing_store_discount", response["reply"], response.get("draft"))
    turn += 1
    
    # Turn 4: Provide message content
    response = chat_message(user_id, session_id, 
                           "The message should say: Hi {{1}}! 🎉 Get 30% off all items this weekend! Use code SAVE30. Shop now at our store!")
    print_chat_turn(turn, "The message should say: Hi {{1}}! 🎉 Get 30% off all items this weekend! Use code SAVE30. Shop now at our store!", 
                   response["reply"], response.get("draft"))
    turn += 1
    
    # Turn 5: Finalize
    response = chat_message(user_id, session_id, "That looks perfect, finalize it")
    print_chat_turn(turn, "That looks perfect, finalize it", response["reply"], response.get("draft"))
    
    # Check if we got a final payload
    final_payload = response.get("final_creation_payload")
    if final_payload:
        print(f"\n✅ SIMPLE JOURNEY SUCCESS!")
        print(f"Final Template: {json.dumps(final_payload, indent=2)}")
        return True
    else:
        print(f"\n❌ SIMPLE JOURNEY FAILED - No final payload")
        return False

def test_complex_journey():
    """Test a complex journey with extras, changes, and multiple rounds"""
    print_separator("COMPLEX JOURNEY TEST")
    
    # Create user
    user_id = create_user("complex_test@example.com", "password123")
    session_id = f"complex_test_{int(time.time())}"
    
    print(f"Created user: {user_id}")
    print(f"Session: {session_id}")
    
    turn = 1
    
    # Turn 1: Start vague, let bot guide
    response = chat_message(user_id, session_id, "I need to create a template for my restaurant")
    print_chat_turn(turn, "I need to create a template for my restaurant", 
                   response["reply"], response.get("draft"))
    turn += 1
    
    # Turn 2: Clarify it's for notifications
    response = chat_message(user_id, session_id, "It's for confirming orders and delivery updates")
    print_chat_turn(turn, "It's for confirming orders and delivery updates", 
                   response["reply"], response.get("draft"))
    turn += 1
    
    # Turn 3: Specify language
    response = chat_message(user_id, session_id, "Use Hindi language - hi_IN")
    print_chat_turn(turn, "Use Hindi language - hi_IN", response["reply"], response.get("draft"))
    turn += 1
    
    # Turn 4: Let bot suggest name
    response = chat_message(user_id, session_id, "You choose a good name for this template")
    print_chat_turn(turn, "You choose a good name for this template", response["reply"], response.get("draft"))
    turn += 1
    
    # Turn 5: Provide message content with placeholders
    response = chat_message(user_id, session_id, 
                           "The message is: नमस्ते {{1}}! आपका ऑर्डर #{{2}} कन्फर्म हो गया है। डिलीवरी का समय: {{3}}। धन्यवाद!")
    print_chat_turn(turn, "The message is: नमस्ते {{1}}! आपका ऑर्डर #{{2}} कन्फर्म हो गया है। डिलीवरी का समय: {{3}}। धन्यवाद!", 
                   response["reply"], response.get("draft"))
    turn += 1
    
    # Turn 6: Ask for header
    response = chat_message(user_id, session_id, "Add a header saying 'Order Confirmed'")
    print_chat_turn(turn, "Add a header saying 'Order Confirmed'", response["reply"], response.get("draft"))
    turn += 1
    
    # Turn 7: Ask for buttons
    response = chat_message(user_id, session_id, "Also add buttons for 'Track Order' and 'Call Restaurant'")
    print_chat_turn(turn, "Also add buttons for 'Track Order' and 'Call Restaurant'", response["reply"], response.get("draft"))
    turn += 1
    
    # Turn 8: Add footer
    response = chat_message(user_id, session_id, "Add a footer with 'Thanks for ordering!'")
    print_chat_turn(turn, "Add a footer with 'Thanks for ordering!'", response["reply"], response.get("draft"))
    turn += 1
    
    # Turn 9: Make a change
    response = chat_message(user_id, session_id, "Actually change the header to 'आपका ऑर्डर तैयार है'")
    print_chat_turn(turn, "Actually change the header to 'आपका ऑर्डर तैयार है'", response["reply"], response.get("draft"))
    turn += 1
    
    # Turn 10: Finalize
    response = chat_message(user_id, session_id, "Perfect! This looks great. Finalize the template now.")
    print_chat_turn(turn, "Perfect! This looks great. Finalize the template now.", response["reply"], response.get("draft"))
    
    # Check if we got a final payload
    final_payload = response.get("final_creation_payload")
    if final_payload:
        print(f"\n✅ COMPLEX JOURNEY SUCCESS!")
        print(f"Final Template: {json.dumps(final_payload, indent=2)}")
        
        # Validate the complex template has all expected components
        components = final_payload.get("components", [])
        has_body = any(c.get("type") == "BODY" for c in components)
        has_header = any(c.get("type") == "HEADER" for c in components) 
        has_footer = any(c.get("type") == "FOOTER" for c in components)
        has_buttons = any(c.get("type") == "BUTTONS" for c in components)
        
        print(f"Components validation:")
        print(f"  ✅ Body: {has_body}")
        print(f"  ✅ Header: {has_header}")
        print(f"  ✅ Footer: {has_footer}")
        print(f"  ✅ Buttons: {has_buttons}")
        
        return has_body and has_header and has_footer and has_buttons
    else:
        print(f"\n❌ COMPLEX JOURNEY FAILED - No final payload")
        print(f"Missing: {response.get('missing', [])}")
        return False

def test_friendly_prompts_integration():
    """Test that friendly prompts are working in the conversation"""
    print_separator("FRIENDLY PROMPTS INTEGRATION TEST")
    
    user_id = create_user("friendly_test@example.com", "password123")
    session_id = f"friendly_test_{int(time.time())}"
    
    # Test a beginner user who needs guidance
    response = chat_message(user_id, session_id, "I don't know anything about templates, help me")
    print(f"👤 Beginner user: I don't know anything about templates, help me")
    print(f"🤖 Bot response: {response['reply']}")
    
    # Check if response is friendly and helpful
    reply_lower = response['reply'].lower()
    is_friendly = any(word in reply_lower for word in ['happy', 'help', 'easy', 'simple', 'guide', 'walk'])
    
    print(f"✅ Friendly response detected: {is_friendly}")
    return is_friendly

def main():
    """Run all tests"""
    print("🚀 Starting WhatsApp Template Builder API Tests")
    
    # Check if server is running
    if not test_health():
        print("❌ Server is not running! Please start the server with: uvicorn app.main:app --reload")
        sys.exit(1)
    
    print("✅ Server is running")
    
    results = {}
    
    try:
        # Test friendly prompts integration
        results['friendly_prompts'] = test_friendly_prompts_integration()
        
        # Test simple journey
        results['simple_journey'] = test_simple_journey()
        
        # Test complex journey  
        results['complex_journey'] = test_complex_journey()
        
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        return False
    
    # Print final results
    print_separator("FINAL RESULTS")
    
    all_passed = True
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print(f"\n🎉 ALL TESTS PASSED! The template builder is working correctly.")
    else:
        print(f"\n💥 SOME TESTS FAILED! Please check the issues above.")
    
    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
