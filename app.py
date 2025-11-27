from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_cors import CORS
import pandas as pd
import os
from werkzeug.utils import secure_filename
from models import db, Vehicle

app = Flask(__name__)

# CORS
CORS(app, resources={r"/api/*": {"origins": "*"}})

app.config['SECRET_KEY'] = 'asdasd06-sigorta-2025'

# PostgreSQL bağlantısı
database_url = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB (büyük Excel için)

db.init_app(app)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

with app.app_context():
    db.create_all()

ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def process_excel_sigorta(filepath):
    """Yeni format: MARKA, MODEL, YIL + Sigorta Şirketleri"""
    try:
        # Excel'i oku
        df = pd.read_excel(filepath)
        
        print(f"📊 Excel okundu: {len(df)} satır, {len(df.columns)} sütun")
        print(f"Sütunlar: {list(df.columns)}")
        
        # Zorunlu sütunları kontrol et
        required_cols = ['MARKA', 'MODEL', 'YIL']
        for col in required_cols:
            if col not in df.columns:
                return 0, f"'{col}' sütunu bulunamadı!"
        
        # Sigorta sütunlarını bul (MARKA, MODEL, YIL hariç)
        sigorta_sutunlari = [col for col in df.columns if col not in required_cols]
        
        print(f"🏢 Sigorta şirketleri: {sigorta_sutunlari}")
        
        saved_count = 0
        skipped_count = 0
        
        # Batch işlem (1000'erli gruplar)
        batch_size = 1000
        
        for idx, row in df.iterrows():
            # Sigorta şirketlerini JSON'a çevir
            sigortalar = {}
            
            for sigorta_col in sigorta_sutunlari:
                fiyat = row[sigorta_col]
                
                # 0, NaN ve boş değerleri ekleme
                if pd.notna(fiyat) and fiyat > 0:
                    # Float'u int'e çevir
                    sigortalar[sigorta_col] = int(fiyat)
            
            # Eğer hiç sigorta fiyatı yoksa bu satırı atla
            if not sigortalar:
                skipped_count += 1
                continue
            
            # Veritabanına ekle
            vehicle = Vehicle(
                marka=str(row['MARKA']).strip(),
                model=str(row['MODEL']).strip(),
                yil=str(int(row['YIL'])),  # 2024.0 → "2024"
                sigortalar=sigortalar
            )
            db.session.add(vehicle)
            saved_count += 1
            
            # Her 1000 kayıtta bir commit (performans)
            if saved_count % batch_size == 0:
                db.session.commit()
                print(f"✅ {saved_count} kayıt eklendi...")
        
        # Son batch'i kaydet
        db.session.commit()
        
        print(f"\n✅ Başarılı: {saved_count} kayıt eklendi")
        print(f"⏭️  Atlanan (boş): {skipped_count} satır")
        
        return saved_count, None
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ HATA: {str(e)}")
        return 0, str(e)

@app.route('/')
def index():
    total_records = Vehicle.query.count()
    
    # Benzersiz marka sayısı
    unique_brands = db.session.query(Vehicle.marka).distinct().count()
    
    # İlk kayıttan sigorta şirketlerini al
    first_vehicle = Vehicle.query.first()
    sigorta_sirketleri = []
    if first_vehicle and first_vehicle.sigortalar:
        sigorta_sirketleri = list(first_vehicle.sigortalar.keys())
    
    return render_template('index.html', 
                         total_records=total_records,
                         unique_brands=unique_brands,
                         sigorta_sirketleri=sigorta_sirketleri)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('Dosya seçilmedi!', 'error')
        return redirect(url_for('index'))
    
    file = request.files['file']
    
    if file.filename == '':
        flash('Dosya seçilmedi!', 'error')
        return redirect(url_for('index'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        print(f"📁 Dosya kaydedildi: {filepath}")
        
        # Excel'i işle
        count, error = process_excel_sigorta(filepath)
        
        # Dosyayı sil
        os.remove(filepath)
        
        if error:
            flash(f'❌ Hata: {error}', 'error')
        else:
            flash(f'✅ Başarılı! {count} kayıt eklendi.', 'success')
        
        return redirect(url_for('index'))
    
    flash('Geçersiz dosya türü! Sadece .xlsx veya .xls', 'error')
    return redirect(url_for('index'))

@app.route('/view')
def view_data():
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    vehicles = Vehicle.query.order_by(Vehicle.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('view_data.html', vehicles=vehicles)

# ==========================================
# API ROUTES
# ==========================================

@app.route('/api/vehicles')
def api_vehicles():
    """Tüm araçları döndür"""
    vehicles = Vehicle.query.all()
    return jsonify([v.to_dict() for v in vehicles])

@app.route('/api/vehicles/<int:vehicle_id>')
def api_vehicle_detail(vehicle_id):
    """Tek bir aracın detayı"""
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    return jsonify(vehicle.to_dict())

@app.route('/api/vehicle/<marka>/<model>/<yil>')
def api_vehicle_search(marka, model, yil):
    """Belirli bir aracı ara"""
    vehicle = Vehicle.query.filter_by(
        marka=marka,
        model=model,
        yil=yil
    ).first()
    
    if vehicle:
        return jsonify({
            'success': True,
            'data': vehicle.to_dict()
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Araç bulunamadı'
        }), 404

@app.route('/api/brands')
def api_brands():
    """Tüm markaları döndür"""
    brands = db.session.query(Vehicle.marka).distinct().order_by(Vehicle.marka).all()
    return jsonify([b[0] for b in brands])

@app.route('/api/models/<brand>')
def api_models(brand):
    """Belirli bir markaya ait modelleri döndür"""
    models = db.session.query(Vehicle.model).filter_by(marka=brand).distinct().order_by(Vehicle.model).all()
    return jsonify([m[0] for m in models])

@app.route('/api/years/<brand>/<model>')
def api_years(brand, model):
    """Belirli bir marka ve modele ait yılları döndür"""
    years = db.session.query(Vehicle.yil).filter_by(
        marka=brand, 
        model=model
    ).distinct().order_by(Vehicle.yil.desc()).all()
    return jsonify([y[0] for y in years])

@app.route('/api/sigorta-sirketleri')
def api_sigorta_sirketleri():
    """Tüm sigorta şirketlerinin listesi"""
    vehicle = Vehicle.query.first()
    if vehicle and vehicle.sigortalar:
        return jsonify(list(vehicle.sigortalar.keys()))
    return jsonify([])

@app.route('/api/search')
def api_search():
    """Marka veya model ile arama"""
    query = request.args.get('q', '')
    
    if len(query) < 2:
        return jsonify([])
    
    vehicles = Vehicle.query.filter(
        db.or_(
            Vehicle.marka.ilike(f'%{query}%'),
            Vehicle.model.ilike(f'%{query}%')
        )
    ).limit(100).all()
    
    return jsonify([v.to_dict() for v in vehicles])

@app.route('/clear', methods=['POST'])
def clear_data():
    """Tüm verileri temizle"""
    try:
        Vehicle.query.delete()
        db.session.commit()
        flash('✅ Tüm veriler temizlendi!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Hata: {str(e)}', 'error')
    
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)