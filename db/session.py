from sqlmodel import create_engine, Session
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Connects app to PostgreSQL database

# Get database connection details from environment variables
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "5432")  # Default PostgreSQL port
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
INSTANCE_CONNECTION_NAME = os.getenv("INSTANCE_CONNECTION_NAME") # For Cloud SQL Proxy

# Validate that all required environment variables are set
# If INSTANCE_CONNECTION_NAME is set, DB_HOST is not required for connection string
# but it's good practice to keep it for validation or other uses if any.
required_vars_for_tcp = ["DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD"]
required_vars_for_socket = ["DB_NAME", "DB_USER", "DB_PASSWORD", "INSTANCE_CONNECTION_NAME"]

if INSTANCE_CONNECTION_NAME:
    missing_vars = [var for var in required_vars_for_socket if not os.getenv(var)]
    if missing_vars:
        raise ValueError(f"Missing required environment variables for Cloud SQL (socket): {', '.join(missing_vars)}")
    # Construct PostgreSQL connection URL for Cloud SQL (Unix socket)
    DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@/{DB_NAME}?host=/cloudsql/{INSTANCE_CONNECTION_NAME}"
else:
    missing_vars = [var for var in required_vars_for_tcp if not os.getenv(var)]
    if missing_vars:
        raise ValueError(f"Missing required environment variables for TCP: {', '.join(missing_vars)}")
    # Construct PostgreSQL connection URL for TCP (e.g., local development)
    DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# The Wire / Link That Lets Us Pass Data from App -> db
# Note: echo=True will log all SQL statements, set to False in production
engine = create_engine(DATABASE_URL, echo=False)

# Getter for this Wire, modified for FastAPI dependency injection
def get_session():
    with Session(engine) as session:
        try:
            yield session
        finally:
            session.close()
