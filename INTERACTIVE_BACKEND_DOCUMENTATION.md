# Interactive Mode Backend Implementation

## Overview

The Interactive Mode backend provides a field-by-field editing interface for WhatsApp template creation. It's designed to be fully backend-driven, with the UI acting as a renderer for field descriptors and validation state returned by the API.

## Architecture

### Module Structure
```
app/interactive/
├── __init__.py          # Module exports
└── routes.py           # API endpoints and core logic
```

### Key Components

1. **Field Descriptors**: Dynamic field configuration based on template category
2. **Category Constraints**: Business rules enforcement (AUTH, MARKETING, UTILITY)
3. **LLM Field Generation**: Context-aware content generation for individual fields
4. **Validation Integration**: Real-time validation using existing schema and lint rules

## API Endpoints

### POST /interactive/start
Start interactive template creation with intent analysis.

**Request:**
```json
{
  "intent": "I want to send discount offers to my customers",
  "session_id": "optional-existing-session",
  "user_id": "optional-user-id"
}
```

**Response:**
```json
{
  "session_id": "uuid",
  "needs_category": false,
  "fields": [
    {
      "id": "category",
      "label": "Category",
      "required": true,
      "can_delete": false,
      "can_generate": false,
      "value": "MARKETING",
      "meta": {"enum": ["MARKETING", "UTILITY", "AUTHENTICATION"]}
    },
    // ... more fields
  ],
  "draft": {"category": "MARKETING", "language": "en_US", ...},
  "issues": [],
  "missing": []
}
```

### POST /interactive/set-category
Manually set template category when auto-detection fails.

**Request:**
```json
{
  "session_id": "uuid",
  "category": "UTILITY"
}
```

### PUT /interactive/field
Update a field value.

**Request:**
```json
{
  "session_id": "uuid",
  "field_id": "body",
  "value": {
    "type": "BODY",
    "text": "Hi {{1}}, your order {{2}} is ready!"
  }
}
```

### POST /interactive/field/generate
Generate content for a specific field using LLM.

**Request:**
```json
{
  "session_id": "uuid",
  "field_id": "header",
  "hints": "Professional appointment reminder",
  "brand": "HealthCare Clinic"
}
```

### DELETE /interactive/field
Delete an optional field.

**Request:**
```json
{
  "session_id": "uuid",
  "field_id": "footer"
}
```

### POST /interactive/finalize
Validate and finalize the template.

**Response:**
```json
{
  "ok": true,
  "issues": [],
  "payload": {
    "name": "appointment_reminder",
    "language": "en_US",
    "category": "UTILITY",
    "components": [...]
  }
}
```

## Category Constraints

The system enforces Meta's WhatsApp Cloud API rules through category-specific constraints:

### AUTHENTICATION
- **Headers**: TEXT format only
- **Buttons**: Not allowed
- **Footer**: Not allowed
- **Use cases**: OTP, verification codes, security messages

### MARKETING
- **Headers**: All formats (TEXT, IMAGE, VIDEO, DOCUMENT, LOCATION)
- **Buttons**: Allowed (QUICK_REPLY only in interactive mode)
- **Footer**: Allowed
- **Use cases**: Promotions, offers, announcements

### UTILITY
- **Headers**: All formats (TEXT, IMAGE, VIDEO, DOCUMENT, LOCATION)
- **Buttons**: Allowed (QUICK_REPLY only in interactive mode)
- **Footer**: Allowed
- **Use cases**: Updates, reminders, confirmations

## Field Descriptors

Each field descriptor provides metadata for UI rendering:

```python
class FieldDescriptor:
    id: str                    # Field identifier
    label: str                 # Display name
    required: bool             # Cannot be empty
    can_delete: bool           # Can be removed
    can_generate: bool         # Can use LLM generation
    value: Optional[Any]       # Current value
    meta: Dict[str, Any]       # Additional constraints/hints
```

### Field Types

1. **Core Fields** (always present):
   - `category`: Template category selection
   - `language`: Language code (defaults to en_US)
   - `name`: Template name (snake_case)
   - `body`: Main message content (required)

2. **Optional Components**:
   - `header`: Title/media header
   - `footer`: Sign-off text
   - `buttons`: Quick reply actions

## LLM Field Generation

The system uses a specialized prompt for field-level generation:

### Generation Rules
- Respects category constraints (e.g., AUTH → TEXT headers only)
- Follows Meta's format requirements (header ≤60 chars)
- Uses proper placeholder sequences ({{1}}, {{2}}, etc.)
- Generates context-appropriate content based on hints and brand

### Generation Context
```json
{
  "category": "MARKETING",
  "language": "en_US",
  "brand": "MyStore",
  "field_id": "header",
  "current_payload": {...},
  "config": {...},
  "hints": "Holiday sale announcement"
}
```

## Intent Analysis

The `/start` endpoint includes basic intent classification:

### Keywords → Categories
- **MARKETING**: offer, promo, greeting, festival, campaign, discount, sale
- **UTILITY**: update, reminder, notification, status, confirmation, appointment
- **AUTHENTICATION**: otp, verify, verification, code, login, security

### Fallback Behavior
If category cannot be determined from intent:
- Set `needs_category: true`
- UI shows category dropdown
- User selects manually via `/set-category`

## Configuration Integration

The interactive mode reads constraints from `config/whatsapp.yaml`:

```yaml
lint_rules:
  category_constraints:
    AUTHENTICATION:
      allow_buttons: false
      allow_footer: false
      allowed_header_formats: [TEXT]
    MARKETING:
      allow_buttons: true
      allow_footer: true
      allowed_header_formats: [TEXT, IMAGE, VIDEO, DOCUMENT, LOCATION]
```

## Error Handling

### Validation Errors
- Real-time validation using existing `validate_schema()` and `lint_rules()`
- Issues reported in every response
- Missing required fields tracked separately

### Generation Failures
- LLM errors return HTTP 400 with descriptive messages
- Graceful fallback allows manual editing
- Context preserved for retry attempts

## Testing

### Test Coverage
1. **Unit Tests**: Field descriptors, value application, validation
2. **Integration Tests**: Complete user journeys for each category
3. **Generation Tests**: LLM field generation and constraint compliance

### Test Files
- `test_interactive_backend.py`: Core functionality tests
- `test_interactive_integration.py`: End-to-end workflow tests
- `test_field_generation.py`: LLM generation validation

## UI Integration Notes

### Backend-Driven Design
- UI never invents business rules or field types
- All validation messages come from backend
- Field availability determined by `can_generate`/`can_delete` flags

### Header Format Handling
- UI shows format selector with options from `meta.allowed_formats`
- TEXT format shows text input
- Other formats show example/media ID input

### Button Defaults
- Generation uses YAML config defaults (no hardcoding)
- Buttons limited to QUICK_REPLY type in interactive mode
- URL/PHONE buttons can be added post-generation if needed

## Security Considerations

### Input Validation
- All field values validated against schema
- Category switching triggers constraint re-evaluation
- Required fields cannot be deleted

### LLM Safety
- Field generation prompts include safety constraints
- Output validated before applying to draft
- User can always override generated content

## Performance Notes

### Database Efficiency
- Single draft per session updated incrementally
- Field changes trigger immediate persistence
- Validation runs on every state change

### LLM Usage
- Field-level generation reduces token usage
- Context includes only relevant current state
- Temperature controlled for consistent output

## Future Enhancements

### Planned Features
1. **Template Previews**: Real-time WhatsApp-style preview rendering
2. **Bulk Operations**: Apply changes to multiple fields simultaneously
3. **Template Library**: Save/load field combinations as templates
4. **Advanced Validation**: Cross-field dependency checks
5. **Collaboration**: Multi-user editing with conflict resolution

### Extension Points
- Custom field types via plugin system
- Additional LLM providers for generation
- Webhook integration for external validation
- Template import/export functionality

## Getting Started

### Quick Test
```bash
# Start the backend
python -m uvicorn app.main:app --reload

# Test interactive endpoints
curl -X POST http://localhost:8000/interactive/start \\
  -H "Content-Type: application/json" \\
  -d '{"intent": "send discount offers"}'
```

### Development Setup
1. Ensure all dependencies installed: `pip install -r requirements.txt`
2. Configure environment: Copy `.env.example` to `.env`
3. Run tests: `python test_interactive_integration.py`
4. Check API docs: `http://localhost:8000/docs#tag/interactive`

The Interactive Mode backend provides a robust, flexible foundation for building sophisticated template creation interfaces while maintaining strict compliance with WhatsApp's requirements.
