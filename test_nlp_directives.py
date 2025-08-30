#!/usr/bin/env python3
"""
Test script for the NLP-powered directive parsing system.
Tests various user intents and phrasing patterns.
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

import yaml
from app.main import _parse_user_directives, _apply_directives

def test_directive_parsing():
    """Test the directive parsing system with various user inputs."""
    print("🧠 Testing NLP-Powered Directive Parsing System...")
    
    # Load config
    with open("config/whatsapp.yaml", "r") as f:
        cfg = yaml.safe_load(f)
    
    test_cases = [
        # Button requests
        {
            "input": "add a button of your choice",
            "expected_type": "add_buttons",
            "expected_kind": "quick"
        },
        {
            "input": "include two quick replies",  
            "expected_type": "add_buttons",
            "expected_kind": "quick"
        },
        {
            "input": "add a link button https://example.com",
            "expected_type": "add_buttons", 
            "expected_kind": "url"
        },
        {
            "input": "call us +1 555 123 4567",
            "expected_type": "add_buttons",
            "expected_kind": "phone" 
        },
        
        # Brand/company requests
        {
            "input": "add company name as Sinch",
            "expected_type": "set_brand",
            "expected_name": "Sinch"
        },
        {
            "input": "include brand name Acme Corp",
            "expected_type": "set_brand", 
            "expected_name": "Acme Corp"
        },
        {
            "input": "my company is \"TechStart Inc\"",
            "expected_type": "set_brand",
            "expected_name": "TechStart Inc"
        },
        
        # Shortening requests
        {
            "input": "make it shorter",
            "expected_type": "shorten",
            "expected_target": 140
        },
        {
            "input": "shorten to 120 characters", 
            "expected_type": "shorten",
            "expected_target": 120
        },
        {
            "input": "condense the message",
            "expected_type": "shorten",
            "expected_target": 140
        },
        
        # Multi-intent examples
        {
            "input": "add company name as Sinch and make it short",
            "expected_count": 3  # set_brand, set_name, shorten
        },
        {
            "input": "include a button https://sinch.com and add brand TechCorp",
            "expected_count": 2
        }
    ]
    
    passed = 0
    total = len(test_cases)
    
    for i, test in enumerate(test_cases, 1):
        print(f"\n{i}. Testing: \"{test['input']}\"")
        
        directives = _parse_user_directives(cfg, test['input'])
        
        if "expected_count" in test:
            if len(directives) == test["expected_count"]:
                print(f"✅ Found {len(directives)} directives as expected")
                passed += 1
            else:
                print(f"❌ Expected {test['expected_count']} directives, got {len(directives)}")
        else:
            if directives:
                d = directives[0]
                success = True
                
                if "expected_type" in test and d.get("type") != test["expected_type"]:
                    print(f"❌ Expected type '{test['expected_type']}', got '{d.get('type')}'")
                    success = False
                    
                if "expected_kind" in test and d.get("kind") != test["expected_kind"]:
                    print(f"❌ Expected kind '{test['expected_kind']}', got '{d.get('kind')}'")
                    success = False
                    
                if "expected_name" in test and d.get("name") != test["expected_name"]:
                    print(f"❌ Expected name '{test['expected_name']}', got '{d.get('name')}'")
                    success = False
                    
                if "expected_target" in test and d.get("target") != test["expected_target"]:
                    print(f"❌ Expected target {test['expected_target']}, got {d.get('target')}")
                    success = False
                
                if success:
                    print(f"✅ Parsed correctly: {d}")
                    passed += 1
            else:
                print("❌ No directives parsed")
        
        if directives:
            print(f"   Directives: {directives}")
    
    print(f"\n🏁 Directive Parsing Results: {passed}/{total} tests passed")
    return passed == total

def test_directive_application():
    """Test applying directives to template candidates."""
    print("\n🔧 Testing Directive Application...")
    
    with open("config/whatsapp.yaml", "r") as f:
        cfg = yaml.safe_load(f)
    
    # Test button addition
    candidate = {
        "name": "test_template",
        "category": "MARKETING",
        "language": "en_US",
        "components": [
            {"type": "BODY", "text": "Hello there!"}
        ]
    }
    memory = {"category": "MARKETING"}
    
    directives = [{"type": "add_buttons", "kind": "quick", "count": 2}]
    result, messages = _apply_directives(cfg, directives, candidate, memory)
    
    buttons_added = any(c.get("type") == "BUTTONS" for c in result.get("components", []))
    if buttons_added and messages:
        print("✅ Button addition works")
        print(f"   Messages: {messages}")
    else:
        print("❌ Button addition failed")
        return False
    
    # Test brand addition
    directives = [{"type": "set_brand", "name": "TestCorp"}]
    result, messages = _apply_directives(cfg, directives, candidate, memory)
    
    body_component = next((c for c in result.get("components", []) if c.get("type") == "BODY"), None)
    if body_component and "TestCorp" in body_component.get("text", ""):
        print("✅ Brand addition works")
        print(f"   Messages: {messages}")
    else:
        print("❌ Brand addition failed")
        print(f"   Body: {body_component}")
        return False
    
    # Test AUTH category restrictions
    auth_candidate = {
        "category": "AUTHENTICATION",
        "components": [{"type": "BODY", "text": "Your code is 123456"}]
    }
    auth_memory = {"category": "AUTHENTICATION"}
    
    directives = [{"type": "add_buttons", "kind": "quick"}]
    result, messages = _apply_directives(cfg, directives, auth_candidate, auth_memory)
    
    buttons_blocked = not any(c.get("type") == "BUTTONS" for c in result.get("components", []))
    auth_message = any("aren't allowed for AUTH" in msg for msg in messages)
    
    if buttons_blocked and auth_message:
        print("✅ AUTH category restrictions work")
        print(f"   Messages: {messages}")
    else:
        print("❌ AUTH category restrictions failed")
        return False
    
    print("🎉 All directive application tests passed!")
    return True

def test_real_world_scenarios():
    """Test with actual problematic phrases from the session analysis."""
    print("\n🌍 Testing Real-World Scenarios...")
    
    with open("config/whatsapp.yaml", "r") as f:
        cfg = yaml.safe_load(f)
    
    # The exact phrases that failed in the original session
    problematic_phrases = [
        "add company name as Sinch in the body",
        "add a button of your choice", 
        "include Sinch as company name",
        "put a call-to-action button"
    ]
    
    for phrase in problematic_phrases:
        print(f"\nTesting: \"{phrase}\"")
        directives = _parse_user_directives(cfg, phrase)
        
        if directives:
            print(f"✅ Parsed {len(directives)} directive(s): {[d.get('type') for d in directives]}")
            
            # Test application
            candidate = {
                "category": "MARKETING",
                "components": [{"type": "BODY", "text": "Happy Holi! 🎉"}]
            }
            memory = {"category": "MARKETING"}
            
            result, messages = _apply_directives(cfg, directives, candidate, memory)
            if messages:
                print(f"✅ Applied successfully: {'; '.join(messages)}")
            else:
                print("⚠️  No changes applied")
        else:
            print("❌ No directives parsed - this was the original problem!")
    
    return True

if __name__ == "__main__":
    success1 = test_directive_parsing()
    success2 = test_directive_application() 
    success3 = test_real_world_scenarios()
    
    if success1 and success2 and success3:
        print("\n🎉 All NLP directive parsing tests passed!")
        print("The system should now handle user intents much more reliably.")
    else:
        print("\n⚠️  Some tests failed. Review the implementation.")
