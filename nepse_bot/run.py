#!/usr/bin/env python3
"""
NEPSE AI Trading Bot — Entry Point
====================================
Starts the NEPSE AI Trading Bot dashboard.

Usage:
    python nepse_bot/run.py

Dashboard will be available at: http://localhost:8888
"""

import sys
import os
import subprocess

# Ensure we can import from the project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

BANNER = """
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║   🇳🇵  NEPSE AI Trading Bot                              ║
║   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━                ║
║   Powered by Kronos Foundation Model                     ║
║   For Nepal Stock Exchange (NEPSE)                        ║
║                                                          ║
║   Dashboard:  http://localhost:8888                       ║
║   Modes:      Intraday (5min) | Swing (Daily)            ║
║                                                          ║
║   ⚠️  For educational/research purposes only              ║
║   ⚠️  Not financial advice — trade at your own risk       ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
"""


def check_dependencies():
    """Check if required packages are installed."""
    required = ['flask', 'flask_cors', 'plotly', 'torch', 'pandas', 'numpy', 'requests']
    missing = []

    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"\n⚠️  Missing packages: {', '.join(missing)}")
        print(f"   Install with: pip install -r nepse_bot/requirements.txt\n")
        return False

    return True


def check_kronos_model():
    """Check if Kronos model code is accessible."""
    try:
        from model import Kronos, KronosTokenizer, KronosPredictor
        print("✅ Kronos model code found")
        return True
    except ImportError as e:
        print(f"⚠️  Kronos model not importable: {e}")
        print("   Predictions will use technical analysis fallback")
        print("   To enable AI predictions, ensure 'model/' directory is accessible")
        return False


def check_device():
    """Check available compute device."""
    import torch
    if torch.backends.mps.is_available():
        print("✅ Apple Silicon MPS detected — GPU acceleration available")
        return 'mps'
    elif torch.cuda.is_available():
        print(f"✅ CUDA GPU detected: {torch.cuda.get_device_name(0)}")
        return 'cuda'
    else:
        print("ℹ️  Using CPU (predictions will be slower)")
        return 'cpu'


def main():
    print(BANNER)

    # Pre-flight checks
    print("Running pre-flight checks...\n")

    if not check_dependencies():
        print("\n❌ Missing dependencies. Install and try again.")
        sys.exit(1)

    check_kronos_model()
    device = check_device()

    print(f"\n{'─' * 50}")
    print("Starting dashboard server...")
    print(f"{'─' * 50}\n")

    # Import and run the Flask app
    from nepse_bot.app import app
    
    try:
        from waitress import serve
        print("⚡ Running on high-performance Production WSGI Server (Waitress)")
        print("🌐 Serving on http://0.0.0.0:8888 (http://localhost:8888)\n")
        serve(app, host='0.0.0.0', port=8888, threads=8)
    except ImportError:
        app.run(
            debug=False,
            host='0.0.0.0',
            port=8888,
            use_reloader=False  # Avoid double-loading models
        )


if __name__ == '__main__':
    main()
