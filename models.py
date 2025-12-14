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

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Kimlik Bilgileri
    tc_kimlik = db.Column(db.String(11), nullable=False)
    tc_seri = db.Column(db.String(10), nullable=False)
    ad_soyad = db.Column(db.String(100), nullable=False)
    telefon = db.Column(db.String(15), nullable=False)
    
    # Ruhsat Bilgileri
    ruhsat_seri = db.Column(db.String(5), nullable=False)
    ruhsat_no = db.Column(db.String(10), nullable=False)
    plaka = db.Column(db.String(15), nullable=False)
    
    # Araç Bilgileri
    marka = db.Column(db.String(50), nullable=False)
    model = db.Column(db.String(100), nullable=False)
    yil = db.Column(db.String(4), nullable=False)
    
    # Sigorta Bilgileri
    secilen_sigorta = db.Column(db.String(100))
    fiyat = db.Column(db.Integer)
    odeme_durumu = db.Column(db.String(20), default='beklemede')
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'tc_kimlik': self.tc_kimlik,
            'tc_seri': self.tc_seri,
            'ad_soyad': self.ad_soyad,
            'telefon': self.telefon,
            'ruhsat_seri': self.ruhsat_seri,
            'ruhsat_no': self.ruhsat_no,
            'plaka': self.plaka,
            'marka': self.marka,
            'model': self.model,
            'yil': self.yil,
            'secilen_sigorta': self.secilen_sigorta,
            'fiyat': self.fiyat,
            'odeme_durumu': self.odeme_durumu,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    def __repr__(self):
        return f'<User {self.ad_soyad} {self.plaka}>'