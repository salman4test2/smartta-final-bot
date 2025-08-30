#!/usr/bin/env python3
"""
Test script for the two generic improvements:
1. Configuration-driven button defaults (no more hardcoded labels)
2. Safer brand insertion with word boundaries
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

import yaml
from app.main import _auto_apply_extras_on_yes, _ensure_brand_in_body

def test_configuration_driven_buttons():
    """Test that button defaults come from YAML config, not hardcoded."""
    print("🧪 Testing Configuration-Driven Button Defaults...")
    
    # Load actual config
    with open("config/whatsapp.yaml", "r") as f:
        cfg = yaml.safe_load(f)
    
    # Test MARKETING category defaults
    marketing_defaults = (cfg.get("components", {})
                         .get("buttons", {})
                         .get("defaults_by_category", {})
                         .get("MARKETING", ["Learn more", "Shop now"]))
    
    print(f"📊 MARKETING defaults from config: {marketing_defaults}")
    
    # Simulate auto-apply for MARKETING category
    memory = {
        "wants_buttons": True,
        "category": "MARKETING"
    }
    candidate = {
        "components": [{"type": "BODY", "text": "Test message"}]
    }
    
    result = _auto_apply_extras_on_yes("yes", candidate, memory)
    
    # Check if buttons were added with config defaults
    buttons_comp = None
    for comp in result.get("components", []):
        if comp.get("type") == "BUTTONS":
            buttons_comp = comp
            break
    
    if buttons_comp:
        button_texts = [btn.get("text") for btn in buttons_comp.get("buttons", [])]
        print(f"✅ Generated button texts: {button_texts}")
        print(f"✅ Matches config defaults: {button_texts == marketing_defaults[:2]}")
        return button_texts == marketing_defaults[:2]
    else:
        print("❌ No buttons component found")
        return False

def test_safer_brand_insertion():
    """Test that brand insertion uses word boundaries to avoid false positives."""
    print("\n🧪 Testing Safer Brand Insertion with Word Boundaries...")
    
    test_cases = [
        {
            "name": "Normal insertion",
            "components": [{"type": "BODY", "text": "Welcome to our store!"}],
            "brand": "Acme",
            "expect_insertion": True,
            "expected_text": "Welcome to our store! Acme"  # Text ending with ! gets space separator, not —
        },
        {
            "name": "Brand already present as whole word",
            "components": [{"type": "BODY", "text": "Welcome to Acme store!"}],
            "brand": "Acme", 
            "expect_insertion": False,
            "expected_text": "Welcome to Acme store!"
        },
        {
            "name": "Brand in URL should not prevent insertion",
            "components": [{"type": "BODY", "text": "Visit https://acme.example.com for more info"}],
            "brand": "Tesla",
            "expect_insertion": True,
            "expected_text": "Visit https://acme.example.com for more info — Tesla"
        },
        {
            "name": "Brand in email should not prevent insertion", 
            "components": [{"type": "BODY", "text": "Contact us at support@acme.com"}],
            "brand": "Tesla",
            "expect_insertion": True,
            "expected_text": "Contact us at support@acme.com — Tesla"
        },
        {
            "name": "Partial match should not prevent insertion",
            "components": [{"type": "BODY", "text": "Welcome to Acme Corporation"}],
            "brand": "Corp",
            "expect_insertion": True,
            "expected_text": "Welcome to Acme Corporation — Corp"
        }
    ]
    
    passed = 0
    for test in test_cases:
        print(f"\n📝 Test: {test['name']}")
        print(f"   Original: {test['components'][0]['text']}")
        print(f"   Brand: {test['brand']}")
        
        result_comps = _ensure_brand_in_body(test["components"], test["brand"])
        actual_text = result_comps[0]["text"]
        
        print(f"   Result: {actual_text}")
        print(f"   Expected: {test['expected_text']}")
        
        if actual_text == test["expected_text"]:
            print("   ✅ PASS")
            passed += 1
        else:
            print("   ❌ FAIL")
    
    print(f"\n🏁 Brand Insertion Results: {passed}/{len(test_cases)} tests passed")
    return passed == len(test_cases)

def test_spot_checks():
    """Spot checks against the scenarios mentioned."""
    print("\n🎯 Running Spot Checks...")
    
    # Spot check 1: Button defaults from YAML
    print("\n1. User: 'add a button of your choice'")
    print("   Expected: Server adds BUTTONS with YAML defaults")
    
    memory = {"wants_buttons": True, "category": "UTILITY"}
    candidate = {"components": [{"type": "BODY", "text": "Your order is ready"}]}
    result = _auto_apply_extras_on_yes("yes", candidate, memory)
    
    buttons = None
    for comp in result.get("components", []):
        if comp.get("type") == "BUTTONS":
            buttons = comp.get("buttons", [])
            break
    
    if buttons:
        labels = [btn.get("text") for btn in buttons]
        print(f"   ✅ Generated: {labels} (from YAML config)")
    else:
        print("   ❌ No buttons generated")
    
    # Spot check 2: Safe brand insertion
    print("\n2. Brand insertion safety")
    print("   Expected: Word boundaries prevent false positives")
    
    test_text = "Visit sinch.com and contact support@sinch.com"
    test_comps = [{"type": "BODY", "text": test_text}]
    result_comps = _ensure_brand_in_body(test_comps, "TechCorp")
    
    final_text = result_comps[0]["text"]
    print(f"   Original: {test_text}")
    print(f"   After adding 'TechCorp': {final_text}")
    
    if "TechCorp" in final_text and "sinch.com" in final_text:
        print("   ✅ Brand added safely without affecting URLs/emails")
    else:
        print("   ❌ Brand insertion issue")

if __name__ == "__main__":
    print("🚀 Testing Generic Improvements...")
    
    # Test 1: Configuration-driven buttons
    buttons_ok = test_configuration_driven_buttons()
    
    # Test 2: Safer brand insertion
    brand_ok = test_safer_brand_insertion()
    
    # Spot checks
    test_spot_checks()
    
    print(f"\n🏁 Overall Results:")
    print(f"   Configuration-driven buttons: {'✅ PASS' if buttons_ok else '❌ FAIL'}")
    print(f"   Safer brand insertion: {'✅ PASS' if brand_ok else '❌ FAIL'}")
    
    if buttons_ok and brand_ok:
        print("🎉 All improvements working correctly!")
        sys.exit(0)
    else:
        print("⚠️  Some improvements need attention")
        sys.exit(1)
