from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from PIL import Image

from flask_cors import CORS
import pandas as pd
import os
from werkzeug.utils import secure_filename
from models import db, Vehicle, User
import threading
import gc
from datetime import datetime
from models import db, Vehicle, User, SiteSettings, BankAccount  # BankAccount ekleyin

app = Flask(__name__)

# CORS
CORS(app, resources={r"/api/*": {"origins": "*"}})

app.config['SECRET_KEY'] = 'asdasd06-sigorta-2025-railway'

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
                
                # Fiyatı string olarak temizle ve sayıya çevir
                fiyat_raw = str(fiyat).replace(" ", "").replace(",", ".").strip()
                fiyat_num = pd.to_numeric(fiyat_raw, errors="coerce")
                
                # Geçersiz veya <=0 ise ekleme
                if pd.isna(fiyat_num) or fiyat_num <= 0:
                    continue

                sigortalar[sigorta_col] = int(fiyat_num)
            
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
    
    flash('Geçersiz dosya türü! Sadece .xlsx veya .xls', 'error')
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

@app.route('/admin-panel')
def admin_panel():
    """Admin Panel - Siparişler"""
    return render_template('admin_panel.html')

# YENİ - BANKA YÖNETİMİ SAYFASI
@app.route('/bank-management')
def bank_management():
    """Banka hesapları yönetim sayfası"""
    return render_template('bank_management.html')

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

@app.route('/api/years/<brand>')
def api_years_by_brand(brand):
    """Belirli bir markaya ait tüm yılları döndür"""
    years = db.session.query(Vehicle.yil).filter_by(marka=brand).distinct().order_by(Vehicle.yil.desc()).all()
    return jsonify([y[0] for y in years])

@app.route('/api/models/<brand>/<yil>')
def api_models_by_year(brand, yil):
    """Belirli bir marka ve yıla ait modelleri döndür"""
    models = db.session.query(Vehicle.model).filter_by(
        marka=brand, 
        yil=yil
    ).distinct().order_by(Vehicle.model).all()
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

@app.route('/api/siparis-kaydet', methods=['POST'])
def api_siparis_kaydet():
    """Kullanıcı sipariş bilgilerini kaydet"""
    try:
        data = request.get_json()
        
        user = User(
            tc_kimlik=data['tcKimlik'],
            tc_seri=data['tcFull'],
            ad_soyad=f"{data['ad']} {data['soyad']}",
            telefon=data['telefon'],
            ruhsat_seri=data['ruhsatSeri'],
            ruhsat_no=data['ruhsatNo'],
            plaka=f"{data['plakaIl']} {data['plakaSeri']} {data['plakaNo']}",
            marka=data['marka'],
            model=data['model'],
            yil=data['yil'],
            secilen_sigorta=data['secilenSigorta'],
            fiyat=data['fiyat'],
            odeme_durumu='beklemede'
        )
        
        db.session.add(user)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Sipariş kaydedildi',
            'siparis_id': user.id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Hata: {str(e)}'
        }), 400

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

# ==========================================
# ADMIN ROUTES
# ==========================================

@app.route('/admin/siparisler')
def admin_siparisler():
    """Admin - Tüm siparişleri listele"""
    try:
        siparisler = User.query.order_by(User.created_at.desc()).all()
        return jsonify([siparis.to_dict() for siparis in siparisler])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/siparis/<int:siparis_id>/durum-guncelle', methods=['POST'])
def admin_siparis_durum_guncelle(siparis_id):
    """Admin - Sipariş durumu güncelle"""
    try:
        data = request.get_json()
        yeni_durum = data.get('durum')
        
        if yeni_durum not in ['beklemede', 'odendi']:
            return jsonify({'error': 'Geçersiz durum'}), 400
        
        siparis = User.query.get_or_404(siparis_id)
        siparis.odeme_durumu = yeni_durum
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Sipariş durumu güncellendi'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/admin/siparis/<int:siparis_id>/sil', methods=['DELETE'])
def admin_siparis_sil(siparis_id):
    """Admin - Siparişi sil"""
    try:
        siparis = User.query.get_or_404(siparis_id)
        db.session.delete(siparis)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Sipariş başarıyla silindi'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/admin/otomatik-temizlik', methods=['POST'])
def admin_otomatik_temizlik():
    """Admin - 48 saat geçen siparişleri otomatik sil"""
    try:
        from datetime import timedelta
        
        # 48 saat önce (2 gün)
        kirk_sekiz_saat_once = datetime.utcnow() - timedelta(hours=48)
        
        # 48 saatten eski siparişleri bul ve sil
        eski_siparisler = User.query.filter(User.created_at < kirk_sekiz_saat_once).all()
        
        silinen_sayisi = len(eski_siparisler)
        
        for siparis in eski_siparisler:
            db.session.delete(siparis)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'{silinen_sayisi} adet eski sipariş temizlendi (48 saat geçenler)'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

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

@app.route('/init-db')
def init_db():
    """Create all database tables"""
    try:
        db.create_all()
        return jsonify({
            'success': True,
            'message': 'Database tables created successfully!',
            'tables': ['vehicles', 'users']
        })
    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500
    
    # ==========================================
# LOGO YÖNETİMİ - ADMIN PANEL
# ==========================================

# Import'lara ekleyin (dosyanın başına):
from models import db, Vehicle, User, SiteSettings  # SiteSettings ekleyin
from PIL import Image
import io

# Logo klasörünü oluştur (with app.app_context()'ten sonra)
LOGO_FOLDER = 'static/logos'
os.makedirs(LOGO_FOLDER, exist_ok=True)

# ==========================================
# API ROUTES - LOGO
# ==========================================

@app.route('/api/logo')
def api_logo():
    """Frontend'e logo URL'sini döndür"""
    try:
        settings = SiteSettings.query.first()
        if settings and settings.logo_path:
            # Logo varsa URL'ini döndür
            return jsonify({
                'success': True,
                'logo_url': f'/static/logos/{settings.logo_path}'
            })
        else:
            # Logo yoksa null döndür
            return jsonify({
                'success': False,
                'logo_url': None
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/admin/upload-logo', methods=['POST'])
def admin_upload_logo():
    """Admin panelinden logo yükle"""
    try:
        if 'logo' not in request.files:
            flash('❌ Logo dosyası seçilmedi!', 'error')
            return redirect(url_for('index'))
        
        file = request.files['logo']
        
        if file.filename == '':
            flash('❌ Dosya seçilmedi!', 'error')
            return redirect(url_for('index'))
        
        # Dosya uzantısı kontrolü
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        
        if file_ext not in allowed_extensions:
            flash('❌ Sadece PNG, JPG, JPEG, GIF veya WEBP formatı kabul edilir!', 'error')
            return redirect(url_for('index'))
        
        # Eski logoyu sil
        settings = SiteSettings.query.first()
        if settings and settings.logo_path:
            old_logo = os.path.join(LOGO_FOLDER, settings.logo_path)
            if os.path.exists(old_logo):
                os.remove(old_logo)
        
        # Yeni dosya adı
        filename = f'logo_{int(datetime.utcnow().timestamp())}.{file_ext}'
        filepath = os.path.join(LOGO_FOLDER, filename)
        
        # Resmi optimize et
        img = Image.open(file)
        
        # Maksimum boyut 500x500
        max_size = (500, 500)
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Kaydet
        img.save(filepath, optimize=True, quality=85)
        
        # Veritabanına kaydet
        if settings:
            settings.logo_path = filename
            settings.updated_at = datetime.utcnow()
        else:
            settings = SiteSettings(logo_path=filename)
            db.session.add(settings)
        
        db.session.commit()
        
        flash('✅ Logo başarıyla güncellendi!', 'success')
        return redirect(url_for('index'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Hata: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/admin/delete-logo', methods=['POST'])
def admin_delete_logo():
    """Logoyu sil"""
    try:
        settings = SiteSettings.query.first()
        
        if settings and settings.logo_path:
            # Dosyayı sil
            logo_path = os.path.join(LOGO_FOLDER, settings.logo_path)
            if os.path.exists(logo_path):
                os.remove(logo_path)
            
            # Veritabanından sil
            settings.logo_path = None
            db.session.commit()
            
            flash('✅ Logo başarıyla silindi!', 'success')
        else:
            flash('⚠️ Silinecek logo bulunamadı!', 'warning')
        
        return redirect(url_for('index'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Hata: {str(e)}', 'error')
        return redirect(url_for('index'))

# ==========================================
# BANKA HESAPLARI YÖNETİMİ - API ROUTES
# ==========================================

# Import'a ekleyin:
from models import db, Vehicle, User, SiteSettings, BankAccount

# ==========================================
# FRONTEND İÇİN - BANKA HESAPLARI
# ==========================================

@app.route('/api/bank-accounts')
def api_bank_accounts():
    """Frontend'e aktif banka hesaplarını döndür"""
    try:
        accounts = BankAccount.query.filter_by(is_active=True).order_by(BankAccount.order).all()
        return jsonify({
            'success': True,
            'accounts': [account.to_dict() for account in accounts]
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ==========================================
# ADMIN - BANKA HESAPLARI YÖNETİMİ
# ==========================================

@app.route('/admin/bank-accounts')
def admin_bank_accounts():
    """Admin - Tüm banka hesaplarını listele"""
    try:
        accounts = BankAccount.query.order_by(BankAccount.order).all()
        return jsonify([account.to_dict() for account in accounts])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/bank-account/add', methods=['POST'])
def admin_add_bank_account():
    """Admin - Yeni banka hesabı ekle"""
    try:
        data = request.get_json()
        
        account = BankAccount(
            bank_name=data['bank_name'],
            iban=data['iban'],
            account_name=data['account_name'],
            branch=data['branch'],
            is_active=data.get('is_active', True),
            order=data.get('order', 0)
        )
        
        db.session.add(account)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Banka hesabı başarıyla eklendi',
            'account': account.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/admin/bank-account/<int:account_id>', methods=['PUT'])
def admin_update_bank_account(account_id):
    """Admin - Banka hesabını güncelle"""
    try:
        account = BankAccount.query.get_or_404(account_id)
        data = request.get_json()
        
        account.bank_name = data.get('bank_name', account.bank_name)
        account.iban = data.get('iban', account.iban)
        account.account_name = data.get('account_name', account.account_name)
        account.branch = data.get('branch', account.branch)
        account.is_active = data.get('is_active', account.is_active)
        account.order = data.get('order', account.order)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Banka hesabı güncellendi',
            'account': account.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/admin/bank-account/<int:account_id>/toggle', methods=['POST'])
def admin_toggle_bank_account(account_id):
    """Admin - Banka hesabını aktif/pasif yap"""
    try:
        account = BankAccount.query.get_or_404(account_id)
        account.is_active = not account.is_active
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Hesap {"aktif" if account.is_active else "pasif"} edildi',
            'is_active': account.is_active
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/admin/bank-account/<int:account_id>', methods=['DELETE'])
def admin_delete_bank_account(account_id):
    """Admin - Banka hesabını sil"""
    try:
        account = BankAccount.query.get_or_404(account_id)
        db.session.delete(account)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Banka hesabı silindi'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
    
    # ==========================================
# POLİÇE İPTAL TALEPLERİ - API ROUTES
# ==========================================

# Import'a ekleyin:
from models import db, Vehicle, User, SiteSettings, BankAccount, CancelRequest

# ==========================================
# FRONTEND - POLİÇE İPTAL KAYDET
# ==========================================

@app.route('/api/cancel-request', methods=['POST'])
def api_cancel_request():
    """Poliçe iptal talebi kaydet"""
    try:
        data = request.get_json()
        
        cancel_req = CancelRequest(
            name=data['name'],
            phone=data['phone'],
            plate=data['plate'],
            status='beklemede'
        )
        
        db.session.add(cancel_req)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'İptal talebi kaydedildi',
            'request_id': cancel_req.id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Hata: {str(e)}'
        }), 400

# ==========================================
# ADMIN - POLİÇE İPTAL TALEPLERİ
# ==========================================

@app.route('/admin/cancel-requests')
def admin_cancel_requests():
    """Admin - Tüm iptal taleplerini listele"""
    try:
        requests = CancelRequest.query.order_by(CancelRequest.created_at.desc()).all()
        return jsonify([req.to_dict() for req in requests])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/cancel-request/<int:request_id>/status', methods=['POST'])
def admin_update_cancel_status(request_id):
    """Admin - İptal talebinin durumunu güncelle"""
    try:
        data = request.get_json()
        new_status = data.get('status')
        
        if new_status not in ['beklemede', 'tamamlandi', 'iptal']:
            return jsonify({'error': 'Geçersiz durum'}), 400
        
        cancel_req = CancelRequest.query.get_or_404(request_id)
        cancel_req.status = new_status
        
        if 'notes' in data:
            cancel_req.notes = data['notes']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Durum güncellendi'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/admin/cancel-request/<int:request_id>', methods=['DELETE'])
def admin_delete_cancel_request(request_id):
    """Admin - İptal talebini sil"""
    try:
        cancel_req = CancelRequest.query.get_or_404(request_id)
        db.session.delete(cancel_req)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'İptal talebi silindi'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/admin/cancel-request/<int:request_id>/notes', methods=['POST'])
def admin_add_notes(request_id):
    """Admin - İptal talebine not ekle"""
    try:
        data = request.get_json()
        notes = data.get('notes', '')
        
        cancel_req = CancelRequest.query.get_or_404(request_id)
        cancel_req.notes = notes
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Not eklendi'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)