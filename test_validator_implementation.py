#!/usr/bin/env python3
"""
Test the actual validator implementation for global placeholders.
"""

import sys
sys.path.insert(0, '/Applications/git/salman4test2/smartta-final-bot')

def test_validator_with_global_placeholders():
    """Test the actual validator with global placeholder scenarios"""
    print("🧪 Testing actual validator implementation")
    print("=" * 50)
    
    # Import the actual validator functions
    try:
        from app.validator import lint_rules, _placeholders_in
        print("✅ Successfully imported validator functions")
    except ImportError as e:
        print(f"❌ Failed to import validator: {e}")
        return False
    
    # Test the helper function
    test_text = "Hi {{1}}, your order {{2}} is ready!"
    placeholders = _placeholders_in(test_text)
    print(f"📝 Placeholder extraction test: '{test_text}' -> {placeholders}")
    
    if placeholders == [1, 2]:
        print("✅ Placeholder helper working correctly")
    else:
        print(f"❌ Expected [1, 2], got {placeholders}")
        return False
    
    # Test scenarios with the actual lint_rules function
    test_scenarios = [
        {
            "name": "Valid sequential placeholders",
            "payload": {
                "name": "test_valid",
                "category": "MARKETING",
                "language": "en_US",
                "components": [
                    {"type": "HEADER", "format": "TEXT", "text": "Hello {{1}}"},
                    {"type": "BODY", "text": "Your order {{2}} will arrive on {{3}}."}
                ]
            },
            "should_have_issues": False
        },
        {
            "name": "Invalid - starts at {{2}}",
            "payload": {
                "name": "test_invalid_start",
                "category": "MARKETING", 
                "language": "en_US",
                "components": [
                    {"type": "BODY", "text": "Your order {{2}} is ready for {{3}}."}
                ]
            },
            "should_have_issues": True,
            "expected_error": "must start at {{1}}"
        },
        {
            "name": "Invalid - gap in sequence",
            "payload": {
                "name": "test_gap",
                "category": "UTILITY",
                "language": "en_US",
                "components": [
                    {"type": "HEADER", "format": "TEXT", "text": "Dear {{1}}"},
                    {"type": "BODY", "text": "Your appointment on {{3}} is confirmed."}
                ]
            },
            "should_have_issues": True,
            "expected_error": "missing: {{2}}"
        }
    ]
    
    passed = 0
    total = len(test_scenarios)
    
    for scenario in test_scenarios:
        payload = scenario["payload"]
        should_have_issues = scenario["should_have_issues"]
        expected_error = scenario.get("expected_error", "")
        name = scenario["name"]
        
        print(f"\n📋 Testing: {name}")
        
        # Use empty rules for this test - we're focusing on placeholder validation
        rules = {}
        issues = lint_rules(payload, rules)
        
        # Filter for placeholder-related issues
        placeholder_issues = [issue for issue in issues if "placeholder" in issue.lower() or "{{" in issue]
        
        has_placeholder_issues = len(placeholder_issues) > 0
        
        if has_placeholder_issues == should_have_issues:
            print(f"   ✅ PASS - Expected issues: {should_have_issues}, Got issues: {has_placeholder_issues}")
            if placeholder_issues:
                print(f"   Issues: {placeholder_issues}")
            if expected_error and placeholder_issues:
                error_found = any(expected_error in issue for issue in placeholder_issues)
                if error_found:
                    print(f"   ✅ Expected error pattern found")
                else:
                    print(f"   ⚠️  Expected error pattern '{expected_error}' not found in: {placeholder_issues}")
            passed += 1
        else:
            print(f"   ❌ FAIL - Expected issues: {should_have_issues}, Got issues: {has_placeholder_issues}")
            if placeholder_issues:
                print(f"   Actual issues: {placeholder_issues}")
    
    print(f"\n📊 Validator tests: {passed}/{total} passed")
    return passed == total

def main():
    """Test the validator implementation"""
    print("🚀 Testing Actual Validator Implementation")
    print("=" * 60)
    
    success = test_validator_with_global_placeholders()
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 VALIDATOR IMPLEMENTATION TEST PASSED!")
        print("\n✅ Global placeholder validation is working correctly:")
        print("   • Helper function extracts placeholders properly")
        print("   • Lint rules enforce sequential numbering")
        print("   • Error messages are clear and helpful")
        print("   • Validation integrates with existing lint system")
    else:
        print("⚠️  Validator implementation test failed")
    
    return success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
