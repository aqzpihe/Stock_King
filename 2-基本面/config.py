import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

REST_API        = os.environ.get("SUPABASE_URL", "https://yxydsxygylpzewumevsz.supabase.co")
service_role    = os.environ.get("SUPABASE_KEY", "")
anon_key        = os.environ.get("SUPABASE_ANON_KEY", "")
Publishable_Key = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
Secret_Key      = os.environ.get("SUPABASE_SECRET_KEY", "")
FINMIND_API     = os.environ.get("FINMIND_API", "")