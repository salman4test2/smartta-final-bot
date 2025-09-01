#!/usr/bin/env python3
"""
Comprehensive test script for button generation and chat flow fixes.
Tests both the main chat endpoint and interactive mode.
"""

import requests
import json
import time
import random

BASE_URL = "http://localhost:8003"

def print_divider(title):
    print(f"\n{'='*20} {title} {'='*20}")

def print_result(test_name, success, details):
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"{status} {test_name}")
    if details:
        print(f"   {details}")

def test_chat_flow_fixes():
    """Test the main chat flow for getting stuck issues."""
    print_divider("CHAT FLOW FIXES TEST")
    
    # Test 1: Content extraction
    print("\n🧪 Test 1: Content Extraction")
    response = requests.post(f"{BASE_URL}/chat", json={
        "message": "I want to create a promotional message. The message should say: Special Diwali offer! Get 20% off on all sweets."
    })
    
    if response.status_code == 200:
        data = response.json()
        draft = data.get('draft', {})
        components = draft.get('components', [])
        body_found = any(c.get('type') == 'BODY' and 'Diwali offer' in (c.get('text', '')) for c in components)
        reply = data.get('reply', '')
        
        if body_found and not reply.lower().startswith('please tell me more'):
            print_result("Content extraction", True, "Message content captured correctly")
        else:
            print_result("Content extraction", False, f"Content not captured or generic reply: {reply}")
    else:
        print_result("Content extraction", False, f"HTTP {response.status_code}")
    
    # Test 2: Business context recognition
    print("\n🧪 Test 2: Business Context Recognition")
    response = requests.post(f"{BASE_URL}/chat", json={
        "message": "I run a sweet shop called Gulab Sweets and want to create promotional templates",
        "session_id": "test_business_" + str(random.randint(1000, 9999))
    })
    
    if response.status_code == 200:
        data = response.json()
        memory = data.get('memory', {})
        has_brand = 'brand_name' in str(memory).lower() or 'gulab' in str(memory).lower()
        reply = data.get('reply', '')
        
        if has_brand and 'sweet' in reply.lower():
            print_result("Business recognition", True, "Sweet shop context recognized")
        else:
            print_result("Business recognition", False, f"Business context not recognized: {reply}")
    else:
        print_result("Business recognition", False, f"HTTP {response.status_code}")

def test_button_generation_fixes():
    """Test the improved button generation."""
    print_divider("BUTTON GENERATION FIXES TEST")
    
    # Test 1: Interactive mode buttons
    print("\n🧪 Test 1: Interactive Mode Business-Aware Buttons")
    
    # Start session
    start_response = requests.post(f"{BASE_URL}/interactive/start", json={
        "intent": "I run a sweet shop and want promotional templates"
    })
    
    if start_response.status_code == 200:
        session_data = start_response.json()
        session_id = session_data['session_id']
        
        # Set name and category
        requests.put(f"{BASE_URL}/interactive/field", json={
            "session_id": session_id,
            "field_id": "name",
            "value": "sweet_shop_diwali"
        })
        
        requests.put(f"{BASE_URL}/interactive/field", json={
            "session_id": session_id,
            "field_id": "category", 
            "value": "MARKETING"
        })
        
        # Generate buttons with business context
        btn_response = requests.post(f"{BASE_URL}/interactive/field/generate", json={
            "session_id": session_id,
            "field_id": "buttons",
            "brand": "Sweet Paradise",
            "hints": "Sweet shop promotional buttons"
        })
        
        if btn_response.status_code == 200:
            btn_data = btn_response.json()
            draft = btn_data.get('draft', {})
            components = draft.get('components', [])
            
            # Find buttons component
            buttons_comp = next((c for c in components if c.get('type') == 'BUTTONS'), None)
            if buttons_comp:
                buttons = buttons_comp.get('buttons', [])
                button_texts = [b.get('text', '') for b in buttons]
                
                # Check for sweet-specific buttons
                sweet_relevant = any(
                    word in ' '.join(button_texts).lower() 
                    for word in ['sweet', 'order', 'menu', 'shop', 'store']
                )
                
                # Check for no duplicates
                no_duplicates = len(set(button_texts)) == len(button_texts)
                
                if sweet_relevant and no_duplicates:
                    print_result("Interactive buttons", True, f"Generated: {button_texts}")
                else:
                    print_result("Interactive buttons", False, f"Not contextual or duplicates: {button_texts}")
            else:
                print_result("Interactive buttons", False, "No buttons generated")
        else:
            print_result("Interactive buttons", False, f"HTTP {btn_response.status_code}")
    else:
        print_result("Interactive buttons", False, f"Start failed: {start_response.status_code}")
    
    # Test 2: Chat flow button generation
    print("\n🧪 Test 2: Chat Flow Smart Buttons")
    response = requests.post(f"{BASE_URL}/chat", json={
        "message": "Create buttons for my bakery's birthday cake promotions",
        "session_id": "test_buttons_" + str(random.randint(1000, 9999))
    })
    
    if response.status_code == 200:
        data = response.json()
        draft = data.get('draft', {})
        components = draft.get('components', [])
        buttons_comp = next((c for c in components if c.get('type') == 'BUTTONS'), None)
        
        if buttons_comp:
            buttons = buttons_comp.get('buttons', [])
            button_texts = [b.get('text', '') for b in buttons]
            
            # Check for bakery/cake relevance
            bakery_relevant = any(
                word in ' '.join(button_texts).lower()
                for word in ['order', 'book', 'cake', 'bakery', 'birthday', 'custom']
            )
            
            if bakery_relevant:
                print_result("Chat buttons", True, f"Generated: {button_texts}")
            else:
                print_result("Chat buttons", False, f"Not contextual: {button_texts}")
        else:
            print_result("Chat buttons", False, "No buttons generated")
    else:
        print_result("Chat buttons", False, f"HTTP {response.status_code}")

def test_conversation_scenarios():
    """Test specific conversation scenarios that were getting stuck."""
    print_divider("CONVERSATION SCENARIOS TEST")
    
    scenarios = [
        {
            "name": "Affirmation handling",
            "messages": [
                "I want to create a WhatsApp template",
                "yes",
                "go ahead"
            ],
            "check": lambda responses: not any("please tell me more" in r.get('reply', '').lower() for r in responses)
        },
        {
            "name": "Business + content flow",
            "messages": [
                "I run a sweet shop",
                "promotional message",
                "create buttons please"
            ],
            "check": lambda responses: any("button" in r.get('reply', '').lower() or 
                                         any(c.get('type') == 'BUTTONS' for c in r.get('draft', {}).get('components', []))
                                         for r in responses)
        },
        {
            "name": "Direct content provision",
            "messages": [
                "Create a template that says: Welcome to our store! Get 10% off today.",
                "add some buttons",
                "finalize it"
            ],
            "check": lambda responses: any(
                any(c.get('type') == 'BODY' and 'Welcome to our store' in (c.get('text', '')) 
                    for c in r.get('draft', {}).get('components', []))
                for r in responses
            )
        }
    ]
    
    for scenario in scenarios:
        print(f"\n🧪 Testing: {scenario['name']}")
        session_id = f"test_{scenario['name'].replace(' ', '_')}_{random.randint(1000, 9999)}"
        responses = []
        
        for i, message in enumerate(scenario['messages']):
            response = requests.post(f"{BASE_URL}/chat", json={
                "message": message,
                "session_id": session_id
            })
            
            if response.status_code == 200:
                responses.append(response.json())
                time.sleep(0.2)  # Brief pause between messages
            else:
                print_result(scenario['name'], False, f"HTTP {response.status_code} at step {i+1}")
                break
        
        if len(responses) == len(scenario['messages']):
            success = scenario['check'](responses)
            last_reply = responses[-1].get('reply', '') if responses else ''
            print_result(scenario['name'], success, f"Final reply: {last_reply[:100]}...")

def test_yaml_config_usage():
    """Test that button defaults come from YAML config."""
    print_divider("YAML CONFIG USAGE TEST")
    
    # Read the config to see current defaults
    try:
        import yaml
        with open('/Applications/git/salman4test2/smartta-final-bot/config/whatsapp.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        defaults = config.get('components', {}).get('buttons', {}).get('defaults_by_category', {})
        marketing_defaults = defaults.get('MARKETING', [])
        
        print(f"📋 Config defaults for MARKETING: {marketing_defaults}")
        
        # Test that these defaults are actually used
        response = requests.post(f"{BASE_URL}/chat", json={
            "message": "Add buttons to my marketing template",
            "session_id": "test_config_" + str(random.randint(1000, 9999))
        })
        
        if response.status_code == 200:
            data = response.json()
            draft = data.get('draft', {})
            components = draft.get('components', [])
            buttons_comp = next((c for c in components if c.get('type') == 'BUTTONS'), None)
            
            if buttons_comp:
                buttons = buttons_comp.get('buttons', [])
                button_texts = [b.get('text', '') for b in buttons]
                
                # Check if any config defaults are used
                uses_config = any(default in button_texts for default in marketing_defaults)
                print_result("YAML config usage", uses_config, f"Generated: {button_texts}")
            else:
                print_result("YAML config usage", False, "No buttons generated")
        else:
            print_result("YAML config usage", False, f"HTTP {response.status_code}")
            
    except Exception as e:
        print_result("YAML config usage", False, f"Config read error: {e}")

def run_all_tests():
    """Run all test suites."""
    print("🚀 Running Comprehensive Button & Chat Flow Tests")
    print("=" * 70)
    
    # Check if server is running
    try:
        health_response = requests.get(f"{BASE_URL}/health")
        if health_response.status_code != 200:
            print("❌ Server not responding to health check")
            return
    except Exception as e:
        print(f"❌ Cannot connect to server: {e}")
        return
    
    print("✅ Server is running")
    
    # Run test suites
    test_chat_flow_fixes()
    test_button_generation_fixes()
    test_conversation_scenarios()
    test_yaml_config_usage()
    
    print_divider("TEST SUMMARY")
    print("🏁 All tests completed!")
    print("\nKey improvements tested:")
    print("  ✓ Business-aware button generation")
    print("  ✓ Content extraction and acknowledgment")
    print("  ✓ Conversation flow without getting stuck")
    print("  ✓ YAML config integration for defaults")
    print("  ✓ Context-specific responses")

if __name__ == "__main__":
    run_all_tests()
