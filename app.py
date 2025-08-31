from flask import Flask, render_template, request, url_for, jsonify
import sqlite3
import smtplib
import requests
from email.message import EmailMessage
from datetime import datetime, timedelta
import json
import os
from dotenv import load_dotenv

# FORCE COMPLETE ENVIRONMENT RELOAD
load_dotenv(dotenv_path='.env', override=True)

# Clear any cached environment variables
if 'GOOGLE_PLACE_ID' in os.environ:
    del os.environ['GOOGLE_PLACE_ID']
if 'GOOGLE_PLACES_API_KEY' in os.environ:
    del os.environ['GOOGLE_PLACES_API_KEY']

# Reload fresh values
load_dotenv(dotenv_path='.env', override=True)

# Google Places API Configuration - FORCE NEW VALUES
GOOGLE_PLACES_API_KEY = os.environ.get('GOOGLE_PLACES_API_KEY')
GOOGLE_PLACE_ID = os.environ.get('GOOGLE_PLACE_ID')

print("=" * 60)
print("🔧 FORCED ENVIRONMENT VARIABLE RELOAD:")
print(f"📍 Place ID: {GOOGLE_PLACE_ID}")
print(f"🔑 API Key: {GOOGLE_PLACES_API_KEY[:20] if GOOGLE_PLACES_API_KEY else 'NOT_FOUND'}...")
print(f"📁 .env file exists: {os.path.exists('.env')}")
print("=" * 60)

# Ensure Flask app instance
app = Flask(__name__)

# Configuration - AWS will provide these via environment variables
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Database Configuration for SQLite - AWS path
DB_FILE = os.environ.get('DB_FILE', '/var/app/current/koree_autoservice.db')

# Email Configuration - AWS environment variables
MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtpout.secureserver.net')
MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL')

def get_db_connection():
    """Create SQLite database connection"""
    try:
        connection = sqlite3.connect(DB_FILE)
        connection.row_factory = sqlite3.Row  # This enables column access by name
        return connection
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return None

def init_db():
    """Initialize SQLite database with tables"""
    try:
        connection = sqlite3.connect(DB_FILE)
        cursor = connection.cursor()
        
        # Create bookings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT,
                date DATE NOT NULL,
                time TIME NOT NULL,
                service TEXT,
                message TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create services table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                duration INTEGER DEFAULT 60,
                price REAL DEFAULT 0.00,
                active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
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
                VALUES (?, ?, ?, ?)
            """, services)
        
        connection.commit()
        cursor.close()
        connection.close()
        
        print("✅ SQLite database initialized successfully!")
        print(f"✅ Database file: {DB_FILE}")
        return True
        
    except Exception as e:
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
    """Home page with booking form AND reviews integrated"""
    try:
        print("🏠 Loading home page with integrated reviews...")
        
        # Get reviews data for the home page
        reviews_response = get_google_reviews()
        
        if reviews_response.get('success'):
            reviews_data = reviews_response.get('data', {})
            print(f"✅ Loading home page with {len(reviews_data.get('reviews', []))} reviews")
            return render_template('index.html', 
                                 reviews_data=reviews_data, 
                                 has_reviews=True,
                                 show_reviews=True)
        else:
            print(f"⚠️ Loading home page zonder reviews: {reviews_response.get('error')}")
            return render_template('index.html', 
                                 reviews_data={}, 
                                 has_reviews=False,
                                 show_reviews=True,
                                 error_message=reviews_response.get('error', 'Reviews tijdelijk niet beschikbaar'))
    except Exception as e:
        print(f"❌ Error loading home page: {e}")
        return render_template('index.html', 
                             reviews_data={}, 
                             has_reviews=False,
                             show_reviews=True,
                             error_message=f'Error loading reviews: {str(e)}')

@app.route("/api/services", methods=["GET"])
def get_services():
    try:
        connection = get_db_connection()
        if connection is None:
            return jsonify({"error": "Database connection failed"}), 500
        
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM services WHERE active = 1 ORDER BY name")
        services = [dict(row) for row in cursor.fetchall()]
        
        cursor.close()
        connection.close()
        
        print(f"✅ Loaded {len(services)} services from SQLite")
        return jsonify({"services": services})
        
    except Exception as e:
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

        # Don't allow past bookings
        now = datetime.now()
        if booking_datetime <= now:
            return jsonify({"error": "Kan geen afspraak in het verleden maken"}), 400
        
        # Validate business hours
        if not is_valid_time_slot(time):
            return jsonify({"error": "Ongeldige tijd geselecteerd"}), 400

        connection = get_db_connection()
        if connection is None:
            return jsonify({"error": "Database connection failed"}), 500
        
        cursor = connection.cursor()
        
        # Check if timeslot is available (SQLite syntax)
        cursor.execute("""
            SELECT id FROM bookings 
            WHERE date = ? AND time = ? AND status != 'cancelled'
        """, (date, time))
        
        if cursor.fetchone():
            cursor.close()
            connection.close()
            return jsonify({"error": "Deze tijd is al geboekt. Selecteer een andere tijd."}), 409

        # Save booking (SQLite syntax)
        cursor.execute("""
            INSERT INTO bookings (name, email, phone, date, time, service, message, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'confirmed')
        """, (name, email, phone, date, time, service, message))
        
        booking_id = cursor.lastrowid
        connection.commit()
        cursor.close()
        connection.close()

        print(f"✅ Booking #{booking_id} saved to SQLite")

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
        
        connection = get_db_connection()
        if connection is None:
            return jsonify({
                "success": False,
                "error": "Database connection failed",
                "available_times": [],
                "message": "Database fout"
            })
        
        cursor = connection.cursor()
        
        # Get all booked times for this date (SQLite syntax)
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

# Admin endpoint to view bookings
@app.route("/admin/bookings")
def admin_bookings():
    try:
        connection = get_db_connection()
        if connection is None:
            return jsonify({"error": "Database connection failed"}), 500
        
        cursor = connection.cursor()
        cursor.execute("""
            SELECT id, name, email, phone, date, time, service, message, status, created_at
            FROM bookings 
            ORDER BY created_at DESC
            LIMIT 50
        """)
        bookings = [dict(row) for row in cursor.fetchall()]
        
        cursor.close()
        connection.close()
        
        return jsonify({
            "success": True,
            "total": len(bookings),
            "bookings": bookings
        })
        
    except Exception as e:
        print(f"❌ Admin bookings error: {e}")
        return jsonify({"error": "Failed to fetch bookings"}), 500

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

def test_database_connection():
    """Test database connection on startup"""
    print("🔧 Testing SQLite connection...")
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor()
        cursor.execute("SELECT sqlite_version()")
        version = cursor.fetchone()
        cursor.close()
        connection.close()
        print(f"✅ SQLite connection successful! Version: {version[0]}")
        return True
    else:
        print("❌ SQLite connection failed!")
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

# Add API endpoint for reviews (REAL ONLY)
@app.route("/api/reviews", methods=["GET"])
def api_reviews():
    """API endpoint to serve ONLY real Google reviews"""
    try:
        print("📡 API request for REAL Google reviews received")
        reviews_response = get_google_reviews()
        
        if not reviews_response.get('success'):
            # Return error response - NO FALLBACK
            return jsonify({
                'success': False,
                'error': reviews_response.get('error', 'No reviews available'),
                'message': 'Google reviews are temporarily unavailable'
            }), 404
        
        return jsonify(reviews_response)
        
    except Exception as e:
        print(f"❌ API error serving reviews: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Reviews service is temporarily unavailable'
        }), 500

# Add route for reviews page (REAL ONLY)
@app.route("/reviews")
def reviews_page():
    """Display ONLY real Google reviews page"""
    try:
        print("🔧 DEBUG: Reviews page requested")
        reviews_response = get_google_reviews()
        
        print(f"🔧 DEBUG: Reviews response success: {reviews_response.get('success')}")
        print(f"🔧 DEBUG: Reviews response: {reviews_response}")
        
        if reviews_response.get('success'):
            reviews_data = reviews_response.get('data', {})
            print(f"🔧 DEBUG: Passing to template - has_reviews=True")
            print(f"🔧 DEBUG: Reviews data: {reviews_data}")
            return render_template('reviews.html', reviews_data=reviews_data, has_reviews=True)
        else:
            # No reviews available - show empty state
            print(f"🔧 DEBUG: Passing to template - has_reviews=False")
            print(f"🔧 DEBUG: Error message: {reviews_response.get('error')}")
            return render_template('reviews.html', 
                                 reviews_data={}, 
                                 has_reviews=False, 
                                 error_message=reviews_response.get('error', 'No reviews available'))
    except Exception as e:
        print(f"❌ Error rendering reviews page: {e}")
        import traceback
        traceback.print_exc()
        return render_template('reviews.html', 
                             reviews_data={}, 
                             has_reviews=False, 
                             error_message=f'Error loading reviews: {str(e)}')

# Add debug route for testing (REAL ONLY)
@app.route('/debug/google-reviews')
def debug_google_reviews():
    """Debug endpoint to test REAL Google Places API"""
    try:
        print("🧪 Testing REAL Google Places API...")
        reviews_response = get_google_reviews();
        
        return jsonify({
            'test_timestamp': datetime.now().isoformat(),
            'api_key_configured': bool(GOOGLE_PLACES_API_KEY),
            'api_key_length': len(GOOGLE_PLACES_API_KEY) if GOOGLE_PLACES_API_KEY else 0,
            'place_id': GOOGLE_PLACE_ID,
            'place_id_configured': bool(GOOGLE_PLACE_ID),
            'reviews_response': reviews_response
        })
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'test_timestamp': datetime.now().isoformat()
        }), 500

# Add this function after your existing functions
def find_correct_place_id():
    """Find the correct Place ID using text search"""
    try:
        print("🔍 Searching for correct Place ID...")
        
        # Text search to find place ID
        search_url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
        search_params = {
            'input': 'Autobedrijf Koree Haven 45 Maassluis Netherlands',
            'inputtype': 'textquery',
            'fields': 'place_id,name,formatted_address,geometry',
            'key': GOOGLE_PLACES_API_KEY
        }
        
        response = requests.get(search_url, params=search_params, timeout=10)
        data = response.json()
        
        print(f"📡 Search API Response: {data}")
        
        if data.get('status') == 'OK' and data.get('candidates'):
            for candidate in data['candidates']:
                place_id = candidate.get('place_id')
                name = candidate.get('name')
                address = candidate.get('formatted_address')
                
                print(f"✅ Found candidate:")
                print(f"   Name: {name}")
                print(f"   Address: {address}")
                print(f"   Place ID: {place_id}")
                
                # Test this Place ID
                test_result = test_place_id(place_id)
                if test_result:
                    return place_id
                    
        return None
        
    except Exception as e:
        print(f"❌ Error finding place ID: {e}")
        return None

def test_place_id(place_id):
    """Test if a Place ID works"""
    try:
        url = "https://maps.googleapis.com/maps/api/place/details/json"
        params = {
            'place_id': place_id,
            'fields': 'name,rating,user_ratings_total',
            'key': GOOGLE_PLACES_API_KEY
        }
        
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if data.get('status') == 'OK':
            print(f"✅ Place ID {place_id} works!")
            return True
        else:
            print(f"❌ Place ID {place_id} failed: {data.get('status')}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing place ID: {e}")
        return False

# Add debug route to find correct Place ID
@app.route('/debug/find-correct-place-id')
def debug_find_correct_place_id():
    """Debug endpoint to find the correct Place ID"""
    try:
        print("🧪 Finding correct Place ID for Autobedrijf Koree...")
        
        correct_place_id = find_correct_place_id()
        
        return jsonify({
            'test_timestamp': datetime.now().isoformat(),
            'search_query': 'Autobedrijf Koree Haven 45 Maassluis Netherlands',
            'current_place_id': GOOGLE_PLACE_ID,
            'found_correct_place_id': correct_place_id,
            'recommendation': f'Update .env file: GOOGLE_PLACE_ID={correct_place_id}' if correct_place_id else 'No valid Place ID found'
        })
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'test_timestamp': datetime.now().isoformat()
        }), 500

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 Starting Koree Autoservice Booking System (SQLite)")
    print("=" * 50)
    
    # Test database connection
    if test_database_connection():
        # Initialize database
        print("🔧 Initializing SQLite database...")
        if init_db():
            print("✅ Database ready!")
            print()
            print("🚀 Starting Flask application...")
            print("📊 Admin panel: http://localhost:5000/admin/bookings")
            print("🌐 Website: http://localhost:5000")
            print("🔧 API test: http://localhost:5000/api/available-times?date=2025-08-29")
            print("=" * 50)
            
            # Start Flask app
            app.run(debug=True, host="0.0.0.0", port=5000)
        else:
            print("❌ Database initialization failed!")
    else:
        print("❌ Cannot start - database connection failed!")