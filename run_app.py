"""PyInstaller entry point (relative imports need a real package)."""

from app.main import main

if __name__ == "__main__":
    raise SystemExit(main())
