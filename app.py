from flask import Flask, render_template, request, url_for, jsonify
import sqlite3
import smtplib
import requests
from email.message import EmailMessage
from datetime import datetime, timedelta
import json
import os

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = 'your-secret-key-here'

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
            return jsonify({"error": "Deze tijd is al geboekt"}), 409

        # Save booking
        c.execute("""
            INSERT INTO bookings (name, email, phone, date, time, service, message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, email, phone, date, time, service, message))
        
        booking_id = c.lastrowid
        conn.commit()
        conn.close()

        return jsonify({
            "message": "Afspraak succesvol geboekt!",
            "booking_id": booking_id
        }), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
                
                # Prepare response data
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
    init_db()
    app.run(debug=True)