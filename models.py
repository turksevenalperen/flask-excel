from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Vehicle(db.Model):
    __tablename__ = 'vehicles'
    
    id = db.Column(db.Integer, primary_key=True)
    marka = db.Column(db.String(100), nullable=False)
    model = db.Column(db.String(200), nullable=False)
    yil = db.Column(db.String(10), nullable=False)
    fiyat = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'marka': self.marka,
            'model': self.model,
            'yil': self.yil,
            'fiyat': self.fiyat,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }