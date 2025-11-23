from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_cors import CORS
import pandas as pd
import os
from werkzeug.utils import secure_filename
from models import db, Vehicle

app = Flask(__name__)

# CORS'u EN BAŞTA ekle
CORS(app, resources={r"/api/*": {"origins": "*"}})

app.config['SECRET_KEY'] = 'asdasd06'

# PostgreSQL bağlantısı
database_url = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

db.init_app(app)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

with app.app_context():
    db.create_all()

ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def process_excel(filepath):
    try:
        df = pd.read_excel(filepath)
        yeni_df = pd.melt(df, id_vars=['Marka', 'Model'], var_name='Yıl', value_name='Fiyat')
        yeni_df = yeni_df[yeni_df['Fiyat'] > 0]
        yeni_df = yeni_df.dropna(subset=['Fiyat'])
        
        saved_count = 0
        for _, row in yeni_df.iterrows():
            vehicle = Vehicle(
                marka=str(row['Marka']),
                model=str(row['Model']),
                yil=str(row['Yıl']),
                fiyat=int(row['Fiyat'])
            )
            db.session.add(vehicle)
            saved_count += 1
        
        db.session.commit()
        return saved_count, None
    except Exception as e:
        db.session.rollback()
        return 0, str(e)

@app.route('/')
def index():
    total_records = Vehicle.query.count()
    return render_template('index.html', total_records=total_records)

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
        
        count, error = process_excel(filepath)
        os.remove(filepath)
        
        if error:
            flash(f'Hata: {error}', 'error')
        else:
            flash(f'✅ Başarılı! {count} kayıt eklendi.', 'success')
        
        return redirect(url_for('index'))
    
    flash('Geçersiz dosya türü!', 'error')
    return redirect(url_for('index'))

@app.route('/view')
def view_data():
    page = request.args.get('page', 1, type=int)
    vehicles = Vehicle.query.order_by(Vehicle.created_at.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    return render_template('view_data.html', vehicles=vehicles)

@app.route('/api/vehicles')
def api_vehicles():
    vehicles = Vehicle.query.all()
    return jsonify([v.to_dict() for v in vehicles])

@app.route('/api/vehicles/<int:vehicle_id>')
def api_vehicle_detail(vehicle_id):
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    return jsonify(vehicle.to_dict())

@app.route('/api/search')
def api_search():
    query = request.args.get('q', '')
    vehicles = Vehicle.query.filter(
        db.or_(
            Vehicle.marka.ilike(f'%{query}%'),
            Vehicle.model.ilike(f'%{query}%')
        )
    ).all()
    return jsonify([v.to_dict() for v in vehicles])

@app.route('/clear', methods=['POST'])
def clear_data():
    try:
        Vehicle.query.delete()
        db.session.commit()
        flash('Tüm veriler temizlendi!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Hata: {str(e)}', 'error')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)