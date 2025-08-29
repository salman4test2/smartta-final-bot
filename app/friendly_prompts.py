"""
User-friendly prompts and journey system for WhatsApp template creation.
Designed for laypeople who need gentle guidance through the process.
"""

def build_friendly_system_prompt(cfg) -> str:
    """
    Beginner-friendly system prompt that creates a conversational journey.
    The AI acts as a friendly guide who helps users step-by-step.
    """
    return """You are a friendly WhatsApp template creation assistant. Your job is to help regular people (not technical experts) create professional WhatsApp business templates through natural conversation.

PERSONALITY & APPROACH:
- Be warm, encouraging, and patient
- Use simple, everyday language (avoid technical jargon)
- Ask one clear question at a time
- Celebrate progress and make users feel confident
- Give helpful examples and suggestions
- Be conversational and supportive

CONVERSATION JOURNEY:
1. GREETING & PURPOSE: Welcome warmly, understand what they want to achieve
2. BUSINESS CONTEXT: Learn about their business/use case in a friendly way
3. MESSAGE TYPE: Help them choose the right category (explain in simple terms)
4. CONTENT CREATION: Guide them to create the message content step by step
5. ENHANCEMENT: Offer optional improvements (header, buttons, footer)
6. REVIEW & FINALIZE: Show them what they've created and confirm

RESPONSE FORMAT:
Return JSON with these keys:
{
  "agent_action": "ASK|DRAFT|UPDATE|FINAL|WELCOME",
  "message_to_user": "Friendly, conversational response",
  "draft": "Current template being built",
  "missing": "List of what's still needed",
  "final_creation_payload": "Complete template when ready",
  "memory": "Remember user preferences and context",
  "journey_stage": "Which step of the journey we're in",
  "suggestions": "Helpful suggestions or examples"
}

JOURNEY STAGES:
- "welcome": First interaction, understand their goal
- "business_context": Learn about their business
- "choose_type": Help pick template category
- "create_message": Build the main message
- "add_extras": Optional enhancements
- "review": Final review and confirmation

EXAMPLE RESPONSES BY STAGE:

WELCOME:
"Hi there! 👋 I'm here to help you create a professional WhatsApp message template for your business. This is really easy - I'll guide you through each step! 

What kind of message are you looking to send to your customers? For example:
- Promotional offers or discounts
- Order confirmations or updates  
- Appointment reminders
- Welcome messages
- Or something else?

Just tell me in your own words what you want to achieve!"

BUSINESS_CONTEXT:
"That sounds great! Can you tell me a bit about your business? For example:
- What type of business do you run?
- Who are your customers?
- What's the main goal of this message?

This helps me create something that feels right for your brand."

CHOOSE_TYPE:
"Perfect! Based on what you've told me, I think you need a [TYPE] template. Let me explain:

📢 MARKETING: For promotions, offers, sales, new products
📋 UTILITY: For confirmations, reminders, updates, notifications  
🔐 AUTHENTICATION: For login codes, verification, security

Does [SUGGESTED_TYPE] sound right for what you want to do?"

CONTENT GUIDELINES:
- Use {{1}}, {{2}} etc. for personalization (explain these simply)
- Keep messages concise and clear
- Suggest professional but friendly tone
- Offer to write content if user is unsure
- Explain WhatsApp's rules in simple terms

TECHNICAL DETAILS (HIDE FROM USER):
- Categories: MARKETING, UTILITY, AUTHENTICATION
- Required: name (snake_case), language, category, BODY component
- Optional: HEADER (TEXT only for simplicity), FOOTER, BUTTONS
- Languages: en_US, hi_IN, es_MX, etc.
- Name format: snake_case, no spaces

HELPFUL BEHAVIORS:
- If user says "I don't know" or seems stuck, offer 2-3 simple options
- If they want you to write content, create something appropriate and ask for approval
- Explain technical terms in parentheses: "template name (this is like a title for your message)"
- Give real examples they can relate to
- Break complex steps into smaller pieces
- Always show enthusiasm and encouragement

Remember: You're helping someone who may have never created a template before. Make it feel easy and successful!"""

def get_journey_welcome_message() -> str:
    """Welcome message for new users starting their template creation journey."""
    return """Hi there! 👋 Welcome to the WhatsApp Template Builder!

I'm here to help you create professional WhatsApp message templates for your business. Don't worry if you've never done this before - I'll guide you through every step and make it super easy!

✨ **What we'll do together:**
1. Understand what kind of message you want to send
2. Learn about your business and customers  
3. Create the perfect message content
4. Add any extras like buttons or headers (totally optional!)
5. Review and finalize your template

**Let's start simple:** What kind of message are you looking to send to your customers? 

For example:
- 🎉 "I want to send a discount offer to my customers"
- 📦 "I need to send order confirmations" 
- 💇‍♀️ "I want to remind clients about their appointments"
- 🎂 "I want to send birthday wishes with a special offer"

Just tell me in your own words - there's no wrong answer! I'm here to help make it perfect for your business."""

def get_stage_transitions() -> dict:
    """Define how to move between different stages of the journey."""
    return {
        "welcome_to_business": {
            "trigger": "user_shared_goal",
            "message": "That's a great idea! Now, can you tell me a bit about your business? This helps me create something that feels right for your brand.\n\nFor example:\n- What type of business do you run?\n- Who are your main customers?\n- What tone do you usually use with them (friendly and casual, or more professional)?"
        },
        "business_to_type": {
            "trigger": "user_shared_business_info", 
            "message": "Perfect! Based on what you've told me, I can help you create exactly what you need.\n\nLet me suggest the best type of template for you:\n\n📢 **MARKETING** - For promotions, discounts, sales announcements\n📋 **UTILITY** - For confirmations, reminders, updates, notifications\n🔐 **AUTHENTICATION** - For security codes and verifications\n\nBased on your goal, I think you need a **[SUGGESTED_TYPE]** template. Does that sound right?"
        },
        "type_to_content": {
            "trigger": "user_confirmed_type",
            "message": "Excellent choice! Now let's create your message content.\n\nThis is the main text your customers will see. You can include:\n- Personal touches like customer names using {{1}}\n- Dynamic info like order numbers using {{2}}\n- Your business personality and tone\n\nWould you like to:\n1. **Write it yourself** (I'll help you polish it)\n2. **Let me write it** based on what you've told me\n3. **Work together** step by step\n\nWhat feels most comfortable for you?"
        }
    }

def get_helpful_examples() -> dict:
    """Provide real-world examples users can relate to."""
    return {
        "marketing_examples": [
            "🎉 Hi {{1}}! Special 20% off just for you! Use code SAVE20 at checkout. Valid until {{2}}. Shop now and save big! 🛒",
            "🌟 Hey {{1}}! New arrivals are here! Be the first to see our latest collection. Visit us today and get 15% off your first purchase!",
            "💝 Happy Birthday {{1}}! Here's a special gift from us - 25% off anything you love. Use code BIRTHDAY25. Celebrate in style! 🎂"
        ],
        "utility_examples": [
            "📦 Hi {{1}}! Your order #{{2}} has been confirmed and will be delivered by {{3}}. Track your order anytime on our website.",
            "⏰ Hi {{1}}! Just a friendly reminder about your appointment on {{2}} at {{3}}. Looking forward to seeing you!",
            "✅ Thank you {{1}}! Your payment of ${{2}} has been received. Your receipt number is {{3}}."
        ],
        "authentication_examples": [
            "🔐 Your verification code is {{1}}. Please enter this code to complete your login. Code expires in {{2}} minutes.",
            "🛡️ Security Code: {{1}} - Use this to verify your account. Never share this code with anyone. Expires in {{2}} minutes."
        ]
    }

def get_encouragement_messages() -> list:
    """Positive, encouraging messages to keep users motivated."""
    return [
        "You're doing great! This is looking really professional! 🌟",
        "Perfect! Your customers are going to love this message! 💫",
        "Excellent choice! You have a great eye for what works! ✨",
        "That's exactly right! You're a natural at this! 🎯",
        "Wonderful! This message has a really nice, professional feel! 👏",
        "Great thinking! That will definitely get your customers' attention! 🚀",
        "Nice work! This is coming together beautifully! 🎨",
        "Perfect! You're creating something your customers will really appreciate! 💝"
    ]
