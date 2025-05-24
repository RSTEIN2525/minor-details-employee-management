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

# Validate that all required environment variables are set
required_vars = ["DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD"]
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

# Construct PostgreSQL connection URL
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# The Wire / Link That Lets Us Pass Data from App -> db
# Note: echo=True will log all SQL statements, set to False in production
engine = create_engine(DATABASE_URL, echo=True)

# Getter for this Wire, modified for FastAPI dependency injection
def get_session():
    with Session(engine) as session:
        try:
            yield session
        finally:
            session.close()
