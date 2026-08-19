# models.py
from sqlalchemy import (
    Column, Integer, String, Boolean, ForeignKey, DateTime, Text, Float
)
from sqlalchemy.orm import relationship
from datetime import datetime
from db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    # ex: "admin", "member", etc. On ajustera plus tard si besoin
    role = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    teams = relationship("UserTeam", back_populates="user")


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    code = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    members = relationship("UserTeam", back_populates="team")
    participants = relationship("Participant", back_populates="team")
    events = relationship("Event", back_populates="team")


class UserTeam(Base):
    __tablename__ = "user_teams"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    # ex: "owner", "coach", "player"
    role = Column(String, nullable=True)

    user = relationship("User", back_populates="teams")
    team = relationship("Team", back_populates="members")


class Participant(Base):
    __tablename__ = "participants"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)

    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)

    # stockage de l'adresse complète qu'on envoie à l'API
    address = Column(Text, nullable=False)

    # optionnel : champs séparés pour saisie côté UI
    street = Column(String, nullable=True)
    postal_code = Column(String, nullable=True)
    city = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    team = relationship("Team", back_populates="participants")
    event_links = relationship("EventParticipant", back_populates="participant")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)

    name = Column(String, nullable=False)
    # ex: "Match vs Tours", "Entraînement", etc.
    event_date = Column(DateTime, nullable=True)

    destination_address = Column(Text, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    team = relationship("Team", back_populates="events")
    participants = relationship("EventParticipant", back_populates="event")
    trips = relationship("Trip", back_populates="event")


class EventParticipant(Base):
    __tablename__ = "event_participants"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    participant_id = Column(Integer, ForeignKey("participants.id"), nullable=False)

    # ex: "driver" / "passenger" si tu veux le stocker ici
    role = Column(String, nullable=True)
    is_driver = Column(Boolean, default=False)

    event = relationship("Event", back_populates="participants")
    participant = relationship("Participant", back_populates="event_links")


class Trip(Base):
    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)

    car_label = Column(String, nullable=False)  # ex: "Voiture 1"
    driver_participant_id = Column(Integer, ForeignKey("participants.id"), nullable=False)

    google_maps_url = Column(Text, nullable=False)
    ordre_adresses = Column(Text, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    event = relationship("Event", back_populates="trips")
    passengers = relationship("TripPassenger", back_populates="trip")
    co2 = relationship("TripCo2", uselist=False, back_populates="trip")


class TripPassenger(Base):
    __tablename__ = "trip_passengers"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    passenger_participant_id = Column(Integer, ForeignKey("participants.id"), nullable=False)

    # si tu veux marquer les cas "marche à pied"
    marche = Column(Boolean, default=False)

    trip = relationship("Trip", back_populates="passengers")


class TripCo2(Base):
    __tablename__ = "trip_co2"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)

    co2_kg = Column(Float, nullable=False)

    trip = relationship("Trip", back_populates="co2")
