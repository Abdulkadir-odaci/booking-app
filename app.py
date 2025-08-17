from flask import Flask, render_template, request, url_for, jsonify
import sqlite3
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

# Email Configuration (SAFE - from environment variables)
MAIL_USERNAME = os.getenv('MAIL_USERNAME')
MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp-mail.outlook.com')
MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL')

def send_booking_emails(booking_data):
    """Send confirmation emails to both customer and admin"""
    try:
        # Customer confirmation email
        customer_subject = "✅ Afspraak Bevestiging - Koree Autoservice"
        customer_body = f"""
Beste {booking_data['name']},

Uw afspraak bij Koree Autoservice is bevestigd!

📅 Afspraak Details:
• Naam: {booking_data['name']}
• Email: {booking_data['email']}
• Telefoon: {booking_data.get('phone', 'Niet opgegeven')}
• Service: {booking_data['service']}
• Datum: {booking_data['date']}
• Tijd: {booking_data['time']}
• Bericht: {booking_data.get('message', 'Geen specifieke wensen')}

📍 Onze Locatie:
Koree Autoservice
Fenacoliuslaan 60-64
3143 AE Maassluis
Telefoon: +31 6 23967989

⚠️ Belangrijk:
• Kom 10 minuten voor uw afspraak
• Neem uw rijbewijs en autopapieren mee
• Bij annulering, bel minimaal 24 uur van tevoren

Voor vragen kunt u contact opnemen via:
📞 +31 6 23967989
📧 info@koreeautoservices.nl
💬 WhatsApp: https://wa.me/31623967989

Met vriendelijke groet,
Team Koree Autoservice
        """

        # Admin notification email
        admin_subject = f"🔔 Nieuwe Afspraak - {booking_data['name']} op {booking_data['date']}"
        admin_body = f"""
Nieuwe afspraak boeking ontvangen:

👤 Klant Informatie:
• Naam: {booking_data['name']}
• Email: {booking_data['email']}
• Telefoon: {booking_data.get('phone', 'Niet opgegeven')}

📅 Afspraak Details:
• Service: {booking_data['service']}
• Datum: {booking_data['date']}
• Tijd: {booking_data['time']}
• Bericht: {booking_data.get('message', 'Geen specifieke wensen')}

🕐 Geboekt op: {datetime.now().strftime('%d-%m-%Y om %H:%M')}

Booking ID: {booking_data.get('booking_id', 'N/A')}
        """

        # Send customer email
        customer_sent = send_email(
            to_email=booking_data['email'],
            subject=customer_subject,
            body=customer_body
        )

        # Send admin email
        admin_sent = send_email(
            to_email=ADMIN_EMAIL,
            subject=admin_subject,
            body=admin_body
        )

        return customer_sent, admin_sent

    except Exception as e:
        print(f"❌ Email sending error: {str(e)}")
        return False, False

def send_email(to_email, subject, body):
    """Send email using Outlook SMTP"""
    try:
        if not all([MAIL_USERNAME, MAIL_PASSWORD, to_email]):
            print("❌ Missing email configuration")
            return False

        # Create email message
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = f"Koree Autoservice <{MAIL_USERNAME}>"
        msg['To'] = to_email
        msg.set_content(body)

        # Send email using Outlook SMTP
        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as server:
            server.starttls()
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.send_message(msg)

        print(f"✅ Email sent successfully to {to_email}")
        return True

    except Exception as e:
        print(f"❌ Email error: {str(e)}")
        return False

def init_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS bookings 
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         name TEXT NOT NULL,
         email TEXT NOT NULL,
         phone TEXT,
         date TEXT NOT NULL,
         time TEXT NOT NULL,
         service TEXT,
         message TEXT,
         status TEXT DEFAULT 'pending',
         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
    """)
    
    # Add services table
    c.execute("""
        CREATE TABLE IF NOT EXISTS services
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         name TEXT NOT NULL,
         description TEXT,
         duration INTEGER)
    """)
    
    # Insert default services if they don't exist
    c.execute("SELECT COUNT(*) FROM services")
    if c.fetchone()[0] == 0:
        services = [
            ('APK Keuring', 'Volledige APK keuring voor uw voertuig', 60),
            ('Onderhoudsbeurt', 'Complete onderhoudsbeurt volgens fabrieksspecificaties', 120),
            ('Banden Service', 'Bandenwissel en uitbalanceren', 45),
            ('Airco Service', 'Airconditioning service en vulling', 90),
            ('Reparaties', 'Algemene reparaties aan uw voertuig', 180),
            ('Diagnose', 'Computudiagnose van motorproblemen', 30)
        ]
        c.executemany("INSERT INTO services (name, description, duration) VALUES (?, ?, ?)", services)
    
    conn.commit()
    conn.close()

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/services", methods=["GET"])
def get_services():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT * FROM services ORDER BY name")
    services = []
    for row in c.fetchall():
        services.append({
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "duration": row[3]
        })
    conn.close()
    return jsonify({"services": services})

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

        # Validate future date
        booking_date = datetime.strptime(date, '%Y-%m-%d')
        if booking_date.date() < datetime.now().date():
            return jsonify({"error": "Datum moet in de toekomst liggen"}), 400

        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        
        # Check if timeslot is available
        c.execute("SELECT id FROM bookings WHERE date = ? AND time = ? AND status != 'cancelled'", (date, time))
        if c.fetchone():
            conn.close()
            return jsonify({"error": "Deze tijd is al geboekt"}), 409

        # Save booking
        c.execute("""
            INSERT INTO bookings (name, email, phone, date, time, service, message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, email, phone, date, time, service, message))
        
        booking_id = c.lastrowid
        conn.commit()
        conn.close()

        # Prepare booking data for emails
        booking_data = {
            'booking_id': booking_id,
            'name': name,
            'email': email,
            'phone': phone,
            'date': date,
            'time': time,
            'service': service,
            'message': message
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

if __name__ == "__main__":
    # Check if email is configured
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        print("⚠️  WARNING: Email not configured. Add credentials to .env file")
    else:
        print(f"✅ Email configured for: {MAIL_USERNAME}")
    
    init_db()
    app.run(debug=True)