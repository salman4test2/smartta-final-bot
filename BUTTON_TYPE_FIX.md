# Button Type Validation Fix

## Issue
The system was generating invalid button types like `type: "reply"` which are not supported by the WhatsApp Business API.

## Valid WhatsApp Button Types
According to the WhatsApp Business API documentation, only these button types are valid:
- `QUICK_REPLY` - for interactive quick reply buttons
- `URL` - for buttons that open web links  
- `PHONE_NUMBER` - for buttons that initiate phone calls

## Solution
Added button type normalization in two key locations in `app/main.py`:

### 1. Component Button Processing (Lines ~430-440)
Normalizes button types when processing BUTTONS components:
```python
# Normalize invalid button types to valid WhatsApp API types
if btn_type.lower() in ("reply", "button"):
    btn_type = "QUICK_REPLY"
elif btn_type.upper() not in ("QUICK_REPLY", "URL", "PHONE_NUMBER"):
    btn_type = "QUICK_REPLY"  # Default fallback
```

### 2. Root-Level Button Conversion (Lines ~550-560)
Normalizes button types when converting root-level buttons to components:
```python
# Normalize invalid button types to valid WhatsApp API types
if btn_type.lower() in ("reply", "button"):
    btn_type = "QUICK_REPLY"
elif btn_type.upper() not in ("QUICK_REPLY", "URL", "PHONE_NUMBER"):
    btn_type = "QUICK_REPLY"  # Default fallback
```

### 3. Special Reply Format Handling
Converts the LLM's reply format to standard format:
```python
if btn.get("type") == "reply" and btn.get("reply"):
    # Convert reply format to standard format
    reply = btn["reply"]
    normalized_btn = {
        "type": "QUICK_REPLY",
        "text": reply.get("title") or reply.get("text", "Button")
    }
    if reply.get("id"):
        normalized_btn["payload"] = reply["id"]
```

## Test Results
✅ All invalid button types are correctly normalized:
- `"reply"` → `"QUICK_REPLY"`
- `"button"` → `"QUICK_REPLY"`  
- `"BUTTON"` → `"QUICK_REPLY"`
- `"click"` → `"QUICK_REPLY"`
- `"invalid_type"` → `"QUICK_REPLY"`
- `"QUICK_REPLY"` → `"QUICK_REPLY"` (unchanged)
- `"URL"` → `"URL"` (unchanged)

## Impact
- ✅ All generated templates now use valid WhatsApp API button types
- ✅ No more API rejection due to invalid button types
- ✅ Backward compatibility maintained
- ✅ Future-proof against new invalid types from LLM responses

## Configuration Reference
Button type validation is defined in `config/whatsapp.yaml`:
```yaml
properties:
  type: { type: string, enum: [QUICK_REPLY, URL, PHONE_NUMBER] }
```

This ensures the system strictly adheres to WhatsApp Business API specifications.
