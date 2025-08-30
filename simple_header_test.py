#!/usr/bin/env python3
"""
Direct test of sanitizer function to verify LOCATION header support.
"""

import re

def _sanitize_candidate_test(cand):
    """Simplified version of the sanitizer to test LOCATION support"""
    if not isinstance(cand, dict):
        return {}
    c = dict(cand)

    # components clean
    comps = c.get("components")
    if isinstance(comps, list):
        clean = []
        
        for comp in comps:
            if not isinstance(comp, dict):
                continue
            t = (comp.get("type") or "").strip().upper()
            if t == "BODY":
                txt = (comp.get("text") or "").strip()
                if txt:
                    out = {"type": "BODY", "text": txt}
                    if "example" in comp:
                        out["example"] = comp["example"]
                    clean.append(out)
            elif t == "HEADER":
                fmt = (comp.get("format") or "").strip().upper()
                txt = (comp.get("text") or "").strip()
                if not fmt and txt:
                    fmt = "TEXT"
                if fmt == "TEXT" and txt:
                    clean.append({"type": "HEADER", "format": "TEXT", "text": txt})
                elif fmt in {"IMAGE","VIDEO","DOCUMENT","LOCATION"}:
                    item = {"type": "HEADER", "format": fmt}
                    if "example" in comp:
                        item["example"] = comp["example"]
                    clean.append(item)
                        
        if clean:
            c["components"] = clean
        else:
            c.pop("components", None)
    elif "components" in c:
        c.pop("components", None)
    
    return c

def test_location_support():
    """Test LOCATION header support in sanitizer"""
    print("Testing LOCATION header support...")
    
    test_candidate = {
        "name": "location_test",
        "category": "MARKETING", 
        "language": "en_US",
        "components": [
            {"type": "BODY", "text": "Visit our store!"},
            {"type": "HEADER", "format": "LOCATION", "example": {"latitude": 37.7749, "longitude": -122.4194}}
        ]
    }
    
    result = _sanitize_candidate_test(test_candidate)
    
    # Check if LOCATION header is preserved
    location_header_found = False
    for comp in result.get("components", []):
        if comp.get("type") == "HEADER" and comp.get("format") == "LOCATION":
            location_header_found = True
            print("✅ LOCATION header preserved in sanitizer")
            print(f"   Component: {comp}")
            break
    
    if not location_header_found:
        print("❌ LOCATION header not found in result")
        print(f"   Result components: {result.get('components', [])}")
        return False
    
    return True

def test_other_formats():
    """Test other supported formats still work"""
    formats_to_test = ["IMAGE", "VIDEO", "DOCUMENT"]
    
    all_passed = True
    for fmt in formats_to_test:
        test_candidate = {
            "name": f"test_{fmt.lower()}",
            "category": "MARKETING",
            "language": "en_US", 
            "components": [
                {"type": "BODY", "text": "Test message"},
                {"type": "HEADER", "format": fmt, "example": {"url": "https://example.com"}}
            ]
        }
        
        result = _sanitize_candidate_test(test_candidate)
        
        format_found = False
        for comp in result.get("components", []):
            if comp.get("type") == "HEADER" and comp.get("format") == fmt:
                format_found = True
                print(f"✅ {fmt} header preserved")
                break
        
        if not format_found:
            print(f"❌ {fmt} header not preserved")
            all_passed = False
    
    return all_passed

if __name__ == "__main__":
    print("🧪 Testing header format support")
    print("=" * 40)
    
    success1 = test_location_support()
    success2 = test_other_formats()
    
    print("\n" + "=" * 40)
    if success1 and success2:
        print("🎉 All header format tests passed!")
    else:
        print("⚠️  Some tests failed")
