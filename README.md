# Freshrelease MCP Server

[![PyPI version](https://badge.fury.io/py/freshrelease-mcp.svg)](https://badge.fury.io/py/freshrelease-mcp)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

An MCP server that enables AI models to interact with Freshrelease through powerful tools for complete project and test management.

## 🚀 Key Features

- **🤖 AI-Native**: Built specifically for AI model integration via MCP protocol
- **🔧 Complete Management**: Projects, tasks, test cases, test runs, and user management  
- **🧠 Smart Resolution**: Automatically converts names to IDs (users, sprints, projects, etc.)
- **📋 Native Filtering**: Full support for Freshrelease's native query_hash format
- **🌲 Hierarchical Navigation**: Navigate through 7-level deep section hierarchies  
- **⚡ Performance Optimized**: Built-in caching, connection pooling, and batch processing
- **🎯 Label-Based Filtering**: Use intuitive field names like "Owner" instead of "owner_id"

## 📊 Tools Overview

| **Category** | **Key Features** |
|-------------|------------------|
| **Core Management** | Projects, tasks, users, and issue types |
| **Test Management** | Test cases, test runs, and execution tracking |  
| **Smart Filtering** | Advanced task and test case filtering |
| **Lookup & Utilities** | Name-to-ID resolution and cache management |

## 🛠️ Available Tools

### **Core Management**
| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `fr_get_project` | Get project details | `project_identifier` |
| `fr_get_task` | Get task by ID/key | `project_identifier`, `key` |
| `fr_get_all_tasks` | List all project tasks | `project_identifier` |
| `fr_get_epic_insights` | Get comprehensive AI insights for epics with detailed task analysis | `epic_key`, `fetch_detailed_tasks`, `max_tasks` |
| `fr_get_issue_type_by_name` | Resolve issue type names | `issue_type_name` |
| `get_task_default_and_custom_fields` | Get form fields for issue types | `issue_type_name` |
| `fr_search_users` | Find users by name/email | `search_text` |

### **Test Management**
| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `fr_list_testcases` | List all test cases | `project_identifier` |
| `fr_get_testcase` | Get specific test case | `test_case_key` |
| `fr_get_testcases_by_section` | Get tests by section | `section_name` |
| `fr_link_testcase_issues` | Link tests to issues | `testcase_keys`, `issue_keys` |
| `fr_testcase_filter_summary` | Advanced test filtering with AI insights | `filter_rules` |
| `fr_add_testcases_to_testrun` | Add tests to run | `test_run_id`, `test_case_keys` |
| `fr_get_testrun_summary` | Get comprehensive test run summary with AI quality analysis | `test_run_id` |

### **Smart Filtering**  
| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `fr_filter_tasks` | Advanced task filtering with native query_hash | `query_hash`, `filter_id`, `include`, pagination |
| `fr_get_issue_form_fields` | Get issue form schema | `issue_type_id` |
| `fr_get_testcase_form_fields` | Get test form schema | - |
| `fr_get_all_issue_type_form_fields` | Get all form schemas | - |

### **Lookup & Utilities**
| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `fr_get_sprint_by_name` | Find sprint by name | `sprint_name` |
| `fr_get_release_by_name` | Find release by name | `release_name` |
| `fr_get_tag_by_name` | Find tag by name | `tag_name` |
| `fr_get_current_subproject_sprint` | Get active sub-project sprint | `sub_project_name` |
| `get_subproject_id_by_name` | Resolve sub-project names | `sub_project_name` |
| `fr_clear_filter_cache` | Clear filter cache | - |
| `fr_clear_all_caches` | Clear all caches | - |


## ✨ Smart Features

- **🧠 Name-to-ID Resolution**: Converts user names, sprint names, issue types, etc. to IDs automatically
- **📋 Native Query Format**: Full support for Freshrelease's `query_hash` format with all operators
- **🌲 Hierarchical Sections**: Navigate up to 7 levels deep section hierarchies (e.g., `"Level1 > Level2 > Level3"`)
- **🔄 API Compatibility**: Handles both nested `{"users": [...]}` and direct array response formats
- **⚡ Performance Optimized**: Multi-level caching, connection pooling, optimized batch processing
- **🔗 Flexible Project IDs**: Accept both project keys (`"FS"`) and numeric IDs (`123`)
- **🎯 Custom Field Support**: Auto-detects and handles custom fields with "cf_" prefixing
- **📊 Multiple Query Formats**: Native query_hash, comma-separated strings, or JSON objects

## 🚀 Quick Start

### 1. Install
```bash
# Easy install (no Python needed)
curl -LsSf https://astral.sh/uv/install.sh | sh
# Or with Python: uv tool install freshrelease-mcp
```

### 2. Get Credentials
- **API Key**: Freshrelease → Profile → API Key
- **Domain**: `company.freshrelease.com` (your domain)
- **Project Key**: e.g., `"FS"`, `"PROJ"` (optional)

### 3. Configure Cursor
Add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "freshrelease-mcp": {
      "command": "uvx",
      "args": ["freshrelease-mcp"],
      "env": {
        "FRESHRELEASE_API_KEY": "your_api_key",
        "FRESHRELEASE_DOMAIN": "company.freshrelease.com",
        "FRESHRELEASE_PROJECT_KEY": "FS"
      }
    }
  }
}
```

### 4. Restart Cursor
✅ You'll see Freshrelease tools available!

## 💡 Usage Examples

### 🎯 Task Management
**Get project overview:**
> "Show me all tasks in the FS project"

**Get specific task details:**
> "Get details for task FS-123"

**Get comprehensive epic insights with AI analysis:**
> "Show me detailed insights for epic FS-223786 including git status and risk assessment"

The AI will automatically:
- Fetch the epic details and all child tasks with full information
- Analyze git/PR development status from task descriptions
- Provide AI-powered insights on completion rates, team distribution, and timeline risks
- Provide status breakdown and progress summary
- Show assignee distribution and priority breakdown

### 📋 Advanced Task Filtering  
**Use natural language filtering:**
> "Find all high priority tasks owned by John Doe that are currently in progress"

The AI understands both:
- **Friendly labels**: "Owner", "Status", "Priority" 
- **Technical names**: "owner_id", "status_id", "priority_id"

**Native Freshrelease filtering with existing filters:**
> "Filter tasks using saved filter ID 102776 with custom fields and date ranges"

**Sprint and date-based filtering:**
> "Show me all bugs in Sprint 1 created between Dec 2024 and Aug 2025"

### 🧪 Test Case Management
**Filter test cases naturally:**
> "Find all high and medium severity functional tests in the Authentication section"

**Navigate hierarchical sections:**
> "Get all test cases from Authentication > Login Tests > Positive Cases section"

The AI can navigate up to 7 levels deep in section hierarchies automatically.

**Get concise test run summary with AI insights:**
> "How is test run 150183 performing?"

**Response example:**
*"23/25 tests executed (92% complete). 21 passed, 2 failed. Quality score: Good. Fix 2 failing test cases."*

## 🛠️ Development Tools

### **Code Quality Assurance**
This project includes comprehensive tools to maintain code quality and prevent common issues:

#### **📋 Code Quality Guide** (`CODE_QUALITY_GUIDE.md`)
- Complete indentation standards and best practices
- Project-specific code patterns and templates  
- Common mistakes to avoid with examples
- Performance optimization guidelines
- Pre-commit checklist for developers

#### **🔍 Automated Quality Checker** (`quality_check.py`)
Run quality checks on any Python file:
```bash
python3 quality_check.py src/freshrelease_mcp/server.py
```

**Features:**
- ✅ Indentation validation (4-space standard)
- ✅ MCP tool structure verification
- ✅ Function docstring checks
- ✅ Async/await pattern validation
- ✅ Error handling analysis

**Example output:**
```
✅ No issues found in src/freshrelease_mcp/server.py
```

## 🆕 Latest Updates

### **v1.9.7 - Optimized AI Insights & Code Quality**
- ✅ **Optimized Test Run AI**: Simplified `fr_get_testrun_summary` with concise insights, quality scores, and focused recommendations
- ✅ **Epic AI Insights**: Renamed and enhanced `fr_get_epic_insights` with comprehensive AI analysis including git/PR status, risk assessment, and detailed task analysis
- ✅ **Test Case AI Summary**: Renamed `fr_filter_testcases` to `fr_testcase_filter_summary` with intelligent insights and automation analysis
- ✅ **Code Quality Tools**: Added comprehensive code quality guide (`CODE_QUALITY_GUIDE.md`) and automated quality checker (`quality_check.py`)
- ✅ **Enhanced Field Mapping**: Fixed filtering issues with improved field label resolution
- ✅ **Better Error Handling**: Comprehensive logging and error messages for debugging
- ✅ **Issue Key Resolution**: Support for parent_id and epic_id filtering using issue keys

### **v1.8.4 - Filter Bug Fixes**  
- ✅ **Fixed Fields Mapping Error**: Resolved "Failed to get project fields mapping: 0" error
- ✅ **API Response Handling**: Better handling of nested vs. direct array responses
- ✅ **Common Field Mappings**: Added support for "Parent", "Epic", "Owner" field labels

## 🔧 Troubleshooting

**Not seeing tools in Cursor?**
1. Check `~/.cursor/mcp.json` is valid JSON
2. Restart Cursor completely
3. Verify credentials: `uvx freshrelease-mcp --help`

**Environment Variables:**
```bash
FRESHRELEASE_API_KEY="your_api_key"      # Required
FRESHRELEASE_DOMAIN="company.freshrelease.com"  # Required  
FRESHRELEASE_PROJECT_KEY="FS"            # Optional default project
```

## 📄 License

MIT License - see LICENSE file for details.

---

⭐ **Like this project?** Give it a star on GitHub!  
🐛 **Found a bug?** [Open an issue](../../issues)  
💡 **Have ideas?** [Start a discussion](../../discussions)

