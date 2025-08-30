from flask import Flask, render_template, request, url_for, jsonify
import sqlite3
import smtplib
import requests
from email.message import EmailMessage
from datetime import datetime, timedelta
import json
import os  # ← ADD THIS MISSING IMPORT!
from dotenv import load_dotenv

# Load environment variables (AWS will provide these, not .env file)
load_dotenv()

# Ensure Flask app instance
app = Flask(__name__)

# Configuration - AWS will provide these via environment variables
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# IMPROVE DATABASE CONFIGURATION:
# Database Configuration for SQLite - AWS path with fallback
if os.environ.get('AWS_EXECUTION_ENV'):
    # Running on AWS
    DB_FILE = '/var/app/current/koree_autoservice.db'
    print("🌟 AWS Environment detected - using AWS database path")
elif os.environ.get('DB_FILE'):
    # Custom environment variable
    DB_FILE = os.environ.get('DB_FILE')
    print(f"🔧 Using custom database path: {DB_FILE}")
else:
    # Local development
    DB_FILE = 'koree_autoservice.db'
    print("💻 Local development - using local database path")

print(f"📊 Database file: {DB_FILE}")

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
    return render_template("index.html")

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

def ensure_database_initialized():
    """Ensure database is initialized on every app startup (AWS compatible)"""
    try:
        print("🔧 Ensuring database is initialized for AWS...")
        
        # Check if database file exists and is accessible
        db_dir = os.path.dirname(DB_FILE)
        if db_dir and not os.path.exists(db_dir):
            print(f"📁 Creating database directory: {db_dir}")
            os.makedirs(db_dir, exist_ok=True)
        
        # Test database connection
        connection = get_db_connection()
        if connection is None:
            print("❌ Database connection failed - initializing...")
            return init_db()
        
        cursor = connection.cursor()
        
        # Check if required tables exist
        cursor.execute("""
            SELECT name FROM sqlite_master WHERE type='table' AND name IN ('bookings', 'services')
        """)
        tables = cursor.fetchall()
        
        if len(tables) < 2:
            print("❌ Required tables are missing - initializing database...")
            return init_db()
        else:
            print("✅ Required tables exist")
        
        cursor.close()
        connection.close()
        return True
    
    except Exception as e:
        print(f"❌ Database initialization error: {e}")
        return False

# Ensure database is initialized on startup
ensure_database_initialized()

# Test database connection on startup
test_database_connection()