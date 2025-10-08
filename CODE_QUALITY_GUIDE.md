# Code Quality & Indentation Guide for Freshrelease MCP

## 🎯 Purpose
This guide ensures consistent, error-free code development for the Freshrelease MCP project, specifically focusing on preventing indentation errors and maintaining high code quality.

## 📐 Indentation Standards

### **Python Indentation Rules**
- **USE 4 SPACES** - Never use tabs
- **Consistent throughout** - All code blocks must use exactly 4 spaces
- **No mixed indentation** - Never mix spaces and tabs
- **Function/Class bodies** - Always indent by 4 spaces from the def/class line

### **Common Indentation Patterns in This Project**

#### ✅ **Correct MCP Tool Function Structure**
```python
@mcp.tool()
@performance_monitor("function_name")
async def function_name(
    param1: Type,
    param2: Optional[Type] = None
) -> Dict[str, Any]:
    """Docstring with proper indentation.
    
    Args:
        param1: Description
        param2: Description
        
    Returns:
        Description
    """
    try:
        # Function body - 4 spaces from def line
        if condition:
            # Nested block - 8 spaces from def line
            result = await some_function()
            return result
        else:
            # Same level as if - 8 spaces from def line
            return error_response
            
    except Exception as e:
        # Exception handling - 4 spaces from def line
        return create_error_response(f"Error: {str(e)}")
```

#### ✅ **Correct Dictionary/List Structures**
```python
# Multi-line dictionary
result = {
    "key1": value1,
    "key2": {
        "nested_key": nested_value,
        "another_key": another_value
    },
    "key3": [
        item1,
        item2,
        item3
    ]
}

# Function call with multiple parameters
response = await make_api_request(
    method="GET",
    url=url,
    headers=headers,
    params={
        "param1": value1,
        "param2": value2
    }
)
```

#### ✅ **Correct If/Else/Try/Except Structures**
```python
# Proper if-else indentation
if condition1:
    # 4 spaces from if
    action1()
    if nested_condition:
        # 8 spaces from original if
        nested_action()
elif condition2:
    # Same level as if
    action2()
else:
    # Same level as if
    default_action()

# Proper try-except indentation
try:
    # 4 spaces from try
    risky_operation()
    if success:
        # 8 spaces from try
        handle_success()
except SpecificError as e:
    # Same level as try
    handle_error(e)
except Exception as e:
    # Same level as try
    handle_generic_error(e)
finally:
    # Same level as try
    cleanup()
```

#### ✅ **Correct Loop Structures**
```python
# For loop indentation
for item in items:
    # 4 spaces from for
    processed_item = process(item)
    if processed_item:
        # 8 spaces from for
        results.append(processed_item)
        if detailed_logging:
            # 12 spaces from for
            logging.info(f"Processed: {processed_item}")

# While loop indentation
while condition:
    # 4 spaces from while
    result = get_next_item()
    if result:
        # 8 spaces from while
        process_result(result)
```

## ❌ Common Indentation Mistakes to Avoid

### **Mistake 1: Inconsistent Spacing**
```python
# WRONG - Mixed indentation levels
def bad_function():
    if condition:
        action1()  # 4 spaces
          action2()  # 6 spaces - WRONG!
      action3()    # 2 spaces - WRONG!
```

### **Mistake 2: Hanging Indents After Colons**
```python
# WRONG - Incorrect indentation after if/else
if condition:
        # 8 spaces instead of 4 - WRONG!
    action()

# WRONG - Incorrect else indentation
if condition:
    action1()
        else:  # Should align with if - WRONG!
    action2()
```

### **Mistake 3: Function/Method Indentation Errors**
```python
# WRONG - Class method indentation
class MyClass:
    def method1(self):
        pass
        
        def method2(self):  # Should be at class level - WRONG!
        pass
```

### **Mistake 4: Dictionary/List Indentation Errors**
```python
# WRONG - Inconsistent dictionary indentation
result = {
    "key1": value1,
        "key2": value2,  # Extra indentation - WRONG!
"key3": value3           # Missing indentation - WRONG!
}
```

## 🛠️ Project-Specific Patterns

### **MCP Tool Function Template**
```python
@mcp.tool()
@performance_monitor("tool_name")
async def tool_name(
    required_param: str,
    optional_param: Optional[str] = None,
    project_identifier: Optional[Union[int, str]] = None
) -> Dict[str, Any]:
    """Tool description.
    
    Args:
        required_param: Description
        optional_param: Description  
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
        
    Returns:
        Dictionary containing results or error response
        
    Examples:
        # Example usage
        tool_name("value")
    """
    try:
        # Environment validation
        env_data = validate_environment()
        project_id = get_project_identifier(project_identifier)
        
        # Main logic
        if condition:
            result = await process_data()
            return {
                "success": True,
                "data": result
            }
        else:
            return create_error_response("Condition not met")
            
    except Exception as e:
        return create_error_response(f"Failed to execute tool: {str(e)}")
```

### **API Request Pattern**
```python
# Standard API request structure
async def make_request():
    try:
        url = f"{base_url}/{endpoint}"
        params = {
            "param1": value1,
            "param2": value2
        }
        
        result = await make_api_request(
            method="GET",
            url=url,
            headers=headers,
            params=params
        )
        
        if "error" not in result:
            return process_success(result)
        else:
            return handle_error(result)
            
    except httpx.HTTPStatusError as e:
        return create_error_response(f"HTTP error: {str(e)}")
    except Exception as e:
        return create_error_response(f"Request failed: {str(e)}")
```

### **AI Analysis Function Pattern**
```python
def _generate_insights(data: List[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]:
    """Generate AI insights from data.
    
    Args:
        data: List of data objects to analyze
        context: Additional context for analysis
        
    Returns:
        Dictionary containing insights, recommendations, and metrics
    """
    if not data:
        return {
            "summary": "No data available for analysis.",
            "insights": [],
            "recommendations": [],
            "metrics": {}
        }
    
    # Initialize counters
    metrics = {}
    insights = []
    recommendations = []
    
    # Analyze data
    for item in data:
        # Process each item
        if item.get("status"):
            status = item["status"]
            metrics[status] = metrics.get(status, 0) + 1
    
    # Generate insights based on analysis
    if metrics:
        total_items = len(data)
        for status, count in metrics.items():
            percentage = (count / total_items) * 100
            insights.append(f"{status}: {count} items ({percentage:.1f}%)")
    
    return {
        "summary": f"Analyzed {len(data)} items",
        "insights": insights,
        "recommendations": recommendations,
        "metrics": metrics
    }
```

## 🔧 Code Optimization Guidelines

### **Performance Optimization**
1. **Use async/await properly**
   ```python
   # Good - Parallel API calls
   tasks = [
       make_api_call(url1),
       make_api_call(url2),
       make_api_call(url3)
   ]
   results = await asyncio.gather(*tasks)
   
   # Avoid - Sequential API calls
   result1 = await make_api_call(url1)
   result2 = await make_api_call(url2)
   result3 = await make_api_call(url3)
   ```

2. **Efficient data processing**
   ```python
   # Good - List comprehension
   processed_items = [
       process_item(item) 
       for item in items 
       if item.get("active")
   ]
   
   # Good - Generator for large datasets
   def process_large_dataset(items):
       for item in items:
           if should_process(item):
               yield process_item(item)
   ```

3. **Memory optimization**
   ```python
   # Good - Process in chunks for large datasets
   def process_in_chunks(items, chunk_size=100):
       for i in range(0, len(items), chunk_size):
           chunk = items[i:i + chunk_size]
           yield process_chunk(chunk)
   ```

### **Error Handling Optimization**
```python
# Comprehensive error handling pattern
async def robust_api_call(url: str, retries: int = 3) -> Dict[str, Any]:
    """Make API call with proper error handling and retries."""
    for attempt in range(retries):
        try:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
            
        except httpx.TimeoutException:
            if attempt == retries - 1:
                return create_error_response("Request timed out after retries")
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return create_error_response("Resource not found")
            elif e.response.status_code >= 500:
                if attempt == retries - 1:
                    return create_error_response(f"Server error: {e.response.status_code}")
                await asyncio.sleep(2 ** attempt)
            else:
                return create_error_response(f"HTTP error: {e.response.status_code}")
                
        except Exception as e:
            return create_error_response(f"Unexpected error: {str(e)}")
    
    return create_error_response("All retry attempts failed")
```

### **Code Reusability Optimization**
```python
# Create reusable helper functions
def _add_ai_summary_to_result(result: Dict[str, Any], data_key: str, summary_func: Callable) -> Dict[str, Any]:
    """Generic helper to add AI summary to any result."""
    if "error" in result:
        return result
        
    data = result.get(data_key, [])
    ai_summary = summary_func(data)
    
    return {
        data_key: data,
        "ai_summary": ai_summary,
        "original_response": result
    }

# Use helper function in multiple places
def process_tasks_with_summary(result):
    return _add_ai_summary_to_result(result, "tasks", _generate_task_insights)

def process_testcases_with_summary(result):
    return _add_ai_summary_to_result(result, "test_cases", _generate_testcase_insights)
```

### **❌ Avoiding Redundant Code and Duplicate Methods**

**Rule:** Always check if functionality already exists before creating new methods. Enhance existing methods rather than duplicating functionality.

#### **❌ Bad Example: Creating Duplicate Methods**
```python
# EXISTING METHOD (already handles field resolution)
async def _resolve_testcase_field_value(condition, value, project_id, client, base_url, headers):
    """Existing method that resolves testcase field values."""
    if condition == "creator_id":
        return await _resolve_user_name_to_id(value, project_id, client, base_url, headers)
    elif condition == "section_id":
        return await _resolve_name_to_id_generic(value, project_id, client, base_url, headers, "sections")
    # ... existing logic

# BAD - Creating a duplicate method with similar functionality
async def resolve_testcase_field_explicit(condition, value):
    """REDUNDANT - Duplicates existing functionality!"""
    if condition == "creator_id":
        return await resolve_creator_to_id(value)  # Same logic, different wrapper
    elif condition == "severity_id":
        return severity_options.get(value.lower())  # Only new part
    # ... duplicate logic
```

#### **✅ Good Example: Enhancing Existing Methods**
```python
# ENHANCED - Add optional parameters to existing method
async def _resolve_testcase_field_value(
    condition: str, 
    value: Any, 
    project_id: Union[int, str],
    client: httpx.AsyncClient,
    base_url: str,
    headers: Dict[str, str],
    severity_options: Optional[Dict[str, int]] = None,  # ← NEW
    section_options: Optional[Dict[str, int]] = None    # ← NEW
) -> Any:
    """Enhanced existing method with new functionality."""
    
    # NEW functionality: Use form field mappings when available
    if condition == "severity_id" and severity_options and value.lower() in severity_options:
        return severity_options[value.lower()]
    
    # EXISTING functionality: Maintained and enhanced
    elif condition == "creator_id":
        return await _resolve_user_name_to_id(value, project_id, client, base_url, headers)
    # ... rest of existing logic
```

#### **🔍 Before Creating New Methods - Ask These Questions:**

1. **Does similar functionality already exist?**
   ```bash
   # Search for existing methods
   grep -n "def.*resolve.*field" src/freshrelease_mcp/server.py
   grep -n "async def.*resolve" src/freshrelease_mcp/server.py
   ```

2. **Can I enhance the existing method instead?**
   - Add optional parameters for new functionality
   - Maintain backward compatibility
   - Use progressive enhancement patterns

3. **Am I duplicating logic?**
   - If you're copying code patterns, refactor instead
   - Create shared helper functions for common logic
   - Use composition over duplication

#### **✅ Code Review Checklist for Redundancy**

Before committing new methods:

- [ ] **Search existing codebase** for similar functionality
- [ ] **Check method signatures** - do they overlap with existing methods?
- [ ] **Analyze logic patterns** - am I copying existing conditional structures?
- [ ] **Consider enhancement** - can I add optional parameters to existing methods?
- [ ] **Test backward compatibility** - do existing calls still work?

#### **🚨 Warning Signs of Redundant Code**

- **Similar method names**: `resolve_field()` vs `resolve_field_explicit()`
- **Duplicate conditional logic**: Same if/elif patterns in multiple methods
- **Wrapper functions**: Methods that just call other methods with minor changes
- **Copy-paste patterns**: Large blocks of similar code with minor variations

#### **✅ Refactoring Strategy When You Find Redundancy**

1. **Identify the core method** that should be enhanced
2. **Add optional parameters** for new functionality  
3. **Update all call sites** to use enhanced method
4. **Remove duplicate methods** completely
5. **Test thoroughly** to ensure no regressions
6. **Update documentation** to reflect changes

**Remember: One well-designed method is better than multiple similar methods!**

## 🔍 Pre-Commit Checklist

### **Before Adding New Code:**
1. ✅ **Check indentation consistency**
   - All function bodies use 4 spaces
   - All nested blocks properly aligned

2. ✅ **Check for redundant code**
   - Search for existing similar functionality
   - Consider enhancing existing methods instead of creating new ones
   - Verify no duplicate conditional logic patterns

3. ✅ **Verify function structure**
   - Proper MCP tool decorators
   - Consistent parameter naming
   - Complete docstrings with Args/Returns

4. ✅ **Test error scenarios**
   - Handle all expected exceptions
   - Provide meaningful error messages
   - Include fallback behaviors

5. ✅ **Optimize performance**
   - Use async/await appropriately
   - Consider parallel processing
   - Implement caching where beneficial

6. ✅ **Code reusability**
   - Extract common patterns into helpers
   - Follow DRY principle
   - Create reusable components

## 🚨 Emergency Indentation Fix

If you encounter indentation errors:

1. **Use your editor's "show whitespace" feature**
2. **Select all code and auto-format** (most editors have this)
3. **Manually check these common areas:**
   - After `if`, `elif`, `else` statements
   - After `try`, `except`, `finally` blocks
   - After `for`, `while` loops
   - After function/class definitions
   - Inside dictionaries and lists

4. **Verify using Python's built-in checker:**
   ```bash
   python -m py_compile filename.py
   ```

## 📋 IDE Configuration Recommendations

### **VS Code Settings**
```json
{
    "python.defaultInterpreterPath": "./venv/bin/python",
    "editor.tabSize": 4,
    "editor.insertSpaces": true,
    "editor.detectIndentation": false,
    "python.linting.enabled": true,
    "python.linting.flake8Enabled": true,
    "python.formatting.provider": "black",
    "editor.formatOnSave": true
}
```

### **PyCharm Settings**
- File → Settings → Editor → Code Style → Python
- Set "Tab size" and "Indent" to 4
- Check "Use tab character" should be UNCHECKED
- Enable "Optimize imports on the fly"

## 🎯 Quality Assurance Commands

```bash
# Check for indentation issues
python -m py_compile src/freshrelease_mcp/server.py

# Format code (if black is installed)
black src/freshrelease_mcp/server.py

# Check linting
flake8 src/freshrelease_mcp/server.py

# Build and test
uv build
```

## 📝 Final Notes

- **Always test your code** before committing
- **Use consistent naming conventions** throughout the project
- **Write comprehensive docstrings** for all public functions
- **Handle edge cases** and provide meaningful error messages
- **Optimize for readability** - code is read more often than written
- **Follow the established patterns** in the existing codebase

---

*This guide should be updated whenever new patterns or conventions are established in the project.*
