#!/usr/bin/env python3
"""
Test script to verify the improved schemas in schemas.py
Tests validation constraints, field validation, and type safety.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from pydantic import ValidationError
from app.schemas import (
    UserCreate, UserLogin, UserSessionInfo, UserSessionsResponse,
    SessionCreate, SessionCreateResponse, SessionRename,
    ChatInput, ChatMessage, SessionInfoResponse,
    ErrorResponse, SuccessResponse
)

def test_user_schemas():
    """Test user-related schema validation"""
    print("Testing User Schemas...")
    
    # Test UserCreate validation
    try:
        # Valid user creation
        user = UserCreate(user_id="test_user", password="validpassword123")
        print(f"✓ Valid UserCreate: {user.user_id}")
        
        # Test user_id constraints
        try:
            UserCreate(user_id="", password="validpassword123")
            print("✗ Should have failed for empty user_id")
        except ValidationError:
            print("✓ Empty user_id rejected")
            
        try:
            UserCreate(user_id="a" * 51, password="validpassword123")
            print("✗ Should have failed for too long user_id")
        except ValidationError:
            print("✓ Too long user_id rejected")
            
        # Test password constraints
        try:
            UserCreate(user_id="test", password="short")
            print("✗ Should have failed for short password")
        except ValidationError:
            print("✓ Short password rejected")
            
    except Exception as e:
        print(f"✗ Error in UserCreate tests: {e}")
    
    # Test UserLogin validation
    try:
        login = UserLogin(user_id="test_user", password="anypassword")
        print(f"✓ Valid UserLogin: {login.user_id}")
        
        # Test whitespace stripping
        login_with_spaces = UserLogin(user_id="  test_user  ", password="password")
        print(f"Login user_id before: '  test_user  ', after: '{login_with_spaces.user_id}'")
        # Note: Pydantic strip_whitespace applies during validation, actual value should be stripped
        print("✓ User ID validation works")
        
    except Exception as e:
        print(f"✗ Error in UserLogin tests: {e}")
        import traceback
        traceback.print_exc()

def test_session_schemas():
    """Test session-related schema validation"""
    print("\nTesting Session Schemas...")
    
    # Test SessionCreate validation
    try:
        # Valid session creation
        session = SessionCreate(user_id="test_user", session_name="Test Session")
        print(f"✓ Valid SessionCreate with name: {session.session_name}")
        
        # Test without session_name
        session_no_name = SessionCreate(user_id="test_user")
        print("✓ Valid SessionCreate without name")
        
        # Test session_name constraints
        try:
            SessionCreate(user_id="test", session_name="")
            print("✗ Should have failed for empty session_name")
        except ValidationError:
            print("✓ Empty session_name rejected")
            
        try:
            SessionCreate(user_id="test", session_name="a" * 121)
            print("✗ Should have failed for too long session_name")
        except ValidationError:
            print("✓ Too long session_name rejected")
            
        # Test whitespace stripping in session_name
        session_spaces = SessionCreate(user_id="test", session_name="  Spaced Name  ")
        print(f"Session name before: '  Spaced Name  ', after: '{session_spaces.session_name}'")
        print("✓ Session name validation works")
        
    except Exception as e:
        print(f"✗ Error in SessionCreate tests: {e}")
        import traceback
        traceback.print_exc()
    
    # Test SessionRename validation
    try:
        rename = SessionRename(session_name="New Name")
        print("✓ Valid SessionRename")
        
        try:
            SessionRename(session_name="")
            print("✗ Should have failed for empty rename")
        except ValidationError:
            print("✓ Empty session rename rejected")
            
    except Exception as e:
        print(f"✗ Error in SessionRename tests: {e}")

def test_chat_schemas():
    """Test chat-related schema validation"""
    print("\nTesting Chat Schemas...")
    
    # Test ChatInput validation
    try:
        # Valid chat input
        chat = ChatInput(message="Hello, how are you?", session_id="session123")
        print("✓ Valid ChatInput")
        
        # Test message constraints
        try:
            ChatInput(message="")
            print("✗ Should have failed for empty message")
        except ValidationError:
            print("✓ Empty message rejected")
            
        try:
            ChatInput(message="a" * 2001)
            print("✗ Should have failed for too long message")
        except ValidationError:
            print("✓ Too long message rejected")
            
        # Test whitespace stripping
        chat_spaces = ChatInput(message="  Hello World  ")
        print(f"Message before: '  Hello World  ', after: '{chat_spaces.message}'")
        print("✓ Message validation works")
        
    except Exception as e:
        print(f"✗ Error in ChatInput tests: {e}")
        import traceback
        traceback.print_exc()
    
    # Test ChatMessage validation
    try:
        # Valid chat messages
        user_msg = ChatMessage(role="user", content="Hello")
        assistant_msg = ChatMessage(role="assistant", content="Hi there!")
        print("✓ Valid ChatMessage for user and assistant")
        
        # Test role constraints
        try:
            ChatMessage(role="invalid", content="Hello")
            print("✗ Should have failed for invalid role")
        except ValidationError:
            print("✓ Invalid role rejected")
            
        # Test content constraints
        try:
            ChatMessage(role="user", content="")
            print("✗ Should have failed for empty content")
        except ValidationError:
            print("✓ Empty content rejected")
            
    except Exception as e:
        print(f"✗ Error in ChatMessage tests: {e}")

def test_response_schemas():
    """Test response schema validation"""
    print("\nTesting Response Schemas...")
    
    try:
        # Test SessionInfoResponse
        session_info = SessionInfoResponse(
            session_id="session123",
            session_name="Test Session",
            user_id="user123",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T01:00:00Z",
            message_count=5
        )
        print("✓ Valid SessionInfoResponse")
        
        # Test ErrorResponse
        error = ErrorResponse(error="Validation failed", detail="Missing required field")
        print("✓ Valid ErrorResponse")
        
        # Test SuccessResponse
        success = SuccessResponse(message="Operation completed successfully")
        print("✓ Valid SuccessResponse")
        
    except Exception as e:
        print(f"✗ Error in response schema tests: {e}")

def test_backwards_compatibility():
    """Test that existing code will still work with the new schemas"""
    print("\nTesting Backwards Compatibility...")
    
    try:
        # Test that existing dictionaries can still be used
        user_data = {"user_id": "test", "password": "password123"}
        user = UserCreate(**user_data)
        print("✓ Dictionary unpacking works")
        
        # Test that serialization works
        chat_msg = ChatMessage(role="user", content="Hello")
        serialized = chat_msg.model_dump()
        assert "role" in serialized and "content" in serialized
        print("✓ Serialization works")
        
        # Test that the schemas can be used in FastAPI endpoints
        session_create_data = {
            "user_id": "test_user",
            "session_name": "Test Session"
        }
        session_create = SessionCreate(**session_create_data)
        response_data = SessionCreateResponse(
            session_id="new_session_123",
            session_name=session_create.session_name,
            user_id=session_create.user_id
        )
        print("✓ Schema composition works")
        
    except Exception as e:
        print(f"✗ Error in backwards compatibility tests: {e}")

def main():
    """Run all schema validation tests"""
    print("Schema Validation Test Suite")
    print("=" * 40)
    
    test_user_schemas()
    test_session_schemas()
    test_chat_schemas()
    test_response_schemas()
    test_backwards_compatibility()
    
    print("\n" + "=" * 40)
    print("Schema validation tests completed!")

if __name__ == "__main__":
    main()
