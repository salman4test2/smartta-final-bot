#!/usr/bin/env python3
"""
Real-world chat flow testing script.
Tests the actual conversation flow with layman language and identifies issues.
"""

import requests
import json
import time

BASE_URL = "http://localhost:8003"

def make_chat_request(message, session_id=None):
    """Make a chat request and return the response."""
    data = {"message": message}
    if session_id:
        data["session_id"] = session_id
    
    try:
        response = requests.post(f"{BASE_URL}/chat", json=data)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"❌ Error making request: {e}")
        return None

def print_response(step, user_msg, response):
    """Print formatted response for analysis."""
    print(f"\n{'='*60}")
    print(f"STEP {step}: USER SAYS")
    print(f"{'='*60}")
    print(f"'{user_msg}'")
    print(f"\n{'='*60}")
    print(f"ASSISTANT RESPONDS")
    print(f"{'='*60}")
    
    if response:
        print(f"Reply: {response.get('reply', 'No reply')}")
        print(f"Session ID: {response.get('session_id', 'None')}")
        
        draft = response.get('draft', {})
        if draft:
            print(f"\nDraft Status:")
            print(f"  Category: {draft.get('category', 'None')}")
            print(f"  Name: {draft.get('name', 'None')}")
            print(f"  Language: {draft.get('language', 'None')}")
            
            components = draft.get('components', [])
            print(f"  Components: {len(components)}")
            for comp in components:
                comp_type = comp.get('type', 'Unknown')
                if comp_type == 'BODY':
                    print(f"    - BODY: {comp.get('text', '')[:50]}...")
                elif comp_type == 'HEADER':
                    print(f"    - HEADER ({comp.get('format', 'TEXT')}): {comp.get('text', '')}")
                elif comp_type == 'BUTTONS':
                    buttons = comp.get('buttons', [])
                    print(f"    - BUTTONS ({len(buttons)}): {[b.get('text', '') for b in buttons]}")
                elif comp_type == 'FOOTER':
                    print(f"    - FOOTER: {comp.get('text', '')}")
        
        missing = response.get('missing', [])
        if missing:
            print(f"\nMissing: {missing}")
        
        final_payload = response.get('final_creation_payload')
        if final_payload:
            print(f"\n🎉 FINAL PAYLOAD CREATED!")
            print(f"Template: {final_payload.get('name', 'Unknown')}")
    else:
        print("❌ No response received")

def test_conversation_flow():
    """Test the exact conversation flow that gets stuck."""
    print("🚀 Testing Real-World Chat Flow (Sweets Business)")
    print("=" * 70)
    
    # Conversation steps from the user's example
    conversation = [
        ("Hi there! I want to create a WhatsApp template", None),
        ("Promotional offers or discounts", None),
        ("sweets, consumer and its a promotional message", None),
        ("yes", None),
        ("go ahead", None),
        ("upto u", None),
        ("any", None),
        ("no", None),
        ("english", None),
        ("create buttons please", None),  # This should trigger button issues
        ("add some quick replies", None),  # Test button generation
        ("make it more engaging", None),   # Test if it gets stuck
    ]
    
    session_id = None
    
    for i, (user_msg, expected_session) in enumerate(conversation, 1):
        print(f"\n⏱️  Step {i}: Making request...")
        response = make_chat_request(user_msg, session_id)
        
        if response:
            session_id = response.get('session_id', session_id)
            print_response(i, user_msg, response)
            
            # Check for specific issues
            reply = response.get('reply', '').lower()
            
            if "please tell me more about your template" in reply:
                print(f"\n🚨 ISSUE DETECTED: Generic 'tell me more' response!")
                print(f"   This suggests the chat flow is lost/confused")
            
            # Check button generation
            draft = response.get('draft', {})
            components = draft.get('components', [])
            buttons_comp = next((c for c in components if c.get('type') == 'BUTTONS'), None)
            
            if buttons_comp:
                buttons = buttons_comp.get('buttons', [])
                if len(buttons) > 1:
                    # Check for duplicate buttons
                    button_texts = [b.get('text', '') for b in buttons]
                    if len(set(button_texts)) < len(button_texts):
                        print(f"\n🚨 ISSUE DETECTED: Duplicate buttons!")
                        print(f"   Buttons: {button_texts}")
                    
                    # Check if buttons are context-relevant
                    if "Learn more" in button_texts and "Shop now" in button_texts:
                        print(f"\n⚠️  WARNING: Generic button labels detected")
                        print(f"   Expected sweet-shop specific buttons")
            
            time.sleep(0.5)  # Avoid overwhelming the server
        else:
            print(f"❌ Failed at step {i}")
            break
    
    return session_id

def test_button_generation_specifically():
    """Test button generation with different contexts."""
    print(f"\n\n🔘 Testing Button Generation Issues")
    print("=" * 70)
    
    test_cases = [
        "I sell sweets and want promotional buttons",
        "Create buttons for a sweet shop discount offer", 
        "Add quick replies for my candy store promotion",
        "Make buttons for dessert special offers"
    ]
    
    for i, message in enumerate(test_cases, 1):
        print(f"\n--- Button Test {i} ---")
        response = make_chat_request(message)
        
        if response:
            draft = response.get('draft', {})
            components = draft.get('components', [])
            buttons_comp = next((c for c in components if c.get('type') == 'BUTTONS'), None)
            
            if buttons_comp:
                buttons = buttons_comp.get('buttons', [])
                button_texts = [b.get('text', '') for b in buttons]
                print(f"Generated buttons: {button_texts}")
                
                # Check for context relevance
                sweet_keywords = ['sweet', 'candy', 'dessert', 'order', 'taste', 'shop']
                relevant = any(keyword in ' '.join(button_texts).lower() for keyword in sweet_keywords)
                
                if not relevant:
                    print(f"⚠️  Buttons not contextually relevant to sweets business")
            else:
                print(f"No buttons generated")
        
        time.sleep(0.5)

def test_interactive_mode_buttons():
    """Test button generation via interactive mode."""
    print(f"\n\n🎯 Testing Interactive Mode Button Generation")
    print("=" * 70)
    
    # Start interactive session
    start_data = {"intent": "I sell sweets and want to create promotional messages"}
    
    try:
        response = requests.post(f"{BASE_URL}/interactive/start", json=start_data)
        response.raise_for_status()
        result = response.json()
        
        session_id = result['session_id']
        print(f"✅ Started interactive session: {session_id}")
        
        # Set template name
        name_data = {
            "session_id": session_id,
            "field_id": "name", 
            "value": "sweet_shop_promo"
        }
        
        response = requests.put(f"{BASE_URL}/interactive/field", json=name_data)
        response.raise_for_status()
        print(f"✅ Set template name")
        
        # Generate buttons with different contexts
        button_contexts = [
            "Quick actions for sweet shop customers",
            "Options for candy store promotion", 
            "Dessert ordering buttons",
            "Sweet treats engagement options"
        ]
        
        for i, context in enumerate(button_contexts, 1):
            print(f"\n--- Interactive Button Test {i} ---")
            print(f"Context: {context}")
            
            gen_data = {
                "session_id": session_id,
                "field_id": "buttons",
                "hints": context,
                "brand": "Sweet Shop"
            }
            
            response = requests.post(f"{BASE_URL}/interactive/field/generate", json=gen_data)
            response.raise_for_status()
            result = response.json()
            
            # Extract buttons
            components = result.get('draft', {}).get('components', [])
            buttons_comp = next((c for c in components if c.get('type') == 'BUTTONS'), None)
            
            if buttons_comp:
                buttons = buttons_comp.get('buttons', [])
                button_texts = [b.get('text', '') for b in buttons]
                print(f"Generated: {button_texts}")
                
                # Check for duplicates
                if len(set(button_texts)) < len(button_texts):
                    print(f"🚨 DUPLICATE BUTTONS DETECTED!")
                
                # Check for generic vs contextual
                generic_buttons = ['Learn more', 'Shop now', 'Contact us', 'Get started']
                if all(btn in generic_buttons for btn in button_texts):
                    print(f"⚠️  All buttons are generic, not context-specific")
                else:
                    print(f"✅ Context-specific buttons generated")
            
            time.sleep(1)  # Space out API calls
            
    except Exception as e:
        print(f"❌ Interactive test failed: {e}")

def main():
    """Run all tests."""
    print("🧪 COMPREHENSIVE CHAT & BUTTON TESTING")
    print("=" * 70)
    print("Testing real-world conversation flows to identify issues...")
    
    # Test the actual conversation flow
    session_id = test_conversation_flow()
    
    # Test button generation specifically
    test_button_generation_specifically()
    
    # Test interactive mode
    test_interactive_mode_buttons()
    
    print(f"\n\n📊 SUMMARY")
    print("=" * 70)
    print("Key issues to look for:")
    print("1. 🔘 Duplicate buttons in generation")
    print("2. 🤖 Generic 'Please tell me more' responses")
    print("3. 🎯 Context-irrelevant button labels")
    print("4. 🔄 Chat flow getting stuck/looping")
    print("5. 🏷️  Non-contextual content generation")

if __name__ == "__main__":
    main()
