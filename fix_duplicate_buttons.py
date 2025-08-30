#!/usr/bin/env python3
"""
Fix duplicate button definitions in sessions and drafts.

This script:
1. Identifies sessions/drafts with duplicate button definitions
2. Removes buttons from the root level of drafts
3. Ensures buttons are only defined in BUTTONS components
4. Logs all changes for review
"""

import sqlite3
import json
import argparse
from datetime import datetime
from typing import Dict, Any, List, Tuple

def find_duplicate_buttons(data: Dict[str, Any]) -> Tuple[bool, List[Dict], List[Dict]]:
    """
    Check if data has duplicate button definitions.
    Returns (has_duplicates, root_buttons, component_buttons)
    """
    root_buttons = data.get('buttons', [])
    component_buttons = []
    
    for comp in data.get('components', []):
        if comp.get('type') == 'BUTTONS':
            component_buttons.extend(comp.get('buttons', []))
    
    has_duplicates = bool(root_buttons) and bool(component_buttons)
    return has_duplicates, root_buttons, component_buttons

def fix_duplicate_buttons(data: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """
    Fix duplicate button definitions by removing root-level buttons.
    Returns (fixed_data, was_changed)
    """
    if 'buttons' not in data:
        return data, False
    
    # Check if we have components with BUTTONS
    has_button_component = any(
        comp.get('type') == 'BUTTONS' 
        for comp in data.get('components', [])
    )
    
    if has_button_component:
        # Remove root-level buttons since they're already in components
        fixed_data = {k: v for k, v in data.items() if k != 'buttons'}
        return fixed_data, True
    else:
        # Move root-level buttons to components
        if data['buttons']:
            components = data.get('components', [])
            components.append({
                'type': 'BUTTONS',
                'buttons': data['buttons']
            })
            fixed_data = {k: v for k, v in data.items() if k != 'buttons'}
            fixed_data['components'] = components
            return fixed_data, True
    
    return data, False

def fix_sessions(db_path: str, dry_run: bool = True) -> Dict[str, Any]:
    """Fix duplicate buttons in sessions table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get sessions with data
    cursor.execute('SELECT id, data FROM sessions WHERE data IS NOT NULL AND data != "{}"')
    sessions = cursor.fetchall()
    
    results = {
        'sessions_checked': len(sessions),
        'sessions_with_duplicates': 0,
        'sessions_fixed': 0,
        'changes': []
    }
    
    for session_id, data_str in sessions:
        try:
            data = json.loads(data_str)
            draft = data.get('draft', {})
            
            has_duplicates, root_buttons, component_buttons = find_duplicate_buttons(draft)
            
            if has_duplicates:
                results['sessions_with_duplicates'] += 1
                
                # Fix the duplicate
                fixed_draft, was_changed = fix_duplicate_buttons(draft)
                
                if was_changed:
                    change_info = {
                        'session_id': session_id,
                        'type': 'session',
                        'root_buttons_removed': len(root_buttons),
                        'component_buttons_kept': len(component_buttons),
                        'before': {
                            'root_buttons': root_buttons,
                            'component_buttons': component_buttons
                        }
                    }
                    results['changes'].append(change_info)
                    
                    if not dry_run:
                        # Update the session
                        data['draft'] = fixed_draft
                        new_data = json.dumps(data)
                        cursor.execute(
                            'UPDATE sessions SET data = ?, updated_at = datetime("now") WHERE id = ?',
                            (new_data, session_id)
                        )
                        results['sessions_fixed'] += 1
        
        except Exception as e:
            print(f"Error processing session {session_id}: {e}")
    
    if not dry_run:
        conn.commit()
    
    conn.close()
    return results

def fix_drafts(db_path: str, dry_run: bool = True) -> Dict[str, Any]:
    """Fix duplicate buttons in drafts table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get drafts with substantial data
    cursor.execute('SELECT id, session_id, draft FROM drafts WHERE draft IS NOT NULL AND draft != "{}"')
    drafts = cursor.fetchall()
    
    results = {
        'drafts_checked': len(drafts),
        'drafts_with_duplicates': 0,
        'drafts_fixed': 0,
        'changes': []
    }
    
    for draft_id, session_id, draft_str in drafts:
        try:
            data = json.loads(draft_str)
            
            has_duplicates, root_buttons, component_buttons = find_duplicate_buttons(data)
            
            if has_duplicates:
                results['drafts_with_duplicates'] += 1
                
                # Fix the duplicate
                fixed_data, was_changed = fix_duplicate_buttons(data)
                
                if was_changed:
                    change_info = {
                        'draft_id': draft_id,
                        'session_id': session_id,
                        'type': 'draft',
                        'root_buttons_removed': len(root_buttons),
                        'component_buttons_kept': len(component_buttons),
                        'before': {
                            'root_buttons': root_buttons,
                            'component_buttons': component_buttons
                        }
                    }
                    results['changes'].append(change_info)
                    
                    if not dry_run:
                        # Update the draft
                        new_draft = json.dumps(fixed_data)
                        cursor.execute(
                            'UPDATE drafts SET draft = ? WHERE id = ?',
                            (new_draft, draft_id)
                        )
                        results['drafts_fixed'] += 1
        
        except Exception as e:
            print(f"Error processing draft {draft_id}: {e}")
    
    if not dry_run:
        conn.commit()
    
    conn.close()
    return results

def main():
    parser = argparse.ArgumentParser(description='Fix duplicate button definitions')
    parser.add_argument('--db-path', default='data/watemp.db', help='Path to SQLite database')
    parser.add_argument('--apply', action='store_true', help='Apply fixes (default is dry-run)')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    db_path = args.db_path
    dry_run = not args.apply
    
    print(f"🔍 Scanning database: {db_path}")
    print(f"📋 Mode: {'DRY RUN' if dry_run else 'APPLY FIXES'}")
    print()
    
    # Fix sessions
    print("=== CHECKING SESSIONS ===")
    session_results = fix_sessions(db_path, dry_run)
    print(f"Sessions checked: {session_results['sessions_checked']}")
    print(f"Sessions with duplicates: {session_results['sessions_with_duplicates']}")
    print(f"Sessions fixed: {session_results['sessions_fixed']}")
    
    # Fix drafts
    print("\\n=== CHECKING DRAFTS ===")
    draft_results = fix_drafts(db_path, dry_run)
    print(f"Drafts checked: {draft_results['drafts_checked']}")
    print(f"Drafts with duplicates: {draft_results['drafts_with_duplicates']}")
    print(f"Drafts fixed: {draft_results['drafts_fixed']}")
    
    # Show changes
    all_changes = session_results['changes'] + draft_results['changes']
    
    if all_changes:
        print(f"\\n=== CHANGES MADE ({len(all_changes)}) ===")
        for i, change in enumerate(all_changes, 1):
            print(f"\\n{i}. {change['type'].upper()}: {change.get('session_id', change.get('draft_id'))}")
            print(f"   Root buttons removed: {change['root_buttons_removed']}")
            print(f"   Component buttons kept: {change['component_buttons_kept']}")
            
            if args.verbose:
                print(f"   Before - Root: {change['before']['root_buttons']}")
                print(f"   Before - Components: {change['before']['component_buttons']}")
    
    total_duplicates = session_results['sessions_with_duplicates'] + draft_results['drafts_with_duplicates']
    total_fixed = session_results['sessions_fixed'] + draft_results['drafts_fixed']
    
    print(f"\\n=== SUMMARY ===")
    print(f"Total items with duplicates: {total_duplicates}")
    print(f"Total items fixed: {total_fixed}")
    
    if dry_run and total_duplicates > 0:
        print("\\n⚠️  This was a dry run. Use --apply to fix the issues.")
    elif total_fixed > 0:
        print("\\n✅ Fixes applied successfully!")
    else:
        print("\\n✅ No duplicate button issues found!")

if __name__ == '__main__':
    main()
