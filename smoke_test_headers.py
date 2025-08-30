#!/usr/bin/env python3
"""
Quick smoke tests for header enforcement integration.
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

import yaml
from app.validator import lint_rules
from app.main import _sanitize_candidate

def smoke_tests():
    """Run quick smoke tests."""
    print("🔥 Running Header Enforcement Smoke Tests...")
    
    with open("config/whatsapp.yaml", "r") as f:
        cfg = yaml.safe_load(f)
    lint_config = cfg.get("lint_rules", {})
    
    # Smoke Test 1: LOCATION header works
    location_ok = {
        "category": "MARKETING",
        "language": "en_US", 
        "name": "store_promo",
        "components": [
            {"type": "HEADER", "format": "LOCATION", "example": {"name": "Main Store", "latitude": 12.34, "longitude": 56.78}},
            {"type": "BODY", "text": "Visit our store at this location!"}
        ]
    }
    
    sanitized = _sanitize_candidate(location_ok)
    issues = lint_rules(sanitized, lint_config)
    assert not issues, f"LOCATION header should work: {issues}"
    print("✅ LOCATION header validation works")
    
    # Smoke Test 2: AUTH + IMAGE fails
    auth_image_fail = {
        "category": "AUTHENTICATION",
        "language": "en_US",
        "name": "auth_otp",
        "components": [
            {"type": "HEADER", "format": "IMAGE", "example": {"url": "https://example.com/logo.jpg"}},
            {"type": "BODY", "text": "Your code is {{1}} - do not share it."}
        ]
    }
    
    sanitized = _sanitize_candidate(auth_image_fail)
    issues = lint_rules(sanitized, lint_config)
    assert any("AUTHENTICATION templates do not allow IMAGE headers" in issue for issue in issues), f"AUTH should reject IMAGE: {issues}"
    print("✅ AUTH category rejects IMAGE headers")
    
    # Smoke Test 3: Media without example fails
    media_no_example = {
        "category": "UTILITY",
        "language": "en_US",
        "name": "notification",
        "components": [
            {"type": "HEADER", "format": "VIDEO"},  # No example
            {"type": "BODY", "text": "Check out our new video!"}
        ]
    }
    
    sanitized = _sanitize_candidate(media_no_example)
    issues = lint_rules(sanitized, lint_config)
    assert any("VIDEO header requires an example" in issue for issue in issues), f"VIDEO should require example: {issues}"
    print("✅ Media headers require examples")
    
    # Smoke Test 4: TEXT too long fails
    text_too_long = {
        "category": "MARKETING",
        "language": "en_US",
        "name": "long_header",
        "components": [
            {"type": "HEADER", "format": "TEXT", "text": "A" * 70},  # Too long
            {"type": "BODY", "text": "This message has a very long header"}
        ]
    }
    
    sanitized = _sanitize_candidate(text_too_long)
    issues = lint_rules(sanitized, lint_config)
    assert any("Header text exceeds 60 chars" in issue for issue in issues), f"Long TEXT should fail: {issues}"
    print("✅ TEXT header length limits enforced")
    
    # Smoke Test 5: LOCATION with text fails
    location_with_text = {
        "category": "MARKETING",
        "language": "en_US",
        "name": "location_bad",
        "components": [
            {"type": "HEADER", "format": "LOCATION", "text": "Our store"},  # Should not have text
            {"type": "BODY", "text": "Visit us today!"}
        ]
    }
    
    issues = lint_rules(location_with_text, lint_config)  # Test before sanitization
    assert any("LOCATION header must not include 'text' field" in issue for issue in issues), f"LOCATION with text should fail: {issues}"
    print("✅ LOCATION headers forbid text field")
    
    print("\n🎉 All smoke tests passed! Header enforcement is working correctly.")

if __name__ == "__main__":
    smoke_tests()
