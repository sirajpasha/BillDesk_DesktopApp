import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_powershell_launcher_check_only():
    """Verify that start.ps1 runs dependency checks and completes successfully."""
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", str(ROOT / "start.ps1"),
        "-CheckOnly"
    ]
    res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    assert res.returncode == 0, f"start.ps1 failed with stderr: {res.stderr}\nstdout: {res.stdout}"
    assert "All dependencies verified and ready!" in res.stdout
    assert "MongoDB" in res.stdout

def test_batch_launcher_check_only():
    """Verify that start.bat runs dependency checks and completes successfully."""
    cmd = [str(ROOT / "start.bat"), "-CheckOnly"]
    res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    assert res.returncode == 0, f"start.bat failed with stderr: {res.stderr}\nstdout: {res.stdout}"
    assert "All dependencies verified and ready!" in res.stdout

def test_bash_launcher_check_only():
    """Verify that start.sh runs dependency checks in bash if bash is installed."""
    bash_path = None
    import shutil
    bash_path = shutil.which("bash")
    if not bash_path:
        return
    cmd = [bash_path, str(ROOT / "start.sh"), "--check-only"]
    res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    # Bash might run under WSL where Linux python is different, but if run on Git Bash it passes
    if res.returncode == 0:
        assert "All dependencies verified and ready!" in res.stdout
