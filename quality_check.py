#!/usr/bin/env python3
"""
Code Quality Checker for Freshrelease MCP Project

This script helps identify common indentation and code quality issues
before they cause problems in the main codebase.
"""

import ast
import re
import sys
from pathlib import Path
from typing import List, Tuple, Dict, Any


class CodeQualityChecker:
    """Automated code quality and indentation checker."""
    
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.issues: List[Dict[str, Any]] = []
        
    def check_file(self) -> List[Dict[str, Any]]:
        """Run all quality checks on the file."""
        if not self.file_path.exists():
            return [{"type": "error", "message": f"File not found: {self.file_path}"}]
        
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.splitlines()
            
            # Check for basic syntax errors first
            try:
                ast.parse(content)
            except SyntaxError as e:
                self.issues.append({
                    "type": "syntax_error",
                    "line": e.lineno,
                    "message": f"Syntax error: {e.msg}",
                    "severity": "critical"
                })
                return self.issues
            
            # Run all checks
            self._check_indentation(lines)
            self._check_mcp_tool_structure(lines)
            self._check_function_docstrings(lines)
            self._check_error_handling(lines)
            self._check_async_patterns(lines)
            
        except Exception as e:
            self.issues.append({
                "type": "error",
                "message": f"Failed to analyze file: {str(e)}",
                "severity": "critical"
            })
        
        return self.issues
    
    def _check_indentation(self, lines: List[str]) -> None:
        """Check for indentation issues."""
        for i, line in enumerate(lines, 1):
            if not line.strip():
                continue
                
            # Check for tabs
            if '\t' in line:
                self.issues.append({
                    "type": "indentation",
                    "line": i,
                    "message": "Tab characters found - use 4 spaces instead",
                    "severity": "error"
                })
            
            # Check for leading spaces
            leading_spaces = len(line) - len(line.lstrip())
            if leading_spaces > 0 and leading_spaces % 4 != 0:
                self.issues.append({
                    "type": "indentation",
                    "line": i,
                    "message": f"Indentation not multiple of 4 (found {leading_spaces} spaces)",
                    "severity": "error"
                })
    
    def _check_mcp_tool_structure(self, lines: List[str]) -> None:
        """Check MCP tool function structure."""
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            
            # Check for MCP tool without performance monitor
            if stripped.startswith('@mcp.tool()'):
                next_line = lines[i] if i < len(lines) else ""
                if not next_line.strip().startswith('@performance_monitor'):
                    self.issues.append({
                        "type": "mcp_structure",
                        "line": i,
                        "message": "MCP tool missing @performance_monitor decorator",
                        "severity": "warning"
                    })
            
            # Check async function return type annotations
            if stripped.startswith('async def ') and 'mcp.tool' in ''.join(lines[max(0, i-3):i]):
                if '-> Dict[str, Any]' not in stripped and '->' not in stripped:
                    self.issues.append({
                        "type": "type_annotation",
                        "line": i,
                        "message": "MCP tool function missing return type annotation",
                        "severity": "warning"
                    })
    
    def _check_function_docstrings(self, lines: List[str]) -> None:
        """Check for proper function docstrings."""
        in_function = False
        function_line = 0
        has_docstring = False
        
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            
            if stripped.startswith('async def ') or stripped.startswith('def '):
                in_function = True
                function_line = i
                has_docstring = False
                continue
            
            if in_function:
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    has_docstring = True
                    in_function = False
                elif stripped and not stripped.startswith('#'):
                    # Found non-comment code without docstring
                    if not has_docstring:
                        self.issues.append({
                            "type": "docstring",
                            "line": function_line,
                            "message": "Function missing docstring",
                            "severity": "warning"
                        })
                    in_function = False
    
    def _check_error_handling(self, lines: List[str]) -> None:
        """Check for proper error handling patterns (improved logic)."""
        try_blocks = []
        
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            indentation = len(line) - len(line.lstrip())
            
            if stripped.startswith('try:'):
                try_blocks.append({
                    'line': i,
                    'indentation': indentation,
                    'has_except': False
                })
            elif stripped.startswith('except') and try_blocks:
                # Find the matching try block by indentation
                for try_block in reversed(try_blocks):
                    if indentation == try_block['indentation']:
                        try_block['has_except'] = True
                        break
            elif stripped.startswith('finally') and try_blocks:
                # Finally blocks don't require except, so mark as handled
                for try_block in reversed(try_blocks):
                    if indentation == try_block['indentation']:
                        try_block['has_except'] = True  # Finally is acceptable
                        break
        
        # Only report actual issues - skip decorator patterns and context managers
        for try_block in try_blocks:
            if not try_block['has_except']:
                # Check if this might be a decorator or context manager
                try_line = try_block['line'] - 1
                if try_line > 0:
                    prev_line = lines[try_line - 1].strip()
                    # Skip if it's likely a decorator context or performance monitor
                    if any(pattern in prev_line.lower() for pattern in 
                          ['@', 'with ', 'performance_monitor', 'context']):
                        continue
                
                self.issues.append({
                    "type": "error_handling",
                    "line": try_block['line'],
                    "message": "Try block might be missing except or finally block",
                    "severity": "warning"  # Reduced to warning since many are false positives
                })
    
    def _check_async_patterns(self, lines: List[str]) -> None:
        """Check for proper async/await usage."""
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            
            # Check for missing await on async calls
            if 'async def' in stripped:
                continue
                
            # Look for common async function calls without await
            async_patterns = [
                'make_api_request',
                'fr_get_task',
                'fr_filter_tasks',
                'fr_get_project'
            ]
            
            for pattern in async_patterns:
                if pattern in stripped and not stripped.startswith('#'):
                    if 'await' not in stripped and '=' in stripped:
                        self.issues.append({
                            "type": "async_pattern",
                            "line": i,
                            "message": f"Possible missing 'await' for async function: {pattern}",
                            "severity": "warning"
                        })
    
    def generate_report(self) -> str:
        """Generate a formatted report of all issues."""
        if not self.issues:
            return f"✅ No issues found in {self.file_path}\n"
        
        report = f"\n📋 Code Quality Report for {self.file_path}\n"
        report += "=" * 50 + "\n\n"
        
        # Group issues by severity
        critical_issues = [i for i in self.issues if i.get("severity") == "critical"]
        error_issues = [i for i in self.issues if i.get("severity") == "error"]
        warning_issues = [i for i in self.issues if i.get("severity") == "warning"]
        
        if critical_issues:
            report += "🚨 CRITICAL ISSUES:\n"
            for issue in critical_issues:
                line_info = f"Line {issue.get('line', '?')}: " if 'line' in issue else ""
                report += f"   {line_info}{issue['message']}\n"
            report += "\n"
        
        if error_issues:
            report += "❌ ERRORS:\n"
            for issue in error_issues:
                line_info = f"Line {issue.get('line', '?')}: " if 'line' in issue else ""
                report += f"   {line_info}{issue['message']}\n"
            report += "\n"
        
        if warning_issues:
            report += "⚠️  WARNINGS:\n"
            for issue in warning_issues:
                line_info = f"Line {issue.get('line', '?')}: " if 'line' in issue else ""
                report += f"   {line_info}{issue['message']}\n"
            report += "\n"
        
        # Summary
        report += f"📊 SUMMARY:\n"
        report += f"   Total Issues: {len(self.issues)}\n"
        report += f"   Critical: {len(critical_issues)}\n"
        report += f"   Errors: {len(error_issues)}\n"
        report += f"   Warnings: {len(warning_issues)}\n"
        
        return report


def main():
    """Main function to run quality checks."""
    if len(sys.argv) != 2:
        print("Usage: python quality_check.py <file_path>")
        print("Example: python quality_check.py src/freshrelease_mcp/server.py")
        sys.exit(1)
    
    file_path = sys.argv[1]
    checker = CodeQualityChecker(file_path)
    issues = checker.check_file()
    report = checker.generate_report()
    
    print(report)
    
    # Exit with error code if critical issues or errors found
    critical_count = len([i for i in issues if i.get("severity") == "critical"])
    error_count = len([i for i in issues if i.get("severity") == "error"])
    
    if critical_count > 0 or error_count > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
