from sqlmodel import create_engine, Session

# Connects app to db

# Creates a file db file in folder
DATABASE_URL = "sqlite:///./timelog.db" '' \

# The Wire / Link That Lets Us Pass Data from App -> db
engine = create_engine(DATABASE_URL, echo=True)

# Getter for this Wire, modified for FastAPI dependency injection
def get_session():
    with Session(engine) as session:
        try:
            yield session
        finally:
            session.close()
