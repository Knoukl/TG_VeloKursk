from sqlalchemy import Column, Integer, String, Float, create_engine, LargeBinary
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()
engine = create_engine("sqlite:///../data/velo.db")


class User(Base):
    __tablename__ = 'users'
    tg_id = Column(Integer, primary_key=True)
    nickname = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    state = Column(String)


class Track(Base):
    __tablename__ = 'tracks'
    id = Column(Integer, primary_key=True, autoincrement=True)
    trailholder = Column(String)
    name = Column(String)
    difficulty = Column(Integer)
    description = Column(String)
    photo1 = Column(LargeBinary)
    photo2 = Column(LargeBinary)
    file = Column(LargeBinary)
    distance = Column(Float)
    primary_wind = Column(String)
