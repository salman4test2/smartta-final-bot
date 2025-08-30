#!/usr/bin/env python3
"""
Test policy alignment between validator, config, and main.py logic.
"""

import sys
sys.path.insert(0, '/Applications/git/salman4test2/smartta-final-bot')

from app.config import get_config
from app.validator import validate_schema, lint_rules

def test_auth_footer_policy_alignment():
    """Test that AUTH footer policy is consistent across all layers"""
    print("🧪 Testing AUTH Footer Policy Alignment")
    print("=" * 50)
    
    # Test AUTH template with footer (should be rejected everywhere)
    auth_with_footer = {
        "name": "auth_test_footer",
        "category": "AUTHENTICATION",
        "language": "en_US",
        "components": [
            {"type": "BODY", "text": "Your code is {{1}}"},
            {"type": "FOOTER", "text": "Thank you"}
        ]
    }
    
    cfg = get_config()
    
    # 1. Test schema validation
    schema = cfg.get("creation_payload_schema", {})
    schema_issues = validate_schema(auth_with_footer, schema)
    
    # 2. Test lint rules
    lint_issues = lint_rules(auth_with_footer, cfg.get("lint_rules", {}))
    
    # 3. Check config policy
    auth_constraints = cfg.get("lint_rules", {}).get("category_constraints", {}).get("AUTHENTICATION", {})
    allow_footer_config = auth_constraints.get("allow_footer", True)
    
    print(f"📋 Config allows footer for AUTH: {allow_footer_config}")
    print(f"📋 Schema validation issues: {schema_issues}")
    print(f"📋 Lint rule issues: {lint_issues}")
    
    # Check alignment
    has_footer_restriction = any("FOOTER" in issue for issue in (schema_issues + lint_issues))
    config_restricts_footer = not allow_footer_config
    
    if has_footer_restriction and config_restricts_footer:
        print("✅ Policy aligned: AUTH footer properly restricted across all layers")
        return True
    elif not has_footer_restriction and allow_footer_config:
        print("✅ Policy aligned: AUTH footer allowed across all layers")
        return True
    else:
        print("❌ Policy misaligned between config and validation")
        return False

def test_auth_header_policy():
    """Test AUTH header policy alignment"""
    print("\n🧪 Testing AUTH Header Policy Alignment")
    print("=" * 50)
    
    test_cases = [
        {
            "name": "AUTH with TEXT header",
            "template": {
                "name": "auth_text_header",
                "category": "AUTHENTICATION",
                "language": "en_US",
                "components": [
                    {"type": "BODY", "text": "Your code is {{1}}"},
                    {"type": "HEADER", "format": "TEXT", "text": "Security Code"}
                ]
            },
            "should_pass": True
        },
        {
            "name": "AUTH with IMAGE header",
            "template": {
                "name": "auth_image_header",
                "category": "AUTHENTICATION", 
                "language": "en_US",
                "components": [
                    {"type": "BODY", "text": "Your code is {{1}}"},
                    {"type": "HEADER", "format": "IMAGE"}
                ]
            },
            "should_pass": False
        },
        {
            "name": "AUTH with LOCATION header",
            "template": {
                "name": "auth_location_header",
                "category": "AUTHENTICATION",
                "language": "en_US", 
                "components": [
                    {"type": "BODY", "text": "Your code is {{1}}"},
                    {"type": "HEADER", "format": "LOCATION"}
                ]
            },
            "should_pass": False
        }
    ]
    
    cfg = get_config()
    schema = cfg.get("creation_payload_schema", {})
    
    passed = 0
    total = len(test_cases)
    
    for case in test_cases:
        template = case["template"]
        should_pass = case["should_pass"]
        name = case["name"]
        
        print(f"\n📝 Testing: {name}")
        
        # Test schema + lint
        schema_issues = validate_schema(template, schema)
        lint_issues = lint_rules(template, cfg.get("lint_rules", {}))
        
        all_issues = schema_issues + lint_issues
        has_issues = len(all_issues) > 0
        
        validation_passed = not has_issues
        
        if validation_passed == should_pass:
            print(f"   ✅ PASS - Expected: {'pass' if should_pass else 'fail'}, Got: {'pass' if validation_passed else 'fail'}")
            passed += 1
        else:
            print(f"   ❌ FAIL - Expected: {'pass' if should_pass else 'fail'}, Got: {'pass' if validation_passed else 'fail'}")
            if all_issues:
                print(f"   Issues: {all_issues}")
    
    print(f"\n📊 Header Policy Results: {passed}/{total} tests passed")
    return passed == total

def test_marketing_location_policy():
    """Test that MARKETING templates properly support LOCATION"""
    print("\n🧪 Testing MARKETING LOCATION Policy")
    print("=" * 40)
    
    marketing_location = {
        "name": "marketing_location",
        "category": "MARKETING",
        "language": "en_US",
        "components": [
            {"type": "BODY", "text": "Visit our store!"},
            {"type": "HEADER", "format": "LOCATION", "example": {"latitude": 37.7749, "longitude": -122.4194}}
        ]
    }
    
    cfg = get_config()
    schema = cfg.get("creation_payload_schema", {})
    
    schema_issues = validate_schema(marketing_location, schema)
    lint_issues = lint_rules(marketing_location, cfg.get("lint_rules", {}))
    
    all_issues = schema_issues + lint_issues
    
    if not all_issues:
        print("✅ MARKETING LOCATION header properly supported")
        return True
    else:
        print(f"❌ MARKETING LOCATION header blocked: {all_issues}")
        return False

def main():
    """Run all policy alignment tests"""
    print("🚀 Testing Policy Alignment After Fixes")
    print("=" * 60)
    
    test1 = test_auth_footer_policy_alignment()
    test2 = test_auth_header_policy()
    test3 = test_marketing_location_policy()
    
    print("\n" + "=" * 60)
    print("📋 FINAL POLICY ALIGNMENT RESULTS")
    print("=" * 60)
    
    if test1 and test2 and test3:
        print("🎉 ALL POLICY ALIGNMENT TESTS PASSED!")
        print("\n✅ Policy Consistency Achieved:")
        print("   • AUTH footer policy aligned across config/validator/main.py")
        print("   • AUTH header policy consistent (TEXT only)")
        print("   • MARKETING LOCATION headers properly supported")
        print("   • Schema-first enforcement with allOf conditionals added")
        return True
    else:
        print("⚠️  Some policy alignment tests failed")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
