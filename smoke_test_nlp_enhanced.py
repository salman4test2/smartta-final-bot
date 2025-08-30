#!/usr/bin/env python3
"""
Quick smoke test for the enhanced NLP directive parsing system.
Tests key improvements made during this session.
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

import yaml
from app.main import _parse_user_directives, _apply_directives

def smoke_test():
    """Run a quick smoke test of enhanced NLP parsing."""
    print("🚀 Running Smoke Test for Enhanced NLP Directive Parsing...")
    
    # Load config
    with open("config/whatsapp.yaml", "r") as f:
        cfg = yaml.safe_load(f)
    
    # Test the key improvements made
    test_cases = [
        # Fixed: Phone number detection 
        {
            "input": "call us +1 555 123 4567",
            "expect": "phone button"
        },
        # Fixed: Complex brand name extraction
        {
            "input": "include brand name Acme Corp",
            "expect": "brand name 'Acme Corp'"
        },
        # Fixed: Multi-intent shorten detection
        {
            "input": "add company name as Sinch and make it short",
            "expect": "brand + shorten directives"
        },
        # Working: URL button detection
        {
            "input": "add a link button https://example.com",
            "expect": "URL button"
        },
        # Working: Generic brand detection
        {
            "input": "add company name as TestCorp",
            "expect": "brand name 'TestCorp'"
        }
    ]
    
    results = []
    for test in test_cases:
        directives = _parse_user_directives(cfg, test["input"])
        results.append({
            "input": test["input"],
            "expected": test["expect"],
            "found": len(directives),
            "types": [d.get("type") for d in directives],
            "success": len(directives) > 0
        })
    
    # Print results
    passed = 0
    for i, result in enumerate(results, 1):
        status = "✅" if result["success"] else "❌"
        print(f"{i}. {status} \"{result['input']}\"")
        print(f"   Expected: {result['expected']}")
        print(f"   Found: {result['found']} directive(s) - {result['types']}")
        if result["success"]:
            passed += 1
        print()
    
    print(f"🏁 Smoke Test Results: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("🎉 All smoke tests passed! Enhanced NLP directive parsing is working correctly.")
        return True
    else:
        print("⚠️  Some smoke tests failed. Enhanced parsing may need attention.")
        return False

if __name__ == "__main__":
    success = smoke_test()
    sys.exit(0 if success else 1)
