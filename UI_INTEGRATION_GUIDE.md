# UI Integration Guide - WhatsApp Template Builder

## 🚀 Production Ready APIs

### Base URL
`https://smartta-final-bot-1.onrender.com`

## 💡 Session Naming Feature

The backend supports **session naming** functionality where users can:

1. **Create sessions with custom names** like "Diwali Template Creation", "Restaurant Promotion"
2. **Auto-naming**: If no name is provided, the system automatically generates a meaningful name based on the first user message
3. **Update session names** later using the PUT endpoint
4. **List all sessions** for a user, ordered by last activity time

### How Session Naming Works:

- **Manual Naming**: When creating a session via `POST /session/new`, provide a `session_name`
- **Auto Naming**: If no name is provided, the system analyzes the first chat message to generate a meaningful name
- **User Association**: Sessions can be associated with users to enable session management and retrieval

---

## 📋 API Endpoints

### 1. User Management

#### Create New User
```http
POST /users
Content-Type: application/json

{
  "user_id": "your_unique_user_id",
  "password": "your_password"
}
```
**Response:**
```json
{
  "user_id": "your_unique_user_id",
  "created_at": "2025-08-29T12:00:00Z",
  "updated_at": "2025-08-29T12:00:00Z"
}
```

#### User Login
```http
POST /users/login
Content-Type: application/json

{
  "user_id": "your_unique_user_id",
  "password": "your_password"
}
```
**Response:**
```json
{
  "user_id": "your_unique_user_id",
  "message": "Login successful",
  "created_at": "2025-08-29T12:00:00Z",
  "updated_at": "2025-08-29T12:00:00Z"
}
```

#### Get User Sessions
```http
GET /users/{user_id}/sessions
```
**Response:**
```json
{
  "user_id": "your_unique_user_id",
  "total_sessions": 5,
  "sessions": [
    {
      "session_id": "uuid-string",
      "session_name": "Restaurant Promotion Template",
      "created_at": "2025-08-29T10:00:00Z",
      "updated_at": "2025-08-29T11:30:00Z",
      "message_count": 8,
      "last_activity": "2025-08-29T11:30:00Z"
    }
  ]
}
```

#### Update Session Name
```http
PUT /users/{user_id}/sessions/{session_id}/name?session_name=My%20Custom%20Template%20Name
```
**Response:**
```json
{
  "message": "Session name updated successfully",
  "session_name": "My Custom Template Name"
}
```

### 2. Session Management

#### Create New Session (GET - Backward Compatible)
```http
GET /session/new?user_id=your_user_id
```
**Response:**
```json
{
  "session_id": "uuid-string"
}
```

#### Create New Session with Name (POST - Recommended)
```http
POST /session/new
Content-Type: application/json

{
  "user_id": "your_user_id",
  "session_name": "Diwali Template Creation"
}
```
**Response:**
```json
{
  "session_id": "uuid-string",
  "session_name": "Diwali Template Creation",
  "user_id": "your_user_id"
}
```

**Note:** If no session_name is provided but user_id is given, the system will automatically generate a meaningful name based on the first message sent (e.g., "Restaurant Promotion Template").

### 3. Chat Interface

#### Send Chat Message
```http
POST /chat
Content-Type: application/json

{
  "message": "user input text",
  "session_id": "uuid-string",
  "user_id": "your_user_id"  // Optional: associates message with user
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

### 4. Get Chat History (NEW!)
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

**Note:** This endpoint is useful for resuming conversations and understanding the current state of template creation. The `last_action` field indicates whether the template is still being built ("ASK", "DRAFT") or finalized ("FINAL").

### 5. Debug Session Data (NEW!)
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

### 6. Health Check
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

### User Authentication Flow

1. **User Registration:**
```javascript
async function registerUser(userId, password) {
  const response = await fetch('/users', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, password: password })
  });
  
  if (response.ok) {
    const userData = await response.json();
    localStorage.setItem('user_id', userData.user_id);
    return userData;
  } else {
    throw new Error('Registration failed');
  }
}
```

2. **User Login:**
```javascript
async function loginUser(userId, password) {
  const response = await fetch('/users/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, password: password })
  });
  
  if (response.ok) {
    const userData = await response.json();
    localStorage.setItem('user_id', userData.user_id);
    return userData;
  } else {
    throw new Error('Invalid credentials');
  }
}
```

3. **Load User Sessions:**
```javascript
async function loadUserSessions(userId) {
  const response = await fetch(`/users/${userId}/sessions`);
  const data = await response.json();
  
  // Display sessions ordered by last activity
  data.sessions.forEach(session => {
    addSessionToUI({
      id: session.session_id,
      name: session.session_name || 'Untitled Template',
      lastActivity: session.last_activity,
      messageCount: session.message_count
    });
  });
  
  return data;
}
```

4. **Create New Session for User:**
```javascript
// Method 1: Create session with custom name
async function createNamedUserSession(userId, sessionName) {
  const response = await fetch('/session/new', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ 
      user_id: userId, 
      session_name: sessionName 
    })
  });
  
  const data = await response.json();
  return {
    sessionId: data.session_id,
    sessionName: data.session_name,
    userId: data.user_id
  };
}

// Method 2: Create session without name (will auto-generate from first message)
async function createAutoNamedUserSession(userId) {
  const response = await fetch('/session/new', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId })
  });
  
  const data = await response.json();
  return data.session_id;
}

// Example usage:
const sessionData = await createNamedUserSession('user123', 'Diwali Celebration Template');
console.log(`Created session: ${sessionData.sessionId} named "${sessionData.sessionName}"`);
```

### Chat Interface Setup

1. **Initialize New Chat:**
```javascript
// Method 1: Simple session creation (no name, no user association)
const response = await fetch('/session/new');
const { session_id } = await response.json();

// Method 2: Create session with user and custom name
const namedResponse = await fetch('/session/new', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    user_id: 'user123',
    session_name: 'Diwali Template Creation'
  })
});
const namedSessionData = await namedResponse.json();

// Store in component state
this.sessionId = namedSessionData.session_id;
this.sessionName = namedSessionData.session_name;
this.userId = namedSessionData.user_id;
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
  
  // Send to API (include user_id if available for better session management)
  const response = await fetch('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: userInput,
      session_id: this.sessionId,
      user_id: this.userId  // Optional: for user association and auto-naming
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

## 🎯 Complete Session Naming Workflow Example

Here's a complete example showing how to implement session naming in your frontend:

```javascript
class TemplateBuilder {
  constructor() {
    this.userId = localStorage.getItem('user_id');
    this.sessionId = null;
    this.sessionName = null;
  }

  // Step 1: Create a named session
  async createNewTemplate(templateName = null) {
    const sessionData = {
      user_id: this.userId,
      session_name: templateName || null  // Let backend auto-generate if null
    };

    const response = await fetch('/session/new', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(sessionData)
    });

    const result = await response.json();
    
    this.sessionId = result.session_id;
    this.sessionName = result.session_name;
    
    // Update UI
    this.updateSessionTitle(this.sessionName || 'New Template');
    
    return result;
  }

  // Step 2: Send messages (auto-naming happens here if no name was provided)
  async sendMessage(message) {
    const response = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: message,
        session_id: this.sessionId,
        user_id: this.userId
      })
    });

    const result = await response.json();
    
    // If this was the first message and no name was provided,
    // the backend may have auto-generated a name
    if (!this.sessionName) {
      // Refresh session info to get auto-generated name
      await this.refreshSessionInfo();
    }
    
    return result;
  }

  // Step 3: Refresh session info to get auto-generated name
  async refreshSessionInfo() {
    const response = await fetch(`/session/${this.sessionId}`);
    const sessionData = await response.json();
    
    // Check if we have a user session with a name
    if (this.userId) {
      const userSessionsResponse = await fetch(`/users/${this.userId}/sessions`);
      const userSessions = await userSessionsResponse.json();
      
      const currentSession = userSessions.sessions.find(s => s.session_id === this.sessionId);
      if (currentSession && currentSession.session_name) {
        this.sessionName = currentSession.session_name;
        this.updateSessionTitle(this.sessionName);
      }
    }
  }

  // Step 4: Allow users to rename sessions
  async renameSession(newName) {
    const encodedName = encodeURIComponent(newName);
    const response = await fetch(`/users/${this.userId}/sessions/${this.sessionId}/name?session_name=${encodedName}`, {
      method: 'PUT'
    });

    if (response.ok) {
      const result = await response.json();
      this.sessionName = result.session_name;
      this.updateSessionTitle(this.sessionName);
      return result;
    } else {
      throw new Error('Failed to rename session');
    }
  }

  // Step 5: Load all user sessions
  async loadUserSessions() {
    const response = await fetch(`/users/${this.userId}/sessions`);
    const data = await response.json();
    
    const sessionList = data.sessions.map(session => ({
      id: session.session_id,
      name: session.session_name || 'Untitled Template',
      lastActivity: new Date(session.last_activity),
      messageCount: session.message_count
    }));

    // Sort by last activity (most recent first)
    sessionList.sort((a, b) => b.lastActivity - a.lastActivity);
    
    return sessionList;
  }

  updateSessionTitle(title) {
    // Update UI with session name
    document.getElementById('session-title').textContent = title;
  }
}

// Usage examples:
const builder = new TemplateBuilder();

// Create a session with a specific name
await builder.createNewTemplate('Diwali Festival Promotion');

// Create a session without a name (will auto-generate from first message)
await builder.createNewTemplate();
await builder.sendMessage('I want to create a restaurant promotion template');
// Backend will auto-generate something like "Restaurant Promotion Template"

// Rename an existing session
await builder.renameSession('Updated Restaurant Campaign');

// Load all user sessions for the sidebar
const sessions = await builder.loadUserSessions();
```

### Session Naming Best Practices

1. **Descriptive Names**: Use names like "Diwali Festival Sale", "Restaurant Weekend Special", "Appointment Reminder"
2. **Auto-naming Fallback**: Always allow auto-naming as a fallback for users who don't want to name sessions
3. **Editing Names**: Provide UI for users to rename sessions later
4. **Session List**: Show sessions with names in a sidebar or dashboard, ordered by activity
5. **Character Limits**: Consider limiting session names to 50-100 characters for UI display

### UI Components for Session Naming

```html
<!-- Session Creation Dialog -->
<div class="session-create-dialog">
  <h3>Create New Template</h3>
  <input 
    type="text" 
    placeholder="Template name (optional)"
    id="session-name-input"
    maxlength="80"
  />
  <button onclick="createNamedSession()">Create Template</button>
  <small>Leave blank to auto-generate name from your first message</small>
</div>

<!-- Session Title with Edit Option -->
<div class="session-header">
  <h2 id="session-title" onclick="editSessionName()">Loading...</h2>
  <button class="edit-btn" onclick="editSessionName()">✏️</button>
</div>

<!-- Session List Sidebar -->
<div class="sessions-sidebar">
  <h3>Your Templates</h3>
  <div id="sessions-list">
    <!-- Populated dynamically -->
  </div>
</div>
```
## 🚀 Production Notes

- All endpoints return proper HTTP status codes
- Database is PostgreSQL (Neon) for scalability
- Session data persists across browser refreshes
- No authentication required (add if needed)
- CORS headers may need configuration for production domain

## 📝 Session Naming Summary

### ✅ What's Working

The session naming functionality is fully implemented and tested:

1. **✅ Manual Session Naming**: Create sessions with custom names like "Diwali Template Creation"
2. **✅ Auto-naming**: Sessions automatically get meaningful names from first user message
3. **✅ Session Renaming**: Users can update session names anytime
4. **✅ Session Listing**: All user sessions displayed with names, ordered by activity
5. **✅ User Association**: Sessions properly linked to users for management

### 🎯 Implementation Checklist

For frontend developers implementing this feature:

**Backend Integration:**
- [x] User registration and login endpoints
- [x] Session creation with name support (`POST /session/new`)
- [x] Auto-naming from first chat message
- [x] Session name updates (`PUT /users/{user_id}/sessions/{session_id}/name`)
- [x] User session listing (`GET /users/{user_id}/sessions`)

**Frontend Components Needed:**
- [ ] User registration/login forms
- [ ] Session creation dialog with optional name input
- [ ] Session list sidebar with rename functionality
- [ ] Session header with editable title
- [ ] Chat interface with user association

**Example Session Names Generated:**
- "Black Friday Sale Electronics Template" (from: "I want to create a Black Friday sale template for my electronics store")
- "Restaurant Promotion Template" (from: "I want to create a restaurant promotion template")
- "Appointment Reminder Template" (from: "Create an appointment reminder message")

### 🔧 Testing Commands

For developers who want to test the functionality:

```bash
# 1. Create a user
curl -X POST "http://localhost:8000/users" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test_user", "password": "test_pass"}'

# 2. Create session with custom name
curl -X POST "http://localhost:8000/session/new" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test_user", "session_name": "My Custom Template"}'

# 3. Create session for auto-naming
curl -X POST "http://localhost:8000/session/new" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test_user"}'

# 4. Send first message to trigger auto-naming
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "Create a birthday party invitation", "session_id": "SESSION_ID", "user_id": "test_user"}'

# 5. List all user sessions
curl -X GET "http://localhost:8000/users/test_user/sessions"

# 6. Rename a session
curl -X PUT "http://localhost:8000/users/test_user/sessions/SESSION_ID/name?session_name=New%20Name"
```

## 🔧 Troubleshooting Common Issues

### Template Creation Stuck in Loop

**Problem:** User requests buttons/header but system keeps asking the same confirmation question.

**Solution:** ✅ **FULLY RESOLVED** in the latest version. The backend now:

1. **Sanitizes LLM missing lists** after auto-applying extras
2. **Records question hashes** on every turn to break loops  
3. **Handles AUTH constraints** properly (no buttons for authentication templates)
4. **Marks applied extras** in memory to prevent re-asking

**Example Flow:**
```javascript
// User: "add 2 buttons"
// Bot: "Should I add two quick replies like 'View offers' and 'Order now'?"
// User: "yes"
// Bot: ✅ "Added two quick replies (View offers / Order now). Anything else to add?"
// OR: ✅ Template finalized with buttons (not stuck in loop)
```

**Technical Fixes Applied:**
- LLM missing list is corrected with actual template state
- Button field variations (`text`, `label`, `title`) are normalized
- Question hash tracking prevents repeated questions
- AUTH templates properly reject button requests with explanation

### Button Format Issues

**Technical Details:** The LLM sometimes generates individual button components instead of a single BUTTONS component with nested buttons array. The backend now automatically converts:

```json
// Malformed (old issue):
{"type": "BUTTONS", "text": "Shop Now"}
{"type": "BUTTONS", "text": "View Offers"}

// To Correct Format:
{
  "type": "BUTTONS",
  "buttons": [
    {"type": "QUICK_REPLY", "text": "Shop Now"},
    {"type": "QUICK_REPLY", "text": "View Offers"}
  ]
}
```

### Debug Session Issues

**Using Debug Endpoint:**
```bash
curl -X GET "http://localhost:8000/session/{session_id}/debug"
```

This endpoint provides complete session information including:
- Chat history
- Current template draft
- LLM interaction logs
- Memory/context state
- Session metadata

### Session Naming Issues

**Auto-naming:** If session names aren't being generated automatically, ensure:
1. `user_id` is provided in chat requests
2. Session is created with user association
3. First message is descriptive enough for name generation

**Manual naming:** Use the POST method for session creation:
```javascript
const response = await fetch('/session/new', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    user_id: 'user123',
    session_name: 'Custom Template Name'
  })
});
```

### Authentication Template Constraints

**Important:** Authentication templates have specific constraints:

- ❌ **No custom buttons allowed** (only OTP functionality)
- ❌ **No custom media/headers** for security
- ✅ **Only BODY with verification code variables**

**Expected Behavior:**
```javascript
// User: "Create auth template with buttons"
// Bot: "Buttons aren't allowed for authentication templates; I'll proceed without them. Want a short TEXT header?"
```

**Valid AUTH Template Structure:**
```json
{
  "category": "AUTHENTICATION",
  "name": "otp_verification", 
  "language": "en_US",
  "components": [
    {
      "type": "BODY",
      "text": "{{1}} is your verification code. Do not share this code. It expires in {{2}} minutes."
    }
  ]
}
```

---

## 🔧 Recent Backend Improvements & Polish

### Version 1.2 - Production Hardening (Latest)

#### Critical Bug Fixes:
- **Button Type Fallback**: Fixed critical bug where malformed BUTTONS components could incorrectly default to "BUTTONS" type instead of "QUICK_REPLY" when normalizing individual button components
- **Import Optimization**: Removed redundant `import re` statement in `_generate_session_name_from_message` function
- **Debug Endpoint**: Fixed mislabeled field in `/session/{id}/debug` endpoint - changed "created_at" to "updated_at" for accuracy

#### Button Normalization Robustness:
- Handles LLM variants: `text`, `label`, `title` are all normalized to `text`
- Preserves button payloads during normalization for both standard and collected buttons
- Malformed BUTTONS components are safely collected into proper format
- All fallback button types default to "QUICK_REPLY" (never "BUTTONS")

#### Loop Prevention & UX:
- Post-sanitization of LLM missing list prevents stale prompts
- Replaced stale header/footer/button questions with confirmation messages
- Consolidated memory management for `extras_choice: accepted`
- AUTH templates never block on missing extras during FINAL submission

#### Verification:
- All changes verified with direct API smoke tests
- Button addition, AUTH flow, and malformed normalization tested
- Loop prevention confirmed working
- Session debug endpoint validated

### Integration Notes:
- Frontend should handle both `text` and `title` fields in button responses for maximum compatibility
- Watch for confirmation messages vs. questions to provide appropriate UI feedback
- DEBUG endpoint now correctly shows `updated_at` timestamp for sessions

---

### Version 1.3 - Final Edge Case Resolution

#### Critical Loop Prevention Fix:
- **Extras Decline Handling**: Fixed remaining edge case where "no buttons" would still trigger button prompts
- **Wants Flag Clearing**: When user declines extras with phrases like "no buttons", "skip header", etc., the system now clears all `wants_*` flags to prevent repeated prompts
- **Skip Honor in Missing Calculation**: `_compute_missing` now respects `extras_choice: "skip"` and won't mark declined extras as missing
- **Complete De-staling**: Extended confirmation replacement to header and footer prompts (matching button behavior)

#### Memory Management Polish:
- **Consolidated Accepted State**: Streamlined `extras_choice: "accepted"` memory writes from three separate blocks to one efficient check
- **Consistent Flag Management**: Ensures memory state accurately reflects user choices throughout the conversation

#### Verification:
- ✅ "no buttons" → immediately clears wants_buttons flag → no more button prompts
- ✅ Skip extras properly honored in missing calculation
- ✅ All extras (header, footer, buttons) get confirmation messages when auto-added
- ✅ Memory state remains clean and consistent

**Result**: Complete elimination of all known loop scenarios while maintaining robust template building flow.

---

### Version 1.4 - Final Polish & Production Readiness (Latest)

#### Quality & Security Improvements:
- **Affirmation Detection**: Fixed false positives with whole-word regex matching - "yesterday" no longer triggers as "yes"
- **Language Normalization**: Enhanced to support space-separated codes ("en us" → "en_US")
- **Auto-naming Robustness**: Category case normalization ensures consistent naming regardless of input case
- **Button Field Management**: Two-phase approach - preserve payloads during draft phase, strip non-schema fields at FINAL validation
- **Logging Security**: Added reminders for production logging hygiene and CORS lockdown

#### Technical Enhancements:
- **First-Message Auto-naming**: Fixed edge case where UserSession association didn't exist yet
- **Request Logging Order**: Moved request logging before LLM call for better failure trail analysis
- **Field Stripping**: Automatic removal of non-WhatsApp-API fields (like `payload`) before final validation
- **Case-Insensitive Categories**: Auto-naming now works with any case variation of category names

#### Verification Results:
- ✅ "yesterday" → `False` (no longer false positive)
- ✅ "en us" → `en_US` (space handling)
- ✅ Category "marketing" → "Marketing Promo Promotion Template" (case normalization)
- ✅ Payloads preserved in draft, stripped in FINAL (two-phase validation)
- ✅ UserSession association created before auto-naming (first message fix)

**Status**: Production-ready with comprehensive edge case handling, security considerations, and robust validation pipeline.
