#!/bin/bash

# Interactive Mode Backend - Complete curl Test Suite
# Run this script to test all interactive endpoints

BASE_URL="http://localhost:8001"
PYTHON_PATH="/Applications/git/salman4test2/smartta-final-bot/.venv/bin/python"

echo "🚀 Interactive Mode Backend API Tests"
echo "======================================"
echo ""

# Test 1: Start with Marketing Intent
echo "📝 Test 1: Start Interactive Session (Marketing Intent)"
echo "-------------------------------------------------------"
MARKETING_RESPONSE=$(curl -X POST $BASE_URL/interactive/start \
  -H "Content-Type: application/json" \
  -d '{"intent": "I want to send discount offers to my customers"}' \
  -s)

MARKETING_SESSION=$(echo $MARKETING_RESPONSE | $PYTHON_PATH -c "import sys, json; print(json.load(sys.stdin)['session_id'])")
echo "✅ Session created: $MARKETING_SESSION"
echo "Category auto-detected: $(echo $MARKETING_RESPONSE | $PYTHON_PATH -c "import sys, json; print(json.load(sys.stdin)['draft'].get('category', 'None'))")"
echo "Needs category: $(echo $MARKETING_RESPONSE | $PYTHON_PATH -c "import sys, json; print(json.load(sys.stdin)['needs_category'])")"
echo ""

# Test 2: Start with Auth Intent  
echo "🔐 Test 2: Start Interactive Session (Auth Intent)"
echo "---------------------------------------------------"
AUTH_RESPONSE=$(curl -X POST $BASE_URL/interactive/start \
  -H "Content-Type: application/json" \
  -d '{"intent": "I need to send verification codes to users"}' \
  -s)

AUTH_SESSION=$(echo $AUTH_RESPONSE | $PYTHON_PATH -c "import sys, json; print(json.load(sys.stdin)['session_id'])")
echo "✅ Auth session created: $AUTH_SESSION"
echo "Category auto-detected: $(echo $AUTH_RESPONSE | $PYTHON_PATH -c "import sys, json; print(json.load(sys.stdin)['draft'].get('category', 'None'))")"

# Show header format constraints
echo "Header allowed formats: $(echo $AUTH_RESPONSE | $PYTHON_PATH -c "import sys, json; data=json.load(sys.stdin); header_field=next((f for f in data['fields'] if f['id']=='header'), None); print(header_field['meta']['allowed_formats'] if header_field else 'None')")"
echo "Buttons can_generate: $(echo $AUTH_RESPONSE | $PYTHON_PATH -c "import sys, json; data=json.load(sys.stdin); buttons_field=next((f for f in data['fields'] if f['id']=='buttons'), None); print(buttons_field['can_generate'] if buttons_field else 'None')")"
echo ""

# Test 3: Manual Category Selection
echo "🎯 Test 3: Manual Category Selection"
echo "-------------------------------------"
AMBIGUOUS_RESPONSE=$(curl -X POST $BASE_URL/interactive/start \
  -H "Content-Type: application/json" \
  -d '{"intent": "I want to send messages to my customers"}' \
  -s)

AMBIGUOUS_SESSION=$(echo $AMBIGUOUS_RESPONSE | $PYTHON_PATH -c "import sys, json; print(json.load(sys.stdin)['session_id'])")
echo "✅ Ambiguous session created: $AMBIGUOUS_SESSION"
echo "Needs category: $(echo $AMBIGUOUS_RESPONSE | $PYTHON_PATH -c "import sys, json; print(json.load(sys.stdin)['needs_category'])")"

# Set category manually
CATEGORY_RESPONSE=$(curl -X POST $BASE_URL/interactive/set-category \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$AMBIGUOUS_SESSION\", \"category\": \"UTILITY\"}" \
  -s)

echo "Category set to: $(echo $CATEGORY_RESPONSE | $PYTHON_PATH -c "import sys, json; print(json.load(sys.stdin)['draft'].get('category', 'None'))")"
echo "Needs category now: $(echo $CATEGORY_RESPONSE | $PYTHON_PATH -c "import sys, json; print(json.load(sys.stdin)['needs_category'])")"
echo ""

# Test 4: Field Updates
echo "✏️  Test 4: Field Updates"
echo "-------------------------"

# Update template name
curl -X PUT $BASE_URL/interactive/field \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$MARKETING_SESSION\", \"field_id\": \"name\", \"value\": \"holiday_discount_2024\"}" \
  -s > /dev/null

echo "✅ Updated template name"

# Update body content
BODY_UPDATE=$(curl -X PUT $BASE_URL/interactive/field \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$MARKETING_SESSION\", \"field_id\": \"body\", \"value\": {\"type\": \"BODY\", \"text\": \"Hi {{1}}! 🎉 Enjoy 25% off everything in our holiday sale. Use code HOLIDAY25. Valid until {{2}}. Shop now!\"}}" \
  -s)

echo "✅ Updated body content"
echo "Missing fields: $(echo $BODY_UPDATE | $PYTHON_PATH -c "import sys, json; print(json.load(sys.stdin).get('missing', []))")"
echo ""

# Test 5: LLM Field Generation
echo "🤖 Test 5: LLM Field Generation"
echo "--------------------------------"

# Generate header
HEADER_GEN=$(curl -X POST $BASE_URL/interactive/field/generate \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$MARKETING_SESSION\", \"field_id\": \"header\", \"hints\": \"Holiday sale announcement\", \"brand\": \"MyStore\"}" \
  -s)

echo "✅ Generated header: $(echo $HEADER_GEN | $PYTHON_PATH -c "import sys, json; data=json.load(sys.stdin); header=next((c for c in data['draft'].get('components', []) if c.get('type')=='HEADER'), None); print(header['text'] if header else 'None')")"

# Generate buttons
BUTTONS_GEN=$(curl -X POST $BASE_URL/interactive/field/generate \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$MARKETING_SESSION\", \"field_id\": \"buttons\", \"hints\": \"Quick action buttons for discount offer\", \"brand\": \"MyStore\"}" \
  -s)

echo "✅ Generated buttons: $(echo $BUTTONS_GEN | $PYTHON_PATH -c "import sys, json; data=json.load(sys.stdin); buttons=next((c for c in data['draft'].get('components', []) if c.get('type')=='BUTTONS'), None); print([b['text'] for b in buttons['buttons']] if buttons else 'None')")"

# Generate footer
FOOTER_GEN=$(curl -X POST $BASE_URL/interactive/field/generate \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$MARKETING_SESSION\", \"field_id\": \"footer\", \"hints\": \"Store disclaimer\", \"brand\": \"MyStore\"}" \
  -s)

echo "✅ Generated footer: $(echo $FOOTER_GEN | $PYTHON_PATH -c "import sys, json; data=json.load(sys.stdin); footer=next((c for c in data['draft'].get('components', []) if c.get('type')=='FOOTER'), None); print(footer['text'] if footer else 'None')")"
echo ""

# Test 6: Field Deletion
echo "🗑️  Test 6: Field Deletion"
echo "--------------------------"

DELETE_RESPONSE=$(curl -X DELETE $BASE_URL/interactive/field \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$MARKETING_SESSION\", \"field_id\": \"footer\"}" \
  -s)

echo "✅ Deleted footer field"
echo "Footer after deletion: $(echo $DELETE_RESPONSE | $PYTHON_PATH -c "import sys, json; data=json.load(sys.stdin); footer=next((c for c in data['draft'].get('components', []) if c.get('type')=='FOOTER'), None); print(footer['text'] if footer else 'None')")"
echo ""

# Test 7: Template Finalization
echo "🏁 Test 7: Template Finalization"
echo "---------------------------------"

FINAL_RESPONSE=$(curl -X POST "$BASE_URL/interactive/finalize?session_id=$MARKETING_SESSION" \
  -H "Content-Type: application/json" \
  -s)

echo "✅ Finalization result: $(echo $FINAL_RESPONSE | $PYTHON_PATH -c "import sys, json; data=json.load(sys.stdin); print('SUCCESS' if data.get('ok') else 'FAILED')")"
echo "Issues: $(echo $FINAL_RESPONSE | $PYTHON_PATH -c "import sys, json; print(json.load(sys.stdin).get('issues', []))")"

if [ "$(echo $FINAL_RESPONSE | $PYTHON_PATH -c "import sys, json; print(json.load(sys.stdin).get('ok', False))")" = "True" ]; then
    echo ""
    echo "🎉 Final Template Details:"
    echo "Name: $(echo $FINAL_RESPONSE | $PYTHON_PATH -c "import sys, json; print(json.load(sys.stdin)['payload']['name'])")"
    echo "Category: $(echo $FINAL_RESPONSE | $PYTHON_PATH -c "import sys, json; print(json.load(sys.stdin)['payload']['category'])")"
    echo "Language: $(echo $FINAL_RESPONSE | $PYTHON_PATH -c "import sys, json; print(json.load(sys.stdin)['payload']['language'])")"
    echo "Components: $(echo $FINAL_RESPONSE | $PYTHON_PATH -c "import sys, json; print(len(json.load(sys.stdin)['payload']['components']))")"
fi

echo ""
echo "✅ All Interactive Mode API tests completed!"
echo ""
echo "📚 Quick Reference - Interactive API Endpoints:"
echo "================================================"
echo ""
echo "1. Start Session:"
echo "   curl -X POST $BASE_URL/interactive/start \\"
echo "     -H \"Content-Type: application/json\" \\"
echo "     -d '{\"intent\": \"send discount offers\"}'"
echo ""
echo "2. Set Category:"
echo "   curl -X POST $BASE_URL/interactive/set-category \\"
echo "     -H \"Content-Type: application/json\" \\"
echo "     -d '{\"session_id\": \"UUID\", \"category\": \"MARKETING\"}'"
echo ""
echo "3. Update Field:"
echo "   curl -X PUT $BASE_URL/interactive/field \\"
echo "     -H \"Content-Type: application/json\" \\"
echo "     -d '{\"session_id\": \"UUID\", \"field_id\": \"name\", \"value\": \"template_name\"}'"
echo ""
echo "4. Generate Field:"
echo "   curl -X POST $BASE_URL/interactive/field/generate \\"
echo "     -H \"Content-Type: application/json\" \\"
echo "     -d '{\"session_id\": \"UUID\", \"field_id\": \"header\", \"hints\": \"sale announcement\"}'"
echo ""
echo "5. Delete Field:"
echo "   curl -X DELETE $BASE_URL/interactive/field \\"
echo "     -H \"Content-Type: application/json\" \\"
echo "     -d '{\"session_id\": \"UUID\", \"field_id\": \"footer\"}'"
echo ""
echo "6. Finalize Template:"
echo "   curl -X POST \"$BASE_URL/interactive/finalize?session_id=UUID\" \\"
echo "     -H \"Content-Type: application/json\""
echo ""
