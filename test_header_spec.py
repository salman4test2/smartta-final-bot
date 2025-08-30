#!/usr/bin/env python3
"""
Test script for Meta header spec changes.
Tests:
1. LOCATION header is accepted in sanitizer
2. TEXT header is allowed for AUTHENTICATION if user requests it
3. Pre-FINAL guard rejects non-TEXT headers in AUTHENTICATION
4. Schema/config/lint rules enforce header policy
"""

import asyncio
import sys
import os
sys.path.append('/Applications/git/salman4test2/smartta-final-bot')

from app.main import _sanitize_candidate, _auto_apply_extras_on_yes
from app.validator import validate_schema, lint_rules
from app.config import get_config

def test_location_header_sanitization():
    """Test that LOCATION header is accepted in sanitizer"""
    print("🧪 Test 1: LOCATION header sanitization")
    
    candidate = {
        "name": "location_test",
        "category": "MARKETING",
        "language": "en_US",
        "components": [
            {"type": "BODY", "text": "Check out our store location!"},
            {"type": "HEADER", "format": "LOCATION", "example": {"latitude": 37.7749, "longitude": -122.4194}}
        ]
    }
    
    result = _sanitize_candidate(candidate)
    
    # Check that LOCATION header is preserved
    header_found = False
    for comp in result.get("components", []):
        if comp.get("type") == "HEADER" and comp.get("format") == "LOCATION":
            header_found = True
            print("✅ LOCATION header preserved in sanitizer")
            break
    
    if not header_found:
        print("❌ LOCATION header not preserved in sanitizer")
        return False
    
    return True

def test_auth_text_header_allowed():
    """Test that TEXT header is allowed for AUTHENTICATION if user requests it"""
    print("\n🧪 Test 2: TEXT header allowed for AUTHENTICATION")
    
    memory = {
        "category": "AUTHENTICATION",
        "wants_header": True,
        "event_label": "Login Code"
    }
    
    candidate = {
        "name": "auth_test",
        "category": "AUTHENTICATION", 
        "language": "en_US",
        "components": [
            {"type": "BODY", "text": "Your login code is {{1}}"}
        ]
    }
    
    result = _auto_apply_extras_on_yes("yes", candidate, memory)
    
    # Check that TEXT header was added
    header_found = False
    for comp in result.get("components", []):
        if comp.get("type") == "HEADER" and comp.get("format") == "TEXT":
            header_found = True
            print("✅ TEXT header added for AUTHENTICATION when requested")
            print(f"   Header text: {comp.get('text')}")
            break
    
    if not header_found:
        print("❌ TEXT header not added for AUTHENTICATION when requested")
        return False
    
    return True

def test_auth_no_buttons_footer():
    """Test that buttons and footer are blocked for AUTHENTICATION"""
    print("\n🧪 Test 3: Buttons and footer blocked for AUTHENTICATION")
    
    memory = {
        "category": "AUTHENTICATION",
        "wants_buttons": True,
        "wants_footer": True
    }
    
    candidate = {
        "name": "auth_test2",
        "category": "AUTHENTICATION",
        "language": "en_US", 
        "components": [
            {"type": "BODY", "text": "Your code is {{1}}"}
        ]
    }
    
    result = _auto_apply_extras_on_yes("yes", candidate, memory)
    
    # Check that buttons and footer were NOT added
    has_buttons = any(comp.get("type") == "BUTTONS" for comp in result.get("components", []))
    has_footer = any(comp.get("type") == "FOOTER" for comp in result.get("components", []))
    
    if not has_buttons and not has_footer:
        print("✅ Buttons and footer correctly blocked for AUTHENTICATION")
        return True
    else:
        print("❌ Buttons or footer incorrectly added for AUTHENTICATION")
        return False

def test_lint_rules_auth_header_format():
    """Test that lint rules enforce TEXT-only headers for AUTHENTICATION"""
    print("\n🧪 Test 4: Lint rules enforce TEXT-only headers for AUTHENTICATION")
    
    # Test invalid header format for AUTH
    auth_template_invalid = {
        "name": "auth_invalid",
        "category": "AUTHENTICATION",
        "language": "en_US",
        "components": [
            {"type": "BODY", "text": "Your code is {{1}}"},
            {"type": "HEADER", "format": "IMAGE", "example": {"header_url": "https://example.com/image.jpg"}}
        ]
    }
    
    cfg = get_config()
    lint_issues = lint_rules(auth_template_invalid, cfg.get("lint_rules", {}))
    
    # Check for specific error about AUTHENTICATION header format
    header_format_error = any("AUTHENTICATION templates only allow TEXT headers" in issue for issue in lint_issues)
    
    if header_format_error:
        print("✅ Lint rules correctly reject non-TEXT headers for AUTHENTICATION")
        print(f"   Issues found: {lint_issues}")
        return True
    else:
        print("❌ Lint rules did not reject non-TEXT headers for AUTHENTICATION")
        print(f"   Issues found: {lint_issues}")
        return False

def test_schema_validation_location():
    """Test that schema validation accepts LOCATION format"""
    print("\n🧪 Test 5: Schema validation accepts LOCATION format")
    
    template_with_location = {
        "name": "location_template",
        "category": "MARKETING",
        "language": "en_US",
        "components": [
            {"type": "BODY", "text": "Visit our store!"},
            {"type": "HEADER", "format": "LOCATION"}
        ]
    }
    
    cfg = get_config()
    schema = cfg.get("creation_payload_schema", {})
    
    validation_issues = validate_schema(template_with_location, schema)
    
    # Check that LOCATION format doesn't cause validation errors
    location_format_error = any("LOCATION" in issue for issue in validation_issues)
    
    if not location_format_error and not validation_issues:
        print("✅ Schema validation accepts LOCATION format")
        return True
    else:
        print("❌ Schema validation rejected LOCATION format")
        print(f"   Validation issues: {validation_issues}")
        return False

def test_all_header_formats():
    """Test that all valid header formats are supported"""
    print("\n🧪 Test 6: All valid header formats supported")
    
    formats = ["TEXT", "IMAGE", "VIDEO", "DOCUMENT", "LOCATION"]
    cfg = get_config()
    schema = cfg.get("creation_payload_schema", {})
    
    all_passed = True
    
    for fmt in formats:
        template = {
            "name": f"test_{fmt.lower()}",
            "category": "MARKETING",
            "language": "en_US",
            "components": [
                {"type": "BODY", "text": "Test message"},
                {"type": "HEADER", "format": fmt}
            ]
        }
        
        if fmt == "TEXT":
            template["components"][1]["text"] = "Test header"
        
        validation_issues = validate_schema(template, schema)
        
        if validation_issues:
            print(f"❌ Format {fmt} validation failed: {validation_issues}")
            all_passed = False
        else:
            print(f"✅ Format {fmt} validation passed")
    
    return all_passed

def main():
    """Run all header spec tests"""
    print("🚀 Testing Meta header spec changes")
    print("=" * 50)
    
    tests = [
        test_location_header_sanitization,
        test_auth_text_header_allowed,
        test_auth_no_buttons_footer,
        test_lint_rules_auth_header_format,
        test_schema_validation_location,
        test_all_header_formats
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All header spec tests passed!")
        return True
    else:
        print("⚠️  Some tests failed")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
