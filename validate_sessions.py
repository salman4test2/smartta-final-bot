#!/usr/bin/env python3
"""
Validate user session responses and check for common issues.

This script checks:
1. Session data integrity
2. Draft structure consistency  
3. Missing user associations
4. Response format compliance
5. Template validation
"""

import sqlite3
import json
import argparse
from typing import Dict, Any, List, Optional
from datetime import datetime

def validate_session_structure(session_data: Dict[str, Any]) -> List[str]:
    """Validate session data structure and return list of issues."""
    issues = []
    
    # Check required fields
    if not isinstance(session_data.get('messages'), list):
        issues.append("Missing or invalid 'messages' field")
    
    # Check draft structure if present
    draft = session_data.get('draft')
    if draft:
        if not isinstance(draft, dict):
            issues.append("Draft is not a dictionary")
        else:
            # Check for duplicate buttons
            root_buttons = draft.get('buttons', [])
            component_buttons = []
            
            for comp in draft.get('components', []):
                if isinstance(comp, dict) and comp.get('type') == 'BUTTONS':
                    component_buttons.extend(comp.get('buttons', []))
            
            if root_buttons and component_buttons:
                issues.append("Duplicate button definitions (both root and component level)")
            
            # Check component structure
            components = draft.get('components', [])
            if components:
                for i, comp in enumerate(components):
                    if not isinstance(comp, dict):
                        issues.append(f"Component {i} is not a dictionary")
                        continue
                    
                    comp_type = comp.get('type')
                    if not comp_type:
                        issues.append(f"Component {i} missing type")
                    elif comp_type == 'BODY' and not comp.get('text'):
                        issues.append(f"BODY component {i} missing text")
                    elif comp_type == 'BUTTONS' and not comp.get('buttons'):
                        issues.append(f"BUTTONS component {i} missing buttons array")
    
    return issues

def validate_user_sessions(db_path: str) -> Dict[str, Any]:
    """Validate all user sessions and their associations."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    results = {
        'total_sessions': 0,
        'sessions_with_data': 0,
        'sessions_with_drafts': 0,
        'sessions_with_user_associations': 0,
        'issues': [],
        'validation_errors': []
    }
    
    # Check if user_sessions table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_sessions'")
    has_user_sessions = cursor.fetchone() is not None
    
    if not has_user_sessions:
        results['issues'].append("user_sessions table does not exist - user associations not available")
    
    # Get all sessions
    cursor.execute('SELECT id, data, active_draft_id, updated_at FROM sessions ORDER BY updated_at DESC')
    sessions = cursor.fetchall()
    results['total_sessions'] = len(sessions)
    
    for session_id, data_str, active_draft_id, updated_at in sessions:
        session_info = {
            'session_id': session_id,
            'updated_at': updated_at,
            'issues': []
        }
        
        # Check session data
        if data_str and data_str != '{}':
            results['sessions_with_data'] += 1
            
            try:
                session_data = json.loads(data_str)
                
                # Validate structure
                validation_issues = validate_session_structure(session_data)
                session_info['issues'].extend(validation_issues)
                
                # Check if has draft
                if session_data.get('draft'):
                    results['sessions_with_drafts'] += 1
                
            except json.JSONDecodeError:
                session_info['issues'].append("Invalid JSON in session data")
        
        # Check user association if table exists
        if has_user_sessions:
            cursor.execute('SELECT user_id, session_name FROM user_sessions WHERE session_id = ?', (session_id,))
            user_assoc = cursor.fetchone()
            if user_assoc:
                results['sessions_with_user_associations'] += 1
                session_info['user_id'] = user_assoc[0]
                session_info['session_name'] = user_assoc[1]
        
        # Check active draft
        if active_draft_id:
            cursor.execute('SELECT draft, status FROM drafts WHERE id = ?', (active_draft_id,))
            draft_info = cursor.fetchone()
            if draft_info:
                try:
                    draft_data = json.loads(draft_info[0])
                    session_info['draft_status'] = draft_info[1]
                    session_info['draft_has_content'] = bool(draft_data and draft_data != {})
                except:
                    session_info['issues'].append("Invalid JSON in draft data")
            else:
                session_info['issues'].append(f"Active draft {active_draft_id} not found")
        
        # Only include sessions with issues or interesting data
        if session_info['issues'] or session_info.get('user_id') or session_info.get('draft_has_content'):
            results['validation_errors'].append(session_info)
    
    conn.close()
    return results

def check_api_endpoints(db_path: str) -> Dict[str, Any]:
    """Check if the API endpoints would work with current data."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    results = {
        'users_endpoint_ready': False,
        'sessions_endpoint_ready': False,
        'issues': []
    }
    
    # Check for users table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    has_users = cursor.fetchone() is not None
    
    if not has_users:
        results['issues'].append("users table missing - /users endpoints won't work")
    else:
        cursor.execute('SELECT COUNT(*) FROM users')
        user_count = cursor.fetchone()[0]
        results['user_count'] = user_count
        results['users_endpoint_ready'] = True
    
    # Check for user_sessions table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_sessions'")
    has_user_sessions = cursor.fetchone() is not None
    
    if not has_user_sessions:
        results['issues'].append("user_sessions table missing - user session listings won't work")
    else:
        cursor.execute('SELECT COUNT(*) FROM user_sessions')
        user_session_count = cursor.fetchone()[0]
        results['user_session_count'] = user_session_count
        results['sessions_endpoint_ready'] = True
    
    conn.close()
    return results

def main():
    parser = argparse.ArgumentParser(description='Validate user sessions and responses')
    parser.add_argument('--db-path', default='data/watemp.db', help='Path to SQLite database')
    parser.add_argument('--show-all', action='store_true', help='Show all sessions, not just those with issues')
    parser.add_argument('--check-specific', help='Check a specific session ID')
    
    args = parser.parse_args()
    
    print(f"🔍 Validating sessions in: {args.db_path}")
    print(f"⏰ Timestamp: {datetime.now().isoformat()}")
    print()
    
    # Check API readiness
    print("=== API ENDPOINT READINESS ===")
    api_results = check_api_endpoints(args.db_path)
    print(f"Users endpoint ready: {api_results['users_endpoint_ready']}")
    print(f"Sessions endpoint ready: {api_results['sessions_endpoint_ready']}")
    
    if api_results.get('user_count') is not None:
        print(f"Total users: {api_results['user_count']}")
    if api_results.get('user_session_count') is not None:
        print(f"Total user sessions: {api_results['user_session_count']}")
    
    if api_results['issues']:
        print("\\nIssues:")
        for issue in api_results['issues']:
            print(f"  ⚠️  {issue}")
    
    print()
    
    # Check specific session if requested
    if args.check_specific:
        print(f"=== SPECIFIC SESSION CHECK: {args.check_specific} ===")
        conn = sqlite3.connect(args.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT data, active_draft_id FROM sessions WHERE id = ?', (args.check_specific,))
        session = cursor.fetchone()
        
        if session:
            data_str, active_draft_id = session
            if data_str:
                try:
                    session_data = json.loads(data_str)
                    issues = validate_session_structure(session_data)
                    
                    print(f"Messages: {len(session_data.get('messages', []))}")
                    print(f"Has draft: {'draft' in session_data}")
                    print(f"Active draft ID: {active_draft_id}")
                    
                    if issues:
                        print("\\nIssues found:")
                        for issue in issues:
                            print(f"  ❌ {issue}")
                    else:
                        print("\\n✅ No issues found")
                        
                except Exception as e:
                    print(f"❌ Error parsing session: {e}")
            else:
                print("❌ No session data")
        else:
            print("❌ Session not found")
        
        conn.close()
        return
    
    # Validate all sessions
    print("=== SESSION VALIDATION ===")
    session_results = validate_user_sessions(args.db_path)
    
    print(f"Total sessions: {session_results['total_sessions']}")
    print(f"Sessions with data: {session_results['sessions_with_data']}")
    print(f"Sessions with drafts: {session_results['sessions_with_drafts']}")
    print(f"Sessions with user associations: {session_results['sessions_with_user_associations']}")
    
    if session_results['issues']:
        print("\\nGeneral issues:")
        for issue in session_results['issues']:
            print(f"  ⚠️  {issue}")
    
    # Show sessions with validation errors
    error_sessions = [s for s in session_results['validation_errors'] if s['issues']]
    if error_sessions:
        print(f"\\n=== SESSIONS WITH ISSUES ({len(error_sessions)}) ===")
        for session in error_sessions:
            print(f"\\nSession: {session['session_id']}")
            print(f"Updated: {session['updated_at']}")
            if session.get('user_id'):
                print(f"User: {session['user_id']}")
            if session.get('session_name'):
                print(f"Name: {session['session_name']}")
            
            for issue in session['issues']:
                print(f"  ❌ {issue}")
    
    # Show interesting sessions (with user associations or drafts)
    if args.show_all:
        interesting_sessions = [
            s for s in session_results['validation_errors'] 
            if not s['issues'] and (s.get('user_id') or s.get('draft_has_content'))
        ]
        
        if interesting_sessions:
            print(f"\\n=== SESSIONS WITH DATA ({len(interesting_sessions)}) ===")
            for session in interesting_sessions:
                print(f"\\nSession: {session['session_id']}")
                print(f"Updated: {session['updated_at']}")
                if session.get('user_id'):
                    print(f"User: {session['user_id']}")
                if session.get('session_name'):
                    print(f"Name: {session['session_name']}")
                if session.get('draft_status'):
                    print(f"Draft: {session['draft_status']}")
    
    # Summary
    total_issues = len(error_sessions)
    if total_issues == 0:
        print("\\n✅ All sessions validated successfully!")
    else:
        print(f"\\n⚠️  Found issues in {total_issues} sessions")

if __name__ == '__main__':
    main()
