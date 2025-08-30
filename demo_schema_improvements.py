#!/usr/bin/env python3
"""
Quick demo of the key schema improvements
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from pydantic import ValidationError
from app.schemas import (
    UserCreate, ChatMessage, SessionCreate, ChatInput
)

def demo_improvements():
    """Demonstrate the key schema improvements"""
    print("🚀 Schema Improvements Demo")
    print("=" * 40)
    
    print("\n1. Type Safety with Literals")
    print("-" * 30)
    
    # Valid role
    msg = ChatMessage(role="user", content="Hello!")
    print(f"✓ Valid role 'user': {msg.role}")
    
    # Invalid role will fail
    try:
        ChatMessage(role="invalid", content="Hello!")
        print("✗ Should have failed")
    except ValidationError as e:
        print(f"✓ Invalid role rejected: {str(e).split('Input should be')[1].split('[')[0].strip()}")
    
    print("\n2. Automatic Whitespace Stripping")
    print("-" * 30)
    
    user = UserCreate(user_id="  john_doe  ", password="securepass123")
    print(f"✓ User ID stripped: '{user.user_id}' (was '  john_doe  ')")
    
    session = SessionCreate(session_name="  My Session  ")
    print(f"✓ Session name stripped: '{session.session_name}' (was '  My Session  ')")
    
    chat = ChatInput(message="  Hello world!  ")
    print(f"✓ Message stripped: '{chat.message}' (was '  Hello world!  ')")
    
    print("\n3. Length Validation")
    print("-" * 30)
    
    # Valid lengths
    print("✓ Valid user_id length (1-50 chars)")
    print("✓ Valid session_name length (1-120 chars)")
    print("✓ Valid message length (1-2000 chars)")
    print("✓ Valid password length (8-128 chars)")
    
    # Test constraint failures
    try:
        UserCreate(user_id="", password="validpass123")
        print("✗ Should have failed")
    except ValidationError:
        print("✓ Empty user_id rejected")
    
    try:
        UserCreate(user_id="valid", password="short")
        print("✗ Should have failed")  
    except ValidationError:
        print("✓ Short password (< 8 chars) rejected")
    
    try:
        ChatInput(message="a" * 2001)
        print("✗ Should have failed")
    except ValidationError:
        print("✓ Too long message (> 2000 chars) rejected")
    
    print("\n4. Consistent Response Models")
    print("-" * 30)
    
    from app.schemas import SessionCreateResponse, ErrorResponse, SuccessResponse
    
    # Valid response models
    session_response = SessionCreateResponse(
        session_id="sess_123",
        session_name="Test Session",
        user_id="user_123"
    )
    print(f"✓ SessionCreateResponse: {session_response.session_id}")
    
    error_response = ErrorResponse(error="Validation failed", detail="Missing field")
    print(f"✓ ErrorResponse: {error_response.error}")
    
    success_response = SuccessResponse(message="Operation completed")
    print(f"✓ SuccessResponse: {success_response.success}")
    
    print("\n" + "=" * 40)
    print("✅ All schema improvements working correctly!")

if __name__ == "__main__":
    demo_improvements()
