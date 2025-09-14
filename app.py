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
from user_agents import parse
from urllib.parse import quote

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

# Email Configuration (SECURE - no hardcoded fallbacks)
MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') 
MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')  # Only non-sensitive fallback
MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))  # Only non-sensitive fallback
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL')

# API Keys (SECURE - no hardcoded fallbacks)
GOOGLE_PLACES_API_KEY = os.environ.get('GOOGLE_PLACES_API_KEY')
GOOGLE_PLACE_ID = os.environ.get('GOOGLE_PLACE_ID')
# Add validation to ensure critical variables exist
# Admin Configuration (SECURE - no hardcoded fallbacks)  
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')

# Add validation to ensure critical variables exist (CORRECTED)
required_env_vars = [
    'MAIL_USERNAME', 'MAIL_PASSWORD', 'ADMIN_EMAIL'  # Only email-related variables
    # Note: ADMIN_USERNAME and ADMIN_PASSWORD are for login, not email
]

missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
if missing_vars:
    print(f"❌ Missing required email environment variables: {missing_vars}")
    print("Please check your .env file!")
    print("Current email .env values:")
    for var in required_env_vars:
        value = os.environ.get(var)
        if var == 'MAIL_PASSWORD':
            print(f"  {var}: {'✅ SET (' + str(len(value)) + ' chars)' if value else '❌ NOT SET'}")
        else:
            print(f"  {var}: {value or '❌ NOT SET'}")
    
    print("\nAdmin credentials (separate from email):")
    print(f"  ADMIN_USERNAME: {'✅ SET' if ADMIN_USERNAME else '❌ NOT SET'}")
    print(f"  ADMIN_PASSWORD: {'✅ SET' if ADMIN_PASSWORD else '❌ NOT SET'}")
    exit(1)

print("✅ All required email environment variables are set")

print("✅ All required environment variables are set")
def test_email_connection():
    """Test email connection and configuration with detailed debugging"""
    try:
        print("🔍 Testing email configuration...")
        print(f"MAIL_SERVER: {MAIL_SERVER}")
        print(f"MAIL_PORT: {MAIL_PORT}")
        print(f"MAIL_USERNAME: {MAIL_USERNAME}")
        print(f"MAIL_PASSWORD: {'✅ SET (' + str(len(MAIL_PASSWORD)) + ' chars)' if MAIL_PASSWORD else '❌ NOT SET'}")
        
        # Show first/last chars of password for debugging (safely)
        if MAIL_PASSWORD and len(MAIL_PASSWORD) > 4:
            masked = MAIL_PASSWORD[0] + '*' * (len(MAIL_PASSWORD) - 2) + MAIL_PASSWORD[-1]
            print(f"Password preview: {masked}")
        
        # Test SMTP connection with detailed debugging
        print("📡 Connecting to SMTP server...")
        server = smtplib.SMTP(MAIL_SERVER, MAIL_PORT, timeout=30)
        server.set_debuglevel(1)  # Enable detailed SMTP debugging
        
        print("🔐 Starting TLS...")
        server.starttls()
        
        print("👤 Attempting login...")
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        
        print("✅ Login successful!")
        server.quit()
        
        print("✅ Email connection test successful!")
        return True
        
    except smtplib.SMTPAuthenticationError as auth_error:
        print(f"❌ SMTP Authentication Error: {auth_error}")
        print("🔧 Possible fixes:")
        print("   1. Check if password is correct")
        print("   2. Enable 'Less Secure Apps' in email settings")
        print("   3. Generate App Password instead of regular password")
        print("   4. Check if 2FA is enabled")
        return False
    except smtplib.SMTPConnectError as conn_error:
        print(f"❌ SMTP Connection Error: {conn_error}")
        print("🔧 Possible fixes:")
        print("   1. Check MAIL_SERVER and MAIL_PORT settings")
        print("   2. Check internet connection")
        print("   3. Try different port (465 instead of 587)")
        return False
    except Exception as e:
        print(f"❌ Email connection test failed: {e}")
        print(f"❌ Error type: {type(e).__name__}")
        return False

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
        
        # Create visitor tracking table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS visitor_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip_address TEXT,
                user_agent TEXT,
                page_visited TEXT,
                referrer TEXT,
                country TEXT,
                city TEXT,
                device_type TEXT,
                browser TEXT,
                os TEXT,
                session_id TEXT,
                visit_duration INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create admin login tracking table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_login_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                ip_address TEXT,
                user_agent TEXT,
                login_successful BOOLEAN,
                failure_reason TEXT,
                country TEXT,
                city TEXT,
                browser TEXT,
                os TEXT,
                session_duration INTEGER,
                logout_time TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create page analytics table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS page_analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page_name TEXT NOT NULL,
                page_url TEXT,
                visitor_ip TEXT,
                session_id TEXT,
                time_spent INTEGER DEFAULT 0,
                scroll_depth INTEGER DEFAULT 0,
                clicks_count INTEGER DEFAULT 0,
                form_interactions INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create APK tables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS apk_clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT,
                licence_plate TEXT NOT NULL UNIQUE,
                car_brand TEXT,
                car_model TEXT,
                car_year INTEGER,
                apk_expiry_date DATE,
                last_reminder_sent DATE,
                reminder_count INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS apk_reminder_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER,
                client_name TEXT,
                client_email TEXT,
                client_licence_plate TEXT,
                reminder_type TEXT DEFAULT 'automatic',
                email_subject TEXT,
                days_until_expiry INTEGER,
                email_sent BOOLEAN DEFAULT 0,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                error_message TEXT,
                FOREIGN KEY (client_id) REFERENCES apk_clients (id)
            )
        """)
        
        # Check if services exist, if not add default ones
        cursor.execute("SELECT COUNT(*) FROM services")
        service_count = cursor.fetchone()[0]
        
        if service_count == 0:
            print("📝 Adding default services...")
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
            print(f"✅ Added {len(default_services)} default services")
        
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
def test_godaddy_smtp_variants():
    """Test different GoDaddy SMTP configurations"""
    configs = [
        {'server': 'smtpout.secureserver.net', 'port': 587, 'tls': True},
        {'server': 'smtpout.secureserver.net', 'port': 465, 'tls': False, 'ssl': True},
        {'server': 'smtp.secureserver.net', 'port': 587, 'tls': True},
        {'server': 'smtp.secureserver.net', 'port': 465, 'tls': False, 'ssl': True},
    ]
    
    for i, config in enumerate(configs, 1):
        try:
            print(f"\n🔍 Testing config {i}: {config['server']}:{config['port']}")
            
            if config.get('ssl'):
                server = smtplib.SMTP_SSL(config['server'], config['port'])
            else:
                server = smtplib.SMTP(config['server'], config['port'])
                if config.get('tls'):
                    server.starttls()
            
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.quit()
            
            print(f"✅ Config {i} WORKS!")
            print(f"   Use: MAIL_SERVER={config['server']}")
            print(f"   Use: MAIL_PORT={config['port']}")
            return config
            
        except Exception as e:
            print(f"❌ Config {i} failed: {e}")
    
    return None
def send_email(to_email, subject, html_body, text_body=None):
    """Send email using GoDaddy SMTP with better error handling"""
    try:
        print(f"📧 Sending email to: {to_email}")
        print(f"📧 Subject: {subject}")
        print(f"📧 Using server: {MAIL_SERVER}:{MAIL_PORT}")
        
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
        
        # Try different connection methods
        server = None
        try:
            # Method 1: Regular SMTP with STARTTLS (port 587)
            if MAIL_PORT == 587:
                print("🔗 Connecting with STARTTLS...")
                server = smtplib.SMTP(MAIL_SERVER, MAIL_PORT, timeout=30)
                server.starttls()
            
            # Method 2: SMTP_SSL (port 465)  
            elif MAIL_PORT == 465:
                print("🔗 Connecting with SSL...")
                server = smtplib.SMTP_SSL(MAIL_SERVER, MAIL_PORT, timeout=30)
            
            # Method 3: Regular SMTP (port 25)
            else:
                print("🔗 Connecting without encryption...")
                server = smtplib.SMTP(MAIL_SERVER, MAIL_PORT, timeout=30)
            
            print("👤 Logging in...")
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            
            print("📤 Sending message...")
            server.send_message(msg)
            server.quit()
            
            print(f"✅ Email sent successfully to {to_email}")
            return True
        
        except smtplib.SMTPAuthenticationError as auth_error:
            print(f"❌ Authentication failed: {auth_error}")
            print("🔧 Try: Check password, enable app access, disable 2FA")
            return False
        
        except smtplib.SMTPConnectError as conn_error:
            print(f"❌ Connection failed: {conn_error}")
            print("🔧 Try: Different port (465 instead of 587)")
            return False
        
        except Exception as smtp_error:
            print(f"❌ SMTP error: {smtp_error}")
            return False
        
        finally:
            if server:
                try:
                    server.quit()
                except:
                    pass
        
    except Exception as e:
        print(f"❌ Email error: {e}")
        print(f"❌ Error type: {type(e).__name__}")
        return False
import requests
import threading

def init_apk_database():
    """Initialize APK database tables if they don't exist"""
    try:
        print("🔧 Initializing APK database tables...")
        
        connection = get_db_connection()
        if connection is None:
            print("❌ Could not connect to database")
            return False
        
        cursor = connection.cursor()
        
        # Create APK clients table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS apk_clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT,
                licence_plate TEXT NOT NULL UNIQUE,
                car_brand TEXT,
                car_model TEXT,
                car_year INTEGER,
                apk_expiry_date DATE,
                last_reminder_sent DATE,
                reminder_count INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create APK reminder log table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS apk_reminder_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER,
                client_name TEXT,
                client_email TEXT,
                client_licence_plate TEXT,
                reminder_type TEXT DEFAULT 'automatic',
                email_subject TEXT,
                days_until_expiry INTEGER,
                email_sent BOOLEAN DEFAULT 0,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                error_message TEXT,
                FOREIGN KEY (client_id) REFERENCES apk_clients (id)
            )
        """)
        
        connection.commit()
        cursor.close()
        connection.close()
        
        print("✅ APK database tables initialized successfully")
        return True
        
    except Exception as e:
        print(f"❌ APK database initialization error: {e}")
        import traceback
        traceback.print_exc()
        return False

def fetch_rdw_vehicle_data(licence_plate):
    """Fetch vehicle info from RDW API"""
    try:
        # Clean the plate - remove spaces and dashes, convert to uppercase
        clean_plate = licence_plate.replace(" ", "").replace("-", "").upper()
        
        url = f"https://opendata.rdw.nl/resource/m9d7-ebf2.json?kenteken={clean_plate}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200 and response.json():
            vehicle_data = response.json()[0]
            print(f"✅ RDW data found for {clean_plate}: {vehicle_data.get('merk')} {vehicle_data.get('handelsbenaming')}")
            return vehicle_data
    except Exception as e:
        print(f"⚠️ RDW API error for {licence_plate}: {e}")
    return None

def format_date_display(date_string):
    """Format date for display"""
    if not date_string:
        return "Niet beschikbaar"
    try:
        if len(date_string) >= 10:
            date_obj = datetime.strptime(date_string[:10], '%Y-%m-%d')
            return date_obj.strftime('%d-%m-%Y')
    except:
        pass
    return date_string

def generate_calendar_event_data(name, service, date_str, time_str, message, booking_id):
    """Generate calendar event data for different calendar systems"""
    try:
        # Parse date and time
        booking_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        booking_time = datetime.strptime(time_str, '%H:%M').time()
        
        # Create datetime objects
        start_datetime = datetime.combine(booking_date, booking_time)
        end_datetime = start_datetime + timedelta(hours=1)  # Default 1 hour duration
        
        # Format for different calendar systems
        start_utc = start_datetime.strftime('%Y%m%dT%H%M%S')
        end_utc = end_datetime.strftime('%Y%m%dT%H%M%S')
        
        # Event details
        title = f"Autobedrijf Koree - {service}"
        description = f"""Afspraak bij Autobedrijf Koree
        
Service: {service}
Klant: {name}
Booking ID: {booking_id}

Locatie: Haven 45-48, 3143 BD Maassluis
Telefoon: 010 592 8497
Website: https://koreeautoservices.nl

{f'Opmerking: {message}' if message else ''}

Dit is uw bevestigde afspraak. Kom op tijd en neem eventuele documenten mee."""
        
        location = "Autobedrijf Koree, Haven 45-48, 3143 BD Maassluis, Nederland"
        
        # URL encode parameters
        title_encoded = quote(title)
        description_encoded = quote(description)
        location_encoded = quote(location)
        
        # Generate Google Calendar URL
        google_url = (
            f"https://calendar.google.com/calendar/render?action=TEMPLATE"
            f"&text={title_encoded}"
            f"&dates={start_utc}/{end_utc}"
            f"&details={description_encoded}"
            f"&location={location_encoded}"
            f"&sf=true&output=xml"
        )
        
        # Generate Outlook Web URL
        outlook_url = (
            f"https://outlook.live.com/calendar/0/deeplink/compose?subject={title_encoded}"
            f"&body={description_encoded}"
            f"&location={location_encoded}"
            f"&startdt={start_datetime.isoformat()}"
            f"&enddt={end_datetime.isoformat()}"
        )
        
        # Generate ICS download URL (we'll create an endpoint for this)
        ics_url = f"{request.url_root}download-calendar-event/{booking_id}"
        
        return {
            'google_url': google_url,
            'outlook_url': outlook_url,
            'ics_url': ics_url,
            'start_datetime': start_datetime,
            'end_datetime': end_datetime,
            'title': title,
            'description': description,
            'location': location
        }
        
    except Exception as e:
        print(f"❌ Calendar generation error: {e}")
        return {
            'google_url': '#',
            'outlook_url': '#',
            'ics_url': '#',
            'start_datetime': None,
            'end_datetime': None,
            'title': 'Calendar Error',
            'description': 'Error generating calendar event',
            'location': 'Autobedrijf Koree'
        }

def generate_ics_content(booking_data):
    """Generate ICS calendar file content"""
    try:
        # Parse booking data
        start_dt = datetime.strptime(f"{booking_data['date']} {booking_data['time']}", '%Y-%m-%d %H:%M')
        end_dt = start_dt + timedelta(hours=1)
        
        # Format for ICS (UTC format)
        start_utc = start_dt.strftime('%Y%m%dT%H%M%SZ')
        end_utc = end_dt.strftime('%Y%m%dT%H%M%SZ')
        created_utc = datetime.now().strftime('%Y%m%dT%H%M%SZ')
        
        # Generate unique UID
        import uuid
        uid = str(uuid.uuid4())
        
        # Prepare description text (separate from f-string to avoid backslash issues)
        base_description = f"Afspraak bij Autobedrijf Koree\\n\\nService: {booking_data['service']}\\nKlant: {booking_data['name']}\\nTelefoon: {booking_data['phone']}\\n\\nLocatie: Haven 45-48\\, 3143 BD Maassluis\\nTelefoon bedrijf: 010 592 8497\\nWebsite: https://koreeautoservices.nl"
        
        # Add message if exists
        if booking_data.get('message'):
            description_text = base_description + f"\\n\\nOpmerking: {booking_data['message']}"
        else:
            description_text = base_description
        
        # ICS content
        ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Autobedrijf Koree//Booking System//NL
CALSCALE:GREGORIAN
METHOD:PUBLISH
BEGIN:VEVENT
UID:{uid}
DTSTAMP:{created_utc}
DTSTART:{start_utc}
DTEND:{end_utc}
SUMMARY:Autobedrijf Koree - {booking_data['service']}
DESCRIPTION:{description_text}
LOCATION:Autobedrijf Koree\\, Haven 45-48\\, 3143 BD Maassluis\\, Nederland
STATUS:CONFIRMED
SEQUENCE:0
BEGIN:VALARM
TRIGGER:-PT1H
DESCRIPTION:Herinnering: Afspraak Autobedrijf Koree over 1 uur
ACTION:DISPLAY
END:VALARM
END:VEVENT
END:VCALENDAR"""
        
        return ics_content
        
    except Exception as e:
        print(f"❌ ICS generation error: {e}")
        return None
@app.route('/download-calendar-event/<int:booking_id>')
def download_calendar_event(booking_id):
    """Download ICS calendar file for booking"""
    try:
        connection = get_db_connection()
        if connection is None:
            return "Database error", 500
        
        cursor = connection.cursor()
        cursor.execute("""
            SELECT id, name, email, phone, service, date, time, message 
            FROM bookings 
            WHERE id = ?
        """, (booking_id,))
        
        booking = cursor.fetchone()
        cursor.close()
        connection.close()
        
        if not booking:
            return "Booking not found", 404
        
        # Convert to dict
        booking_data = {
            'id': booking[0],
            'name': booking[1],
            'email': booking[2],
            'phone': booking[3],
            'service': booking[4],
            'date': booking[5],
            'time': booking[6],
            'message': booking[7]
        }
        
        # Generate ICS content
        ics_content = generate_ics_content(booking_data)
        
        if not ics_content:
            return "Error generating calendar file", 500
        
        # Create response
        from flask import Response
        
        filename = f"autobedrijf_koree_afspraak_{booking_id}.ics"
        
        response = Response(
            ics_content,
            mimetype='text/calendar',
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Type": "text/calendar; charset=utf-8"
            }
        )
        
        print(f"📅 Calendar file downloaded for booking {booking_id}")
        return response
        
    except Exception as e:
        print(f"❌ Calendar download error: {e}")
        return "Calendar download error", 500
def send_apk_reminder_email(client_data, days_until_expiry):
    """Send APK reminder email using existing email configuration"""
    try:
        subject = f"APK Herinnering - {client_data['licence_plate']} verloopt over {days_until_expiry} dagen"
        
        # Create professional HTML email
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #d32f2f 0%, #f44336 100%); color: white; padding: 25px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ padding: 25px; background: #f9f9f9; }}
                .warning-box {{ background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 8px; margin: 20px 0; }}
                .vehicle-details {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .contact-info {{ background: #e3f2fd; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                .footer {{ text-align: center; padding: 20px; color: #666; background: #f5f5f5; border-radius: 0 0 10px 10px; }}
                .urgent {{ color: #d32f2f; font-weight: bold; }}
                .btn {{ background: #d32f2f; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 10px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🚗 APK Herinnering</h1>
                    <h2>Autobedrijf Koree</h2>
                    <p>Uw APK verloopt binnenkort!</p>
                </div>
                
                <div class="content">
                    <h2>Beste {client_data['name']},</h2>
                    
                    <div class="warning-box">
                        <h3>⚠️ Belangrijke herinnering</h3>
                        <p class="urgent">Uw APK verloopt over {days_until_expiry} dagen!</p>
                        <p>Plan nu uw APK keuring in om problemen te voorkomen.</p>
                    </div>
                    
                    <div class="vehicle-details">
                        <h3>🚙 Voertuiggegevens</h3>
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Kenteken:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{client_data['licence_plate']}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Merk:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{client_data.get('car_brand', 'Onbekend')}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Model:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{client_data.get('car_model', 'Onbekend')}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>APK vervalt op:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee; color: #d32f2f; font-weight: bold;">{format_date_display(client_data['apk_expiry_date'])}</td></tr>
                        </table>
                    </div>
                    
                    <div class="contact-info">
                        <h3>📞 Maak nu een afspraak!</h3>
                        <p><strong>Autobedrijf Koree - Uw specialist voor APK keuringen</strong></p>
                        <p>📍 <strong>Adres:</strong> Haven 45-48, 3143 BD Maassluis</p>
                        <p>📞 <strong>Telefoon:</strong> 010 592 8497</p>
                        <p>📧 <strong>Email:</strong> info@koreeautoservices.nl</p>
                        <p>🌐 <strong>Website:</strong> <a href="https://koreeautoservices.nl">koreeautoservices.nl</a></p>
                        
                        <a href="https://koreeautoservices.nl" class="btn">💻 Online Afspraak Maken</a>
                    </div>
                    
                    <p><strong>Waarom kiezen voor Autobedrijf Koree?</strong></p>
                    <ul>
                        <li>✅ Erkend APK keuringsstation</li>
                        <li>✅ Snelle en betrouwbare service</li>
                        <li>✅ Eerlijke prijzen</li>
                        <li>✅ Ervaren monteurs</li>
                        <li>✅ Directe reparaties mogelijk</li>
                    </ul>
                    
                    <p>Neem vandaag nog contact met ons op om uw APK keuring in te plannen!</p>
                    
                    <p style="margin-top: 30px;">
                        Met vriendelijke groet,<br>
                        <strong>Team Autobedrijf Koree</strong>
                    </p>
                </div>
                
                <div class="footer">
                    <p><small>Dit is een automatische herinnering. Heeft u al een afspraak gemaakt? Dan kunt u deze email negeren.</small></p>
                    <p><small>Haven 45-48, 3143 BD Maassluis | 010 592 8497 | info@koreeautoservices.nl</small></p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Send email using your existing function
        email_success = send_email(client_data['email'], subject, html_body)
        
        if email_success:
            print(f"✅ APK reminder email sent to {client_data['email']}")
            return True, "Email sent successfully"
        else:
            return False, "Failed to send email"
        
    except Exception as e:
        error_msg = f"Error sending APK reminder email: {str(e)}"
        print(f"❌ {error_msg}")
        return False, error_msg
def check_and_send_apk_reminders():
    """Check for expiring APK dates and send reminders (only at 30 days)"""
    try:
        print("🔍 Checking for APK reminders...")
        
        connection = get_db_connection()
        if connection is None:
            print("❌ Database connection failed for APK check")
            return False
        
        cursor = connection.cursor()
        
        # Get clients with APK expiring in exactly 30 days (or 29-31 days to handle weekends)
        cursor.execute("""
            SELECT id, name, email, licence_plate, car_brand, car_model, apk_expiry_date, last_reminder_sent
            FROM apk_clients 
            WHERE is_active = 1 
            AND apk_expiry_date IS NOT NULL
            AND DATE(apk_expiry_date) >= DATE('now', '+29 days')
            AND DATE(apk_expiry_date) <= DATE('now', '+31 days')
            AND (last_reminder_sent IS NULL OR DATE(last_reminder_sent) < DATE('now', '-7 days'))
            ORDER BY apk_expiry_date ASC
        """)
        
        clients_to_remind = cursor.fetchall()
        
        if not clients_to_remind:
            print("ℹ️ No APK reminders needed today")
            cursor.close()
            connection.close()
            return True
        
        today = datetime.now().date()
        success_count = 0
        
        for client in clients_to_remind:
            try:
                client_id = client[0]
                apk_date = datetime.strptime(client[6], '%Y-%m-%d').date()
                days_until = (apk_date - today).days
                
                client_data = {
                    'name': client[1],
                    'email': client[2],
                    'licence_plate': client[3],
                    'car_brand': client[4],
                    'car_model': client[5],
                    'apk_expiry_date': client[6]
                }
                
                # Send reminder email
                email_success, email_message = send_apk_reminder_email(client_data, days_until)
                
                # Log the reminder
                cursor.execute("""
                    INSERT INTO apk_reminder_log (client_id, reminder_type, email_subject, days_until_expiry, email_sent, error_message)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (client_id, 'automatic', f"APK Reminder - {client[3]}", days_until, email_success, None if email_success else email_message))
                
                if email_success:
                    # Update last reminder sent
                    cursor.execute("""
                        UPDATE apk_clients 
                        SET last_reminder_sent = DATE('now'), reminder_count = reminder_count + 1
                        WHERE id = ?
                    """, (client_id,))
                    success_count += 1
                    print(f"✅ Reminder sent to {client[1]} ({client[3]}) - {days_until} days until expiry")
                
                connection.commit();
                
            except Exception as e:
                print(f"❌ Error sending reminder to {client[1]}: {e}")
        
        cursor.close()
        connection.close()
        
        print(f"✅ APK reminder check complete: {success_count} reminders sent")
        return True
        
    except Exception as e:
        print(f"❌ APK reminder check error: {e}")
        return False
def start_daily_apk_check():
    """Start daily APK reminder check in background"""
    def daily_check():
        import time
        while True:
            try:
                # Check every 24 hours (86400 seconds)
                # For testing, you can change this to 60 seconds
                check_and_send_apk_reminders()
                time.sleep(86400)  # 24 hours
            except Exception as e:
                print(f"❌ Daily APK check error: {e}")
                time.sleep(3600)  # Try again in 1 hour on error
    
    # Start background thread
    thread = threading.Thread(target=daily_check, daemon=True)
    thread.start()
    print("🕐 Daily APK reminder check started in background")
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

# Add this to the beginning of any APK route
def ensure_apk_tables_exist():
    """Ensure APK tables exist before using them"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        
        # Check if APK tables exist
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name IN ('apk_clients', 'apk_reminder_log')
        """)
        
        existing_tables = [row[0] for row in cursor.fetchall()]
        
        if len(existing_tables) < 2:
            print("🔧 APK tables missing, creating them...")
            cursor.close()
            connection.close()
            return init_apk_database()
        
        cursor.close()
        connection.close()
        return True
        
    except Exception as e:
        print(f"❌ Error checking APK tables: {e}")
        return False

def get_client_info(request):
    """Extract client information from request (works in cloud and local)"""
    try:
        # Get IP address (works with AWS load balancers)
        ip_address = request.headers.get('X-Forwarded-For', 
                    request.headers.get('X-Real-IP', 
                    request.remote_addr or 'unknown'))
        
        # Handle comma-separated IPs from load balancers
        if ',' in ip_address:
            ip_address = ip_address.split(',')[0].strip()
        
        user_agent_string = request.headers.get('User-Agent', '')
        user_agent = parse(user_agent_string)
        
        # Get referrer
        referrer = request.headers.get('Referer', 'direct')
        
        client_info = {
            'ip_address': ip_address,
            'user_agent': user_agent_string,
            'referrer': referrer,
            'browser': f"{user_agent.browser.family} {user_agent.browser.version_string}",
            'os': f"{user_agent.os.family} {user_agent.os.version_string}",
            'device_type': 'Mobile' if user_agent.is_mobile else 'Desktop',
            'country': 'Unknown',  # You can add GeoIP later
            'city': 'Unknown'
        }
        
        return client_info
        
    except Exception as e:
        print(f"❌ Error getting client info: {e}")
        return {
            'ip_address': 'unknown',
            'user_agent': '',
            'referrer': 'unknown',
            'browser': 'unknown',
            'os': 'unknown',
            'device_type': 'unknown',
            'country': 'unknown',
            'city': 'unknown'
        }

def track_visitor(request, page_name, page_url):
    """Track website visitor (works in cloud and local)"""
    try:
        client_info = get_client_info(request)
        session_id = session.get('visitor_session_id')
        
        if not session_id:
            import uuid
            session_id = str(uuid.uuid4())
            session['visitor_session_id'] = session_id
        
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        
        cursor.execute("""
            INSERT INTO visitor_logs 
            (ip_address, user_agent, page_visited, referrer, country, city, 
             device_type, browser, os, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            client_info['ip_address'],
            client_info['user_agent'],
            page_name,
            client_info['referrer'],
            client_info['country'],
            client_info['city'],
            client_info['device_type'],
            client_info['browser'],
            client_info['os'],
            session_id
        ))
        
        connection.commit()
        cursor.close()
        connection.close()
        
        print(f"📊 Tracked visitor: {client_info['ip_address']} -> {page_name}")
        return True
        
    except Exception as e:
        print(f"❌ Error tracking visitor: {e}")
        return False

def track_admin_login(request, username, success, failure_reason=None):
    """Track admin login attempts (works in cloud and local)"""
    try:
        client_info = get_client_info(request)
        
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        
        cursor.execute("""
            INSERT INTO admin_login_logs 
            (username, ip_address, user_agent, login_successful, failure_reason,
             country, city, browser, os)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            username,
            client_info['ip_address'],
            client_info['user_agent'],
            success,
            failure_reason,
            client_info['country'],
            client_info['city'],
            client_info['browser'],
            client_info['os']
        ))
        
        connection.commit()
        cursor.close()
        connection.close()
        
        status = "✅ SUCCESS" if success else "❌ FAILED"
        print(f"🔐 Admin login {status}: {username} from {client_info['ip_address']}")
        return True
        
    except Exception as e:
        print(f"❌ Error tracking admin login: {e}")
        return False
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
        
        # Generate calendar event data
        calendar_data = generate_calendar_event_data(name, service, date, time, message, booking_id)
        
        # Send confirmation emails with calendar integration
        try:
            # Customer email with calendar buttons
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
                    .calendar-buttons {{ background: #e8f5e8; padding: 20px; border-radius: 8px; margin: 20px 0; text-align: center; }}
                    .calendar-btn {{ display: inline-block; padding: 12px 25px; margin: 5px; text-decoration: none; border-radius: 5px; font-weight: bold; color: white; }}
                    .outlook-btn {{ background: #0078d4; }}
                    .google-btn {{ background: #4285f4; }}
                    .ics-btn {{ background: #28a745; }}
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
                            <p><strong>Datum:</strong> {datetime.strptime(date, '%Y-%m-%d').strftime('%d-%m-%Y')}</p>
                            <p><strong>Tijd:</strong> {time}</p>
                            <p><strong>Naam:</strong> {name}</p>
                            <p><strong>Telefoon:</strong> {phone}</p>
                            <p><strong>Email:</strong> {email}</p>
                            {f'<p><strong>Bericht:</strong> {message}</p>' if message else ''}
                        </div>
                        
                        <div class="calendar-buttons">
                            <h3>📅 Voeg toe aan uw agenda</h3>
                            <p>Klik op één van onderstaande knoppen om deze afspraak toe te voegen aan uw agenda:</p>
                            
                            <a href="{calendar_data['outlook_url']}" class="calendar-btn outlook-btn" target="_blank">
                                📅 Outlook Agenda
                            </a>
                            
                            <a href="{calendar_data['google_url']}" class="calendar-btn google-btn" target="_blank">
                                📅 Google Agenda
                            </a>
                            
                            <a href="{calendar_data['ics_url']}" class="calendar-btn ics-btn">
                                📅 Download ICS Bestand
                            </a>
                        </div>
                        
                        <p>Wij zien u graag op de afgesproken tijd. Heeft u vragen? Bel ons op 010 592 8497.</p>
                        
                        <p><strong>🏢 Autobedrijf Koree</strong><br>
                        Haven 45-48, 3143 BD Maassluis<br>
                        📞 010 592 8497<br>
                        📧 info@koreeautoservices.nl</p>
                        
                        <p>Met vriendelijke groet,<br>
                        Team Autobedrijf Koree</p>
                    </div>
                    <div class="footer">
                        <p>Haven 45-48, 3143 BD Maassluis | info@koreeautoservices.nl</p>
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
                            <p><strong>Datum:</strong> {datetime.strptime(date, '%Y-%m-%d').strftime('%d-%m-%Y')}</p>
                            <p><strong>Tijd:</strong> {time}</p>
                            <p><strong>Naam:</strong> {name}</p>
                            <p><strong>Telefoon:</strong> {phone}</p>
                            <p><strong>Email:</strong> {email}</p>
                            {f'<p><strong>Bericht:</strong> {message}</p>' if message else ''}
                        </div>
                        
                        <p><a href="{calendar_data['outlook_url']}" style="background: #0078d4; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">📅 Voeg toe aan Outlook</a></p>
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
            "message": f"Afspraak succesvol geboekt voor {datetime.strptime(date, '%Y-%m-%d').strftime('%d-%m-%Y')} om {time}. Bevestiging verzonden naar {email}.",
            "booking_id": booking_id,
            "calendar_links": calendar_data
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
    # Track admin login page visit
    track_visitor(request, 'Admin Login Page', '/admin/login')
    
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_login.html')

@app.route('/admin/authenticate', methods=['POST'])
def admin_authenticate():
    try:
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        admin_username = os.environ.get('ADMIN_USERNAME')
        admin_password = os.environ.get('ADMIN_PASSWORD')
        
        if username == admin_username and password == admin_password:
            import time
            session['admin_logged_in'] = True
            session['admin_username'] = username
            session['admin_login_time'] = time.time()
            session['last_activity'] = time.time()
            session.permanent = True
            
            # Track successful login
            track_admin_login(request, username, True)
            
            print(f"✅ Successful admin login: {username}")
            flash('Welcome to admin dashboard!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            # Track failed login
            track_admin_login(request, username, False, 'Invalid credentials')
            
            print(f"❌ Failed login attempt for username: {username}")
            flash('Invalid username or password', 'error')
            return redirect(url_for('admin_login'))
            
    except Exception as e:
        # Track system error
        track_admin_login(request, username if 'username' in locals() else 'unknown', False, f'System error: {str(e)}')
        
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
    """Admin dashboard with APK statistics"""
    try:
        connection = get_db_connection()
        if connection is None:
            flash('Database connection failed', 'error')
            return redirect(url_for('admin_login'))
        
        cursor = connection.cursor()
        
        # Existing booking stats
        cursor.execute("SELECT COUNT(*) FROM bookings")
        total_bookings = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(*) FROM bookings 
            WHERE date >= date('now', '-7 days')
        """)
        recent_bookings = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(*) FROM bookings 
            WHERE date >= date('now') AND status = 'confirmed'
        """)
        upcoming_bookings = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT id, name, email, phone, service, date, time, status, created_at 
            FROM bookings 
            ORDER BY created_at DESC 
            LIMIT 8
        """)
        recent_bookings_details = cursor.fetchall()
        
        # APK statistics (check if table exists first)
        try:
            cursor.execute("SELECT COUNT(*) FROM apk_clients WHERE is_active = 1")
            apk_result = cursor.fetchone()
            total_apk_clients = apk_result[0] if apk_result else 0
            
            cursor.execute("""
                SELECT COUNT(*) FROM apk_clients 
                WHERE is_active = 1 AND apk_expiry_date IS NOT NULL
                AND DATE(apk_expiry_date) >= DATE('now') 
                AND DATE(apk_expiry_date) <= DATE('now', '+30 days')
            """)
            apk_result = cursor.fetchone()
            apk_expiring_soon = apk_result[0] if apk_result else 0
            
            cursor.execute("""
                SELECT COUNT(*) FROM apk_clients 
                WHERE is_active = 1 AND apk_expiry_date IS NOT NULL
                AND DATE(apk_expiry_date) < DATE('now')
            """)
            apk_result = cursor.fetchone()
            apk_expired = apk_result[0] if apk_result else 0
        except:
            # APK tables don't exist yet
            total_apk_clients = 0
            apk_expiring_soon = 0
            apk_expired = 0
        
        cursor.close()
        connection.close()
        
        stats = {
            'total_bookings': total_bookings,
            'recent_bookings': recent_bookings,
            'upcoming_bookings': upcoming_bookings,
            'recent_bookings_details': recent_bookings_details
        }
        
        apk_stats = {
            'total_clients': total_apk_clients,
            'expiring_soon': apk_expiring_soon,
            'expired': apk_expired
        }
        
        admin_info = {
            'username': session.get('admin_username', 'admin'),
            'full_name': 'Administrator'
        }
        
        return render_template('admin_dashboard.html', 
                             stats=stats, 
                             apk_stats=apk_stats,
                             admin_info=admin_info)
        
    except Exception as e:
        print(f"❌ Dashboard error: {e}")
        flash('Dashboard error occurred', 'error')
        return redirect(url_for('admin_login'))
def upgrade_database_schema():
    """Upgrade database schema to add missing columns"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        
        # Check if duration_minutes column exists in services table
        cursor.execute("PRAGMA table_info(services)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'duration_minutes' not in columns:
            print("🔧 Adding duration_minutes column to services table...")
            cursor.execute("ALTER TABLE services ADD COLUMN duration_minutes INTEGER DEFAULT 60")
            connection.commit()
            print("✅ duration_minutes column added successfully")
        
        cursor.close()
        connection.close()
        return True
        
    except Exception as e:
        print(f"❌ Database upgrade error: {e}")
        return False    
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
# APK Management Routes
@app.route('/admin/apk-clients')
@require_admin_auth
def admin_apk_clients():
    """View all APK clients"""
    try:
        connection = get_db_connection()
        if connection is None:
            flash('Database verbinding mislukt', 'error')
            return redirect(url_for('admin_dashboard'))
        
        cursor = connection.cursor()
        
        # Check if APK tables exist first
        try:
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='apk_clients'
            """)
            
            if not cursor.fetchone():
                # APK tables don't exist, initialize them
                print("🔧 APK tables not found, initializing...")
                cursor.close()
                connection.close()
                
                # Initialize APK database
                if init_apk_database():
                    flash('APK systeem succesvol geïnitialiseerd', 'success')
                else:
                    flash('Fout bij initialiseren APK systeem', 'error')
                    return redirect(url_for('admin_dashboard'))
                
                # Get new connection after initialization
                connection = get_db_connection()
                if connection is None:
                    flash('Database verbinding mislukt na initialisatie', 'error')
                    return redirect(url_for('admin_dashboard'))
                cursor = connection.cursor()
        except Exception as table_check_error:
            print(f"❌ Table check error: {table_check_error}")
            cursor.close()
            connection.close()
            
            # Try to initialize
            if init_apk_database():
                flash('APK systeem geïnitialiseerd', 'success')
                connection = get_db_connection()
                if connection is None:
                    flash('Database verbinding mislukt', 'error')
                    return redirect(url_for('admin_dashboard'))
                cursor = connection.cursor()
            else:
                flash('Kan APK systeem niet initialiseren', 'error')
                return redirect(url_for('admin_dashboard'))
        
        # Now safely query the APK clients
        try:
            cursor.execute("""
                SELECT id, name, email, phone, licence_plate, car_brand, car_model, 
                       apk_expiry_date, last_reminder_sent, reminder_count, is_active, created_at
                FROM apk_clients 
                ORDER BY apk_expiry_date ASC, created_at DESC
            """)
            
            apk_clients = cursor.fetchall()
        except Exception as query_error:
            print(f"❌ Query error: {query_error}")
            # If query fails, return empty list
            apk_clients = []
            flash('Kan APK klanten niet laden - lege lijst getoond', 'warning')
        
        cursor.close()
        connection.close()
        
        # Calculate days until expiry for each client
        today = datetime.now().date()
        clients_with_status = []
        
        for client in apk_clients:
            client_dict = {
                'id': client[0],
                'name': client[1],
                'email': client[2],
                'phone': client[3],
                'licence_plate': client[4],
                'car_brand': client[5],
                'car_model': client[6],
                'apk_expiry_date': client[7],
                'last_reminder_sent': client[8],
                'reminder_count': client[9],
                'is_active': client[10],
                'created_at': client[11],
                'days_until_expiry': None,
                'status': 'unknown'
            }
            
            if client[7]:  # apk_expiry_date
                try:
                    apk_date = datetime.strptime(client[7], '%Y-%m-%d').date()
                    days_until = (apk_date - today).days
                    client_dict['days_until_expiry'] = days_until
                    
                    if days_until < 0:
                        client_dict['status'] = 'expired'
                    elif days_until <= 3:
                        client_dict['status'] = 'urgent'
                    elif days_until <= 14:
                        client_dict['status'] = 'warning'
                    elif days_until <= 30:
                        client_dict['status'] = 'upcoming'
                    else:
                        client_dict['status'] = 'valid'
                except:
                    pass
            
            clients_with_status.append(client_dict)
        
        return render_template('admin_apk_clients.html', apk_clients=clients_with_status)
        
    except Exception as e:
        print(f"❌ APK clients error: {e}")
        import traceback
        traceback.print_exc()
        flash(f'Fout bij laden APK klanten: {str(e)}', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/add-apk-client')
@require_admin_auth
def admin_add_apk_client():
    """Show form to add new APK client"""
    return render_template('admin_add_apk_client.html')

@app.route('/admin/create-apk-client', methods=['POST'])
@require_admin_auth
def admin_create_apk_client():
    """Create new APK client with automatic RDW data fetching"""
    try:
        # Get form data
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        licence_plate = request.form.get('licence_plate', '').strip().upper()
        
        # Validation
        errors = []
        if not name:
            errors.append("Naam is verplicht")
        if not email:
            errors.append("E-mail is verplicht")
        if not licence_plate:
            errors.append("Kenteken is verplicht")
        
        if errors:
            for error in errors:
                flash(error, 'error')
            return redirect(url_for('admin_add_apk_client'))
        
        # Check if licence plate already exists
        connection = get_db_connection()
        if connection is None:
            flash('Database verbinding mislukt', 'error')
            return redirect(url_for('admin_add_apk_client'))
        
        cursor = connection.cursor()
        
        # Check if APK table exists, if not initialize
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='apk_clients'
        """)
        
        if not cursor.fetchone():
            cursor.close()
            connection.close()
            
            # Initialize APK tables
            if not init_apk_database():
                flash('Fout bij initialiseren APK systeem', 'error')
                return redirect(url_for('admin_add_apk_client'))
            
            # Get new connection
            connection = get_db_connection()
            if connection is None:
                flash('Database verbinding mislukt na initialisatie', 'error')
                return redirect(url_for('admin_add_apk_client'))
            cursor = connection.cursor()
        
        # Check if licence plate already exists
        cursor.execute("SELECT id FROM apk_clients WHERE licence_plate = ?", (licence_plate,))
        existing = cursor.fetchone()
        
        if existing:
            cursor.close()
            connection.close()
            flash('Kenteken bestaat al in de database', 'error')
            return redirect(url_for('admin_add_apk_client'))
        
        # Fetch vehicle data from RDW API
        print(f"🔍 Fetching RDW data for: {licence_plate}")
        vehicle_data = fetch_rdw_vehicle_data(licence_plate)
        
        car_brand = None
        car_model = None
        apk_expiry_date = None
        car_year = None
        
        if vehicle_data:
            car_brand = vehicle_data.get('merk')
            car_model = vehicle_data.get('handelsbenaming')
            if vehicle_data.get('vervaldatum_apk'):
                apk_expiry_date = vehicle_data.get('vervaldatum_apk')
            if vehicle_data.get('datum_eerste_toelating'):
                try:
                    first_reg = vehicle_data.get('datum_eerste_toelating')
                    car_year = int(first_reg[:4]) if len(first_reg) >= 4 else None
                except:
                    pass
        
        # Save to database
        cursor.execute("""
            INSERT INTO apk_clients (name, email, phone, licence_plate, car_brand, car_model, car_year, apk_expiry_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, email, phone, licence_plate, car_brand, car_model, car_year, apk_expiry_date))
        
        connection.commit()
        cursor.close()
        connection.close()
        
        success_msg = f'APK klant {name} succesvol toegevoegd!'
        if vehicle_data:
            success_msg += f' Voertuig: {car_brand} {car_model}'
            if apk_expiry_date:
                success_msg += f', APK vervalt: {format_date_display(apk_expiry_date)}'
        else:
            success_msg += ' (Geen RDW gegevens gevonden - controleer kenteken)'
        
        flash(success_msg, 'success')
        return redirect(url_for('admin_apk_clients'))
        
    except Exception as e:
        print(f"❌ Create APK client error: {e}")
        import traceback
        traceback.print_exc()
        flash(f'Fout bij aanmaken APK klant: {str(e)}', 'error')
        return redirect(url_for('admin_add_apk_client'))

@app.route('/admin/send-apk-reminders')
@require_admin_auth
def admin_send_apk_reminders():
    """Send APK reminders manually"""
    try:
        check_and_send_apk_reminders()
        flash('APK reminder check completed successfully', 'success')
        return redirect(url_for('admin_apk_clients'))
        
    except Exception as e:
        print(f"❌ Manual APK reminder error: {e}")
        flash('Error sending APK reminders', 'error')
        return redirect(url_for('admin_apk_clients'))

@app.route('/admin/delete-apk-client/<int:client_id>')
@require_admin_auth
def admin_delete_apk_client(client_id):
    """Delete APK client"""
    try:
        connection = get_db_connection()
        if connection is None:
            flash('Database connection failed', 'error')
            return redirect(url_for('admin_apk_clients'))
        
        cursor = connection.cursor()
        cursor.execute("DELETE FROM apk_clients WHERE id = ?", (client_id,))
        cursor.execute("DELETE FROM apk_reminder_log WHERE client_id = ?", (client_id,))
        
        connection.commit()
        cursor.close()
        connection.close()
        
        flash('APK client deleted successfully', 'success')
        
    except Exception as e:
        print(f"❌ Delete APK client error: {e}")
        flash('Error deleting APK client', 'error')
    
    return redirect(url_for('admin_apk_clients'))

@app.route('/admin/apk-reminder-logs')
@require_admin_auth
def admin_apk_reminder_logs():
    """View APK reminder logs"""
    try:
        connection = get_db_connection()
        if connection is None:
            flash('Database connection failed', 'error')
            return redirect(url_for('admin_dashboard'))
        
        cursor = connection.cursor()
        cursor.execute("""
            SELECT l.id, c.name, c.email, c.licence_plate, l.reminder_type, 
                   l.email_subject, l.days_until_expiry, l.email_sent, l.sent_at, l.error_message
            FROM apk_reminder_log l
            JOIN apk_clients c ON l.client_id = c.id
            ORDER BY l.sent_at DESC
            LIMIT 100
        """)
        
        logs = cursor.fetchall()
        cursor.close()
        connection.close()
        
        return render_template('admin_apk_logs.html', logs=logs)
        
    except Exception as e:
        print(f"❌ APK logs error: {e}")
        flash('Error loading APK logs', 'error')
        return redirect(url_for('admin_dashboard'))
@app.route('/admin/analytics')
@require_admin_auth
def admin_analytics():
    """View website analytics and admin login logs"""
    try:
        connection = get_db_connection()
        if connection is None:
            flash('Database connection failed', 'error')
            return redirect(url_for('admin_dashboard'))
        
        cursor = connection.cursor()
        
        # Initialize empty data in case queries fail
        analytics_data = {
            'visitor_stats': {
                'unique_visitors': 0,
                'total_page_views': 0,
                'active_days': 0
            },
            'popular_pages': [],
            'browser_stats': [],
            'device_stats': [],
            'recent_visitors': [],
            'admin_logins': [],
            'daily_stats': []
        }
        
        try:
            # Check if visitor_logs table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='visitor_logs'
            """)
            
            if not cursor.fetchone():
                print("⚠️ visitor_logs table doesn't exist, creating it...")
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS visitor_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ip_address TEXT,
                        user_agent TEXT,
                        page_visited TEXT,
                        referrer TEXT,
                        country TEXT,
                        city TEXT,
                        device_type TEXT,
                        browser TEXT,
                        os TEXT,
                        session_id TEXT,
                        visit_duration INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                connection.commit()
            
            # Check if admin_login_logs table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='admin_login_logs'
            """)
            
            if not cursor.fetchone():
                print("⚠️ admin_login_logs table doesn't exist, creating it...")
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS admin_login_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT,
                        ip_address TEXT,
                        user_agent TEXT,
                        login_successful BOOLEAN,
                        failure_reason TEXT,
                        country TEXT,
                        city TEXT,
                        browser TEXT,
                        os TEXT,
                        session_duration INTEGER,
                        logout_time TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                connection.commit()
            
            # Get visitor statistics
            cursor.execute("""
                SELECT 
                    COUNT(DISTINCT session_id) as unique_visitors,
                    COUNT(*) as total_page_views,
                    COUNT(DISTINCT DATE(created_at)) as active_days
                FROM visitor_logs 
                WHERE created_at >= datetime('now', '-30 days')
            """)
            visitor_stats = cursor.fetchone()
            
            if visitor_stats:
                analytics_data['visitor_stats'] = {
                    'unique_visitors': visitor_stats[0] or 0,
                    'total_page_views': visitor_stats[1] or 0,
                    'active_days': visitor_stats[2] or 0
                }
            
            # Get popular pages
            cursor.execute("""
                SELECT page_visited, COUNT(*) as visits
                FROM visitor_logs 
                WHERE created_at >= datetime('now', '-30 days')
                GROUP BY page_visited
                ORDER BY visits DESC
                LIMIT 10
            """)
            analytics_data['popular_pages'] = cursor.fetchall()
            
            # Get browser statistics
            cursor.execute("""
                SELECT browser, COUNT(*) as count
                FROM visitor_logs 
                WHERE created_at >= datetime('now', '-30 days')
                AND browser != 'unknown' AND browser IS NOT NULL AND browser != ''
                GROUP BY browser
                ORDER BY count DESC
                LIMIT 10
            """)
            analytics_data['browser_stats'] = cursor.fetchall()
            
            # Get device statistics
            cursor.execute("""
                SELECT device_type, COUNT(*) as count
                FROM visitor_logs 
                WHERE created_at >= datetime('now', '-30 days')
                AND device_type IS NOT NULL AND device_type != ''
                GROUP BY device_type
                ORDER BY count DESC
            """)
            analytics_data['device_stats'] = cursor.fetchall()
            
            # Get recent visitors
            cursor.execute("""
                SELECT ip_address, page_visited, browser, device_type, created_at
                FROM visitor_logs 
                ORDER BY created_at DESC
                LIMIT 50
            """)
            analytics_data['recent_visitors'] = cursor.fetchall()
            
            # Get admin login attempts
            cursor.execute("""
                SELECT username, ip_address, login_successful, failure_reason, 
                       browser, created_at
                FROM admin_login_logs 
                ORDER BY created_at DESC
                LIMIT 100
            """)
            analytics_data['admin_logins'] = cursor.fetchall()
            
        except Exception as query_error:
            print(f"⚠️ Query error in analytics: {query_error}")
            # Keep default empty data
        
        cursor.close()
        connection.close()
        
        print(f"✅ Analytics data prepared: {len(analytics_data['recent_visitors'])} visitors, {len(analytics_data['admin_logins'])} admin logs")
        
        return render_template('admin_analytics.html', analytics=analytics_data)
        
    except Exception as e:
        print(f"❌ Analytics error: {e}")
        import traceback
        traceback.print_exc()
        
        # Return template with empty data instead of crashing
        empty_analytics = {
            'visitor_stats': {'unique_visitors': 0, 'total_page_views': 0, 'active_days': 0},
            'popular_pages': [],
            'browser_stats': [],
            'device_stats': [],
            'recent_visitors': [],
            'admin_logins': [],
            'daily_stats': []
        }
        
        flash('Analytics data could not be loaded', 'warning')
        return render_template('admin_analytics.html', analytics=empty_analytics)
        
    except Exception as e:
        print(f"❌ Analytics error: {e}")
        import traceback
        traceback.print_exc()
        
        # Return template with empty data instead of crashing
        empty_analytics = {
            'visitor_stats': {'unique_visitors': 0, 'total_page_views': 0, 'active_days': 0},
            'popular_pages': [],
            'browser_stats': [],
            'device_stats': [],
            'recent_visitors': [],
            'admin_logins': [],
            'daily_stats': []
        }
        
        flash('Analytics data could not be loaded', 'warning')
        return render_template('admin_analytics.html', analytics=empty_analytics)

@app.route('/')
def index():
    try:
        # Track visitor
        track_visitor(request, 'Homepage', '/')
        
        is_admin = session.get('admin_logged_in', False)
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

# Debug routes
@app.route('/debug/init-analytics-tables')
def debug_init_analytics_tables():
    """Create analytics tables if they don't exist"""
    try:
        connection = get_db_connection()
        if connection is None:
            return "❌ Database connection failed", 500
        
        cursor = connection.cursor()
        
        # Create visitor tracking table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS visitor_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip_address TEXT,
                user_agent TEXT,
                page_visited TEXT,
                referrer TEXT,
                country TEXT,
                city TEXT,
                device_type TEXT,
                browser TEXT,
                os TEXT,
                session_id TEXT,
                visit_duration INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create admin login tracking table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_login_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                ip_address TEXT,
                user_agent TEXT,
                login_successful BOOLEAN,
                failure_reason TEXT,
                country TEXT,
                city TEXT,
                browser TEXT,
                os TEXT,
                session_duration INTEGER,
                logout_time TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        connection.commit()
        cursor.close()
        connection.close()
        
        return """
        <h1>✅ Analytics Tables Created Successfully!</h1>
        <p><a href="/admin/analytics">Test Analytics Page</a></p>
        <p><a href="/admin/dashboard">Back to Dashboard</a></p>
        """
        
    except Exception as e:
        return f"❌ Error: {str(e)}", 500

# Application startup
if __name__ == "__main__":
    print("=" * 60)
    print("🚗 KOREE AUTOSERVICE BOOKING SYSTEM")
    print("=" * 60)
    print(f"📍 Environment: {'AWS' if IS_AWS else 'Local'}")
    print(f"🗄️ Database: {DB_FILE}")
    
    # List database files
    app_dir = os.path.dirname(__file__) or '.'
    db_files = [f for f in os.listdir(app_dir) if f.endswith('.db')]
    print(f"📋 Found database files: {db_files}")
    print("=" * 60)
    
    # Consolidate and test database
    consolidate_databases()
    upgrade_database_schema()
    test_email_connection()
    test_godaddy_smtp_variants()
    
    if test_database_connection():
        print("✅ Database connection successful!")
        print()
        print("🚀 Starting Flask application...")
        
        # Start APK reminder checker in background
        start_daily_apk_check()
        
        if IS_AWS:
            print("🌐 Running on AWS")
            print("📊 Admin: /admin/dashboard")
            print("📈 Analytics: /admin/analytics")
            print("🔧 Debug: /debug/database")
        else:
            print("💻 Running locally")
            print("📊 Admin: http://localhost:5000/admin/dashboard")
            print("🌐 Website: http://localhost:5000")
            print("📈 Analytics: http://localhost:5000/admin/analytics")
            print("🔧 Debug: http://localhost:5000/debug/database")
        
        print("=" * 60)
        
        # Run the app
        port = int(os.environ.get('PORT', 5000))
        app.run(debug=not IS_AWS, host="0.0.0.0", port=port)
    else:
        print("❌ Database connection failed!")
        print(f"🔍 Trying to create database at: {DB_FILE}")
        if init_db():
            print("✅ Database created successfully!")
            print("🚀 Starting Flask application...")
            
            # Start APK reminder checker
            start_daily_apk_check()
            
            port = int(os.environ.get('PORT', 5000))
            app.run(debug=not IS_AWS, host="0.0.0.0", port=port)
        else:
            print("❌ Failed to create database!")
            print("Please check your database configuration and permissions.")



