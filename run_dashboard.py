"""Launcher for Mission Control dashboard."""
import os, sys

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)
os.chdir(script_dir)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("dashboard.api:app", host="127.0.0.1", port=8560)
