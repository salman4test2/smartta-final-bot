#!/usr/bin/env python3
"""
Fix duplicate button definitions in PostgreSQL database.
"""

import asyncio
import json
import argparse
from typing import Dict, Any, List, Tuple

async def find_duplicate_buttons_postgres(data: Dict[str, Any]) -> Tuple[bool, List[Dict], List[Dict]]:
    """Check if data has duplicate button definitions."""
    root_buttons = data.get('buttons', [])
    component_buttons = []
    
    for comp in data.get('components', []):
        if comp.get('type') == 'BUTTONS':
            component_buttons.extend(comp.get('buttons', []))
    
    has_duplicates = bool(root_buttons) and bool(component_buttons)
    return has_duplicates, root_buttons, component_buttons

async def fix_postgres_duplicates(dry_run: bool = True):
    """Fix duplicate buttons in PostgreSQL database."""
    print(f"🔍 Checking PostgreSQL database for duplicate button issues")
    print(f"📋 Mode: {'DRY RUN' if dry_run else 'APPLY FIXES'}")
    
    from app.db import SessionLocal
    from sqlalchemy import text
    
    results = {
        'sessions_checked': 0,
        'drafts_checked': 0,
        'sessions_with_duplicates': 0,
        'drafts_with_duplicates': 0,
        'sessions_fixed': 0,
        'drafts_fixed': 0,
        'changes': []
    }
    
    async with SessionLocal() as db:
        # Check sessions with draft data
        print("\n=== CHECKING SESSIONS ===")
        result = await db.execute(
            text("SELECT id, data FROM sessions WHERE data IS NOT NULL")
        )
        sessions = result.fetchall()
        results['sessions_checked'] = len(sessions)
        
        for session_id, session_data in sessions:
            try:
                if isinstance(session_data, str):
                    data = json.loads(session_data)
                else:
                    data = session_data
                
                draft = data.get('draft', {})
                if draft:
                    has_duplicates, root_buttons, component_buttons = await find_duplicate_buttons_postgres(draft)
                    
                    if has_duplicates:
                        results['sessions_with_duplicates'] += 1
                        
                        change_info = {
                            'type': 'session',
                            'id': session_id,
                            'root_buttons_count': len(root_buttons),
                            'component_buttons_count': len(component_buttons),
                            'root_buttons': root_buttons,
                            'component_buttons': component_buttons
                        }
                        results['changes'].append(change_info)
                        
                        if not dry_run:
                            # Fix by removing root buttons
                            draft.pop('buttons', None)
                            data['draft'] = draft
                            new_data = json.dumps(data) if isinstance(session_data, str) else data
                            
                            await db.execute(
                                text("UPDATE sessions SET data = :data WHERE id = :id"),
                                {'data': new_data, 'id': session_id}
                            )
                            results['sessions_fixed'] += 1
                            
            except Exception as e:
                print(f"Error processing session {session_id}: {e}")
        
        # Check drafts
        print("\n=== CHECKING DRAFTS ===")
        result = await db.execute(
            text("SELECT id, session_id, draft FROM drafts WHERE draft IS NOT NULL")
        )
        drafts = result.fetchall()
        results['drafts_checked'] = len(drafts)
        
        for draft_id, session_id, draft_data in drafts:
            try:
                if isinstance(draft_data, str):
                    draft = json.loads(draft_data)
                else:
                    draft = draft_data
                
                has_duplicates, root_buttons, component_buttons = await find_duplicate_buttons_postgres(draft)
                
                if has_duplicates:
                    results['drafts_with_duplicates'] += 1
                    
                    change_info = {
                        'type': 'draft', 
                        'id': draft_id,
                        'session_id': session_id,
                        'root_buttons_count': len(root_buttons),
                        'component_buttons_count': len(component_buttons),
                        'root_buttons': root_buttons,
                        'component_buttons': component_buttons
                    }
                    results['changes'].append(change_info)
                    
                    if not dry_run:
                        # Fix by removing root buttons
                        draft.pop('buttons', None)
                        new_draft = json.dumps(draft) if isinstance(draft_data, str) else draft
                        
                        await db.execute(
                            text("UPDATE drafts SET draft = :draft WHERE id = :id"),
                            {'draft': new_draft, 'id': draft_id}
                        )
                        results['drafts_fixed'] += 1
                        
            except Exception as e:
                print(f"Error processing draft {draft_id}: {e}")
        
        if not dry_run:
            await db.commit()
    
    return results

async def main():
    parser = argparse.ArgumentParser(description='Fix duplicate button definitions in PostgreSQL')
    parser.add_argument('--apply', action='store_true', help='Apply fixes (default is dry-run)')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    dry_run = not args.apply
    
    results = await fix_postgres_duplicates(dry_run)
    
    print(f"\\nSessions checked: {results['sessions_checked']}")
    print(f"Sessions with duplicates: {results['sessions_with_duplicates']}")
    print(f"Sessions fixed: {results['sessions_fixed']}")
    
    print(f"\\nDrafts checked: {results['drafts_checked']}")
    print(f"Drafts with duplicates: {results['drafts_with_duplicates']}")
    print(f"Drafts fixed: {results['drafts_fixed']}")
    
    if results['changes']:
        print(f"\\n=== CHANGES MADE ({len(results['changes'])}) ===")
        for i, change in enumerate(results['changes'], 1):
            print(f"\\n{i}. {change['type'].upper()}: {change['id']}")
            if 'session_id' in change:
                print(f"   Session: {change['session_id']}")
            print(f"   Root buttons: {change['root_buttons_count']}")
            print(f"   Component buttons: {change['component_buttons_count']}")
            
            if args.verbose:
                print(f"   Root buttons removed: {change['root_buttons']}")
                print(f"   Component buttons kept: {change['component_buttons']}")
    
    total_issues = results['sessions_with_duplicates'] + results['drafts_with_duplicates']
    total_fixed = results['sessions_fixed'] + results['drafts_fixed']
    
    print(f"\\n=== SUMMARY ===")
    print(f"Total items with duplicates: {total_issues}")
    print(f"Total items fixed: {total_fixed}")
    
    if dry_run and total_issues > 0:
        print("\\n⚠️  This was a dry run. Use --apply to fix the issues.")
    elif total_fixed > 0:
        print("\\n✅ Fixes applied successfully!")
    else:
        print("\\n✅ No duplicate button issues found!")

if __name__ == '__main__':
    asyncio.run(main())
