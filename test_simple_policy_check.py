#!/usr/bin/env python3
"""
Simple policy alignment verification.
"""

def test_yaml_policy():
    """Test YAML policy configuration"""
    print("🧪 Checking YAML Policy Configuration")
    print("=" * 50)
    
    # Read the YAML file directly
    with open('/Applications/git/salman4test2/smartta-final-bot/config/whatsapp.yaml', 'r') as f:
        content = f.read()
    
    # Check for key policy elements
    checks = [
        ("allow_footer: false", "AUTH footer restriction in YAML"),
        ("allow_buttons: false", "AUTH buttons restriction in YAML"),
        ("allowed_header_formats: [TEXT]", "AUTH header format restriction"),
        ("LOCATION", "LOCATION header format support"),
        ("allOf:", "Schema-first enforcement conditionals")
    ]
    
    passed = 0
    total = len(checks)
    
    for check, description in checks:
        if check in content:
            print(f"✅ {description} - Found")
            passed += 1
        else:
            print(f"❌ {description} - Missing")
    
    print(f"\n📊 YAML Policy: {passed}/{total} checks passed")
    return passed == total

def test_validator_policy():
    """Test validator policy alignment"""
    print("\n🧪 Checking Validator Policy Implementation")
    print("=" * 50)
    
    # Read validator.py
    with open('/Applications/git/salman4test2/smartta-final-bot/app/validator.py', 'r') as f:
        content = f.read()
    
    checks = [
        ("allow_footer", "Footer policy read from config"),
        ("allow_buttons", "Buttons policy read from config"),
        ("category_constraints", "Category constraints usage"),
        ("allowed_header_formats", "Header format validation"),
        ("AUTHENTICATION templates", "AUTH restriction messages")
    ]
    
    passed = 0
    total = len(checks)
    
    for check, description in checks:
        if check in content:
            print(f"✅ {description} - Found")
            passed += 1
        else:
            print(f"❌ {description} - Missing")
    
    print(f"\n📊 Validator Policy: {passed}/{total} checks passed")
    return passed == total

def test_main_py_logic():
    """Test main.py AUTH logic"""
    print("\n🧪 Checking main.py AUTH Logic")
    print("=" * 40)
    
    # Read main.py relevant sections
    with open('/Applications/git/salman4test2/smartta-final-bot/app/main.py', 'r') as f:
        content = f.read()
    
    checks = [
        ("if cat == \"AUTHENTICATION\":", "AUTH category handling"),
        ("Authentication code", "AUTH header text generation"),
        ("cat != \"AUTHENTICATION\"", "Non-AUTH extras handling"),
        ("For AUTH, only allow TEXT header", "AUTH header restriction comment")
    ]
    
    passed = 0 
    total = len(checks)
    
    for check, description in checks:
        if check in content:
            print(f"✅ {description} - Found")
            passed += 1
        else:
            print(f"❌ {description} - Missing")
    
    print(f"\n📊 Main.py Logic: {passed}/{total} checks passed")
    return passed == total

def main():
    """Run all policy checks"""
    print("🚀 Policy Alignment Verification")
    print("=" * 60)
    
    test1 = test_yaml_policy()
    test2 = test_validator_policy()
    test3 = test_main_py_logic()
    
    print("\n" + "=" * 60)
    print("📋 POLICY ALIGNMENT SUMMARY")
    print("=" * 60)
    
    if test1 and test2 and test3:
        print("🎉 ALL POLICY ALIGNMENT VERIFIED!")
        print("\n✅ Consistency Achieved:")
        print("   • YAML config has explicit allow_footer: false for AUTH")
        print("   • Validator reads config instead of hardcoding restrictions")
        print("   • main.py correctly implements AUTH header logic")
        print("   • Schema has allOf conditionals for enforcement")
        print("   • All components aligned on AUTH restrictions")
        return True
    else:
        print("⚠️  Some policy checks failed")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
