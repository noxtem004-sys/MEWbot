"""
Check if project is ready for Railway deployment
"""
import os
import sys
from pathlib import Path

def check_file_exists(filepath: str, required: bool = True) -> bool:
    """Check if a file exists"""
    exists = Path(filepath).exists()
    status = "✅" if exists else ("❌" if required else "⚠️")
    req_text = "(required)" if required else "(optional)"
    print(f"{status} {filepath} {req_text}")
    return exists or not required

def check_requirements():
    """Check requirements.txt"""
    req_file = Path("requirements.txt")
    if not req_file.exists():
        print("❌ requirements.txt not found")
        return False
    
    with open(req_file) as f:
        content = f.read()
    
    required_packages = [
        "aiogram",
        "aiohttp",
        "aiosqlite",
        "cryptography"
    ]
    
    all_found = True
    for package in required_packages:
        if package.lower() in content.lower():
            print(f"✅ {package} found in requirements.txt")
        else:
            print(f"❌ {package} NOT found in requirements.txt")
            all_found = False
    
    return all_found

def check_environment_example():
    """Check .env.example"""
    env_file = Path(".env.example")
    if not env_file.exists():
        print("⚠️  .env.example not found (optional but recommended)")
        return True
    
    with open(env_file) as f:
        content = f.read()
    
    required_vars = [
        "LICENSE_SERVER_SECRET_KEY",
        "LICENSE_BOT_TOKEN",
        "LICENSE_BOT_ADMIN_IDS"
    ]
    
    for var in required_vars:
        if var in content:
            print(f"✅ {var} documented in .env.example")
        else:
            print(f"⚠️  {var} not in .env.example")
    
    return True

def check_gitignore():
    """Check .gitignore"""
    gitignore = Path(".gitignore")
    if not gitignore.exists():
        print("⚠️  .gitignore not found")
        return True
    
    with open(gitignore) as f:
        content = f.read()
    
    if ".env" in content:
        print("✅ .env is in .gitignore (good for security)")
    else:
        print("⚠️  .env should be in .gitignore")
    
    if "*.db" in content:
        print("✅ *.db is in .gitignore")
    else:
        print("⚠️  *.db should be in .gitignore")
    
    return True

def main():
    """Main check function"""
    print("=" * 60)
    print("Railway Deployment Readiness Check")
    print("=" * 60)
    print()
    
    print("📁 Checking required files...")
    print("-" * 60)
    
    checks = [
        check_file_exists("requirements.txt", required=True),
        check_file_exists("Procfile", required=True),
        check_file_exists("runtime.txt", required=False),
        check_file_exists("railway.toml", required=False),
        check_file_exists("backend/license_server.py", required=True),
        check_file_exists("backend/license_bot.py", required=True),
        check_file_exists("backend/license_database.py", required=True),
        check_file_exists("core/license_client.py", required=True),
        check_file_exists(".gitignore", required=False),
        check_file_exists(".env.example", required=False),
        check_file_exists("RAILWAY_DEPLOYMENT.md", required=False),
    ]
    
    print()
    print("📦 Checking Python packages...")
    print("-" * 60)
    checks.append(check_requirements())
    
    print()
    print("🔧 Checking environment configuration...")
    print("-" * 60)
    checks.append(check_environment_example())
    
    print()
    print("🔒 Checking security files...")
    print("-" * 60)
    checks.append(check_gitignore())
    
    print()
    print("=" * 60)
    
    if all(checks):
        print("✅ Project is READY for Railway deployment!")
        print()
        print("Next steps:")
        print("1. Create a Railway account at https://railway.com")
        print("2. Push your code to GitHub/GitLab")
        print("3. Deploy on Railway: New Project → Deploy from repo")
        print("4. Set environment variables (see .env.example)")
        print("5. Generate domain for license-server")
        print()
        print("For detailed guide, read: RAILWAY_DEPLOYMENT.md")
        return 0
    else:
        print("❌ Some issues found. Please fix them before deploying.")
        print()
        print("Missing files or configurations may cause deployment to fail.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
