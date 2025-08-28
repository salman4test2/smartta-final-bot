# UI Integration Guide - WhatsApp Template Builder

## 🚀 Production Ready APIs

### Base URL: `http://your-domain:8002`

## 📋 API Endpoints

### 1. Create New Session
```http
GET /session/new
```
**Response:**
```json
{
  "session_id": "uuid-string"
}
```

### 2. Send Chat Message
```http
POST /chat
Content-Type: application/json

{
  "message": "user input text",
  "session_id": "uuid-string"
}
```
**Response:**
```json
{
  "session_id": "uuid-string",
  "reply": "bot response text",
  "draft": {
    "category": "MARKETING",
    "language": "en_US", 
    "name": "template_name",
    "components": [...]
  },
  "missing": ["field1", "field2"] // or null if complete,
  "final_creation_payload": {...} // or null if not ready
}
```

### 3. Get Chat History (NEW!)
```http
GET /session/{session_id}
```
**Response:**
```json
{
  "session_id": "uuid-string",
  "messages": [
    {
      "role": "user",
      "content": "user message text"
    },
    {
      "role": "assistant", 
      "content": "bot response text"
    }
  ],
  "draft": {...current template state...},
  "memory": {...conversation context...},
  "last_action": "ASK|DRAFT|FINAL",
  "updated_at": "2025-08-28T20:30:37"
}
```

### 4. Debug Session Data (NEW!)
```http
GET /session/{session_id}/debug
```
**Purpose:** Complete session information for troubleshooting and development
**Response:**
```json
{
  "session_id": "uuid-string",
  "session_info": {
    "id": "session_id",
    "active_draft_id": "uuid",
    "total_messages": 6,
    "total_llm_calls": 6,
    "created_at": "2025-08-28T20:48:50.938091+00:00"
  },
  "messages": [...], // Same as endpoint #3
  "current_draft": {...}, // Latest template state
  "memory": {...}, // AI conversation memory
  "llm_logs": [
    {
      "timestamp": "2025-08-28T20:48:50.938091+00:00",
      "direction": "request|response",
      "payload": {...}, // Complete LLM request/response
      "model": "gpt-4o-mini",
      "latency_ms": 3953
    }
  ],
  "last_action": "FINAL",
  "updated_at": "2025-08-28T20:48:50.938091+00:00"
}
```

### 5. Health Check
```http
GET /health
```
**Response:**
```json
{
  "status": "ok",
  "model": "gpt-4o-mini", 
  "db": "ok"
}
```

## 💡 UI Implementation Guide

### Chat Interface Setup

1. **Initialize New Chat:**
```javascript
// Create new session
const response = await fetch('/session/new');
const { session_id } = await response.json();

// Store in component state
this.sessionId = session_id;
this.messages = [];
```

2. **Load Existing Chat:**
```javascript
// Resume existing session
const response = await fetch(`/session/${sessionId}`);
const sessionData = await response.json();

// Populate chat UI
this.messages = sessionData.messages;
this.currentDraft = sessionData.draft;
```

3. **Display Messages:**
```javascript
sessionData.messages.forEach(message => {
  if (message.role === 'user') {
    // Render user message bubble (right side)
    addUserMessage(message.content);
  } else {
    // Render bot message bubble (left side)  
    addBotMessage(message.content);
  }
});
```

4. **Send Message:**
```javascript
async function sendMessage(userInput) {
  // Add user message to UI immediately
  addUserMessage(userInput);
  
  // Send to API
  const response = await fetch('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: userInput,
      session_id: this.sessionId
    })
  });
  
  const data = await response.json();
  
  // Add bot response
  addBotMessage(data.reply);
  
  // Check completion status
  if (data.final_creation_payload) {
    // Template is complete!
    showTemplateComplete(data.final_creation_payload);
  } else if (data.missing) {
    // Show progress indicator
    showProgress(data.missing);
  }
}
```

5. **Progress Indicator:**
```javascript
function showProgress(missing) {
  if (!missing || missing.length === 0) {
    // Template complete
    showStatus("✅ Template Ready");
  } else {
    // Show what's still needed
    showStatus(`📝 Still need: ${missing.join(', ')}`);
  }
}
```

## 🎨 UI/UX Recommendations

### Chat Bubbles
- **User messages**: Right-aligned, blue background
- **Bot messages**: Left-aligned, gray background  
- **System notifications**: Center-aligned, subtle styling

### Template Preview
When `final_creation_payload` is received:
- Show WhatsApp template preview
- Display category, language, name
- Render components (HEADER, BODY, FOOTER, BUTTONS)
- Highlight placeholder variables like `{{1}}`, `{{2}}`

### Progress Tracking
- Visual progress bar based on `missing` array
- Check marks for completed fields
- Clear labels for what's still needed

### Session Management  
- Allow users to bookmark/share session URLs
- Implement auto-save (state preserved in database)
- Support resuming conversations from any point

## 🔧 Error Handling

```javascript
try {
  const response = await fetch('/chat', {...});
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  const data = await response.json();
  // Handle success
} catch (error) {
  // Show user-friendly error message
  showError("Sorry, something went wrong. Please try again.");
}
```

## 🐛 Debugging & Troubleshooting

### Using the Debug Endpoint

The debug endpoint provides complete session information for troubleshooting user issues:

```javascript
// Get complete session debug data
async function debugSession(sessionId) {
  const response = await fetch(`/session/${sessionId}/debug`);
  const debugData = await response.json();
  
  console.log('Session Info:', debugData.session_info);
  console.log('All Messages:', debugData.messages);
  console.log('Current Template:', debugData.current_draft);
  console.log('AI Memory:', debugData.memory);
  console.log('LLM API Calls:', debugData.llm_logs);
  
  return debugData;
}
```

### Debug Use Cases

1. **User Reports "Not Working"**
   - Get session ID from user
   - Call debug endpoint to see conversation history
   - Check `llm_logs` for API errors or timeouts
   - Review `memory` state for context issues

2. **Template Not Completing** 
   - Check `current_draft` for missing fields
   - Review `messages` to see what user provided
   - Look at `last_action` to understand AI state

3. **Performance Issues**
   - Check `latency_ms` in `llm_logs` 
   - Count `total_llm_calls` vs `total_messages`
   - Monitor session creation timestamps

4. **Content Quality Issues**
   - Review LLM request/response in `llm_logs.payload`
   - Check prompt context and user input
   - Verify AI responses match expected format

### Development Tools

```javascript
// Add debug panel to your UI (development only)
function showDebugPanel(sessionId) {
  const debugButton = document.createElement('button');
  debugButton.textContent = '🐛 Debug Session';
  debugButton.onclick = async () => {
    const data = await debugSession(sessionId);
    console.table(data.session_info);
    
    // Show in modal or side panel
    showDebugModal(data);
  };
  
  document.body.appendChild(debugButton);
}
```

## 📱 Mobile Considerations

- Responsive chat interface
- Touch-friendly message bubbles
- Auto-scroll to latest message
- Loading indicators for API calls
- Offline state handling

## 🚀 Production Notes

- All endpoints return proper HTTP status codes
- Database is PostgreSQL (Neon) for scalability
- Session data persists across browser refreshes
- No authentication required (add if needed)
- CORS headers may need configuration for production domain
