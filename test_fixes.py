#!/usr/bin/env python3
"""
Test script to verify all critical fixes are working
"""
import sys
import os

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_imports():
    """Test that all imports work correctly"""
    try:
        from app.models import User, UserSession, Session, Draft, LlmLog
        from app.main import app, _auto_apply_extras_on_yes, _upsert_user_session
        from app.schemas import SessionCreate, SessionCreateResponse
        print("✅ All imports successful")
        return True
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return False

def test_auth_guard():
    """Test that AUTH category blocks extras"""
    try:
        from app.main import _auto_apply_extras_on_yes
        
        # Test with AUTHENTICATION category
        memory = {"category": "AUTHENTICATION", "wants_header": True, "wants_buttons": True}
        candidate = {"category": "AUTHENTICATION"}
        result = _auto_apply_extras_on_yes("yes", candidate, memory)
        
        # Should not have added any components
        assert result.get("components") is None or len(result.get("components", [])) == 0
        print("✅ AUTH guard working - no extras added for AUTHENTICATION")
        
        # Test with MARKETING category
        memory = {"category": "MARKETING", "wants_header": True}
        candidate = {"category": "MARKETING", "components": []}
        result = _auto_apply_extras_on_yes("yes", candidate, memory)
        
        # Should have added header
        assert "components" in result and len(result["components"]) > 0
        print("✅ Extras working for MARKETING category")
        return True
    except Exception as e:
        print(f"❌ AUTH guard test failed: {e}")
        return False

def test_model_constraints():
    """Test that UserSession model has proper constraints"""
    try:
        from app.models import UserSession
        
        # Check that table args exist
        assert hasattr(UserSession, '__table_args__')
        table_args = UserSession.__table_args__
        assert isinstance(table_args, tuple)
        
        # Should have a unique index
        found_index = False
        for arg in table_args:
            if hasattr(arg, 'name') and 'user_session' in arg.name.lower():
                found_index = True
                break
        
        assert found_index, "Unique constraint not found"
        print("✅ UserSession model has proper constraints")
        return True
    except Exception as e:
        print(f"❌ Model constraint test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🧪 Running critical functionality tests...")
    print("-" * 50)
    
    tests = [
        test_imports,
        test_auth_guard,
        test_model_constraints,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} crashed: {e}")
            failed += 1
        print()
    
    print("-" * 50)
    print(f"📊 Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All tests passed! The fixes are working correctly.")
        return 0
    else:
        print("⚠️  Some tests failed. Check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
