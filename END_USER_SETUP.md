# 🚀 Freshrelease MCP for Cursor - End User Setup

**⚡ No Python Installation Required!**

## What This Does
Enables Cursor AI to interact with your Freshrelease projects - create tasks, filter issues, manage test cases, and more!

## Quick Setup (3 minutes)

### Step 1: Install uv (one-time setup)

**macOS/Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows:**
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Step 2: Configure Cursor

1. Open/create `~/.cursor/mcp.json`
2. Add this configuration:

```json
{
  "mcpServers": {
    "freshrelease-mcp": {
      "command": "uvx",
      "args": ["freshrelease-mcp"],
      "env": {
        "FRESHRELEASE_API_KEY": "your_api_key_here",
        "FRESHRELEASE_DOMAIN": "yourcompany.freshrelease.com", 
        "FRESHRELEASE_PROJECT_KEY": "your_default_project_key"
      }
    }
  }
}
```

### Step 3: Get Your Freshrelease Credentials

1. **API Key**: Go to Freshrelease → Profile → API Key
2. **Domain**: Your Freshrelease URL (e.g., `company.freshrelease.com`)  
3. **Project Key**: Your project identifier (e.g., `PROJ`, `FS`)

### Step 4: Restart Cursor

Close and reopen Cursor completely.

## ✅ Verification

You should now see Freshrelease tools available in Cursor:
- `fr_create_task` - Create tasks/issues
- `fr_get_all_tasks` - Get all tasks  
- `fr_filter_tasks` - Filter tasks by criteria
- `fr_get_testcase` - Get test cases
- `fr_link_testcase_issues` - Link test cases to issues
- And 20+ more functions!

## 🛠️ Troubleshooting

### Not seeing tools?
1. Check your `mcp.json` syntax
2. Verify environment variables are correct
3. Restart Cursor completely
4. Check Cursor's developer console for errors

### Test the MCP directly:
```bash
uvx freshrelease-mcp --help
```

### Clear cache if needed:
```bash
uvx --reinstall freshrelease-mcp
```

### Check uv installation:
```bash
uv --version
```

## 🎯 How It Works

- `uvx` automatically downloads Python and the package
- No Python installation needed on your system  
- Everything runs in isolated environments
- Updates are automatic
- Works on all platforms

## 📞 Support

If you encounter issues:
1. Verify your Freshrelease credentials
2. Check the troubleshooting steps above
3. Ensure you have network access to PyPI and Freshrelease

---

**🎉 You're all set! Cursor can now interact with your Freshrelease projects seamlessly.**
