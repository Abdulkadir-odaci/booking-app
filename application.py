from app import app
import os

# Import and run database initialization
try:
    from app import ensure_database_initialized
    print("🌟 AWS Application startup - initializing database...")
    ensure_database_initialized()
    print("✅ AWS database initialization complete!")
except Exception as e:
    print(f"❌ AWS database initialization failed: {e}")

application = app

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    application.run(host='0.0.0.0', port=port, debug=False)
