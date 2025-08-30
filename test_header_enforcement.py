#!/usr/bin/env python3
"""
Comprehensive test for header enforcement patches.
Tests Meta-aligned header validation, LOCATION headers, and config-driven rules.
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

import yaml
from app.validator import lint_header, lint_rules, validate_schema
from app.main import _sanitize_candidate

def load_config():
    """Load the WhatsApp configuration."""
    with open("config/whatsapp.yaml", "r") as f:
        return yaml.safe_load(f)

def test_header_enforcement():
    """Test all header enforcement scenarios."""
    print("🧪 Testing Header Enforcement Patches...")
    cfg = load_config()
    lint_rules_config = cfg.get("lint_rules", {})
    schema = cfg.get("creation_payload_schema", {})
    
    tests_passed = 0
    tests_total = 0
    
    # Test 1: LOCATION header validation
    print("\n1. Testing LOCATION header acceptance...")
    tests_total += 1
    location_template = {
        "name": "store_location",
        "language": "en_US",
        "category": "MARKETING",
        "components": [
            {"type": "HEADER", "format": "LOCATION"},
            {"type": "BODY", "text": "Visit our store at this location!"}
        ]
    }
    
    # Sanitize and validate
    sanitized = _sanitize_candidate(location_template)
    schema_issues = validate_schema(sanitized, schema)
    lint_issues = lint_rules(sanitized, lint_rules_config)
    
    if not schema_issues and not lint_issues:
        print("✅ LOCATION header accepted for MARKETING")
        tests_passed += 1
    else:
        print(f"❌ LOCATION header rejected. Schema: {schema_issues}, Lint: {lint_issues}")
    
    # Test 2: AUTH + IMAGE header rejection
    print("\n2. Testing AUTH category IMAGE header rejection...")
    tests_total += 1
    auth_image_template = {
        "name": "auth_code_image",
        "language": "en_US", 
        "category": "AUTHENTICATION",
        "components": [
            {"type": "HEADER", "format": "IMAGE", "example": {"url": "https://example.com/image.jpg"}},
            {"type": "BODY", "text": "Your verification code is {{1}}"}
        ]
    }
    
    sanitized = _sanitize_candidate(auth_image_template)
    lint_issues = lint_rules(sanitized, lint_rules_config)
    
    expected_error = any("AUTHENTICATION templates do not allow IMAGE headers" in issue for issue in lint_issues)
    if expected_error:
        print("✅ AUTH category correctly rejects IMAGE headers")
        tests_passed += 1
    else:
        print(f"❌ AUTH category should reject IMAGE headers. Issues: {lint_issues}")
    
    # Test 3: Media header without example
    print("\n3. Testing media header without example...")
    tests_total += 1
    image_no_example = {
        "name": "promo_image",
        "language": "en_US",
        "category": "MARKETING", 
        "components": [
            {"type": "HEADER", "format": "IMAGE"},
            {"type": "BODY", "text": "Check out our latest products!"}
        ]
    }
    
    sanitized = _sanitize_candidate(image_no_example)
    lint_issues = lint_rules(sanitized, lint_rules_config)
    
    expected_error = any("IMAGE header requires an example" in issue for issue in lint_issues)
    if expected_error:
        print("✅ IMAGE header correctly requires example")
        tests_passed += 1
    else:
        print(f"❌ IMAGE header should require example. Issues: {lint_issues}")
    
    # Test 4: TEXT header too long
    print("\n4. Testing TEXT header length limit...")
    tests_total += 1
    long_text_header = {
        "name": "long_header_test",
        "language": "en_US",
        "category": "MARKETING",
        "components": [
            {"type": "HEADER", "format": "TEXT", "text": "A" * 70},  # Exceeds 60 char limit
            {"type": "BODY", "text": "This is the body text"}
        ]
    }
    
    sanitized = _sanitize_candidate(long_text_header)
    lint_issues = lint_rules(sanitized, lint_rules_config)
    
    expected_error = any("Header text exceeds 60 chars" in issue for issue in lint_issues)
    if expected_error:
        print("✅ TEXT header length limit enforced")
        tests_passed += 1
    else:
        print(f"❌ TEXT header should enforce length limit. Issues: {lint_issues}")
    
    # Test 5: TEXT header with variables but no example
    print("\n5. Testing TEXT header variable example requirement...")
    tests_total += 1
    text_var_no_example = {
        "name": "welcome_user",
        "language": "en_US",
        "category": "UTILITY",
        "components": [
            {"type": "HEADER", "format": "TEXT", "text": "Welcome {{1}}!"},
            {"type": "BODY", "text": "Thanks for joining us."}
        ]
    }
    
    sanitized = _sanitize_candidate(text_var_no_example)
    lint_issues = lint_rules(sanitized, lint_rules_config)
    
    expected_error = any("Provide example values for header variables" in issue for issue in lint_issues)
    if expected_error:
        print("✅ TEXT header with variables requires example")
        tests_passed += 1
    else:
        print(f"❌ TEXT header with variables should require example. Issues: {lint_issues}")
    
    # Test 6: LOCATION header with text field (should be rejected)
    print("\n6. Testing LOCATION header with forbidden text field...")
    tests_total += 1
    location_with_text = {
        "name": "location_with_text",
        "language": "en_US",
        "category": "MARKETING",
        "components": [
            {"type": "HEADER", "format": "LOCATION", "text": "Our store location"},
            {"type": "BODY", "text": "Visit us today!"}
        ]
    }
    
    # Test before sanitization to catch the text field issue
    lint_issues = lint_rules(location_with_text, lint_rules_config)
    
    expected_error = any("LOCATION header must not include 'text' field" in issue for issue in lint_issues)
    if expected_error:
        print("✅ LOCATION header correctly forbids text field")
        tests_passed += 1
    else:
        print(f"❌ LOCATION header should forbid text field. Issues: {lint_issues}")
    
    # Test 7: Valid AUTH template with TEXT header
    print("\n7. Testing valid AUTH template with TEXT header...")
    tests_total += 1
    auth_valid = {
        "name": "auth_code_valid",
        "language": "en_US",
        "category": "AUTHENTICATION", 
        "components": [
            {"type": "HEADER", "format": "TEXT", "text": "Verification Code"},
            {"type": "BODY", "text": "Your verification code is {{1}}. Please enter this code to complete your login."}
        ]
    }
    
    sanitized = _sanitize_candidate(auth_valid)
    schema_issues = validate_schema(sanitized, schema)
    lint_issues = lint_rules(sanitized, lint_rules_config)
    
    if not schema_issues and not lint_issues:
        print("✅ Valid AUTH template with TEXT header accepted")
        tests_passed += 1
    else:
        print(f"❌ Valid AUTH template rejected. Schema: {schema_issues}, Lint: {lint_issues}")
    
    # Test 8: Test lint_header function directly
    print("\n8. Testing lint_header function directly...")
    tests_total += 1
    
    # Test LOCATION header
    location_header = {"type": "HEADER", "format": "LOCATION"}
    location_issues = lint_header(location_header, "MARKETING", lint_rules_config)
    
    if not location_issues:
        print("✅ lint_header accepts valid LOCATION header")
        tests_passed += 1
    else:
        print(f"❌ lint_header should accept LOCATION header. Issues: {location_issues}")
    
    # Test 9: Component config validation
    print("\n9. Testing component config validation...")
    tests_total += 1
    
    # Check if component header config is present
    component_config = lint_rules_config.get("components", {}).get("header", {})
    if component_config and "formats" in component_config:
        print("✅ Component header config block found")
        tests_passed += 1
    else:
        print("❌ Component header config block missing")
    
    # Test 10: Example preservation in _sanitize_candidate
    print("\n10. Testing example preservation in sanitization...")
    tests_total += 1
    
    template_with_examples = {
        "name": "test_examples",
        "language": "en_US",
        "category": "MARKETING",
        "components": [
            {"type": "HEADER", "format": "TEXT", "text": "Hello {{1}}", "example": {"header_text": ["Hello John"]}},
            {"type": "BODY", "text": "Welcome to our store!"}
        ]
    }
    
    sanitized = _sanitize_candidate(template_with_examples)
    
    # Check if examples are preserved
    headers = [c for c in sanitized.get("components", []) if c.get("type") == "HEADER"]
    
    if len(headers) == 1 and "example" in headers[0]:
        print("✅ Example preservation working correctly")
        tests_passed += 1
    else:
        print(f"❌ Example preservation failed. Headers: {headers}")
    
    # Summary
    print(f"\n🏁 Test Results: {tests_passed}/{tests_total} tests passed")
    
    if tests_passed == tests_total:
        print("🎉 All header enforcement tests passed!")
        return True
    else:
        print("⚠️  Some tests failed. Review implementation.")
        return False

if __name__ == "__main__":
    test_header_enforcement()
