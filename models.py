from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Vehicle(db.Model):
    __tablename__ = 'vehicles'
    
    id = db.Column(db.Integer, primary_key=True)
    marka = db.Column(db.String(100), nullable=False, index=True)
    model = db.Column(db.String(300), nullable=False, index=True)
    yil = db.Column(db.String(10), nullable=False, index=True)
    
    # Sigorta şirketleri JSON olarak
    sigortalar = db.Column(db.JSON, nullable=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Birleşik index - Hızlı arama için
    __table_args__ = (
        db.Index('idx_vehicle_lookup', 'marka', 'model', 'yil'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'marka': self.marka,
            'model': self.model,
            'yil': self.yil,
            'sigortalar': self.sigortalar,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    def __repr__(self):
        return f'<Vehicle {self.marka} {self.model} {self.yil}>'