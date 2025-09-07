from flask import Flask, render_template, request, url_for, jsonify, redirect, flash
import sqlite3
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
import re
from functools import wraps
from flask import session

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'koree-super-secret-production-key-2024')

# Database configuration based on your actual files
if os.environ.get('AWS_EXECUTION_ENV') or os.environ.get('ELASTIC_BEANSTALK_ENVIRONMENT'):
    # On AWS, use the database file from your deployment
    DB_FILE = os.path.join(os.path.dirname(__file__), 'koree_autoservice.db')
    IS_AWS = True
    print(f"🌐 AWS Environment - Database: {DB_FILE}")
else:
    # Local development - use existing database
    DB_FILE = os.path.join(os.path.dirname(__file__), 'koree_autoservice.db')
    IS_AWS = False
    print(f"💻 Local Environment - Database: {DB_FILE}")

print(f"🗄️ Database file path: {DB_FILE}")
print(f"📁 Database file exists: {os.path.exists(DB_FILE)}")

# Email configuration
MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtpout.secureserver.net')
MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
MAIL_USERNAME = os.environ.get('MAIL_USERNAME', 'info@koreeautoservices.nl')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', 'Batman72@')
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'info@koreeautoservices.nl')

# Google Places configuration
GOOGLE_PLACES_API_KEY = os.environ.get('GOOGLE_PLACES_API_KEY')
GOOGLE_PLACE_ID = os.environ.get('GOOGLE_PLACE_ID', 'ChIJIUb6ApRMxEcRDLLwZYBbzz0')

# Business hours configuration
BUSINESS_HOURS = {
    'monday': {'start': '08:00', 'end': '17:00'},
    'tuesday': {'start': '08:00', 'end': '17:00'},
    'wednesday': {'start': '08:00', 'end': '17:00'},
    'thursday': {'start': '08:00', 'end': '17:00'},
    'friday': {'start': '08:00', 'end': '17:00'},
    'saturday': {'start': '09:00', 'end': '17:00'},
    'sunday': {'start': '09:00', 'end': '15:00'},
}

def consolidate_databases():
    """Consolidate data from multiple database files into main one"""
    try:
        main_db = os.path.join(os.path.dirname(__file__), 'koree_autoservice.db')
        bookings_db = os.path.join(os.path.dirname(__file__), 'bookings.db')
        database_db = os.path.join(os.path.dirname(__file__), 'database.db')
        
        print("🔄 Consolidating database files...")
        
        # If main database doesn't exist but others do, copy data
        if not os.path.exists(main_db):
            if os.path.exists(bookings_db):
                print(f"📋 Copying from bookings.db to main database")
                import shutil
                shutil.copy2(bookings_db, main_db)
            elif os.path.exists(database_db):
                print(f"📋 Copying from database.db to main database")
                import shutil
                shutil.copy2(database_db, main_db)
        
        print(f"✅ Main database ready: {main_db}")
        return True
        
    except Exception as e:
        print(f"❌ Database consolidation error: {e}")
        return False

def init_db():
    """Initialize database with tables and default data"""
    try:
        print(f"🔧 Initializing database schema...")
        
        connection = sqlite3.connect(DB_FILE)
        cursor = connection.cursor()
        
        # Create services table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                price REAL DEFAULT 0.0,
                duration_minutes INTEGER DEFAULT 60,
                active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create bookings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL,
                service TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                message TEXT,
                status TEXT DEFAULT 'confirmed',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Check if services exist, if not add default ones
        cursor.execute("SELECT COUNT(*) FROM services")
        service_count = cursor.fetchone()[0]
        
        if service_count == 0:
            print("📝 Adding default services (without prices)...")
            default_services = [
                ("APK Keuring", "Officiële APK keuring voor uw voertuig", 0.0, 45),
                ("Grote Beurt", "Uitgebreide onderhoudsbeurt", 0.0, 120),
                ("Kleine Beurt", "Basis onderhoudsbeurt", 0.0, 60),
                ("Reparatie", "Diagnose en reparatie van defecten", 0.0, 90),
                ("Banden Service", "Bandenwissel en balanceren", 0.0, 30),
                ("Airco Service", "Airco onderhoud en reparatie", 0.0, 60),
                ("Remmen Service", "Remmen controle en onderhoud", 0.0, 90),
                ("Motor Diagnostiek", "Uitgebreide motor diagnose", 0.0, 60)
            ]
            
            for service in default_services:
                cursor.execute("""
                    INSERT INTO services (name, description, price, duration_minutes) 
                    VALUES (?, ?, ?, ?)
                """, service)
            
            connection.commit()
            print(f"✅ Added {len(default_services)} default services (no prices displayed)")
        
        cursor.close()
        connection.close()
        print("✅ Database initialization complete")
        return True
        
    except Exception as e:
        print(f"❌ Database initialization error: {e}")
        import traceback
        traceback.print_exc()
        return False

def get_db_connection():
    """Get database connection with proper path handling"""
    try:
        # Ensure we're using the correct database
        if not os.path.exists(DB_FILE):
            print(f"⚠️ Database not found: {DB_FILE}")
            
            # Try to consolidate from other database files
            consolidate_databases()
            
            # If still doesn't exist, create it
            if not os.path.exists(DB_FILE):
                print(f"📝 Creating new database: {DB_FILE}")
                init_db()
        
        connection = sqlite3.connect(DB_FILE)
        connection.row_factory = sqlite3.Row
        return connection
        
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return None

def test_database_connection():
    """Test database connection and functionality"""
    try:
        print(f"🔍 Testing database connection to: {DB_FILE}")
        
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        
        # Test query
        cursor.execute("SELECT COUNT(*) FROM services")
        service_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM bookings")
        booking_count = cursor.fetchone()[0]
        
        print(f"✅ Database test successful!")
        print(f"📊 Services: {service_count}, Bookings: {booking_count}")
        
        cursor.close()
        connection.close()
        return True
        
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False

def generate_time_slots():
    """Generate 30-minute time slots for business hours"""
    time_slots = []
    
    # Business hours: 8:00 - 16:30 (30-minute slots)
    start_hour = 8
    end_hour = 17  # Will generate up to 16:30
    
    current_hour = start_hour
    current_minute = 0
    
    while current_hour < end_hour:
        time_str = f"{current_hour:02d}:{current_minute:02d}"
        time_slots.append(time_str)
        
        # Add 30 minutes
        current_minute += 30
        if current_minute >= 60:
            current_minute = 0
            current_hour += 1
    
    print(f"✅ Generated {len(time_slots)} time slots: {time_slots}")
    return time_slots

def send_email(to_email, subject, html_body, text_body=None):
    """Send email using GoDaddy SMTP"""
    try:
        print(f"📧 Sending email to: {to_email}")
        print(f"📧 Subject: {subject}")
        
        msg = MIMEMultipart('alternative')
        msg['From'] = MAIL_USERNAME
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Add text version if provided
        if text_body:
            text_part = MIMEText(text_body, 'plain')
            msg.attach(text_part)
        
        # Add HTML version
        html_part = MIMEText(html_body, 'html')
        msg.attach(html_part)
        
        # Connect to GoDaddy SMTP
        server = smtplib.SMTP(MAIL_SERVER, MAIL_PORT)
        server.starttls()
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        
        # Send email
        server.send_message(msg)
        server.quit()
        
        print(f"✅ Email sent successfully to {to_email}")
        return True
        
    except Exception as e:
        print(f"❌ Email error: {e}")
        return False

def get_google_reviews():
    """Return real Google reviews data (manually added from API response)"""
    try:
        print("=== USING REAL GOOGLE REVIEWS DATA (MANUAL) ===")
        
        # Real Google Reviews data from your API response
        real_reviews_data = {
            'success': True,
            'data': {
                'business_name': 'Autobedrijf Koree',
                'business_address': 'Haven 45-48, 3143 BD Maassluis, Nederland',
                'business_phone': '010 592 8497',
                'overall_rating': 4.6,
                'total_reviews': 32,
                'place_id': 'ChIJIUb6ApRMxEcRDLLwZYBbzz0',
                'last_updated': datetime.now().isoformat(),
                'source': 'google_places_manual_data',
                'reviews': [
                    {
                        "author_name": "Petra Kors",
                        "author_url": "https://www.google.com/maps/contrib/107767823563844740700/reviews",
                        "date": "28-06-2025",
                        "is_local_guide": False,
                        "profile_photo_url": "https://lh3.googleusercontent.com/a-/ALV-UjWc-Gb1bQzgkXjjok3J1CyU3hpr277T9otdg-2jwvMOTW8mT3Dv4Q=s128-c0x00000000-cc-rp-mo-ba3",
                        "rating": 5,
                        "relative_time_description": "2 maanden geleden",
                        "text": "Ik werd snel en vriendelijk geholpen 👍",
                        "time": 1751095836
                    },
                    {
                        "author_name": "Arsha Dhore",
                        "author_url": "https://www.google.com/maps/contrib/110495330569103914158/reviews",
                        "date": "16-03-2025",
                        "is_local_guide": False,
                        "profile_photo_url": "https://lh3.googleusercontent.com/a-/ALV-UjXGY0Z47Gs80V034WBQfwPPTD7YhxaTrkz198g1VKevLfmbINl9=s128-c0x00000000-cc-rp-mo-ba2",
                        "rating": 5,
                        "relative_time_description": "5 maanden geleden",
                        "text": "Super service. 2 dagen mn auto deuken eruit en opnieuw gespoten",
                        "time": 1742105434
                    },
                    {
                        "author_name": "Arthur Steevensz",
                        "author_url": "https://www.google.com/maps/contrib/107585197038612599171/reviews",
                        "date": "19-10-2024",
                        "is_local_guide": False,
                        "profile_photo_url": "https://lh3.googleusercontent.com/a/ACg8ocJuxM4ZMoFrlUb-COWa5Gsvw8K3fLaDmlC9YhL8UnxexPDXvA=s128-c0x00000000-cc-rp-mo",
                        "rating": 5,
                        "relative_time_description": "10 maanden geleden",
                        "text": "Vakkundigheid\nVriendelijke personeel\nGoede service",
                        "time": 1729350918
                    }
                ]
            },
            'business': {
                'name': 'Autobedrijf Koree',
                'address': 'Haven 45-48, 3143 BD Maassluis, Nederland',
                'phone': '010 592 8497',
                'email': 'info@koreeautoservices.nl',
                'website': 'https://koreeautoservices.nl'
            }
        }
        
        print(f"✅ Loaded {len(real_reviews_data['data']['reviews'])} REAL Google reviews (manual)")
        print(f"📊 Business: {real_reviews_data['data']['business_name']}")
        print(f"⭐ Rating: {real_reviews_data['data']['overall_rating']}/5 ({real_reviews_data['data']['total_reviews']} total reviews)")
        
        return real_reviews_data
            
    except Exception as e:
        print(f"❌ Error loading manual reviews: {e}")
        return {'success': False, 'error': f'Error: {str(e)}'}

# Authentication decorator
def require_admin_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            flash('Please log in to access admin area', 'error')
            return redirect(url_for('admin_login'))
        
        # Check session timeout (1 hour default)
        import time
        session_timeout = 3600  # 1 hour
        last_activity = session.get('last_activity')
        
        if last_activity and (time.time() - last_activity) > session_timeout:
            session.clear()
            flash('Session expired. Please log in again.', 'warning')
            return redirect(url_for('admin_login'))
        
        session['last_activity'] = time.time()
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route("/api/services", methods=["GET"])
def get_services():
    """Get all available services (without prices)"""
    try:
        print("🔧 Getting services...")
        
        connection = get_db_connection()
        if connection is None:
            print("❌ Database connection failed")
            return jsonify({"error": "Database connection failed"}), 500
        
        cursor = connection.cursor()
        cursor.execute("SELECT id, name, description, duration_minutes FROM services WHERE active = 1")
        services_raw = cursor.fetchall()
        
        print(f"📊 Raw services from database: {len(services_raw)} rows")
        
        services = []
        for service in services_raw:
            service_dict = {
                'id': service[0],
                'name': service[1],
                'description': service[2] or '',
                'duration_minutes': int(service[3]) if service[3] else 60
            }
            services.append(service_dict)
            print(f"  📝 Service: {service_dict['name']}")
        
        cursor.close()
        connection.close()
        
        print(f"✅ Returning {len(services)} services (without prices)")
        return jsonify({"success": True, "services": services})
        
    except Exception as e:
        print(f"❌ Services error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": "Failed to fetch services"}), 500

@app.route("/api/available-times", methods=["GET"])
def get_available_times():
    """Get available time slots for a specific date"""
    try:
        date = request.args.get('date')
        print(f"🔍 Received date parameter: '{date}'")
        
        if not date:
            return jsonify({"success": False, "error": "Date parameter required"}), 400
        
        print(f"🔍 Checking available times for date: {date}")
        
        # Validate date format
        try:
            booking_date = datetime.strptime(date, '%Y-%m-%d').date()
            print(f"📅 Parsed date successfully: {booking_date}")
        except ValueError as ve:
            print(f"❌ Date parsing error: {ve}")
            return jsonify({
                "success": False,
                "error": "Invalid date format",
                "available_times": [],
                "message": "Ongeldige datum"
            })
        
        # Don't allow past dates
        today = datetime.now().date()
        if booking_date < today:
            print(f"❌ Past date not allowed: {booking_date} < {today}")
            return jsonify({
                "success": False,
                "error": "Cannot book in the past",
                "available_times": [],
                "message": "Kan geen afspraken in het verleden maken"
            })
        
        connection = get_db_connection()
        if connection is None:
            print("❌ Database connection failed")
            return jsonify({
                "success": False,
                "error": "Database connection failed",
                "available_times": [],
                "message": "Database fout"
            })
        
        cursor = connection.cursor()
        
        # Get all booked times for this date
        cursor.execute("""
            SELECT time FROM bookings 
            WHERE date = ? AND status != 'cancelled'
        """, (date,))
        
        booked_times_raw = cursor.fetchall()
        booked_times = [row[0] for row in booked_times_raw]
        
        print(f"📊 Booked times for {date}: {booked_times}")
        
        cursor.close()
        connection.close()
        
        # Generate all possible time slots
        all_time_slots = generate_time_slots()
        print(f"⏰ Generated time slots: {all_time_slots}")
        
        # Get current time for today's comparison
        now = datetime.now()
        is_today = booking_date == now.date()
        print(f"📅 Is today: {is_today}, Current time: {now.strftime('%H:%M')}")
        
        # Filter available times
        available_times = []
        
        for time_slot in all_time_slots:
            is_booked = time_slot in booked_times
            
            # Check if time has passed for today
            is_past_time = False
            if is_today:
                try:
                    slot_time = datetime.strptime(time_slot, '%H:%M').time()
                    slot_datetime = datetime.combine(booking_date, slot_time)
                    is_past_time = slot_datetime <= now
                    if is_past_time:
                        print(f"  ⏰ Past time: {time_slot}")
                except Exception as te:
                    print(f"❌ Time parsing error for {time_slot}: {te}")
                    is_past_time = False
            
            is_available = not is_booked and not is_past_time
            
            # Only add to available_times if actually available
            if is_available:
                available_times.append(time_slot)
                print(f"  ✅ Available: {time_slot}")
            elif is_booked:
                print(f"  ❌ Booked: {time_slot}")
        
        print(f"✅ Total slots: {len(all_time_slots)}, Available: {len(available_times)}, Booked: {len(booked_times)}")
        
        return jsonify({
            "success": True,
            "date": date,
            "available_times": available_times,
            "booked_times": booked_times,
            "total_slots": len(all_time_slots),
            "available_count": len(available_times),
            "is_today": is_today,
            "message": f"{len(available_times)} beschikbare tijden gevonden" if available_times else "Geen beschikbare tijden"
        })
        
    except Exception as e:
        print(f"❌ Available times error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": "Failed to fetch available times",
            "available_times": [],
            "message": "Fout bij laden tijden"
        }), 500

@app.route("/api/book", methods=["POST"])
def book_appointment():
    """Book an appointment"""
    try:
        print("📝 Processing booking request...")
        
        # Get form data
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        service = request.form.get('service', '').strip()
        date = request.form.get('date', '').strip()
        time = request.form.get('time', '').strip()
        message = request.form.get('message', '').strip()
        
        # Validate required fields
        if not all([name, email, phone, service, date, time]):
            return jsonify({"error": "Alle velden zijn verplicht"}), 400
        
        # Validate email format
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            return jsonify({"error": "Ongeldig email adres"}), 400
        
        print(f"👤 Booking for: {name} ({email})")
        print(f"📅 Date/Time: {date} at {time}")
        print(f"🔧 Service: {service}")
        
        connection = get_db_connection()
        if connection is None:
            return jsonify({"error": "Database verbinding mislukt"}), 500
        
        cursor = connection.cursor()
        
        # Check if time slot is still available
        cursor.execute("""
            SELECT COUNT(*) FROM bookings 
            WHERE date = ? AND time = ? AND status != 'cancelled'
        """, (date, time))
        
        if cursor.fetchone()[0] > 0:
            cursor.close()
            connection.close()
            return jsonify({"error": "Deze tijd is al geboekt"}), 400
        
        # Insert booking
        cursor.execute("""
            INSERT INTO bookings (name, email, phone, service, date, time, message, status) 
            VALUES (?, ?, ?, ?, ?, ?, ?, 'confirmed')
        """, (name, email, phone, service, date, time, message))
        
        booking_id = cursor.lastrowid
        connection.commit()
        cursor.close()
        connection.close()
        
        print(f"✅ Booking saved with ID: {booking_id}")
        
        # Send confirmation emails
        try:
            # Customer email
            customer_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: #2c3e50; color: white; padding: 20px; text-align: center; }}
                    .content {{ padding: 20px; background: #f9f9f9; }}
                    .booking-details {{ background: white; padding: 15px; border-radius: 5px; margin: 15px 0; }}
                    .footer {{ text-align: center; padding: 20px; color: #666; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🚗 Autobedrijf Koree</h1>
                        <p>Bevestiging van uw afspraak</p>
                    </div>
                    <div class="content">
                        <h2>Beste {name},</h2>
                        <p>Bedankt voor uw afspraak bij Autobedrijf Koree. Hieronder vindt u de details:</p>
                        
                        <div class="booking-details">
                            <h3>📅 Afspraak Details</h3>
                            <p><strong>Service:</strong> {service}</p>
                            <p><strong>Datum:</strong> {date}</p>
                            <p><strong>Tijd:</strong> {time}</p>
                            <p><strong>Naam:</strong> {name}</p>
                            <p><strong>Telefoon:</strong> {phone}</p>
                            <p><strong>Email:</strong> {email}</p>
                            {f'<p><strong>Bericht:</strong> {message}</p>' if message else ''}
                        </div>
                        
                        <p>Wij zien u graag op de afgesproken tijd. Heeft u vragen? Bel ons op +31 6 23967989.</p>
                        
                        <p>Met vriendelijke groet,<br>
                        Team Autobedrijf Koree</p>
                    </div>
                    <div class="footer">
                        <p>Haven 45-48, 3143 BD Maassluis | 010 592 8497 | info@koreeautoservices.nl</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            send_email(email, "Bevestiging afspraak - Autobedrijf Koree", customer_html)
            
            # Admin email
            admin_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: #e74c3c; color: white; padding: 20px; text-align: center; }}
                    .content {{ padding: 20px; background: #f9f9f9; }}
                    .booking-details {{ background: white; padding: 15px; border-radius: 5px; margin: 15px 0; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🔔 Nieuwe Afspraak</h1>
                        <p>Autobedrijf Koree</p>
                    </div>
                    <div class="content">
                        <h2>Nieuwe afspraak geboekt!</h2>
                        
                        <div class="booking-details">
                            <h3>📅 Afspraak Details</h3>
                            <p><strong>Booking ID:</strong> {booking_id}</p>
                            <p><strong>Service:</strong> {service}</p>
                            <p><strong>Datum:</strong> {date}</p>
                            <p><strong>Tijd:</strong> {time}</p>
                            <p><strong>Naam:</strong> {name}</p>
                            <p><strong>Telefoon:</strong> {phone}</p>
                            <p><strong>Email:</strong> {email}</p>
                            {f'<p><strong>Bericht:</strong> {message}</p>' if message else ''}
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
            
            send_email(ADMIN_EMAIL, f"Nieuwe afspraak: {name} - {date} {time}", admin_html)
            
        except Exception as email_error:
            print(f"⚠️ Email error: {email_error}")
            # Don't fail the booking if email fails
        
        return jsonify({
            "message": f"Afspraak succesvol geboekt voor {date} om {time}. Bevestiging verzonden naar {email}.",
            "booking_id": booking_id
        })
        
    except Exception as e:
        print(f"❌ Booking error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Er is een fout opgetreden bij het boeken"}), 500

@app.route('/admin')
def admin_redirect():
    """Redirect /admin to login or dashboard"""
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('admin_login'))

@app.route('/admin/login')
def admin_login():
    """Admin login page"""
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_login.html')

@app.route('/admin/authenticate', methods=['POST'])
def admin_authenticate():
    """Handle admin login"""
    try:
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        # Get admin credentials from environment
        admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
        admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
        
        if username == admin_username and password == admin_password:
            # Successful login
            import time
            session['admin_logged_in'] = True
            session['admin_username'] = username
            session['admin_login_time'] = time.time()
            session['last_activity'] = time.time()
            session.permanent = True
            
            print(f"✅ Successful admin login: {username}")
            flash('Welcome to admin dashboard!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            print(f"❌ Failed login attempt for username: {username}")
            flash('Invalid username or password', 'error')
            return redirect(url_for('admin_login'))
            
    except Exception as e:
        print(f"❌ Authentication error: {e}")
        flash('Login error occurred', 'error')
        return redirect(url_for('admin_login'))

@app.route('/admin/logout')
def admin_logout():
    """Admin logout"""
    session.clear()
    print(f"👋 Admin logout")
    flash('Successfully logged out', 'info')
    return redirect(url_for('index'))

@app.route('/admin/dashboard')
@require_admin_auth
def admin_dashboard():
    """Admin dashboard"""
    try:
        # Get booking statistics
        connection = get_db_connection()
        if connection is None:
            flash('Database connection failed', 'error')
            return redirect(url_for('admin_login'))
        
        cursor = connection.cursor()
        
        # Total bookings
        cursor.execute("SELECT COUNT(*) FROM bookings")
        total_bookings = cursor.fetchone()[0]
        
        # Recent bookings (last 7 days)
        cursor.execute("""
            SELECT COUNT(*) FROM bookings 
            WHERE date >= date('now', '-7 days')
        """)
        recent_bookings = cursor.fetchone()[0]
        
        # Upcoming bookings
        cursor.execute("""
            SELECT COUNT(*) FROM bookings 
            WHERE date >= date('now') AND status = 'confirmed'
        """)
        upcoming_bookings = cursor.fetchone()[0]
        
        # Recent bookings details
        cursor.execute("""
            SELECT id, name, email, phone, service, date, time, status, created_at 
            FROM bookings 
            ORDER BY created_at DESC 
            LIMIT 8
        """)
        recent_bookings_details = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        stats = {
            'total_bookings': total_bookings,
            'recent_bookings': recent_bookings,
            'upcoming_bookings': upcoming_bookings,
            'recent_bookings_details': recent_bookings_details
        }
        
        admin_info = {
            'username': session.get('admin_username', 'admin'),
            'full_name': 'Administrator'
        }
        
        return render_template('admin_dashboard.html', 
                             stats=stats, 
                             admin_info=admin_info)
        
    except Exception as e:
        print(f"❌ Dashboard error: {e}")
        flash('Dashboard error occurred', 'error')
        return redirect(url_for('admin_login'))

@app.route('/admin/bookings')
@require_admin_auth
def admin_bookings():
    """View all bookings"""
    try:
        connection = get_db_connection()
        if connection is None:
            flash('Database connection failed', 'error')
            return redirect(url_for('admin_dashboard'))
        
        cursor = connection.cursor()
        cursor.execute("""
            SELECT id, name, email, phone, service, date, time, message, status, created_at 
            FROM bookings 
            ORDER BY date DESC, time DESC
        """)
        
        bookings = cursor.fetchall()
        cursor.close()
        connection.close()
        
        return render_template('admin_bookings.html', bookings=bookings)
        
    except Exception as e:
        print(f"❌ Admin bookings error: {e}")
        flash('Error loading bookings', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/download-db')
@require_admin_auth
def download_database():
    """Download database file"""
    try:
        from flask import send_file
        import os
        
        if os.path.exists(DB_FILE):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            download_name = f'koree_database_{timestamp}.db'
            
            print(f"📥 Database download by admin")
            
            return send_file(
                DB_FILE,
                as_attachment=True,
                download_name=download_name,
                mimetype='application/x-sqlite3'
            )
        else:
            flash('Database file not found', 'error')
            return redirect(url_for('admin_dashboard'))
            
    except Exception as e:
        print(f"❌ Download error: {e}")
        flash('Download error occurred', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/export-csv')
@require_admin_auth
def export_bookings_csv():
    """Export bookings as CSV"""
    try:
        import csv
        from io import StringIO
        from flask import Response
        
        connection = get_db_connection()
        if connection is None:
            flash('Database connection failed', 'error')
            return redirect(url_for('admin_dashboard'))
        
        cursor = connection.cursor()
        cursor.execute("""
            SELECT id, name, email, phone, service, date, time, message, status, created_at 
            FROM bookings 
            ORDER BY created_at DESC
        """)
        
        bookings = cursor.fetchall()
        cursor.close()
        connection.close()
        
        # Create CSV
        output = StringIO()
        writer = csv.writer(output)
        
        # Write headers
        writer.writerow(['ID', 'Name', 'Email', 'Phone', 'Service', 'Date', 'Time', 'Message', 'Status', 'Created At'])
        
        # Write data
        for booking in bookings:
            writer.writerow(booking)
        
        # Create response
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f'koree_bookings_{timestamp}.csv'
        
        response = Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={"Content-Disposition": f"attachment;filename={filename}"}
        )
        
        print(f"📊 CSV export by admin")
        return response
        
    except Exception as e:
        print(f"❌ CSV export error: {e}")
        flash('Export error occurred', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/debug/database')
def debug_database():
    """Debug database information"""
    try:
        connection = get_db_connection()
        if connection is None:
            return "Database connection failed", 500
        
        cursor = connection.cursor()
        
        # Get database info
        debug_info = {
            'database_file': DB_FILE,
            'file_exists': os.path.exists(DB_FILE),
            'file_size': os.path.getsize(DB_FILE) if os.path.exists(DB_FILE) else 0,
            'tables': {}
        }
        
        # Get table info
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        for table in tables:
            table_name = table[0]
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            debug_info['tables'][table_name] = count
        
        # Get recent bookings
        cursor.execute("""
            SELECT id, name, service, date, time, status, created_at 
            FROM bookings 
            ORDER BY created_at DESC 
            LIMIT 10
        """)
        recent_bookings = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        # Format output
        output = f"""
        <h1>🔧 Database Debug Information</h1>
        <h2>📁 File Information</h2>
        <p><strong>Database File:</strong> {debug_info['database_file']}</p>
        <p><strong>File Exists:</strong> {debug_info['file_exists']}</p>
        <p><strong>File Size:</strong> {debug_info['file_size']} bytes</p>
        
        <h2>📊 Tables</h2>
        <ul>
        """
        
        for table_name, count in debug_info['tables'].items():
            output += f"<li><strong>{table_name}:</strong> {count} records</li>"
        
        output += "</ul><h2>📋 Recent Bookings</h2><table border='1'>"
        output += "<tr><th>ID</th><th>Name</th><th>Service</th><th>Date</th><th>Time</th><th>Status</th><th>Created</th></tr>"
        
        for booking in recent_bookings:
            output += f"<tr><td>{booking[0]}</td><td>{booking[1]}</td><td>{booking[2]}</td><td>{booking[3]}</td><td>{booking[4]}</td><td>{booking[5]}</td><td>{booking[6]}</td></tr>"
        
        output += "</table>"
        output += f"<p><a href='/admin/dashboard'>← Back to Admin Dashboard</a></p>"
        
        return output
        
    except Exception as e:
        print(f"❌ Debug error: {e}")
        return f"Debug error: {str(e)}", 500

# Update your main route to show admin status
@app.route('/')
def index():
    """Main page with admin login status"""
    try:
        # Check if admin is logged in
        is_admin = session.get('admin_logged_in', False)
        
        # Get reviews data
        reviews_response = get_google_reviews()
        reviews_data = reviews_response.get('data', {}) if reviews_response.get('success') else {}
        
        print(f"🏠 Main page loaded. Admin logged in: {is_admin}")
        
        return render_template('index.html', 
                             reviews_data=reviews_data,
                             is_admin=is_admin)
        
    except Exception as e:
        print(f"❌ Index error: {e}")
        return render_template('index.html', 
                             reviews_data={},
                             is_admin=False)

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

# Application startup
if __name__ == "__main__":
    print("=" * 60)
    print("🚗 KOREE AUTOSERVICE BOOKING SYSTEM")
    print("=" * 60)
    print(f"📍 Environment: {'AWS' if IS_AWS else 'Local'}")
    print(f"🗄️ Database: {DB_FILE}")
    
    # List database files in directory
    app_dir = os.path.dirname(__file__) or '.'
    db_files = [f for f in os.listdir(app_dir) if f.endswith('.db')]
    print(f"📋 Found database files: {db_files}")
    print("=" * 60)
    
    # Consolidate databases if needed
    consolidate_databases()
    
    # Test database connection
    if test_database_connection():
        print("✅ Database connection successful!")
        print()
        print("🚀 Starting Flask application...")
        
        if IS_AWS:
            print("🌐 Running on AWS")
            print("📊 Admin: /admin/bookings")
            print("🔧 Debug: /debug/database")
            print("💗 Health: /health")
        else:
            print("💻 Running locally")
            print("📊 Admin: http://localhost:5000/admin/bookings")
            print("🌐 Website: http://localhost:5000")
            print("🔧 Debug: http://localhost:5000/debug/database")
        
        print("=" * 60)
        
        # Start Flask
        port = int(os.environ.get('PORT', 5000))
        app.run(debug=not IS_AWS, host="0.0.0.0", port=port)
    else:
        print("❌ Database connection failed!")
        print(f"🔍 Trying to create database at: {DB_FILE}")
        if init_db():
            print("✅ Database created successfully!")
            port = int(os.environ.get('PORT', 5000))
            app.run(debug=not IS_AWS, host="0.0.0.0", port=port)
        else:
            print("❌ Failed to create database!")

# AWS Lambda handler (if using Lambda)
def lambda_handler(event, context):
    """AWS Lambda entry point"""
    consolidate_databases()
    if not test_database_connection():
        init_db()
    return app(event, context)