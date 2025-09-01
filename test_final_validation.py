#!/usr/bin/env python3
"""
Final validation test for all button and chat flow fixes.
Tests the complete user journey with layman-style interactions.
"""

import requests
import json
import time

BASE_URL = "http://localhost:8003"

def test_server_health():
    """Test if server is running."""
    try:
        response = requests.get(f"{BASE_URL}/health")
        return response.status_code == 200
    except:
        return False

def test_interactive_mode_comprehensive():
    """Test comprehensive interactive mode functionality."""
    print("\n🎯 INTERACTIVE MODE COMPREHENSIVE TEST")
    print("=" * 60)
    
    # Test 1: Sweet shop context
    response = requests.post(f"{BASE_URL}/interactive/start", json={
        "intent": "I run a sweet shop and want promotional templates"
    })
    
    if response.status_code != 200:
        print("❌ Session start failed")
        return False
        
    data = response.json()
    session_id = data['session_id']
    print(f"✅ Session started: {session_id[:8]}...")
    
    # Test 2: Generate contextual buttons
    btn_response = requests.post(f"{BASE_URL}/interactive/field/generate", json={
        'session_id': session_id,
        'field_id': 'buttons',
        'brand': 'Sweet Paradise',
        'hints': 'Diwali festival promotion'
    })
    
    if btn_response.status_code == 200:
        btn_data = btn_response.json()
        draft = btn_data.get('draft', {})
        components = draft.get('components', [])
        
        buttons_comp = next((c for c in components if c.get('type') == 'BUTTONS'), None)
        if buttons_comp:
            buttons = buttons_comp.get('buttons', [])
            button_texts = [b.get('text', '') for b in buttons]
            print(f"✅ Contextual buttons: {button_texts}")
            
            # Check for sweet-shop relevance
            sweet_keywords = ['sweet', 'order', 'menu', 'shop', 'store', 'diwali', 'festival']
            relevant = any(keyword in ' '.join(button_texts).lower() for keyword in sweet_keywords)
            
            if relevant:
                print("✅ Buttons are contextually relevant")
                return True
            else:
                print(f"⚠️ Buttons may not be contextual enough: {button_texts}")
                return False
        else:
            print("❌ No buttons generated")
            return False
    else:
        print(f"❌ Button generation failed: {btn_response.status_code}")
        return False

def test_chat_flow_comprehensive():
    """Test comprehensive chat flow with real user scenarios."""
    print("\n💬 CHAT FLOW COMPREHENSIVE TEST")
    print("=" * 60)
    
    scenarios = [
        {
            "name": "Content Extraction",
            "message": "Create a template that says: Special Diwali offer! Get 20% off on all sweets until October 31st!",
            "expected_content": "Special Diwali offer",
            "test_body": True
        },
        {
            "name": "Business Recognition", 
            "message": "I run Gulab Sweets, a traditional sweet shop",
            "expected_business": "sweets",
            "test_memory": True
        },
        {
            "name": "Smart Button Generation",
            "message": "Add some buttons for my sweet shop promotion",
            "expected_buttons": ["Order", "Menu", "Store"], 
            "test_buttons": True
        },
        {
            "name": "Affirmation Handling",
            "message": "yes, that looks good",
            "expected_progression": True,
            "test_progress": True
        }
    ]
    
    session_id = None
    results = []
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"\n🧪 Test {i}: {scenario['name']}")
        
        response = requests.post(f"{BASE_URL}/chat", json={
            "message": scenario["message"],
            "session_id": session_id
        })
        
        if response.status_code != 200:
            print(f"❌ Request failed: {response.status_code}")
            results.append(False)
            continue
            
        data = response.json()
        session_id = data.get('session_id', session_id)
        
        # Test content extraction
        if scenario.get("test_body"):
            draft = data.get('draft', {})
            components = draft.get('components', [])
            body_comp = next((c for c in components if c.get('type') == 'BODY'), None)
            
            if body_comp and scenario["expected_content"] in body_comp.get('text', ''):
                print(f"✅ Content extracted: '{body_comp.get('text', '')[:50]}...'")
                results.append(True)
            else:
                print(f"❌ Content not extracted properly")
                results.append(False)
                
        # Test business recognition
        elif scenario.get("test_memory"):
            memory = data.get('memory', {})
            business_type = memory.get('business_type', '')
            brand_name = memory.get('brand_name', '')
            
            if scenario["expected_business"] in business_type.lower() or brand_name:
                print(f"✅ Business recognized: type={business_type}, brand={brand_name}")
                results.append(True)
            else:
                print(f"❌ Business not recognized: memory={memory}")
                results.append(False)
                
        # Test button generation
        elif scenario.get("test_buttons"):
            draft = data.get('draft', {})
            components = draft.get('components', [])
            buttons_comp = next((c for c in components if c.get('type') == 'BUTTONS'), None)
            
            if buttons_comp:
                buttons = buttons_comp.get('buttons', [])
                button_texts = [b.get('text', '') for b in buttons]
                
                # Check if any expected keywords are present
                relevant = any(keyword.lower() in ' '.join(button_texts).lower() 
                             for keyword in scenario["expected_buttons"])
                
                if relevant:
                    print(f"✅ Smart buttons generated: {button_texts}")
                    results.append(True)
                else:
                    print(f"⚠️ Buttons may not be smart enough: {button_texts}")
                    results.append(False)
            else:
                print(f"❌ No buttons generated")
                results.append(False)
                
        # Test progression
        elif scenario.get("test_progress"):
            reply = data.get('reply', '').lower()
            
            # Check that it's not stuck with generic responses
            stuck_phrases = [
                "please tell me more about your template",
                "what kind of template",
                "which category"
            ]
            
            is_stuck = any(phrase in reply for phrase in stuck_phrases)
            
            if not is_stuck:
                print(f"✅ Progress made: '{reply[:50]}...'")
                results.append(True)
            else:
                print(f"❌ Conversation seems stuck: '{reply[:50]}...'")
                results.append(False)
        
        time.sleep(0.3)  # Rate limiting
    
    success_rate = sum(results) / len(results) * 100 if results else 0
    print(f"\n📊 Chat Flow Success Rate: {success_rate:.1f}% ({sum(results)}/{len(results)})")
    return success_rate >= 75  # 75% success threshold

def test_end_to_end_sweet_shop():
    """Test complete end-to-end sweet shop template creation."""
    print("\n🍬 END-TO-END SWEET SHOP TEST")
    print("=" * 60)
    
    conversation = [
        "Hi, I want to create WhatsApp templates for my sweet shop",
        "My shop is called Mithai Palace and we sell traditional Indian sweets",
        "I want to send Diwali festival offers to customers",
        "The message should say: Special Diwali celebration! Get 25% off on all sweets and gift boxes. Valid until November 5th!",
        "Yes, add some buttons for customers",
        "Also add a header about the festival",
        "Perfect, finalize it"
    ]
    
    session_id = None
    success_steps = 0
    
    for i, message in enumerate(conversation, 1):
        print(f"\n👤 Step {i}: {message}")
        
        response = requests.post(f"{BASE_URL}/chat", json={
            "message": message,
            "session_id": session_id
        })
        
        if response.status_code != 200:
            print(f"❌ Failed at step {i}")
            break
            
        data = response.json()
        session_id = data.get('session_id', session_id)
        reply = data.get('reply', '')
        
        print(f"🤖 Reply: {reply[:100]}...")
        
        # Check for final payload
        final_payload = data.get('final_creation_payload')
        if final_payload:
            print(f"\n🎉 TEMPLATE COMPLETED!")
            print(f"   Name: {final_payload.get('name', 'Unknown')}")
            print(f"   Category: {final_payload.get('category', 'Unknown')}")
            
            components = final_payload.get('components', [])
            for comp in components:
                comp_type = comp.get('type', 'Unknown')
                if comp_type == 'BODY':
                    print(f"   Body: {comp.get('text', '')[:50]}...")
                elif comp_type == 'BUTTONS':
                    button_texts = [b.get('text', '') for b in comp.get('buttons', [])]
                    print(f"   Buttons: {button_texts}")
                elif comp_type == 'HEADER':
                    print(f"   Header: {comp.get('text', 'N/A')}")
            
            success_steps = i
            break
            
        # Check for progression indicators
        if any(indicator in reply.lower() for indicator in [
            "captured", "noted", "added", "generated", "created", "perfect"
        ]):
            success_steps = i
        
        time.sleep(0.3)
    
    completion_rate = success_steps / len(conversation) * 100
    print(f"\n📊 Completion Rate: {completion_rate:.1f}% ({success_steps}/{len(conversation)} steps)")
    return completion_rate >= 80  # 80% completion threshold

def main():
    """Run all validation tests."""
    print("🚀 FINAL VALIDATION - ALL FIXES")
    print("=" * 70)
    
    # Check server health
    if not test_server_health():
        print("❌ Server not running on", BASE_URL)
        return
    print("✅ Server is healthy")
    
    # Run all tests
    tests = [
        ("Interactive Mode", test_interactive_mode_comprehensive),
        ("Chat Flow", test_chat_flow_comprehensive), 
        ("End-to-End", test_end_to_end_sweet_shop)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name.upper()} {'='*20}")
        try:
            result = test_func()
            results.append((test_name, result))
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"\n{status} {test_name}")
        except Exception as e:
            print(f"\n❌ ERROR in {test_name}: {e}")
            results.append((test_name, False))
    
    # Final summary
    print(f"\n{'='*70}")
    print("🏁 FINAL VALIDATION RESULTS")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅" if result else "❌"
        print(f"{status} {test_name}")
    
    overall_success = passed / total * 100 if total > 0 else 0
    print(f"\n📊 Overall Success Rate: {overall_success:.1f}% ({passed}/{total})")
    
    if overall_success >= 75:
        print("\n🎉 VALIDATION SUCCESSFUL! All major fixes are working.")
    else:
        print("\n⚠️ Some issues remain. Review failed tests above.")

if __name__ == "__main__":
    main()
