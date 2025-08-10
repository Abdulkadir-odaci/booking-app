# Koree Autoservice Booking App

A modern Flask web application for automotive service bookings with real-time Google Reviews integration.

## Features

- 🚗 Online appointment booking system
- ⭐ Real-time Google Reviews (last 2 years)
- 📱 WhatsApp integration
- 🎨 Modern responsive design
- 🗺️ Google Maps integration
- 📊 Local Guide detection

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/booking-app.git
cd booking-app
```

2. Install dependencies:
```bash
pip install flask requests
```

3. Run the application:
```bash
python app.py
```

4. Open your browser and go to `http://localhost:5000`

## Project Structure

```
booking_app/
├── app.py                 # Main Flask application
├── database.db            # SQLite database
├── templates/
│   └── index.html         # Main HTML template
├── static/
│   ├── css/
│   │   └── style.css      # Custom styles
│   └── js/
│       └── reviews.js     # Reviews functionality
└── README.md
```

## Configuration

- Update Google Maps API key in `app.py`
- Modify business name and location in the reviews API call
- Customize colors in `style.css` to match your branding

## License

This project is licensed under the MIT License.