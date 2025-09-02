#!/usr/bin/env python3
"""
Test Runner - Runs all tests in the tests folder
"""

import os
import sys
import subprocess
import time
from pathlib import Path

def run_all_tests():
    """Run all Python test files in the tests directory"""
    tests_dir = Path(__file__).parent / "tests"
    
    if not tests_dir.exists():
        print("❌ Tests directory not found!")
        return False
    
    # Get all Python test files
    test_files = list(tests_dir.glob("test_*.py"))
    
    if not test_files:
        print("❌ No test files found in tests directory!")
        return False
    
    print(f"🚀 Found {len(test_files)} test files")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for test_file in sorted(test_files):
        print(f"\n📝 Running: {test_file.name}")
        print("-" * 40)
        
        try:
            # Run the test file using pytest
            python_path = Path(__file__).parent / ".venv" / "bin" / "python"
            if not python_path.exists():
                python_path = sys.executable
            
            result = subprocess.run(
                [str(python_path), "-m", "pytest", str(test_file), "-v", "-k", "not trio"],
                cwd=tests_dir.parent,
                capture_output=True,
                text=True,
                timeout=120  # 2 minute timeout per test
            )
            
            if result.returncode == 0:
                print(f"✅ PASSED: {test_file.name}")
                passed += 1
            else:
                print(f"❌ FAILED: {test_file.name}")
                if result.stderr:
                    print(f"Error: {result.stderr[:500]}...")
                failed += 1
                
        except subprocess.TimeoutExpired:
            print(f"⏰ TIMEOUT: {test_file.name}")
            failed += 1
        except Exception as e:
            print(f"💥 EXCEPTION: {test_file.name} - {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    print(f"Total Tests: {len(test_files)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success Rate: {(passed/len(test_files))*100:.1f}%")
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED!")
        return True
    else:
        print(f"\n⚠️ {failed} tests failed. Check output above.")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
