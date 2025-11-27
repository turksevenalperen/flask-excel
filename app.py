from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_cors import CORS
import pandas as pd
import os
from werkzeug.utils import secure_filename
from models import db, Vehicle
import threading
import gc

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
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 5,
    'pool_recycle': 300,
    'pool_pre_ping': True,
}
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB

db.init_app(app)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

with app.app_context():
    db.create_all()

ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
 
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Global değişken - işlem durumu
upload_status = {
    'is_processing': False,
    'progress': 0,
    'total': 0,
    'saved': 0,
    'error': None
}

def process_excel_sigorta(filepath):
    """Bellek dostu batch işleme - Excel için optimize"""
    global upload_status
    
    try:
        upload_status['is_processing'] = True
        upload_status['progress'] = 0
        upload_status['error'] = None
        
        print(f"📁 Excel dosyası açılıyor...")
        
        # Excel'i bir kerede oku ama optimize et
        df = pd.read_excel(filepath, engine='openpyxl')
        
        print(f"📊 Excel okundu: {len(df)} satır, {len(df.columns)} sütun")
        print(f"Sütunlar: {list(df.columns)}")
        
        # Zorunlu sütunları kontrol et
        required_cols = ['MARKA', 'MODEL', 'YIL']
        for col in required_cols:
            if col not in df.columns:
                upload_status['error'] = f"'{col}' sütunu bulunamadı!"
                upload_status['is_processing'] = False
                return 0, upload_status['error']
        
        # Sigorta sütunlarını bul
        sigorta_sutunlari = [col for col in df.columns if col not in required_cols]
        
        print(f"🏢 Sigorta şirketleri: {sigorta_sutunlari}")
        
        saved_count = 0
        skipped_count = 0
        batch_size = 1000  # Her 1000 kayıtta bir veritabanına yaz
        
        vehicles_batch = []
        
        total_rows = len(df)
        upload_status['total'] = total_rows
        
        print(f"🚀 Toplam {total_rows} satır işlenecek...")
        
        for idx, row in df.iterrows():
            sigortalar = {}
            
            for sigorta_col in sigorta_sutunlari:
                fiyat = row[sigorta_col]
                
                # 0, NaN ve boş değerleri ekleme
                if pd.notna(fiyat) and fiyat > 0:
                    try:
                        sigortalar[sigorta_col] = int(float(fiyat))
                    except:
                        continue
            
            # Eğer hiç sigorta fiyatı yoksa bu satırı atla
            if not sigortalar:
                skipped_count += 1
                continue
            
            vehicle = Vehicle(
                marka=str(row['MARKA']).strip(),
                model=str(row['MODEL']).strip(),
                yil=str(int(float(row['YIL']))),
                sigortalar=sigortalar
            )
            
            vehicles_batch.append(vehicle)
            saved_count += 1
            
            # Her 1000 kayıtta bir veritabanına yaz (BULK INSERT)
            if len(vehicles_batch) >= batch_size:
                db.session.bulk_save_objects(vehicles_batch)
                db.session.commit()
                
                # İlerleme güncelle
                upload_status['progress'] = saved_count
                upload_status['saved'] = saved_count
                
                print(f"✅ {saved_count}/{total_rows} kayıt eklendi...")
                
                # Belleği temizle
                vehicles_batch = []
                gc.collect()
        
        # Kalan kayıtları ekle
        if vehicles_batch:
            db.session.bulk_save_objects(vehicles_batch)
            db.session.commit()
        
        # DataFrame'i belleğe sil
        del df
        gc.collect()
        
        upload_status['is_processing'] = False
        upload_status['progress'] = saved_count
        upload_status['saved'] = saved_count
        upload_status['total'] = saved_count
        
        print(f"\n🎉 TAMAMLANDI: {saved_count} kayıt eklendi, {skipped_count} atlandı")
        
        return saved_count, None
        
    except Exception as e:
        db.session.rollback()
        upload_status['is_processing'] = False
        upload_status['error'] = str(e)
        print(f"❌ HATA: {str(e)}")
        import traceback
        traceback.print_exc()
        return 0, str(e)

@app.route('/')
def index():
    total_records = Vehicle.query.count()
    
    unique_brands = db.session.query(Vehicle.marka).distinct().count()
    
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
    global upload_status
    
    if upload_status['is_processing']:
        flash('⏳ Bir dosya zaten işleniyor, lütfen bekleyin!', 'warning')
        return redirect(url_for('index'))
    
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
        
        # ARKA PLANDA İŞLE - TIMEOUT YOK
        def process_in_background():
            with app.app_context():
                count, error = process_excel_sigorta(filepath)
                
                # Dosyayı sil
                try:
                    os.remove(filepath)
                    print(f"🗑️ Geçici dosya silindi: {filepath}")
                except:
                    pass
                
                if error:
                    print(f"❌ Hata: {error}")
                else:
                    print(f"✅ Başarılı: {count} kayıt")
        
        thread = threading.Thread(target=process_in_background, daemon=True)
        thread.start()
        
        flash('📤 Dosya yüklendi! Arka planda işleniyor... (İlerleyi /upload-status adresinden takip edebilirsiniz)', 'info')
        return redirect(url_for('index'))
    
    flash('Geçersizz dosya türü! Sadece .xlsx veya .xls', 'error')
    return redirect(url_for('index'))

@app.route('/upload-status')
def upload_status_page():
    """İşlem durumunu göster"""
    global upload_status
    return jsonify(upload_status)

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