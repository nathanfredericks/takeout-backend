import os
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from models import Base

load_dotenv()

DB_TYPE = os.getenv("DB_TYPE", "sqlite")

sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

mysql_user = os.getenv("MYSQL_USER")
mysql_password = os.getenv("MYSQL_PASSWORD")
mysql_host = os.getenv("MYSQL_HOST")
mysql_port = os.getenv("MYSQL_PORT")
mysql_database = os.getenv("MYSQL_DATABASE")
mysql_url = f"mysql+pymysql://{mysql_user}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_database}"

if DB_TYPE.lower() == "mysql" or DB_TYPE.lower() == "mariadb":
    db_url = mysql_url
    connect_args = {}
else:
    db_url = sqlite_url
    connect_args = {"check_same_thread": False}

engine = create_engine(db_url, echo=True, connect_args=connect_args)


def create_db_and_tables():
    Base.metadata.create_all(engine)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_session():
    with SessionLocal() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
