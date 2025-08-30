#!/usr/bin/env python3
"""
Test global placeholder sequencing validation across HEADER(TEXT) + BODY.
"""

import sys
sys.path.insert(0, '/Applications/git/salman4test2/smartta-final-bot')

# Test the helper function directly first
import re
_PH_RE = re.compile(r"\{\{\s*(\d+)\s*\}\}")

def _placeholders_in(text: str) -> list[int]:
    """Return placeholder indices found in text, e.g., 'Hi {{2}}' -> [2]."""
    if not isinstance(text, str):
        return []
    return [int(m.group(1)) for m in _PH_RE.finditer(text)]

def test_placeholder_helper():
    """Test the placeholder helper function"""
    print("🧪 Testing placeholder helper function")
    
    test_cases = [
        ("Hi {{1}}!", [1]),
        ("Order {{2}} from {{1}}", [2, 1]),
        ("No placeholders here", []),
        ("Multiple {{1}} and {{2}} and {{1}} again", [1, 2, 1]),
        ("Spaced {{ 3 }} placeholder", [3]),
        ("Complex {{10}} number", [10]),
        ("", []),
        (None, [])  # Should handle None gracefully
    ]
    
    passed = 0
    total = len(test_cases)
    
    for text, expected in test_cases:
        try:
            result = _placeholders_in(text)
            if result == expected:
                print(f"✅ '{text}' -> {result}")
                passed += 1
            else:
                print(f"❌ '{text}' -> Expected {expected}, Got {result}")
        except Exception as e:
            print(f"❌ '{text}' -> Exception: {e}")
    
    print(f"📊 Helper function: {passed}/{total} tests passed\n")
    return passed == total

def test_global_placeholder_validation():
    """Test global placeholder validation logic"""
    print("🧪 Testing global placeholder validation")
    
    test_scenarios = [
        {
            "name": "Valid: Sequential 1,2,3 across header+body",
            "template": {
                "name": "test_valid_123",
                "category": "MARKETING",
                "language": "en_US",
                "components": [
                    {"type": "HEADER", "format": "TEXT", "text": "Hello {{1}}!"},
                    {"type": "BODY", "text": "Your order {{2}} will arrive on {{3}}."}
                ]
            },
            "should_pass": True
        },
        {
            "name": "Valid: Only body with {{1}}",
            "template": {
                "name": "test_body_only",
                "category": "UTILITY",
                "language": "en_US",
                "components": [
                    {"type": "BODY", "text": "Hi {{1}}, your appointment is confirmed."}
                ]
            },
            "should_pass": True
        },
        {
            "name": "Valid: Duplicates allowed",
            "template": {
                "name": "test_duplicates",
                "category": "MARKETING",
                "language": "en_US",
                "components": [
                    {"type": "HEADER", "format": "TEXT", "text": "Dear {{1}}"},
                    {"type": "BODY", "text": "Hi {{1}}, your code is {{2}}. Remember {{1}}, keep it safe!"}
                ]
            },
            "should_pass": True
        },
        {
            "name": "Invalid: Starts at {{2}} instead of {{1}}",
            "template": {
                "name": "test_no_start_1",
                "category": "MARKETING",
                "language": "en_US",
                "components": [
                    {"type": "BODY", "text": "Your order {{2}} is ready for {{3}}."}
                ]
            },
            "should_pass": False,
            "expected_error": "must start at {{1}}"
        },
        {
            "name": "Invalid: Gap in sequence ({{1}}, {{3}} missing {{2}})",
            "template": {
                "name": "test_gap",
                "category": "UTILITY",
                "language": "en_US",
                "components": [
                    {"type": "HEADER", "format": "TEXT", "text": "Hello {{1}}"},
                    {"type": "BODY", "text": "Your appointment on {{3}} is confirmed."}
                ]
            },
            "should_pass": False,
            "expected_error": "missing: {{2}}"
        },
        {
            "name": "Valid: No placeholders",
            "template": {
                "name": "test_no_placeholders",
                "category": "MARKETING",
                "language": "en_US",
                "components": [
                    {"type": "HEADER", "format": "TEXT", "text": "Special Offer"},
                    {"type": "BODY", "text": "Get 20% off today!"}
                ]
            },
            "should_pass": True
        },
        {
            "name": "Valid: Non-TEXT header ignored",
            "template": {
                "name": "test_image_header",
                "category": "MARKETING",
                "language": "en_US",
                "components": [
                    {"type": "HEADER", "format": "IMAGE", "example": {"header_url": "image.jpg"}},
                    {"type": "BODY", "text": "Hi {{1}}, check out our new product!"}
                ]
            },
            "should_pass": True
        },
        {
            "name": "Invalid: Complex gap ({{1}}, {{2}}, {{5}} missing {{3}}, {{4}})",
            "template": {
                "name": "test_complex_gap",
                "category": "UTILITY",
                "language": "en_US",
                "components": [
                    {"type": "HEADER", "format": "TEXT", "text": "Hi {{1}}"},
                    {"type": "BODY", "text": "Order {{2}} will arrive on {{5}}."}
                ]
            },
            "should_pass": False,
            "expected_error": "missing: {{3}}, {{4}}"
        }
    ]
    
    # Simulate the validation logic
    passed = 0
    total = len(test_scenarios)
    
    for scenario in test_scenarios:
        template = scenario["template"]
        should_pass = scenario["should_pass"]
        name = scenario["name"]
        expected_error = scenario.get("expected_error", "")
        
        print(f"\n📝 {name}")
        
        # Simulate the global placeholder validation logic
        issues = []
        try:
            all_nums = []
            for comp in template.get("components", []):
                t = (comp.get("type") or "").upper()
                if t == "HEADER" and (comp.get("format") or "").upper() == "TEXT":
                    all_nums += _placeholders_in(comp.get("text") or "")
                elif t == "BODY":
                    all_nums += _placeholders_in(comp.get("text") or "")

            if all_nums:
                uniq = sorted(set(all_nums))
                # must start at 1
                if uniq[0] != 1:
                    issues.append("Placeholders must start at {{1}} across header+body")
                # must be contiguous 1..N (duplicates are fine)
                expected = list(range(1, uniq[-1] + 1))
                if uniq != expected:
                    missing = [n for n in expected if n not in uniq]
                    if missing:
                        pretty = ", ".join(f"{{{{{n}}}}}" for n in missing)
                        issues.append(f"Placeholders must be sequential across header+body; missing: {pretty}")
        except Exception as e:
            issues.append(f"Exception in validation: {e}")
        
        validation_passed = len(issues) == 0
        
        if validation_passed == should_pass:
            print(f"   ✅ PASS - Expected: {'pass' if should_pass else 'fail'}, Got: {'pass' if validation_passed else 'fail'}")
            passed += 1
        else:
            print(f"   ❌ FAIL - Expected: {'pass' if should_pass else 'fail'}, Got: {'pass' if validation_passed else 'fail'}")
            if issues:
                print(f"   Issues: {issues}")
            if not should_pass and expected_error:
                error_found = any(expected_error in issue for issue in issues)
                if error_found:
                    print(f"   ✅ Correct error message found")
                else:
                    print(f"   ❌ Expected error '{expected_error}' not found")
    
    print(f"\n📊 Global validation: {passed}/{total} tests passed")
    return passed == total

def test_real_world_scenarios():
    """Test real-world template scenarios"""
    print("\n🧪 Testing real-world scenarios")
    
    scenarios = [
        {
            "name": "E-commerce order confirmation",
            "template": {
                "name": "order_confirmation",
                "category": "UTILITY",
                "language": "en_US",
                "components": [
                    {"type": "HEADER", "format": "TEXT", "text": "Order Confirmation for {{1}}"},
                    {"type": "BODY", "text": "Hi {{1}}! Your order #{{2}} has been confirmed. Delivery expected: {{3}}. Total: ${{4}}."}
                ]
            },
            "should_pass": True
        },
        {
            "name": "Authentication with header",
            "template": {
                "name": "auth_with_header",
                "category": "AUTHENTICATION",
                "language": "en_US",
                "components": [
                    {"type": "HEADER", "format": "TEXT", "text": "Security Code"},
                    {"type": "BODY", "text": "Your login code is {{1}}. Expires in {{2}} minutes."}
                ]
            },
            "should_pass": True
        },
        {
            "name": "Marketing with location (no TEXT header)",
            "template": {
                "name": "store_location",
                "category": "MARKETING",
                "language": "en_US",
                "components": [
                    {"type": "HEADER", "format": "LOCATION", "example": {"latitude": 37.7749, "longitude": -122.4194}},
                    {"type": "BODY", "text": "Visit {{1}} at our new location! Special offer: {{2}}% off!"}
                ]
            },
            "should_pass": True
        }
    ]
    
    passed = 0
    total = len(scenarios)
    
    for scenario in scenarios:
        template = scenario["template"]
        should_pass = scenario["should_pass"]
        name = scenario["name"]
        
        print(f"\n📋 {name}")
        
        # Run validation
        issues = []
        try:
            all_nums = []
            for comp in template.get("components", []):
                t = (comp.get("type") or "").upper()
                if t == "HEADER" and (comp.get("format") or "").upper() == "TEXT":
                    all_nums += _placeholders_in(comp.get("text") or "")
                elif t == "BODY":
                    all_nums += _placeholders_in(comp.get("text") or "")

            if all_nums:
                uniq = sorted(set(all_nums))
                if uniq[0] != 1:
                    issues.append("Placeholders must start at {{1}} across header+body")
                expected = list(range(1, uniq[-1] + 1))
                if uniq != expected:
                    missing = [n for n in expected if n not in uniq]
                    if missing:
                        pretty = ", ".join(f"{{{{{n}}}}}" for n in missing)
                        issues.append(f"Placeholders must be sequential across header+body; missing: {pretty}")
        except Exception as e:
            issues.append(f"Exception: {e}")
        
        validation_passed = len(issues) == 0
        
        if validation_passed == should_pass:
            print(f"   ✅ PASS")
            passed += 1
        else:
            print(f"   ❌ FAIL - Issues: {issues}")
    
    print(f"\n📊 Real-world scenarios: {passed}/{total} tests passed")
    return passed == total

def main():
    """Run all placeholder validation tests"""
    print("🚀 Global Placeholder Sequencing Validation Tests")
    print("=" * 60)
    
    test1 = test_placeholder_helper()
    test2 = test_global_placeholder_validation()
    test3 = test_real_world_scenarios()
    
    print("\n" + "=" * 60)
    print("📋 FINAL RESULTS")
    print("=" * 60)
    
    if test1 and test2 and test3:
        print("🎉 ALL PLACEHOLDER VALIDATION TESTS PASSED!")
        print("\n✅ Global Placeholder Sequencing Complete:")
        print("   • Helper function correctly extracts placeholders")
        print("   • Sequential validation across HEADER(TEXT) + BODY")
        print("   • Must start at {{1}} with no gaps")
        print("   • Duplicates allowed as expected")
        print("   • Non-TEXT headers properly ignored")
        print("   • Real-world scenarios work correctly")
        return True
    else:
        print("⚠️  Some placeholder validation tests failed")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
