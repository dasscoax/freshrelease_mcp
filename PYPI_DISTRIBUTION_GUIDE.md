# Freshrelease MCP - PyPI Distribution Guide

## 🎯 **End Users Don't Need Python Installed!**

With `uvx` and PyPI distribution, your end users only need the `uv` tool (a single binary) and can run your MCP without any Python installation.

## 📦 Publishing to PyPI

### 1. **Prepare for Publication**

Your package is ready! I've enhanced `pyproject.toml` with proper metadata:
- ✅ Added PyPI classifiers
- ✅ Added keywords for discoverability  
- ✅ Cleaned up dependencies
- ✅ Added proper description

### 2. **Publish to PyPI**

```bash
# 1. Build the package (already done)
uv build

# 2. Install twine if needed
uv tool install twine

# 3. Upload to PyPI (you'll need PyPI account)
uv tool run twine upload dist/*

# Optional: Upload to Test PyPI first
uv tool run twine upload --repository testpypi dist/*
```

### 3. **Get PyPI Account**
- Go to [https://pypi.org/account/register/](https://pypi.org/account/register/)
- Create account and get API token
- Use token for authentication during upload

## 🚀 End User Installation (NO Python Required!)

### **For End Users - Super Simple Setup:**

1. **Install uv (one-time setup)**:
   ```bash
   # macOS/Linux
   curl -LsSf https://astral.sh/uv/install.sh | sh
   
   # Windows
   powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

2. **Use your MCP** (no Python installation needed!):
   ```bash
   # This automatically downloads Python + your package + dependencies
   uvx freshrelease-mcp --help
   ```

### **Cursor Configuration for End Users:**

Once published to PyPI, end users can use this config:

```json
{
  "mcpServers": {
    "freshrelease-mcp": {
      "command": "uvx",
      "args": ["freshrelease-mcp"],
      "env": {
        "FRESHRELEASE_API_KEY": "your_api_key_here", 
        "FRESHRELEASE_DOMAIN": "your_domain.freshrelease.com",
        "FRESHRELEASE_PROJECT_KEY": "your_project_key"
      }
    }
  }
}
```

## 🧪 Testing the Distribution

### Test with TestPyPI first:
```bash
# Upload to Test PyPI
uv tool run twine upload --repository testpypi dist/*

# Test installation from Test PyPI
uvx --index-url https://test.pypi.org/simple/ freshrelease-mcp
```

## 📋 Complete End User Instructions

Create this for your users:

---

## **Freshrelease MCP for Cursor - User Guide**

### **What You Need:**
- Cursor IDE
- `uv` tool (single binary - no Python needed!)

### **Setup Steps:**

1. **Install uv** (one-time):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Add to Cursor config** (`~/.cursor/mcp.json`):
   ```json
   {
     "mcpServers": {
       "freshrelease-mcp": {
         "command": "uvx", 
         "args": ["freshrelease-mcp"],
         "env": {
           "FRESHRELEASE_API_KEY": "your_api_key",
           "FRESHRELEASE_DOMAIN": "yourcompany.freshrelease.com", 
           "FRESHRELEASE_PROJECT_KEY": "PROJ"
         }
       }
     }
   }
   ```

3. **Restart Cursor** - Done! 🎉

### **How it Works:**
- `uvx` automatically downloads Python and the package
- No Python installation needed on your system
- Everything is managed automatically
- Updates work seamlessly

---

## 🔧 Version Management

### **Updating Your Package:**

1. **Bump version** in `pyproject.toml`:
   ```toml
   version = "1.6.6"  # Increment version
   ```

2. **Rebuild and republish**:
   ```bash
   uv build
   uv tool run twine upload dist/*
   ```

3. **Users get updates automatically** with `uvx`!

## 🎯 Benefits for End Users

- ✅ **No Python installation required**
- ✅ **Single command installation** 
- ✅ **Automatic dependency management**
- ✅ **Isolated environments**
- ✅ **Easy updates**
- ✅ **Works on all platforms**

## 🛠️ Troubleshooting

### **For End Users:**
```bash
# Clear uvx cache if issues
uvx --reinstall freshrelease-mcp

# Check if uv is working
uv --version

# Test the MCP directly
uvx freshrelease-mcp --help
```

### **For Publishers:**
```bash
# Check package contents
uv tool run twine check dist/*

# Test installation locally
uvx --force-reinstall freshrelease-mcp
```

---

**🎉 Result: Your end users get a professional, easy-to-install MCP that works without any Python setup!**
