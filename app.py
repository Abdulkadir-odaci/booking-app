from flask import Flask, render_template, request, url_for, jsonify
import mysql.connector
from mysql.connector import Error
import smtplib
import requests
from email.message import EmailMessage
from datetime import datetime, timedelta
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = 'your-secret-key-here'

# Database Configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'koree_autoservice'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci',
    'autocommit': True
}

# Email Configuration - FIXED to use correct defaults
MAIL_USERNAME = os.getenv('MAIL_USERNAME')
MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtpout.secureserver.net')  # Changed default to GoDaddy
MAIL_PORT = int(os.getenv('MAIL_PORT', 587))  # Changed default port
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL')

def get_db_connection():
    """Create database connection"""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        if connection.is_connected():
            return connection
    except Error as e:
        print(f"❌ Database connection error: {e}")
        return None

def init_db():
    """Initialize database with tables"""
    try:
        # First, connect without specifying database to create it
        temp_config = DB_CONFIG.copy()
        database_name = temp_config.pop('database')
        
        connection = mysql.connector.connect(**temp_config)
        cursor = connection.cursor()
        
        # Create database if it doesn't exist
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {database_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        cursor.execute(f"USE {database_name}")
        
        # Create bookings table with proper MariaDB syntax
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                email VARCHAR(255) NOT NULL,
                phone VARCHAR(20),
                date DATE NOT NULL,
                time TIME NOT NULL,
                service VARCHAR(255),
                message TEXT,
                status ENUM('pending', 'confirmed', 'cancelled') DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_date_time (date, time),
                INDEX idx_email (email),
                INDEX idx_status (status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        # Create services table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS services (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL UNIQUE,
                description TEXT,
                duration INT DEFAULT 60,
                price DECIMAL(10,2) DEFAULT 0.00,
                active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_name (name),
                INDEX idx_active (active)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        # Insert default services if they don't exist
        cursor.execute("SELECT COUNT(*) FROM services")
        if cursor.fetchone()[0] == 0:
            services = [
                ('APK Keuring', 'Volledige APK keuring voor uw voertuig', 60, 35.00),
                ('Onderhoudsbeurt', 'Complete onderhoudsbeurt volgens fabrieksspecificaties', 120, 150.00),
                ('Banden Service', 'Bandenwissel en uitbalanceren', 45, 25.00),
                ('Airco Service', 'Airconditioning service en vulling', 90, 75.00),
                ('Reparaties', 'Algemene reparaties aan uw voertuig', 180, 0.00),
                ('Diagnose', 'Computerdiagnose van motorproblemen', 30, 45.00)
            ]
            cursor.executemany("""
                INSERT INTO services (name, description, duration, price) 
                VALUES (%s, %s, %s, %s)
            """, services)
        
        connection.commit()
        cursor.close()
        connection.close()
        
        print("✅ MariaDB database initialized successfully!")
        print(f"✅ Database: {database_name}")
        print(f"✅ Host: {DB_CONFIG['host']}:{DB_CONFIG['port']}")
        return True
        
    except Error as e:
        print(f"❌ Database initialization error: {e}")
        return False

def send_booking_emails(booking_data):
    """Send professional HTML confirmation emails"""
    try:
        # Customer confirmation email
        customer_subject = "✅ Afspraak Bevestiging - Koree Autoservice"
        customer_body = create_customer_email_html(booking_data)
        
        # Admin notification email
        admin_subject = f"🔔 Nieuwe Afspraak #{booking_data['booking_id']} - {booking_data['name']}"
        admin_body = create_admin_email_html(booking_data)

        # Send emails
        customer_sent = send_html_email(
            to_email=booking_data['email'],
            subject=customer_subject,
            html_body=customer_body
        )

        admin_sent = send_html_email(
            to_email=ADMIN_EMAIL,
            subject=admin_subject,
            html_body=admin_body
        )

        return customer_sent, admin_sent

    except Exception as e:
        print(f"❌ Email sending error: {str(e)}")
        return False, False

def create_customer_email_html(booking_data):
    """Create professional HTML email for customer"""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Afspraak Bevestiging</title>
        <style>
            body {{
                margin: 0;
                padding: 0;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: #f4f4f4;
                line-height: 1.6;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                background-color: #ffffff;
                border-radius: 10px;
                overflow: hidden;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }}
            .header {{
                background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
                color: white;
                padding: 30px 20px;
                text-align: center;
            }}
            .logo {{
                font-size: 28px;
                font-weight: bold;
                margin-bottom: 10px;
            }}
            .content {{
                padding: 30px 20px;
            }}
            .confirmation-box {{
                background: #e8f5e8;
                border-left: 4px solid #4CAF50;
                padding: 20px;
                margin: 20px 0;
                border-radius: 5px;
            }}
            .booking-details {{
                background: #f8f9fa;
                padding: 20px;
                border-radius: 8px;
                margin: 20px 0;
            }}
            .detail-row {{
                display: flex;
                justify-content: space-between;
                padding: 8px 0;
                border-bottom: 1px solid #e0e0e0;
            }}
            .detail-row:last-child {{
                border-bottom: none;
            }}
            .detail-label {{
                font-weight: bold;
                color: #333;
            }}
            .detail-value {{
                color: #666;
            }}
            .location-box {{
                background: #fff3cd;
                border: 1px solid #ffeaa7;
                padding: 20px;
                border-radius: 8px;
                margin: 20px 0;
            }}
            .important-box {{
                background: #d1ecf1;
                border: 1px solid #bee5eb;
                padding: 20px;
                border-radius: 8px;
                margin: 20px 0;
            }}
            .contact-section {{
                background: #f8f9fa;
                padding: 20px;
                border-radius: 8px;
                margin: 20px 0;
            }}
            .contact-item {{
                margin: 10px 0;
                padding: 8px 0;
            }}
            .contact-icon {{
                display: inline-block;
                width: 20px;
                margin-right: 10px;
            }}
            .footer {{
                background: #2c3e50;
                color: white;
                padding: 20px;
                text-align: center;
                font-size: 14px;
            }}
            .btn {{
                display: inline-block;
                padding: 12px 25px;
                background: #4CAF50;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                margin: 10px 5px;
            }}
            .btn-secondary {{
                background: #007bff;
            }}
            @media only screen and (max-width: 600px) {{
                .container {{
                    margin: 10px;
                    border-radius: 0;
                }}
                .detail-row {{
                    flex-direction: column;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <!-- Header -->
            <div class="header">
                <div class="logo">🔧 KOREE AUTOSERVICE</div>
                <p>Uw betrouwbare partner voor autoservice</p>
            </div>
            
            <!-- Content -->
            <div class="content">
                <h2>Beste {booking_data['name']},</h2>
                
                <div class="confirmation-box">
                    <h3 style="margin-top: 0; color: #4CAF50;">✅ Uw afspraak is bevestigd!</h3>
                    <p>Wij hebben uw afspraak succesvol ontvangen en bevestigd. Hieronder vindt u alle details.</p>
                </div>
                
                <!-- Booking Details -->
                <div class="booking-details">
                    <h3 style="margin-top: 0; color: #333;">📋 Afspraak Details</h3>
                    <div class="detail-row">
                        <span class="detail-label">Booking ID:</span>
                        <span class="detail-value">#{booking_data['booking_id']}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Naam:</span>
                        <span class="detail-value">{booking_data['name']}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Email:</span>
                        <span class="detail-value">{booking_data['email']}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Telefoon:</span>
                        <span class="detail-value">{booking_data.get('phone', 'Niet opgegeven')}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Service:</span>
                        <span class="detail-value">{booking_data['service']}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Datum:</span>
                        <span class="detail-value">{booking_data['date']}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Tijd:</span>
                        <span class="detail-value">{booking_data['time']}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Bericht:</span>
                        <span class="detail-value">{booking_data.get('message', 'Geen specifieke wensen')}</span>
                    </div>
                </div>
                
                <!-- Location -->
                <div class="location-box">
                    <h3 style="margin-top: 0; color: #856404;">📍 Onze Locatie</h3>
                    <p><strong>Koree Autoservice</strong><br>
                    Fenacoliuslaan 60-64<br>
                    3143 AE Maassluis<br>
                    Nederland</p>
                </div>
                
                <!-- Important Notes -->
                <div class="important-box">
                    <h3 style="margin-top: 0; color: #0c5460;">⚠️ Belangrijk</h3>
                    <ul style="margin: 0; padding-left: 20px;">
                        <li>Kom 10 minuten voor uw afspraak</li>
                        <li>Neem uw rijbewijs en autopapieren mee</li>
                        <li>Bij annulering, bel minimaal 24 uur van tevoren</li>
                        <li>Parkeren is gratis op ons terrein</li>
                    </ul>
                </div>
                
                <!-- Contact Section -->
                <div class="contact-section">
                    <h3 style="margin-top: 0; color: #333;">📞 Contact</h3>
                    <div class="contact-item">
                        <span class="contact-icon">📱</span>
                        <strong>Telefoon:</strong> +31 6 23967989
                    </div>
                    <div class="contact-item">
                        <span class="contact-icon">📧</span>
                        <strong>Email:</strong> info@koreeautoservices.nl
                    </div>
                    <div class="contact-item">
                        <span class="contact-icon">💬</span>
                        <strong>WhatsApp:</strong> 
                        <a href="https://wa.me/31623967989" class="btn btn-secondary" style="color: white; text-decoration: none;">
                            Stuur WhatsApp
                        </a>
                    </div>
                </div>
            </div>
            
            <!-- Footer -->
            <div class="footer">
                <p><strong>Koree Autoservice</strong> - Uw betrouwbare partner sinds jaren</p>
                <p>Bedankt voor uw vertrouwen! 🚗✨</p>
            </div>
        </div>
    </body>
    </html>
    """

def create_admin_email_html(booking_data):
    """Create professional HTML email for admin"""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Nieuwe Afspraak</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: #f4f4f4;
                margin: 0;
                padding: 20px;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                background: white;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            .header {{
                background: linear-gradient(45deg, #FF6B6B, #4ECDC4);
                color: white;
                padding: 20px;
                text-align: center;
            }}
            .content {{
                padding: 20px;
            }}
            .booking-card {{
                background: #f8f9fa;
                border-radius: 8px;
                padding: 20px;
                margin: 15px 0;
                border-left: 4px solid #4ECDC4;
            }}
            .detail-grid {{
                display: grid;
                grid-template-columns: 1fr 2fr;
                gap: 10px;
                margin: 10px 0;
            }}
            .label {{
                font-weight: bold;
                color: #333;
            }}
            .value {{
                color: #666;
            }}
            .status-badge {{
                display: inline-block;
                padding: 4px 12px;
                background: #28a745;
                color: white;
                border-radius: 20px;
                font-size: 12px;
                font-weight: bold;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>🔔 Nieuwe Afspraak Ontvangen</h2>
                <p>Booking ID: #{booking_data['booking_id']}</p>
            </div>
            
            <div class="content">
                <div class="booking-card">
                    <h3>👤 Klant Informatie</h3>
                    <div class="detail-grid">
                        <span class="label">Naam:</span>
                        <span class="value">{booking_data['name']}</span>
                        <span class="label">Email:</span>
                        <span class="value">{booking_data['email']}</span>
                        <span class="label">Telefoon:</span>
                        <span class="value">{booking_data.get('phone', 'Niet opgegeven')}</span>
                    </div>
                </div>
                
                <div class="booking-card">
                    <h3>📅 Afspraak Details</h3>
                    <div class="detail-grid">
                        <span class="label">Service:</span>
                        <span class="value">{booking_data['service']}</span>
                        <span class="label">Datum:</span>
                        <span class="value">{booking_data['date']}</span>
                        <span class="label">Tijd:</span>
                        <span class="value">{booking_data['time']}</span>
                        <span class="label">Status:</span>
                        <span class="value"><span class="status-badge">Bevestigd</span></span>
                        <span class="label">Bericht:</span>
                        <span class="value">{booking_data.get('message', 'Geen specifieke wensen')}</span>
                    </div>
                </div>
                
                <div class="booking-card">
                    <h3>🕐 Systeem Info</h3>
                    <div class="detail-grid">
                        <span class="label">Geboekt op:</span>
                        <span class="value">{datetime.now().strftime('%d-%m-%Y om %H:%M')}</span>
                        <span class="label">Booking ID:</span>
                        <span class="value">#{booking_data['booking_id']}</span>
                    </div>
                </div>
                
                <p><strong>💡 Tip:</strong> Je kunt deze afspraak beheren via HeidiSQL of de admin interface.</p>
            </div>
        </div>
    </body>
    </html>
    """

def send_html_email(to_email, subject, html_body):
    """Send HTML email using GoDaddy SMTP with enhanced debugging"""
    try:
        print(f"🔧 Email Configuration Check:")
        print(f"  MAIL_USERNAME: {MAIL_USERNAME}")
        print(f"  MAIL_SERVER: {MAIL_SERVER}")
        print(f"  MAIL_PORT: {MAIL_PORT}")
        print(f"  TO: {to_email}")
        print(f"  PASSWORD LENGTH: {len(MAIL_PASSWORD) if MAIL_PASSWORD else 0}")
        
        if not all([MAIL_USERNAME, MAIL_PASSWORD, to_email]):
            print("❌ Missing email configuration")
            return False

        # Validate GoDaddy SMTP settings
        if 'secureserver' not in MAIL_SERVER:
            print(f"⚠️  Warning: SMTP server '{MAIL_SERVER}' is not GoDaddy server")
            print("💡 Expected: smtpout.secureserver.net")

        # Create email message
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = f"Koree Autoservice <{MAIL_USERNAME}>"
        msg['To'] = to_email
        
        # Set HTML content
        msg.set_content("Plain text fallback")  # Fallback for non-HTML clients
        msg.add_alternative(html_body, subtype='html')

        print(f"🔄 Connecting to {MAIL_SERVER}:{MAIL_PORT}...")
        
        # Try multiple GoDaddy SMTP configurations
        smtp_configs = [
            {'server': 'smtpout.secureserver.net', 'port': 587, 'use_tls': True},
            {'server': 'smtpout.secureserver.net', 'port': 465, 'use_ssl': True},
            {'server': 'smtp.office365.com', 'port': 587, 'use_tls': True},  # If using Workspace Email
            {'server': 'smtp.secureserver.net', 'port': 587, 'use_tls': True}
        ]
        
        for config in smtp_configs:
            try:
                print(f"🔄 Trying {config['server']}:{config['port']}...")
                
                if config.get('use_ssl'):
                    # Use SSL for port 465
                    with smtplib.SMTP_SSL(config['server'], config['port']) as server:
                        server.set_debuglevel(1)  # Enable debug output
                        print(f"🔄 Logging in as {MAIL_USERNAME}...")
                        server.login(MAIL_USERNAME, MAIL_PASSWORD)
                        print(f"🔄 Sending message...")
                        server.send_message(msg)
                else:
                    # Use TLS for port 587
                    with smtplib.SMTP(config['server'], config['port']) as server:
                        server.set_debuglevel(1)  # Enable debug output
                        print(f"🔄 Starting TLS...")
                        server.starttls()
                        print(f"🔄 Logging in as {MAIL_USERNAME}...")
                        server.login(MAIL_USERNAME, MAIL_PASSWORD)
                        print(f"🔄 Sending message...")
                        server.send_message(msg)

                print(f"✅ Email sent successfully via {config['server']}:{config['port']}")
                return True
                
            except smtplib.SMTPAuthenticationError as e:
                print(f"❌ Authentication failed with {config['server']}:{config['port']} - {str(e)}")
                continue
            except Exception as e:
                print(f"❌ Connection failed with {config['server']}:{config['port']} - {str(e)}")
                continue

        print("❌ All SMTP configurations failed")
        return False

    except Exception as e:
        print(f"❌ Email error: {str(e)}")
        return False

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/services", methods=["GET"])
def get_services():
    try:
        connection = get_db_connection()
        if connection is None:
            return jsonify({"error": "Database connection failed"}), 500
        
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM services WHERE active = TRUE ORDER BY name")
        services = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        print(f"✅ Loaded {len(services)} services from MariaDB")
        return jsonify({"services": services})
        
    except Error as e:
        print(f"❌ Services error: {e}")
        return jsonify({"error": "Failed to fetch services"}), 500

@app.route("/api/book", methods=["POST"])
def book_appointment():
    try:
        data = request.form
        name = data.get("name")
        email = data.get("email")
        phone = data.get("phone")
        date = data.get("date")
        time = data.get("time")
        service = data.get("service", "General Service")
        message = data.get("message", "")

        if not all([name, email, date, time]):
            return jsonify({"error": "Verplichte velden ontbreken"}), 400

        # Validate date and time
        try:
            booking_date = datetime.strptime(date, '%Y-%m-%d').date()
            booking_time = datetime.strptime(time, '%H:%M').time()
            booking_datetime = datetime.combine(booking_date, booking_time)
        except ValueError:
            return jsonify({"error": "Ongeldige datum of tijd"}), 400

        # Don't allow past bookings (including today's past times)
        now = datetime.now()
        if booking_datetime <= now:
            return jsonify({"error": "Kan geen afspraak in het verleden maken"}), 400
        
        # Validate business hours
        if not is_valid_time_slot(time):
            return jsonify({"error": "Ongeldige tijd geselecteerd"}), 400
        
        # REMOVED: Sunday check - Sunday is now a working day
        # Sunday is now available for bookings

        connection = get_db_connection()
        if connection is None:
            return jsonify({"error": "Database connection failed"}), 500
        
        cursor = connection.cursor()
        
        # Check if timeslot is available
        cursor.execute("""
            SELECT id FROM bookings 
            WHERE date = %s AND time = %s AND status != 'cancelled'
        """, (date, time))
        
        if cursor.fetchone():
            cursor.close()
            connection.close()
            return jsonify({"error": "Deze tijd is al geboekt. Selecteer een andere tijd."}), 409

        # Save booking
        cursor.execute("""
            INSERT INTO bookings (name, email, phone, date, time, service, message, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'confirmed')
        """, (name, email, phone, date, time, service, message))
        
        booking_id = cursor.lastrowid
        connection.commit()
        cursor.close()
        connection.close()

        print(f"✅ Booking #{booking_id} saved to MariaDB")

        # Prepare booking data for emails
        booking_data = {
            'booking_id': booking_id,
            'name': name,
            'email': email,
            'phone': phone,
            'date': date,
            'time': time,
            'service': service,
            'message': message,
            'status': 'confirmed'
        }

        # Send emails
        customer_sent, admin_sent = send_booking_emails(booking_data)

        # Prepare response message
        response_message = "Afspraak succesvol geboekt!"
        if customer_sent:
            response_message += " Een bevestigingsmail is verzonden."
        else:
            response_message += " Let op: bevestigingsmail kon niet worden verzonden."

        return jsonify({
            "message": response_message,
            "booking_id": booking_id,
            "email_sent": customer_sent,
            "admin_notified": admin_sent
        }), 201

    except Exception as e:
        print(f"❌ Booking error: {str(e)}")
        return jsonify({"error": "Er is een fout opgetreden. Probeer het opnieuw."}), 500

def is_valid_time_slot(time_str):
    """Validate if the time slot is within business hours and 30-minute intervals"""
    try:
        time_obj = datetime.strptime(time_str, '%H:%M').time()
        hour = time_obj.hour
        minute = time_obj.minute
        
        # Business hours: 8:00 - 16:30
        if hour < 8 or hour > 16:
            return False
        
        # If hour is 16, only allow 16:00 and 16:30
        if hour == 16 and minute > 30:
            return False
        
        # Only 30-minute intervals (00 or 30 minutes)
        if minute not in [0, 30]:
            return False
        
        return True
    except ValueError:
        return False

def generate_time_slots():
    """Generate 30-minute time slots for business hours INCLUDING lunch time"""
    time_slots = []
    
    # Business hours: 8:00 - 16:30 (30-minute slots)
    # INCLUDING lunch hours 12:00-13:00
    start_hour = 8
    end_hour = 17  # Will generate up to 16:30
    
    current_hour = start_hour
    current_minute = 0
    
    while current_hour < end_hour:
        time_str = f"{current_hour:02d}:{current_minute:02d}"
        display_str = f"{current_hour:02d}:{current_minute:02d}"
        
        time_slots.append({
            "value": time_str,
            "display": display_str
        })
        
        # Add 30 minutes
        current_minute += 30
        if current_minute >= 60:
            current_minute = 0
            current_hour += 1
    
    print(f"✅ Generated {len(time_slots)} time slots: {[slot['value'] for slot in time_slots]}")
    return time_slots

@app.route("/api/reviews", methods=["GET"])
def get_reviews():
    print("=== MAKING REAL-TIME API CALL ===")
    
    # REAL-TIME API CALL - No caching
    search_url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    search_params = {
        "input": "Koree Autoservice Maassluis",
        "inputtype": "textquery",
        "fields": "place_id,formatted_address,name",
        "key": "AIzaSyBPG2bpACmH0ThEtnC5u8qPeVoGW-N7bZ4"
    }
    
    try:
        print("Step 1: Searching for business...")
        search_response = requests.get(search_url, params=search_params)
        search_data = search_response.json()
        
        if search_data.get('status') == 'OK' and search_data.get('candidates'):
            place_id = search_data['candidates'][0]['place_id']
            print(f"Step 2: Found place_id: {place_id}")
            
            details_url = "https://maps.googleapis.com/maps/api/place/details/json"
            details_params = {
                "place_id": place_id,
                "key": "AIzaSyBPG2bpACmH0ThEtnC5u8qPeVoGW-N7bZ4",
                "language": "nl",
                "fields": "name,rating,reviews(author_name,author_url,rating,relative_time_description,text,time,profile_photo_url),user_ratings_total,formatted_address"
            }
            
            print("Step 3: Fetching reviews...")
            details_response = requests.get(details_url, params=details_params)
            details_data = details_response.json()
            
            if details_data.get('status') == 'OK' and 'result' in details_data:
                result = details_data['result']
                all_reviews = result.get('reviews', [])
                print(f"Step 4: Found {len(all_reviews)} total reviews")
                
                # Filter reviews from last 2 years
                two_years_ago = datetime.now() - timedelta(days=730)
                recent_reviews = []
                
                print("Step 5: Filtering reviews from last 2 years...")
                for i, review in enumerate(all_reviews):
                    review_timestamp = review.get('time', 0)
                    review_date = datetime.fromtimestamp(review_timestamp)
                    years_ago = (datetime.now() - review_date).days / 365.25
                    
                    print(f"Review {i+1}: {review.get('author_name')} - {years_ago:.1f} years ago")
                    
                    # Only include reviews from last 2 years
                    if review_date >= two_years_ago:
                        author_url = review.get('author_url', '')
                        
                        # FIXED Local Guide detection - more accurate
                        is_local_guide = False
                        if author_url:
                            url_lower = author_url.lower()
                            # Only consider as Local Guide if URL contains specific Local Guide patterns
                            is_local_guide = (
                                'localguides' in url_lower or 
                                'local-guides' in url_lower or
                                '/contrib/local' in url_lower or
                                'guides.google.com' in url_lower
                            )
                            
                            # If it's just /maps/contrib/NUMBER/reviews, it's NOT a Local Guide
                            if '/maps/contrib/' in url_lower and 'localguides' not in url_lower:
                                is_local_guide = False
                        
                        print(f"  ✓ Including: {review.get('author_name')} - Local Guide: {is_local_guide}")
                        print(f"    URL: {author_url}")
                        
                        processed_review = {
                            "author": review.get('author_name'),
                            "rating": review.get('rating'),
                            "time": review.get('relative_time_description'),
                            "text": review.get('text'),
                            "profile_photo": review.get('profile_photo_url'),
                            "date": review_date.strftime('%d-%m-%Y'),
                            "author_url": author_url,
                            "is_local_guide": is_local_guide
                        }
                        recent_reviews.append(processed_review)
                    else:
                        print(f"  ✗ Skipping: {review.get('author_name')} (too old)")
                
                # Sort by newest first
                recent_reviews.sort(key=lambda x: datetime.strptime(x['date'], '%d-%m-%Y'), reverse=True)
                
                # Limit to 5 most recent reviews
                recent_reviews = recent_reviews[:5]
                
                print(f"Step 6: Final result - {len(recent_reviews)} reviews")
                for i, review in enumerate(recent_reviews):
                    print(f"  {i+1}. {review['author']} - {review['date']} - Local Guide: {review['is_local_guide']}")
                
                # Prepare response data - REMOVED the 2-year message
                response_data = {
                    "success": True,
                    "data": {
                        "name": result.get('name'),
                        "rating": result.get('rating'),
                        "total_ratings": result.get('user_ratings_total'),
                        "reviews": recent_reviews,
                        "api_call_time": datetime.now().strftime('%H:%M:%S')
                    }
                }
                
                print("=== API CALL COMPLETED ===")
                return jsonify(response_data)
            else:
                print(f"Error: No business data found - {details_data.get('status')}")
                return jsonify({"error": "No business data found"}), 404
        else:
            print(f"Error: Business not found - {search_data.get('status')}")
            return jsonify({"error": "Business not found"}), 404
            
    except Exception as e:
        print(f"Exception: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/debug/reviews")
def debug_reviews():
    try:
        print("=== DEBUG ENDPOINT - REAL-TIME CALL ===")
        
        # Make the API call to see raw data
        search_url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
        search_params = {
            "input": "Koree Autoservice Maassluis",
            "inputtype": "textquery",
            "fields": "place_id",
            "key": "AIzaSyBPG2bpACmH0ThEtnC5u8qPeVoGW-N7bZ4"
        }
        
        search_response = requests.get(search_url, params=search_params)
        search_data = search_response.json()
        
        if search_data.get('status') == 'OK' and search_data.get('candidates'):
            place_id = search_data['candidates'][0]['place_id']
            
            details_url = "https://maps.googleapis.com/maps/api/place/details/json"
            details_params = {
                "place_id": place_id,
                "key": "AIzaSyBPG2bpACmH0ThEtnC5u8qPeVoGW-N7bZ4",
                "language": "nl",
                "fields": "reviews(author_name,author_url,rating,relative_time_description,text,time,profile_photo_url)"
            }
            
            details_response = requests.get(details_url, params=details_params)
            details_data = details_response.json()
            
            if details_data.get('status') == 'OK' and 'result' in details_data:
                reviews = details_data['result'].get('reviews', [])
                
                debug_info = {
                    "api_call_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "total_reviews": len(reviews),
                    "current_timestamp": datetime.now().timestamp(),
                    "two_years_ago_timestamp": (datetime.now() - timedelta(days=730)).timestamp(),
                    "reviews": []
                }
                
                for review in reviews:
                    review_timestamp = review.get('time', 0)
                    review_date = datetime.fromtimestamp(review_timestamp)
                    years_ago = (datetime.now() - review_date).days / 365.25
                    
                    # FIXED Local Guide detection
                    author_url = review.get('author_url', '')
                    is_local_guide = False
                    if author_url:
                        url_lower = author_url.lower()
                        is_local_guide = (
                            'localguides' in url_lower or 
                            'local-guides' in url_lower or
                            '/contrib/local' in url_lower or
                            'guides.google.com' in url_lower
                        )
                        
                        if '/maps/contrib/' in url_lower and 'localguides' not in url_lower:
                            is_local_guide = False
                    
                    debug_info["reviews"].append({
                        "author": review.get('author_name'),
                        "timestamp": review_timestamp,
                        "date": review_date.strftime('%d-%m-%Y'),
                        "relative_time": review.get('relative_time_description'),
                        "years_ago": round(years_ago, 1),
                        "within_2_years": years_ago <= 2,
                        "author_url": author_url,
                        "is_local_guide": is_local_guide,
                        "rating": review.get('rating'),
                        "text_preview": review.get('text', '')[:100] + "..." if review.get('text') and len(review.get('text', '')) > 100 else review.get('text', '')
                    })
                
                return jsonify(debug_info)
        
        return jsonify({"error": "Could not fetch debug info"})
    
    except Exception as e:
        return jsonify({"error": str(e)})

# Admin endpoint to view bookings (for development)
@app.route("/admin/bookings")
def admin_bookings():
    try:
        connection = get_db_connection()
        if connection is None:
            return jsonify({"error": "Database connection failed"}), 500
        
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, name, email, phone, date, time, service, message, status, created_at
            FROM bookings 
            ORDER BY created_at DESC
            LIMIT 50
        """)
        bookings = cursor.fetchall()
        
        # Convert datetime objects to strings for JSON serialization
        for booking in bookings:
            if booking['created_at']:
                booking['created_at'] = booking['created_at'].strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.close()
        connection.close()
        
        return jsonify({
            "success": True,
            "total": len(bookings),
            "bookings": bookings
        })
        
    except Error as e:
        print(f"❌ Admin bookings error: {e}")
        return jsonify({"error": "Failed to fetch bookings"}), 500

@app.route("/test/config")
def test_config():
    """Test if environment variables are loaded"""
    return jsonify({
        "mail_username": MAIL_USERNAME,
        "mail_password_length": len(MAIL_PASSWORD) if MAIL_PASSWORD else 0,
        "mail_server": MAIL_SERVER,
        "mail_port": MAIL_PORT,
        "admin_email": ADMIN_EMAIL,
        "password_set": bool(MAIL_PASSWORD)
    })

@app.route("/debug/password")
def debug_password():
    """Debug password loading"""
    return jsonify({
        "env_file_exists": os.path.exists('.env'),
        "mail_username": MAIL_USERNAME,
        "mail_password_from_env": os.getenv('MAIL_PASSWORD'),
        "mail_password_variable": MAIL_PASSWORD,
        "mail_password_length": len(MAIL_PASSWORD) if MAIL_PASSWORD else 0,
        "passwords_match": os.getenv('MAIL_PASSWORD') == MAIL_PASSWORD
    })

@app.route("/api/available-times", methods=["GET"])
def get_available_times():
    """Get available time slots for a specific date with booking status"""
    try:
        date = request.args.get('date')
        if not date:
            return jsonify({"error": "Date parameter required"}), 400
        
        print(f"🔍 Checking available times for date: {date}")
        
        # Validate date format
        try:
            booking_date = datetime.strptime(date, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({
                "success": False,
                "error": "Invalid date format",
                "available_times": [],
                "message": "Ongeldige datum"
            })
        
        # Don't allow past dates
        if booking_date < datetime.now().date():
            return jsonify({
                "success": False,
                "error": "Cannot book in the past",
                "available_times": [],
                "message": "Kan geen afspraken in het verleden maken"
            })
        
        # REMOVED: Sunday check - now Sunday is a working day
        # Sunday is now a normal working day like any other day
        
        connection = get_db_connection()
        if connection is None:
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
            WHERE date = %s AND status != 'cancelled'
        """, (date,))
        
        booked_times_raw = cursor.fetchall()
        booked_times = []
        
        # Handle both timedelta and time objects
        for row in booked_times_raw:
            time_value = row[0]
            if isinstance(time_value, timedelta):
                # Convert timedelta to time string
                total_seconds = int(time_value.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                time_str = f"{hours:02d}:{minutes:02d}"
            else:
                # It's already a time object
                time_str = time_value.strftime('%H:%M')
            
            booked_times.append(time_str)
        
        print(f"📊 Booked times for {date}: {booked_times}")
        
        cursor.close()
        connection.close()
        
        # Generate all possible time slots (30-minute intervals)
        all_time_slots = generate_time_slots()
        
        # Get current time for today's comparison
        now = datetime.now()
        is_today = booking_date == now.date()
        
        # Create detailed time information
        available_times = []
        all_times_with_status = []
        
        for time_slot in all_time_slots:
            is_booked = time_slot['value'] in booked_times
            
            # Check if time has passed for today
            is_past_time = False
            if is_today:
                try:
                    slot_time = datetime.strptime(time_slot['value'], '%H:%M').time()
                    slot_datetime = datetime.combine(booking_date, slot_time)
                    is_past_time = slot_datetime <= now
                except:
                    is_past_time = False
            
            is_available = not is_booked and not is_past_time
            
            status = "available"
            if is_booked:
                status = "booked"
            elif is_past_time:
                status = "past"
            
            time_info = {
                "value": time_slot['value'],
                "display": time_slot['display'],
                "available": is_available,
                "status": status,
                "is_booked": is_booked,
                "is_past": is_past_time
            }
            
            all_times_with_status.append(time_info)
            
            # Only add to available_times if actually available
            if is_available:
                available_times.append({
                    "value": time_slot['value'],
                    "display": time_slot['display']
                })
        
        print(f"✅ Total slots: {len(all_time_slots)}, Available: {len(available_times)}, Booked: {len(booked_times)}")
        
        return jsonify({
            "success": True,
            "date": date,
            "available_times": available_times,
            "all_times": all_times_with_status,
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

@app.route("/api/booking-status", methods=["POST"])
def check_booking_status():
    """Check the status of a booking by ID"""
    try:
        data = request.json
        booking_id = data.get("booking_id")
        
        if not booking_id:
            return jsonify({"error": "Booking ID is required"}), 400
        
        connection = get_db_connection()
        if connection is None:
            return jsonify({"error": "Database connection failed"}), 500
        
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, name, email, phone, date, time, service, message, status, created_at
            FROM bookings 
            WHERE id = %s
            LIMIT 1
        """, (booking_id,))
        booking = cursor.fetchone()
        
        cursor.close()
        connection.close()
        
        if booking:
            # Format the booking details for response
            booking_data = {
                "id": booking["id"],
                "name": booking["name"],
                "email": booking["email"],
                "phone": booking["phone"],
                "date": booking["date"],
                "time": booking["time"],
                "service": booking["service"],
                "message": booking["message"],
                "status": booking["status"],
                "created_at": booking["created_at"].strftime('%Y-%m-%d %H:%M:%S')
            }
            
            return jsonify({
                "success": True,
                "booking": booking_data
            })
        else:
            return jsonify({
                "success": False,
                "error": "Booking not found"
            }), 404

    except Exception as e:
        print(f"❌ Error checking booking status: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/cancel-booking", methods=["POST"])
def cancel_booking():
    """Cancel a booking by ID"""
    try:
        data = request.json
        booking_id = data.get("booking_id")
        
        if not booking_id:
            return jsonify({"error": "Booking ID is required"}), 400
        
        connection = get_db_connection()
        if connection is None:
            return jsonify({"error": "Database connection failed"}), 500
        
        cursor = connection.cursor()
        cursor.execute("""
            UPDATE bookings 
            SET status = 'cancelled'
            WHERE id = %s AND status != 'cancelled'
        """, (booking_id,))
        
        if cursor.rowcount == 0:
            cursor.close()
            connection.close()
            return jsonify({
                "success": False,
                "error": "Booking not found or already cancelled"
            }), 404

        connection.commit()
        cursor.close()
        connection.close()

        print(f"✅ Booking #{booking_id} cancelled in MariaDB")

        return jsonify({
            "success": True,
            "message": "Afspraak succesvol geannuleerd"
        })

    except Exception as e:
        print(f"❌ Error cancelling booking: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/reschedule-booking", methods=["POST"])
def reschedule_booking():
    """Reschedule a booking to a new date and/or time"""
    try:
        data = request.json
        booking_id = data.get("booking_id")
        new_date = data.get("date")
        new_time = data.get("time")
        
        if not all([booking_id, new_date, new_time]):
            return jsonify({"error": "Booking ID, new date, and new time are required"}), 400
        
        # Validate new date and time
        try:
            new_booking_date = datetime.strptime(new_date, '%Y-%m-%d').date()
            new_booking_time = datetime.strptime(new_time, '%H:%M').time()
            new_booking_datetime = datetime.combine(new_booking_date, new_booking_time)
        except ValueError:
            return jsonify({"error": "Ongeldige nieuwe datum of tijd"}), 400

        # Don't allow past bookings (including today's past times)
        now = datetime.now()
        if new_booking_datetime <= now:
            return jsonify({"error": "Kan geen afspraak in het verleden maken"}), 400
        
        # Validate business hours
        if not is_valid_time_slot(new_time):
            return jsonify({"error": "Ongeldige nieuwe tijd geselecteerd"}), 400
        
        connection = get_db_connection()
        if connection is None:
            return jsonify({"error": "Database connection failed"}), 500
        
        cursor = connection.cursor()
        
        # Check if new timeslot is available
        cursor.execute("""
            SELECT id FROM bookings 
            WHERE date = %s AND time = %s AND status != 'cancelled'
        """, (new_date, new_time))
        
        if cursor.fetchone():
            cursor.close()
            connection.close()
            return jsonify({"error": "Deze nieuwe tijd is al geboekt. Selecteer een andere tijd."}), 409

        # Update booking with new date and time
        cursor.execute("""
            UPDATE bookings 
            SET date = %s, time = %s, status = 'confirmed'
            WHERE id = %s AND status != 'cancelled'
        """, (new_date, new_time, booking_id))
        
        if cursor.rowcount == 0:
            cursor.close()
            connection.close()
            return jsonify({
                "success": False,
                "error": "Booking not found or already cancelled"
            }), 404

        connection.commit()
        cursor.close()
        connection.close()

        print(f"✅ Booking #{booking_id} rescheduled to {new_date} {new_time} in MariaDB")

        # Prepare rescheduled booking data for emails
        rescheduled_booking_data = {
            'booking_id': booking_id,
            'name': data.get("name"),
            'email': data.get("email"),
            'phone': data.get("phone"),
            'date': new_date,
            'time': new_time,
            'service': data.get("service", "General Service"),
            'message': data.get("message", ""),
            'status': 'confirmed'
        }

        # Send reschedule confirmation emails
        customer_sent, admin_sent = send_booking_emails(rescheduled_booking_data)

        return jsonify({
            "success": True,
            "message": "Afspraak succesvol verplaatst",
            "booking_id": booking_id,
            "email_sent": customer_sent,
            "admin_notified": admin_sent
        })

    except Exception as e:
        print(f"❌ Error rescheduling booking: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/service-info", methods=["POST"])
def get_service_info():
    """Get detailed information about a specific service"""
    try:
        data = request.json
        service_name = data.get("service_name")
        
        if not service_name:
            return jsonify({"error": "Service name is required"}), 400
        
        connection = get_db_connection()
        if connection is None:
            return jsonify({"error": "Database connection failed"}), 500
        
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT * FROM services 
            WHERE name = %s AND active = TRUE
            LIMIT 1
        """, (service_name,))
        service = cursor.fetchone()
        
        cursor.close()
        connection.close()
        
        if service:
            # Format the service details for response
            service_data = {
                "id": service["id"],
                "name": service["name"],
                "description": service["description"],
                "duration": service["duration"],
                "price": service["price"],
                "active": service["active"],
                "created_at": service["created_at"].strftime('%Y-%m-%d %H:%M:%S')
            }
            
            return jsonify({
                "success": True,
                "service": service_data
            })
        else:
            return jsonify({
                "success": False,
                "error": "Service not found"
            }), 404

    except Exception as e:
        print(f"❌ Error fetching service info: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/update-service", methods=["POST"])
def update_service():
    """Update an existing service"""
    try:
        data = request.json
        service_id = data.get("id")
        name = data.get("name")
        description = data.get("description")
        duration = data.get("duration")
        price = data.get("price")
        active = data.get("active")

        if not service_id:
            return jsonify({"error": "Service ID is required"}), 400

        connection = get_db_connection()
        if connection is None:
            return jsonify({"error": "Database connection failed"}), 500
        
        cursor = connection.cursor()
        
        # Check if service exists
        cursor.execute("""
            SELECT id FROM services 
            WHERE id = %s
            LIMIT 1
        """, (service_id,))
        
        if not cursor.fetchone():
            cursor.close()
            connection.close()
            return jsonify({
                "success": False,
                "error": "Service not found"
            }), 404

        # Update service details
        cursor.execute("""
            UPDATE services 
            SET name = %s, description = %s, duration = %s, price = %s, active = %s
            WHERE id = %s
        """, (name, description, duration, price, active, service_id))
        
        connection.commit()
        cursor.close()
        connection.close()

        print(f"✅ Service #{service_id} updated in MariaDB")

        return jsonify({
            "success": True,
            "message": "Service succesvol bijgewerkt"
        })

    except Exception as e:
        print(f"❌ Error updating service: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/add-service", methods=["POST"])
def add_service():
    """Add a new service"""
    try:
        data = request.json
        name = data.get("name")
        description = data.get("description")
        duration = data.get("duration", 60)
        price = data.get("price", 0.00)
        active = data.get("active", True)

        if not name:
            return jsonify({"error": "Service name is required"}), 400

        connection = get_db_connection()
        if connection is None:
            return jsonify({"error": "Database connection failed"}), 500
        
        cursor = connection.cursor()
        
        # Check if service with the same name already exists
        cursor.execute("""
            SELECT id FROM services 
            WHERE name = %s
            LIMIT 1
        """, (name,))
        
        if cursor.fetchone():
            cursor.close()
            connection.close()
            return jsonify({
                "success": False,
                "error": "Service with this name already exists"
            }), 409

        # Insert new service
        cursor.execute("""
            INSERT INTO services (name, description, duration, price, active)
            VALUES (%s, %s, %s, %s, %s)
        """, (name, description, duration, price, active))
        
        service_id = cursor.lastrowid
        connection.commit()
        cursor.close()
        connection.close()

        print(f"✅ New service #{service_id} added to MariaDB")

        return jsonify({
            "success": True,
            "message": "Service succesvol toegevoegd",
            "service_id": service_id
        }), 201

    except Exception as e:
        print(f"❌ Error adding service: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/delete-service", methods=["POST"])
def delete_service():
    """Delete a service by ID"""
    try:
        data = request.json
        service_id = data.get("id")

        if not service_id:
            return jsonify({"error": "Service ID is required"}), 400

        connection = get_db_connection()
        if connection is None:
            return jsonify({"error": "Database connection failed"}), 500
        
        cursor = connection.cursor()
        
        # Check if service exists
        cursor.execute("""
            SELECT id FROM services 
            WHERE id = %s
            LIMIT 1
        """, (service_id,))
        
        if not cursor.fetchone():
            cursor.close()
            connection.close()
            return jsonify({
                "success": False,
                "error": "Service not found"
            }), 404

        # Delete service
        cursor.execute("""
            DELETE FROM services 
            WHERE id = %s
        """, (service_id,))
        
        connection.commit()
        cursor.close()
        connection.close()

        print(f"✅ Service #{service_id} deleted from MariaDB")

        return jsonify({
            "success": True,
            "message": "Service succesvol verwijderd"
        })

    except Exception as e:
        print(f"❌ Error deleting service: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/notifications", methods=["GET"])
def get_notifications():
    """Get notifications for the admin dashboard"""
    try:
        connection = get_db_connection()
        if connection is None:
            return jsonify({"error": "Database connection failed"}), 500
        
        cursor = connection.cursor(dictionary=True)
        
        # Count of new bookings
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM bookings 
            WHERE status = 'pending' AND DATE(created_at) = CURDATE()
        """)
        new_bookings_count = cursor.fetchone().get('count', 0)
        
        # Count of total bookings
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM bookings 
        """)
        total_bookings_count = cursor.fetchone().get('count', 0)
        
        # Count of services offered
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM services 
            WHERE active = TRUE
        """)
        active_services_count = cursor.fetchone().get('count', 0)
        
        # Recent bookings
        cursor.execute("""
            SELECT id, name, email, phone, date, time, service, status, created_at
            FROM bookings 
            ORDER BY created_at DESC
            LIMIT 5
        """)
        recent_bookings = cursor.fetchall()
        
        # Convert datetime objects to strings for JSON serialization
        for booking in recent_bookings:
            if booking['created_at']:
                booking['created_at'] = booking['created_at'].strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.close()
        connection.close()
        
        return jsonify({
            "success": True,
            "new_bookings_count": new_bookings_count,
            "total_bookings_count": total_bookings_count,
            "active_services_count": active_services_count,
            "recent_bookings": recent_bookings
        })
        
    except Error as e:
        print(f"❌ Notifications error: {e}")
        return jsonify({"error": "Failed to fetch notifications"}), 500

@app.route("/api/system-status", methods=["GET"])
def get_system_status():
    """Get the current system status"""
    try:
        # Check database connection
        db_connection = get_db_connection()
        db_status = "connected" if db_connection else "disconnected"
        
        # Check email configuration
        email_status = "valid" if MAIL_USERNAME and MAIL_PASSWORD else "invalid"
        
        # Check if essential environment variables are set
        env_vars = {
            "DB_HOST": os.getenv('DB_HOST'),
            "DB_USER": os.getenv('DB_USER'),
            "DB_NAME": os.getenv('DB_NAME'),
            "MAIL_USERNAME": MAIL_USERNAME,
            "MAIL_PASSWORD": MAIL_PASSWORD,
            "ADMIN_EMAIL": ADMIN_EMAIL
        }
        
        return jsonify({
            "success": True,
            "db_status": db_status,
            "email_status": email_status,
            "env_vars": env_vars
        })
        
    except Exception as e:
        print(f"❌ System status error: {e}")
        return jsonify({"error": "Failed to fetch system status"}), 500

@app.route("/api/test-smtp", methods=["POST"])
def test_smtp():
    """Test SMTP configuration by sending a test email"""
    try:
        data = request.json
        to_email = data.get("to_email")
        
        if not to_email:
            return jsonify({"error": "Recipient email is required"}), 400

        # Test email content
        subject = "Test Email from Koree Autoservice"
        html_body = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Test Email</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background-color: #f4f4f4;
                    margin: 0;
                    padding: 20px;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: white;
                    border-radius: 8px;
                    overflow: hidden;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }}
                .header {{
                    background: linear-gradient(45deg, #FF6B6B, #4ECDC4);
                    color: white;
                    padding: 20px;
                    text-align: center;
                }}
                .content {{
                    padding: 20px;
                }}
                .footer {{
                    background: #2c3e50;
                    color: white;
                    padding: 10px;
                    text-align: center;
                    font-size: 12px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>✅ Test Email Verzonden</h2>
                </div>
                <div class="content">
                    <p>Dit is een testemail van Koree Autoservice om de SMTP-configuratie te verifiëren.</p>
                    <p>Als u deze e-mail ontvangt, betekent dit dat de SMTP-instellingen correct zijn geconfigureerd.</p>
                </div>
                <div class="footer">
                    <p>&copy; 2023 Koree Autoservice. Alle rechten voorbehouden.</p>
                </div>
            </div>
        </body>
        </html>
        """

        # Send test email
        email_sent = send_html_email(to_email, subject, html_body)

        if email_sent:
            return jsonify({
                "success": True,
                "message": "Test email succesvol verzonden"
            })
        else:
            return jsonify({
                "success": False,
                "error": "Failed to send test email"
            }), 500

    except Exception as e:
        print(f"❌ SMTP test error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/logs", methods=["GET"])
def get_logs():
    """Get the latest logs from the server"""
    try:
        # For security, limit log access to admin email
        if request.remote_addr != '127.0.0.1' and request.remote_addr != '::1':
            return jsonify({"error": "Unauthorized access"}), 403
        
        # Read the log file
        log_file = 'koree_autoservice.log'
        with open(log_file, 'r') as file:
            logs = file.readlines()
        
        # Limit to the latest 100 lines
        logs = logs[-100:]
        
        return jsonify({
            "success": True,
            "logs": [log.strip() for log in logs]
        })
        
    except Exception as e:
        print(f"❌ Logs error: {e}")
        return jsonify({"error": "Failed to fetch logs"}), 500

@app.route("/api/clear-logs", methods=["POST"])
def clear_logs():
    """Clear the log file"""
    try:
        # For security, limit log access to admin email
        if request.remote_addr != '127.0.0.1' and request.remote_addr != '::1':
            return jsonify({"error": "Unauthorized access"}), 403
        
        # Clear the log file
        log_file = 'koree_autoservice.log'
        open(log_file, 'w').close()
        
        return jsonify({
            "success": True,
            "message": "Logs succesvol gewist"
        })

    except Exception as e:
        print(f"❌ Clear logs error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/backup-db", methods=["POST"])
def backup_database():
    """Backup the database to a SQL file"""
    try:
        # For security, limit backup access to admin email
        if request.remote_addr != '127.0.0.1' and request.remote_addr != '::1':
            return jsonify({"error": "Unauthorized access"}), 403
        
        # Backup file name with timestamp
        backup_file = f"backup/koree_autoservice_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
        
        # Create backup directory if not exists
        os.makedirs(os.path.dirname(backup_file), exist_ok=True)
        
        # Dump the database to the backup file
        os.system(f"mysqldump -u {DB_CONFIG['user']} -p{DB_CONFIG['password']} -h {DB_CONFIG['host']} --port={DB_CONFIG['port']} {DB_CONFIG['database']} > {backup_file}")
        
        return jsonify({
            "success": True,
            "message": "Database backup succesvol gemaakt",
            "backup_file": backup_file
        })

    except Exception as e:
        print(f"❌ Backup database error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/restore-db", methods=["POST"])
def restore_database():
    """Restore the database from a SQL file"""
    try:
        # For security, limit restore access to admin email
        if request.remote_addr != '127.0.0.1' and request.remote_addr != '::1':
            return jsonify({"error": "Unauthorized access"}), 403
        
        data = request.json
        backup_file = data.get("backup_file")
        
        if not backup_file:
            return jsonify({"error": "Backup file is required"}), 400

        # Restore the database from the backup file
        os.system(f"mysql -u {DB_CONFIG['user']} -p{DB_CONFIG['password']} -h {DB_CONFIG['host']} --port={DB_CONFIG['port']} {DB_CONFIG['database']} < {backup_file}")
        
        return jsonify({
            "success": True,
            "message": "Database herstel succesvol uitgevoerd"
        })

    except Exception as e:
        print(f"❌ Restore database error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/optimize-db", methods=["POST"])
def optimize_database():
    """Optimize the database tables"""
    try:
        # For security, limit optimize access to admin email
        if request.remote_addr != '127.0.0.1' and request.remote_addr != '::1':
            return jsonify({"error": "Unauthorized access"}), 403
        
        connection = get_db_connection()
        if connection is None:
            return jsonify({"error": "Database connection failed"}), 500
        
        cursor = connection.cursor()
        
        # Optimize all tables in the database
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        
        for table in tables:
            table_name = table[0]
            cursor.execute(f"OPTIMIZE TABLE {table_name}")
            print(f"✅ Optimized table: {table_name}")
        
        connection.commit()
        cursor.close()
        connection.close()

        return jsonify({
            "success": True,
            "message": "Database optimalisatie succesvol uitgevoerd"
        })

    except Exception as e:
        print(f"❌ Optimize database error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/check-updates", methods=["GET"])
def check_updates():
    """Check for software updates"""
    try:
        # For now, just return the current version
        current_version = "1.0.0"
        
        return jsonify({
            "success": True,
            "current_version": current_version,
            "latest_version": current_version,  # Assume latest version is the same for now
            "update_available": False
        })

    except Exception as e:
        print(f"❌ Check updates error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/download-update", methods=["POST"])
def download_update():
    """Download and install software update"""
    try:
        # For security, limit update access to admin email
        if request.remote_addr != '127.0.0.1' and request.remote_addr != '::1':
            return jsonify({"error": "Unauthorized access"}), 403
        
        # Simulate download and installation
        import time
        time.sleep(2)  # Simulate time delay for download
        
        return jsonify({
            "success": True,
            "message": "Update succesvol gedownload en geïnstalleerd"
        })

    except Exception as e:
        print(f"❌ Download update error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/reboot-server", methods=["POST"])
def reboot_server():
    """Reboot the server (simulated)"""
    try:
        # For security, limit reboot access to admin email
        if request.remote_addr != '127.0.0.1' and request.remote_addr != '::1':
            return jsonify({"error": "Unauthorized access"}), 403
        
        # Simulate server reboot
        import time
        time.sleep(2)  # Simulate time delay for reboot
        
        return jsonify({
            "success": True,
            "message": "Server succesvol opnieuw opgestart"
        })

    except Exception as e:
        print(f"❌ Reboot server error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/shutdown-server", methods=["POST"])
def shutdown_server():
    """Shutdown the server (simulated)"""
    try:
        # For security, limit shutdown access to admin email
        if request.remote_addr != '127.0.0.1' and request.remote_addr != '::1':
            return jsonify({"error": "Unauthorized access"}), 403
        
        # Simulate server shutdown
        import time
        time.sleep(2)  # Simulate time delay for shutdown
        
        return jsonify({
            "success": True,
            "message": "Server succesvol afgesloten"
        })

    except Exception as e:
        print(f"❌ Shutdown server error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/test-endpoint", methods=["GET"])
def test_endpoint():
    """A test endpoint to check server response"""
    return jsonify({
        "success": True,
        "message": "API is working correctly",
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

# Error handler for 404 - Not Found
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "success": False,
        "error": "Not found",
        "message": "The requested resource was not found"
    }), 404

# Error handler for 500 - Internal Server Error
@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "success": False,
        "error": "Internal server error",
        "message": "An unexpected error occurred on the server"
    }), 500

# Global error handler
@app.errorhandler(Exception)
def handle_exception(e):
    """Handle all uncaught exceptions"""
    print(f"❌ Uncaught exception: {str(e)}")
    return jsonify({
        "success": False,
        "error": "Internal server error",
        "message": "An unexpected error occurred"
    }), 500

@app.route("/test/times")
def test_times():
    """Test available times for debugging"""
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    
    try:
        # Call the actual logic directly, not the Flask route
        connection = get_db_connection()
        if connection is None:
            return "<h2>Database Error</h2><p>Cannot connect to database</p>"
        
        cursor = connection.cursor()
        cursor.execute("""
            SELECT time FROM bookings 
            WHERE date = %s AND status != 'cancelled'
        """, (date,))
        
        booked_times_raw = cursor.fetchall()
        booked_times = []
        
        # Handle both timedelta and time objects
        for row in booked_times_raw:
            time_value = row[0]
            if isinstance(time_value, timedelta):
                # Convert timedelta to time string
                total_seconds = int(time_value.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                time_str = f"{hours:02d}:{minutes:02d}"
            else:
                # It's already a time object
                time_str = time_value.strftime('%H:%M')
            
            booked_times.append(time_str)
        
        cursor.close()
        connection.close()
        
        # Generate time slots
        all_time_slots = generate_time_slots()
        available_times = []
        
        for time_slot in all_time_slots:
            if time_slot['value'] not in booked_times:
                available_times.append(time_slot)
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Time Slots Debug</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                pre {{ background: #f4f4f4; padding: 15px; border-radius: 5px; }}
                .available {{ color: green; font-weight: bold; }}
                .booked {{ color: red; text-decoration: line-through; }}
            </style>
        </head>
        <body>
            <h2>Time Slots Debug for {date}</h2>
            
            <h3>All Time Slots:</h3>
            <ul>
                {''.join([f'<li class="{"available" if slot["value"] not in booked_times else "booked"}">{slot["value"]} - {"Available" if slot["value"] not in booked_times else "BOOKED"}</li>' for slot in all_time_slots])}
            </ul>
            
            <h3>Statistics:</h3>
            <p><strong>Total Slots:</strong> {len(all_time_slots)}</p>
            <p><strong>Available:</strong> {len(available_times)}</p>
            <p><strong>Booked:</strong> {len(booked_times)}</p>
            <p><strong>Booked Times:</strong> {', '.join(booked_times) if booked_times else 'None'}</p>
            
            <h3>Direct API Test:</h3>
            <p><a href="/api/available-times?date={date}" target="_blank">Test API: /api/available-times?date={date}</a></p>
            
            <h3>Test All Days (Including Sunday):</h3>
            <ul>
                <li><a href="/test/times?date=2025-08-31">2025-08-31 (Sunday)</a></li>
                <li><a href="/test/times?date=2025-09-01">2025-09-01 (Monday)</a></li>
                <li><a href="/test/times?date=2025-09-02">2025-09-02 (Tuesday)</a></li>
            </ul>
        </body>
        </html>
        """
    except Exception as e:
        return f"<h2>Error:</h2><pre>{str(e)}</pre>"

@app.route("/test/email-debug")
def test_email_debug():
    """Debug email configuration"""
    try:
        return f"""
        <h2>Email Configuration Debug</h2>
        <table border="1" style="border-collapse: collapse;">
            <tr><th>Setting</th><th>Value</th><th>Status</th></tr>
            <tr><td>MAIL_USERNAME</td><td>{MAIL_USERNAME}</td><td>{'✅' if MAIL_USERNAME else '❌'}</td></tr>
            <tr><td>MAIL_PASSWORD</td><td>{'*' * len(MAIL_PASSWORD) if MAIL_PASSWORD else 'None'}</td><td>{'✅' if MAIL_PASSWORD else '❌'}</td></tr>
            <tr><td>MAIL_SERVER</td><td>{MAIL_SERVER}</td><td>{'✅' if 'secureserver' in MAIL_SERVER else '❌'}</td></tr>
            <tr><td>MAIL_PORT</td><td>{MAIL_PORT}</td><td>{'✅' if MAIL_PORT == 587 else '❌'}</td></tr>
            <tr><td>ADMIN_EMAIL</td><td>{ADMIN_EMAIL}</td><td>{'✅' if ADMIN_EMAIL else '❌'}</td></tr>
        </table>
        
        <h3>Environment File Check:</h3>
        <pre>
MAIL_USERNAME from .env: {os.getenv('MAIL_USERNAME')}
MAIL_PASSWORD from .env: {'*' * len(os.getenv('MAIL_PASSWORD', '')) if os.getenv('MAIL_PASSWORD') else 'None'}
MAIL_SERVER from .env: {os.getenv('MAIL_SERVER')}
MAIL_PORT from .env: {os.getenv('MAIL_PORT')}
        </pre>
        
        <h3>Recommendations:</h3>
        <ul>
            <li>MAIL_SERVER should be: smtpout.secureserver.net</li>
            <li>MAIL_PORT should be: 587</li>
            <li>Make sure .env file has no quotes around password</li>
            <li>Test your email login at: <a href="https://outlook.office365.com" target="_blank">https://outlook.office365.com</a></li>
        </ul>
        
        <p><a href="/test/email-send">Test Send Email</a></p>
        """
    except Exception as e:
        return f"Error: {str(e)}"

@app.route("/test/email-send")
def test_email_send():
    """Test email sending"""
    try:
        test_subject = "Test Email - Koree Autoservice"
        test_body = """
        <h2>Test Email</h2>
        <p>This is a test email from your Koree Autoservice booking system.</p>
        <p>If you receive this, your email configuration is working correctly!</p>
        <p>Time: {}</p>
        """.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        # Try to send test email
        result = send_html_email(
            to_email=ADMIN_EMAIL,
            subject=test_subject,
            html_body=test_body
        )
        
        if result:
            return "<h2>✅ Test Email Sent Successfully!</h2><p>Check your inbox at: " + ADMIN_EMAIL + "</p>"
        else:
            return "<h2>❌ Test Email Failed</h2><p>Check the console for error details.</p>"
            
    except Exception as e:
        return f"<h2>❌ Error:</h2><pre>{str(e)}</pre>"

def validate_email_config():
    """Validate email configuration"""
    if not all([MAIL_USERNAME, MAIL_PASSWORD]):
        print("⚠️  Email configuration incomplete - emails will be disabled")
        return False
    
    print(f"✅ Email configured for: {MAIL_USERNAME}")
    return True

def test_database_connection():
    """Test database connection on startup"""
    print("🔧 Testing MariaDB connection...")
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor()
        cursor.execute("SELECT VERSION()")
        version = cursor.fetchone()
        cursor.close()
        connection.close()
        print(f"✅ MariaDB connection successful! Version: {version[0]}")
        return True
    else:
        print("❌ MariaDB connection failed!")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 Starting Koree Autoservice Booking System")
    print("=" * 50)
    
    # Validate email configuration
    validate_email_config()
    
    # Test database connection
    if test_database_connection():
        # Initialize database
        print("🔧 Initializing database...")
        if init_db():
            print("✅ Database ready!")
            print()
            print("🚀 Starting Flask application...")
            print("📊 Admin panel: http://localhost:5000/admin/bookings")
            print("🌐 Website: http://localhost:5000")
            print("🔧 API test: http://localhost:5000/api/available-times?date=2025-08-29")
            print("🧪 Debug routes:")
            print("   - http://localhost:5000/test/email-debug")
            print("   - http://localhost:5000/test/times")
            print("=" * 50)
            
            # Start Flask app
            app.run(debug=True, host="0.0.0.0", port=5000)
        else:
            print("❌ Database initialization failed!")
    else:
        print("❌ Cannot start - database connection failed!")
        print("💡 Make sure XAMPP MySQL/MariaDB is running")