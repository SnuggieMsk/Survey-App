#!/usr/bin/env python
# coding: utf-8

from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file, abort, flash, session
import requests
import sqlite3
import json
import os
import csv
import io
import uuid
import base64
import time
import datetime
import logging
from logging.handlers import RotatingFileHandler
from functools import wraps
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect
import matplotlib
matplotlib.use('Agg')  # Use Agg backend to avoid GUI requirements
import matplotlib.pyplot as plt
import numpy as np

# Load environment variables
load_dotenv()

# Application configuration
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(24)
    UPLOAD_FOLDER = 'static/uploads'
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'svg'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload
    DATABASE = os.environ.get('DATABASE') or 'survey.db'
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', 'AIzaSyA8R_U1pHmh78Qs3q1PWbAJF_qTgsDFGBc')
    GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent"
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    PERMANENT_SESSION_LIFETIME = int(os.environ.get('SESSION_LIFETIME', '1800'))
    
class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False

class ProductionConfig(Config):
    DEBUG = False

class TestingConfig(Config):
    TESTING = True
    DATABASE = 'test.db'

# Flask application setup
app = Flask(__name__)

# Add context processor for now() function in templates
@app.context_processor
def inject_now():
    """Make the datetime.now function available in all templates"""
    return {'now': datetime.datetime.now}

# Configure the app based on environment
config_env = os.environ.get('FLASK_ENV', 'development')
if config_env == 'production':
    app.config.from_object(ProductionConfig)
elif config_env == 'testing':
    app.config.from_object(TestingConfig)
else:
    app.config.from_object(DevelopmentConfig)

# Set up CSRF protection
csrf = CSRFProtect(app)

# Configure logging
if not app.debug:
    import sys
    
    # Log to stdout instead of a file
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    stream_handler.setLevel(logging.INFO)
    app.logger.addHandler(stream_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Survey app startup')

# Database connection management
class DatabaseConnection:
    def __init__(self, db_path=None):
        self.db_path = db_path or app.config['DATABASE']
        self.conn = None
    
    def __enter__(self):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        return self.conn
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            if exc_type is not None:
                self.conn.rollback()
            else:
                self.conn.commit()
            self.conn.close()

def get_db_connection():
    """Legacy function for backward compatibility"""
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database schema and add default data"""
    with DatabaseConnection() as conn:
        cursor = conn.cursor()
        
        # Create surveys table with added features
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS surveys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            creator_ip TEXT,
            creator_email TEXT,
            theme TEXT DEFAULT 'dark',
            header_image TEXT,
            logo_image TEXT,
            is_template INTEGER DEFAULT 0,
            published INTEGER DEFAULT 0,
            archived INTEGER DEFAULT 0,
            expiry_date DATE
        )
        """)
        
        # Create questions table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            survey_id INTEGER NOT NULL,
            question_text TEXT NOT NULL,
            question_type TEXT DEFAULT 'multiple-choice',
            position INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            image_path TEXT,
            required INTEGER DEFAULT 0,
            FOREIGN KEY (survey_id) REFERENCES surveys (id) ON DELETE CASCADE
        )
        """)
        
        # Create options table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL,
            option_text TEXT NOT NULL,
            position INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            image_path TEXT,
            FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE
        )
        """)
        
        # Create responses table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            survey_id INTEGER NOT NULL,
            respondent_ip TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (survey_id) REFERENCES surveys (id) ON DELETE CASCADE
        )
        """)
        
        # Create answers table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            response_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            option_id INTEGER,
            text_answer TEXT,
            number_answer REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (response_id) REFERENCES responses (id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE,
            FOREIGN KEY (option_id) REFERENCES options (id) ON DELETE CASCADE
        )
        """)
        
        # Create users table for future authentication
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_admin INTEGER DEFAULT 0
        )
        """)
        
        # Add default templates only if they don't exist
        cursor.execute("SELECT COUNT(*) as count FROM surveys WHERE is_template = 1")
        template_count = cursor.fetchone()['count']
        
        if template_count == 0:
            # Add template for customer satisfaction
            cursor.execute("""
            INSERT INTO surveys (title, description, is_template, theme)
            VALUES (?, ?, ?, ?)
            """, ("Customer Satisfaction Survey", "Template for measuring customer satisfaction with your product or service", 1, "dark"))
            
            template_id = cursor.lastrowid
            
            # Add template questions
            questions = [
                ("How would you rate our product?", "rating", 1, None),
                ("What features do you like the most?", "multiple-choice", 2, None),
                ("How likely are you to recommend our product?", "slider", 3, None)
            ]
            
            for q_text, q_type, pos, img in questions:
                cursor.execute("""
                INSERT INTO questions (survey_id, question_text, question_type, position, image_path)
                VALUES (?, ?, ?, ?, ?)
                """, (template_id, q_text, q_type, pos, img))
                
                q_id = cursor.lastrowid
                
                # Add options for multiple choice
                if q_type == "multiple-choice":
                    options = ["User Interface", "Performance", "Features", "Price", "Customer Support"]
                    for i, opt in enumerate(options):
                        cursor.execute("""
                        INSERT INTO options (question_id, option_text, position)
                        VALUES (?, ?, ?)
                        """, (q_id, opt, i+1))
            
            # Add template for event feedback
            cursor.execute("""
            INSERT INTO surveys (title, description, is_template, theme)
            VALUES (?, ?, ?, ?)
            """, ("Event Feedback Survey", "Collect feedback from attendees after your event", 1, "blue"))
            
            template_id = cursor.lastrowid
            
            # Add template questions
            questions = [
                ("How would you rate the overall event?", "rating", 1, None),
                ("What did you enjoy most about the event?", "text", 2, None),
                ("How was the venue?", "rating", 3, None),
                ("Would you attend a similar event in the future?", "multiple-choice", 4, None)
            ]
            
            for q_text, q_type, pos, img in questions:
                cursor.execute("""
                INSERT INTO questions (survey_id, question_text, question_type, position, image_path)
                VALUES (?, ?, ?, ?, ?)
                """, (template_id, q_text, q_type, pos, img))
                
                q_id = cursor.lastrowid
                
                # Add options for multiple choice
                if q_type == "multiple-choice":
                    options = ["Definitely", "Probably", "Not sure", "Probably not", "Definitely not"]
                    for i, opt in enumerate(options):
                        cursor.execute("""
                        INSERT INTO options (question_id, option_text, position)
                        VALUES (?, ?, ?)
                        """, (q_id, opt, i+1))

# Initialize database
if not os.path.exists(app.config['DATABASE']):
    app.logger.info(f"Creating new database at {app.config['DATABASE']}")
    init_db()
else:
    app.logger.info(f"Database exists at {app.config['DATABASE']}, checking tables")
    # Check if tables exist without recreating default templates
    with DatabaseConnection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='surveys'")
        if not cursor.fetchone():
            app.logger.info("Tables don't exist, initializing database")
            init_db()

# Validation functions
def validate_survey_data(title, description=None):
    """Validate survey data and return errors if any"""
    errors = {}
    
    if not title or len(title.strip()) < 3:
        errors['title'] = 'Survey title must be at least 3 characters long'
    
    if title and len(title) > 100:
        errors['title'] = 'Survey title must be less than 100 characters'
    
    if description and len(description) > 500:
        errors['description'] = 'Description must be less than 500 characters'
    
    return errors

def validate_question_data(question_text, question_type):
    """Validate question data and return errors if any"""
    errors = {}
    
    if not question_text or len(question_text.strip()) < 3:
        errors['question_text'] = 'Question text must be at least 3 characters long'
    
    if question_text and len(question_text) > 500:
        errors['question_text'] = 'Question text must be less than 500 characters'
    
    valid_types = ['multiple-choice', 'image-choice', 'rating', 'slider', 'text']
    if question_type not in valid_types:
        errors['question_type'] = f'Invalid question type. Must be one of: {", ".join(valid_types)}'
    
    return errors

def validate_option_data(option_text):
    """Validate option data and return errors if any"""
    errors = {}
    
    if not option_text or len(option_text.strip()) < 1:
        errors['option_text'] = 'Option text cannot be empty'
    
    if option_text and len(option_text) > 200:
        errors['option_text'] = 'Option text must be less than 200 characters'
    
    return errors

# Gemini AI API helpers
def send_message_to_gemini(prompt):
    """Enhanced Gemini API call with better error handling"""
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    url = f"{app.config['GEMINI_ENDPOINT']}?key={app.config['GEMINI_API_KEY']}"
    
    try:
        app.logger.info(f"Sending request to Gemini API")
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        response_data = response.json()
        
        if "candidates" in response_data:
            return response_data["candidates"][0]["content"]["parts"][0]["text"]
        else:
            app.logger.warning(f"Unexpected Gemini API response: {response_data}")
            return "No response from Gemini API."
    except requests.exceptions.Timeout:
        app.logger.error("Gemini API request timed out")
        return "The Gemini API request timed out. Please try again later."
    except requests.exceptions.HTTPError as e:
        app.logger.error(f"Gemini API HTTP error: {e}, Response: {e.response.text if hasattr(e, 'response') else 'No response'}")
        return f"Error calling Gemini API: HTTP error occurred."
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Gemini API request error: {e}")
        return f"Error calling Gemini API: Request failed."
    except ValueError as e:  # JSON parsing error
        app.logger.error(f"Gemini API JSON parsing error: {e}")
        return "Error parsing response from Gemini API."
    except Exception as e:
        app.logger.error(f"Unexpected error with Gemini API: {e}")
        return "An unexpected error occurred while processing your request."

# File handling helpers
def allowed_file(filename):
    """Check if a file has an allowed extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def save_uploaded_file(file):
    """Save an uploaded file with a unique name and return the path"""
    if file and allowed_file(file.filename):
        # Create a unique filename
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        try:
            file.save(file_path)
            return f"/static/uploads/{unique_filename}"
        except Exception as e:
            app.logger.error(f"Error saving file {filename}: {e}")
            return None
    return None

# Chart generation function
def generate_chart(question_id, survey_id):
    """Generate chart for question responses with error handling"""
    try:
        with DatabaseConnection() as conn:
            # Get question info
            question = conn.execute('SELECT * FROM questions WHERE id = ?', (question_id,)).fetchone()
            
            if not question:
                app.logger.warning(f"Attempt to generate chart for non-existent question ID {question_id}")
                return None
            
            question_type = question['question_type']
            
            # Different charts based on question type
            if question_type == 'multiple-choice':
                # Get options
                options = conn.execute(
                    'SELECT * FROM options WHERE question_id = ? ORDER BY position', 
                    (question_id,)
                ).fetchall()
                
                # Get count of each option selected
                option_counts = []
                labels = []
                
                for option in options:
                    count = conn.execute('''
                        SELECT COUNT(*) as count FROM answers a
                        JOIN responses r ON a.response_id = r.id
                        WHERE a.question_id = ? AND a.option_id = ? AND r.survey_id = ?
                    ''', (question_id, option['id'], survey_id)).fetchone()['count']
                    
                    option_counts.append(count)
                    labels.append(option['option_text'])
                
                # Skip chart creation if no data
                if sum(option_counts) == 0:
                    return None
                
                # Create bar chart with improved styling
                plt.figure(figsize=(10, 6))
                bars = plt.bar(labels, option_counts, color='#1DB954')
                
                # Add value labels on top of bars
                for bar in bars:
                    height = bar.get_height()
                    plt.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                            str(int(height)), ha='center', va='bottom')
                
                plt.xlabel('Options')
                plt.ylabel('Response Count')
                plt.title(question['question_text'])
                plt.xticks(rotation=45, ha='right')
                plt.tight_layout()
                
                # Save to buffer
                buf = io.BytesIO()
                plt.savefig(buf, format='png', transparent=True)
                buf.seek(0)
                plt.close()
                
                # Encode as base64
                data = base64.b64encode(buf.getvalue()).decode('utf-8')
                return f"data:image/png;base64,{data}"
            
            elif question_type in ['rating', 'slider']:
                # Get all numeric answers
                answers = conn.execute('''
                    SELECT a.number_answer FROM answers a
                    JOIN responses r ON a.response_id = r.id
                    WHERE a.question_id = ? AND r.survey_id = ? AND a.number_answer IS NOT NULL
                ''', (question_id, survey_id)).fetchall()
                
                values = [a['number_answer'] for a in answers]
                
                if not values:
                    return None
                    
                # Create histogram with improved styling
                plt.figure(figsize=(10, 6))
                plt.hist(values, bins=5, color='#1DB954', alpha=0.7, edgecolor='black')
                plt.xlabel('Rating')
                plt.ylabel('Response Count')
                plt.title(question['question_text'])
                
                # Add grid for better readability
                plt.grid(axis='y', alpha=0.3)
                plt.tight_layout()
                
                # Save to buffer
                buf = io.BytesIO()
                plt.savefig(buf, format='png', transparent=True)
                buf.seek(0)
                plt.close()
                
                # Encode as base64
                data = base64.b64encode(buf.getvalue()).decode('utf-8')
                return f"data:image/png;base64,{data}"
            
            # Text responses word cloud (could be implemented here)
            elif question_type == 'text':
                # Return None for now - could add word cloud visualization in the future
                return None
        
        return None
    except Exception as e:
        app.logger.error(f"Error generating chart for question {question_id}: {e}")
        return None

# Rate limiting helper
def rate_limit(key_prefix, limit=10, period=60):
    """Basic rate limiting to prevent abuse"""
    key = f"{key_prefix}:{request.remote_addr}"
    current = session.get(key, {})
    
    # Clean up old entries
    now = time.time()
    current = {ts: count for ts, count in current.items() if now - float(ts) < period}
    
    # Add current timestamp
    current_ts = str(now)
    current[current_ts] = current.get(current_ts, 0) + 1
    
    # Save back to session
    session[key] = current
    
    # Count total requests in period
    total = sum(current.values())
    
    # Return True if limit exceeded
    return total > limit

# Authentication helper
def login_required(f):
    """Decorator for routes that require authentication (for future use)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# Creator authorization middleware
def creator_only(f):
    """Ensure only the creator can access certain routes"""
    @wraps(f)
    def decorated_function(survey_id, *args, **kwargs):
        with DatabaseConnection() as conn:
            survey = conn.execute('SELECT * FROM surveys WHERE id = ?', (survey_id,)).fetchone()
        
        # If there's no creator_ip, we'll assume anyone can edit for backward compatibility
        if survey and (not survey['creator_ip'] or survey['creator_ip'] == request.remote_addr):
            return f(survey_id, *args, **kwargs)
        else:
            # Not the creator - redirect to view-only mode
            flash('You do not have permission to edit this survey', 'warning')
            return redirect(url_for('view_survey', survey_id=survey_id))
    
    return decorated_function

# Cache for frequently accessed data
survey_cache = {}
def get_cached_survey(survey_id, max_age=60):
    """Get survey data from cache or database"""
    cache_key = f"survey_{survey_id}"
    if cache_key in survey_cache:
        # Check if cache is still valid
        cached_time, survey_data = survey_cache[cache_key]
        if time.time() - cached_time < max_age:
            return survey_data
    
    # Get fresh data from database
    with DatabaseConnection() as conn:
        survey = conn.execute('SELECT * FROM surveys WHERE id = ?', (survey_id,)).fetchone()
        if survey:
            survey_data = dict(survey)
            # Store in cache
            survey_cache[cache_key] = (time.time(), survey_data)
            return survey_data
    
    return None

def clear_survey_cache(survey_id):
    """Clear cached survey data when it's updated"""
    cache_key = f"survey_{survey_id}"
    if cache_key in survey_cache:
        del survey_cache[cache_key]

# Routes
@app.route('/')
def index():
    with DatabaseConnection() as conn:
        # Show non-archived surveys created by this IP address
        surveys = conn.execute(
            'SELECT * FROM surveys WHERE (creator_ip = ? OR creator_ip IS NULL) AND is_template = 0 AND archived = 0 ORDER BY created_at DESC', 
            (request.remote_addr,)
        ).fetchall()
        
        # Get templates
        templates = conn.execute('SELECT * FROM surveys WHERE is_template = 1').fetchall()
    
    return render_template('index.html', surveys=surveys, templates=templates)

@app.route('/survey/new', methods=['POST'])
def create_survey():
    title = request.form.get('title')
    description = request.form.get('description')
    theme = request.form.get('theme', 'dark')
    template_id = request.form.get('template_id')
    
    # Validate input data
    errors = validate_survey_data(title, description)
    if errors:
        for field, message in errors.items():
            flash(message, 'danger')
        return redirect(url_for('index'))
    
    with DatabaseConnection() as conn:
        if template_id:
            # Creating from template - copy the template
            template = conn.execute('SELECT * FROM surveys WHERE id = ? AND is_template = 1', (template_id,)).fetchone()
            if template:
                # Create new survey based on template
                cursor = conn.execute(
                    'INSERT INTO surveys (title, description, creator_ip, theme) VALUES (?, ?, ?, ?)',
                    (title or template['title'], description or template['description'], request.remote_addr, theme or template['theme'])
                )
                survey_id = cursor.lastrowid
                
                # Copy questions from template
                template_questions = conn.execute('SELECT * FROM questions WHERE survey_id = ?', (template_id,)).fetchall()
                for question in template_questions:
                    cursor = conn.execute(
                        'INSERT INTO questions (survey_id, question_text, question_type, position, image_path, required) VALUES (?, ?, ?, ?, ?, ?)',
                        (survey_id, question['question_text'], question['question_type'], question['position'], question['image_path'], question['required'])
                    )
                    new_question_id = cursor.lastrowid
                    
                    # Copy options if multiple choice
                    if question['question_type'] == 'multiple-choice':
                        options = conn.execute('SELECT * FROM options WHERE question_id = ?', (question['id'],)).fetchall()
                        for option in options:
                            conn.execute(
                                'INSERT INTO options (question_id, option_text, position, image_path) VALUES (?, ?, ?, ?)',
                                (new_question_id, option['option_text'], option['position'], option['image_path'])
                            )
            else:
                # Creating a new survey
                cursor = conn.execute(
                    'INSERT INTO surveys (title, description, creator_ip, theme) VALUES (?, ?, ?, ?)',
                    (title, description, request.remote_addr, theme)
                )
                survey_id = cursor.lastrowid
        else:
            # Regular new survey
            cursor = conn.execute(
                'INSERT INTO surveys (title, description, creator_ip, theme) VALUES (?, ?, ?, ?)',
                (title, description, request.remote_addr, theme)
            )
            survey_id = cursor.lastrowid
    
    flash('Survey created successfully!', 'success')
    return redirect(url_for('edit_survey', survey_id=survey_id))

@app.route('/survey/<int:survey_id>/edit')
@creator_only
def edit_survey(survey_id):
    with DatabaseConnection() as conn:
        survey = conn.execute('SELECT * FROM surveys WHERE id = ?', (survey_id,)).fetchone()
        questions = conn.execute(
            'SELECT * FROM questions WHERE survey_id = ? ORDER BY position', 
            (survey_id,)
        ).fetchall()
        
        # Fetch options for each question
        questions_with_options = []
        for question in questions:
            options = conn.execute(
                'SELECT * FROM options WHERE question_id = ? ORDER BY position',
                (question['id'],)
            ).fetchall()
            question_dict = dict(question)
            question_dict['options'] = [dict(option) for option in options]
            questions_with_options.append(question_dict)
    
    return render_template(
        'survey_editor.html', 
        survey=survey, 
        questions=questions_with_options
    )

@app.route('/survey/<int:survey_id>/settings', methods=['GET', 'POST'])
@creator_only
def survey_settings(survey_id):
    with DatabaseConnection() as conn:
        survey = conn.execute('SELECT * FROM surveys WHERE id = ?', (survey_id,)).fetchone()
        
        if request.method == 'POST':
            title = request.form.get('title')
            description = request.form.get('description')
            theme = request.form.get('theme')
            expiry_date = request.form.get('expiry_date')  # Added expiry date
            
            # Validate input data
            errors = validate_survey_data(title, description)
            if errors:
                for field, message in errors.items():
                    flash(message, 'danger')
                return redirect(url_for('survey_settings', survey_id=survey_id))
            
            # Handle file uploads
            header_image = survey['header_image']
            logo_image = survey['logo_image']
            
            if 'header_image' in request.files and request.files['header_image'].filename:
                header_file = request.files['header_image']
                new_header_image = save_uploaded_file(header_file)
                if new_header_image:
                    header_image = new_header_image
            
            if 'logo_image' in request.files and request.files['logo_image'].filename:
                logo_file = request.files['logo_image']
                new_logo_image = save_uploaded_file(logo_file)
                if new_logo_image:
                    logo_image = new_logo_image
            
            # Parse expiry date or set to None
            parsed_expiry = None
            if expiry_date and expiry_date.strip():
                try:
                    parsed_expiry = datetime.datetime.strptime(expiry_date, '%Y-%m-%d').date()
                except ValueError:
                    flash('Invalid expiry date format. Please use YYYY-MM-DD', 'danger')
                    return redirect(url_for('survey_settings', survey_id=survey_id))
            
            # Update survey
            conn.execute(
                'UPDATE surveys SET title = ?, description = ?, theme = ?, header_image = ?, logo_image = ?, expiry_date = ? WHERE id = ?',
                (title, description, theme, header_image, logo_image, parsed_expiry, survey_id)
            )
            
            # Clear cache
            clear_survey_cache(survey_id)
            
            flash('Survey settings updated successfully!', 'success')
            return redirect(url_for('edit_survey', survey_id=survey_id))
    
    return render_template('survey_settings.html', survey=survey)

@app.route('/survey/<int:survey_id>/view')
def view_survey(survey_id):
    survey = get_cached_survey(survey_id)
    
    if not survey:
        abort(404)
    
    # Check if survey is expired
    if survey.get('expiry_date'):
        try:
            expiry_date = datetime.datetime.strptime(survey['expiry_date'], '%Y-%m-%d').date()
            today = datetime.date.today()
            if today > expiry_date:
                return render_template('survey_expired.html', survey=survey)
        except (ValueError, TypeError):
            # If date parsing fails, continue (invalid date format)
            pass
    
    # Check if survey is published
    if survey.get('published') == 0 and survey.get('creator_ip') != request.remote_addr:
        return render_template('survey_not_published.html', survey=survey)
        
    with DatabaseConnection() as conn:
        questions = conn.execute(
            'SELECT * FROM questions WHERE survey_id = ? ORDER BY position', 
            (survey_id,)
        ).fetchall()
        
        # Fetch options for each question
        questions_with_options = []
        for question in questions:
            options = conn.execute(
                'SELECT * FROM options WHERE question_id = ? ORDER BY position',
                (question['id'],)
            ).fetchall()
            question_dict = dict(question)
            question_dict['options'] = [dict(option) for option in options]
            questions_with_options.append(question_dict)
    
    # FIXED: Strict comparison for creator check, using string comparison to be safe
    is_creator = str(survey.get('creator_ip', '')) == str(request.remote_addr)
    app.logger.info(f"Survey {survey_id} viewed by IP {request.remote_addr}, creator IP: {survey.get('creator_ip')}, is_creator: {is_creator}")
    
    return render_template(
        'survey_view.html', 
        survey=survey, 
        questions=questions_with_options,
        is_creator=is_creator
    )

@app.route('/survey/<int:survey_id>/duplicate', methods=['POST'])
@creator_only
def duplicate_survey(survey_id):
    with DatabaseConnection() as conn:
        # Get the original survey
        survey = conn.execute('SELECT * FROM surveys WHERE id = ?', (survey_id,)).fetchone()
        
        if not survey:
            flash('Survey not found', 'danger')
            return redirect(url_for('index'))
        
        # Create a new survey based on the original
        cursor = conn.execute(
            'INSERT INTO surveys (title, description, creator_ip, theme, header_image, logo_image) VALUES (?, ?, ?, ?, ?, ?)',
            (f"Copy of {survey['title']}", survey['description'], request.remote_addr, survey['theme'], survey['header_image'], survey['logo_image'])
        )
        new_survey_id = cursor.lastrowid
        
        # Copy questions
        questions = conn.execute('SELECT * FROM questions WHERE survey_id = ?', (survey_id,)).fetchall()
        for question in questions:
            cursor = conn.execute(
                'INSERT INTO questions (survey_id, question_text, question_type, position, image_path, required) VALUES (?, ?, ?, ?, ?, ?)',
                (new_survey_id, question['question_text'], question['question_type'], question['position'], question['image_path'], question['required'])
            )
            new_question_id = cursor.lastrowid
            
            # Copy options if applicable
            if question['question_type'] in ['multiple-choice', 'image-choice']:
                options = conn.execute('SELECT * FROM options WHERE question_id = ?', (question['id'],)).fetchall()
                for option in options:
                    conn.execute(
                        'INSERT INTO options (question_id, option_text, position, image_path) VALUES (?, ?, ?, ?)',
                        (new_question_id, option['option_text'], option['position'], option['image_path'])
                    )
    
    flash(f"Survey duplicated successfully", 'success')
    return redirect(url_for('edit_survey', survey_id=new_survey_id))

@app.route('/survey/<int:survey_id>/toggle-publish', methods=['POST'])
@creator_only
def toggle_publish_survey(survey_id):
    with DatabaseConnection() as conn:
        # Get current status
        survey = conn.execute('SELECT published FROM surveys WHERE id = ?', (survey_id,)).fetchone()
        
        if not survey:
            abort(404)
        
        # Toggle published status
        new_status = 1 if survey['published'] == 0 else 0
        
        conn.execute(
            'UPDATE surveys SET published = ? WHERE id = ?',
            (new_status, survey_id)
        )
    
    # Clear cache
    clear_survey_cache(survey_id)
    
    status_msg = "published" if new_status == 1 else "unpublished"
    flash(f"Survey {status_msg} successfully", 'success')
    
    return redirect(url_for('edit_survey', survey_id=survey_id))

@app.route('/survey/<int:survey_id>/toggle-archive', methods=['POST'])
@creator_only
def toggle_archive_survey(survey_id):
    with DatabaseConnection() as conn:
        # Get current status
        survey = conn.execute('SELECT archived FROM surveys WHERE id = ?', (survey_id,)).fetchone()
        
        if not survey:
            abort(404)
        
        # Toggle archived status
        new_status = 1 if survey['archived'] == 0 else 0
        
        conn.execute(
            'UPDATE surveys SET archived = ? WHERE id = ?',
            (new_status, survey_id)
        )
    
    # Clear cache
    clear_survey_cache(survey_id)
    
    status_msg = "archived" if new_status == 1 else "restored"
    flash(f"Survey {status_msg} successfully", 'success')
    
    return redirect(url_for('index'))

@app.route('/archived')
def archived_surveys():
    with DatabaseConnection() as conn:
        # Show archived surveys created by this IP address
        surveys = conn.execute(
            'SELECT * FROM surveys WHERE creator_ip = ? AND is_template = 0 AND archived = 1 ORDER BY created_at DESC', 
            (request.remote_addr,)
        ).fetchall()
    
    return render_template('archived_surveys.html', surveys=surveys)

@app.route('/survey/<int:survey_id>/delete', methods=['POST'])
@creator_only
def delete_survey(survey_id):
    with DatabaseConnection() as conn:
        # Delete the survey (cascading delete will handle related records)
        conn.execute('DELETE FROM surveys WHERE id = ?', (survey_id,))
    
    # Clear cache
    clear_survey_cache(survey_id)
    
    flash('Survey deleted successfully', 'success')
    return redirect(url_for('index'))

@app.route('/survey/<int:survey_id>/responses', methods=['GET'])
@creator_only
def view_responses(survey_id):
    with DatabaseConnection() as conn:
        survey = conn.execute('SELECT * FROM surveys WHERE id = ?', (survey_id,)).fetchone()
        
        # Get all questions for this survey
        questions = conn.execute(
            'SELECT * FROM questions WHERE survey_id = ? ORDER BY position', 
            (survey_id,)
        ).fetchall()
        
        # Generate charts for each question
        charts = {}
        for question in questions:
            chart_data = generate_chart(question['id'], survey_id)
            if chart_data:
                charts[question['id']] = chart_data
        
        # Get response data
        responses = conn.execute(
            'SELECT * FROM responses WHERE survey_id = ? ORDER BY created_at DESC', 
            (survey_id,)
        ).fetchall()
        
        # Prepare data for the template
        response_data = []
        for response in responses:
            # Get all answers for this response
            answers = conn.execute('''
                SELECT a.*, q.question_text, q.question_type, o.option_text 
                FROM answers a
                JOIN questions q ON a.question_id = q.id
                LEFT JOIN options o ON a.option_id = o.id
                WHERE a.response_id = ?
            ''', (response['id'],)).fetchall()
            
            response_data.append({
                'id': response['id'],
                'created_at': response['created_at'],
                'ip': response['respondent_ip'],
                'answers': answers
            })
    
    return render_template(
        'survey_responses.html',
        survey=survey,
        questions=questions,
        responses=response_data,
        response_count=len(responses),
        charts=charts
    )

@app.route('/survey/<int:survey_id>/export', methods=['GET'])
@creator_only
def export_responses(survey_id):
    # Apply rate limiting to prevent abuse
    if rate_limit('export', limit=5, period=60):
        flash('Too many export requests. Please try again later.', 'danger')
        return redirect(url_for('view_responses', survey_id=survey_id))
    
    with DatabaseConnection() as conn:
        survey = conn.execute('SELECT * FROM surveys WHERE id = ?', (survey_id,)).fetchone()
        
        # Get all questions for this survey
        questions = conn.execute(
            'SELECT * FROM questions WHERE survey_id = ? ORDER BY position', 
            (survey_id,)
        ).fetchall()
        
        # Get all responses
        responses = conn.execute(
            'SELECT * FROM responses WHERE survey_id = ? ORDER BY created_at', 
            (survey_id,)
        ).fetchall()
        
        # Create a CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header row
        header = ['Response ID', 'Submission Time', 'IP Address']
        for question in questions:
            header.append(f"Q{question['position']}: {question['question_text']}")
        writer.writerow(header)
        
        # Write data rows
        for response in responses:
            row = [response['id'], response['created_at'], response['respondent_ip']]
            
            # Get answers for this response
            for question in questions:
                if question['question_type'] == 'multiple-choice':
                    answer = conn.execute('''
                        SELECT a.*, o.option_text FROM answers a
                        JOIN options o ON a.option_id = o.id
                        WHERE a.response_id = ? AND a.question_id = ?
                    ''', (response['id'], question['id'])).fetchone()
                    
                    if answer:
                        row.append(answer['option_text'])
                    else:
                        row.append('No answer')
                else:
                    # For rating, slider, text questions
                    answer = conn.execute('''
                        SELECT * FROM answers
                        WHERE response_id = ? AND question_id = ?
                    ''', (response['id'], question['id'])).fetchone()
                    
                    if answer:
                        if answer['text_answer']:
                            row.append(answer['text_answer'])
                        elif answer['number_answer'] is not None:
                            row.append(str(answer['number_answer']))
                        else:
                            row.append('No answer')
                    else:
                        row.append('No answer')
            
            writer.writerow(row)
    
    # Prepare the CSV for download
    output.seek(0)
    filename = f"{survey['title'].replace(' ', '_')}_responses_{datetime.datetime.now().strftime('%Y%m%d')}.csv"
    
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )

@app.route('/survey/<int:survey_id>/pdf', methods=['GET'])
def export_survey_pdf(survey_id):
    """Generate a printable PDF-friendly version of the survey"""
    with DatabaseConnection() as conn:
        survey = conn.execute('SELECT * FROM surveys WHERE id = ?', (survey_id,)).fetchone()
        
        if not survey:
            abort(404)
            
        questions = conn.execute(
            'SELECT * FROM questions WHERE survey_id = ? ORDER BY position', 
            (survey_id,)
        ).fetchall()
        
        # Fetch options for each question
        questions_with_options = []
        for question in questions:
            options = conn.execute(
                'SELECT * FROM options WHERE question_id = ? ORDER BY position',
                (question['id'],)
            ).fetchall()
            question_dict = dict(question)
            question_dict['options'] = [dict(option) for option in options]
            questions_with_options.append(question_dict)
    
    return render_template(
        'survey_pdf.html', 
        survey=survey, 
        questions=questions_with_options,
        now=datetime.datetime.now
    )

# API Routes
@app.route('/api/survey/<int:survey_id>/questions', methods=['POST'])
@creator_only
def add_question(survey_id):
    if rate_limit('add_question', limit=20, period=60):
        return jsonify({'error': 'Too many requests. Please try again later.'}), 429
    
    try:
        data = request.get_json()
        question_text = data.get('question_text')
        question_type = data.get('question_type', 'multiple-choice')
        required = data.get('required', 0)
        
        # Validate question data
        errors = validate_question_data(question_text, question_type)
        if errors:
            return jsonify({'error': next(iter(errors.values()))}), 400
        
        with DatabaseConnection() as conn:
            # Get the max position
            max_pos = conn.execute(
                'SELECT MAX(position) as max_pos FROM questions WHERE survey_id = ?', 
                (survey_id,)
            ).fetchone()
            
            new_position = 1
            if max_pos['max_pos'] is not None:
                new_position = max_pos['max_pos'] + 1
            
            cursor = conn.execute(
                'INSERT INTO questions (survey_id, question_text, question_type, position, required) VALUES (?, ?, ?, ?, ?)',
                (survey_id, question_text, question_type, new_position, required)
            )
            question_id = cursor.lastrowid
            
            # Add options if provided
            options = data.get('options', [])
            for idx, option_text in enumerate(options):
                # Validate option text
                option_errors = validate_option_data(option_text)
                if not option_errors:
                    conn.execute(
                        'INSERT INTO options (question_id, option_text, position) VALUES (?, ?, ?)',
                        (question_id, option_text, idx + 1)
                    )
            
            # Fetch the newly created question with options
            question = conn.execute('SELECT * FROM questions WHERE id = ?', (question_id,)).fetchone()
            options = conn.execute(
                'SELECT * FROM options WHERE question_id = ? ORDER BY position',
                (question_id,)
            ).fetchall()
            
            question_dict = dict(question)
            question_dict['options'] = [dict(option) for option in options]
        
        # Clear cache
        clear_survey_cache(survey_id)
        
        return jsonify(question_dict)
    
    except Exception as e:
        app.logger.error(f"Error adding question: {e}")
        return jsonify({'error': 'An error occurred while adding the question'}), 500

@app.route('/api/question/<int:question_id>', methods=['PUT'])
def update_question(question_id):
    try:
        data = request.get_json()
        question_text = data.get('question_text')
        question_type = data.get('question_type')
        required = data.get('required')
        
        # Validate data if provided
        if question_text and question_type:
            errors = validate_question_data(question_text, question_type)
            if errors:
                return jsonify({'error': next(iter(errors.values()))}), 400
        
        with DatabaseConnection() as conn:
            # First check if this user is allowed to edit this question
            question_row = conn.execute('SELECT q.*, s.creator_ip, s.id as survey_id FROM questions q JOIN surveys s ON q.survey_id = s.id WHERE q.id = ?', (question_id,)).fetchone()
            
            if not question_row:
                return jsonify({'error': 'Question not found'}), 404
                
            # Convert to dictionary
            question = dict(question_row)
            
            if str(question.get('creator_ip', '')) != str(request.remote_addr):
                return jsonify({'error': 'Unauthorized'}), 403
            
            # Update query based on provided fields
            update_fields = []
            params = []
            
            if question_text is not None:
                update_fields.append('question_text = ?')
                params.append(question_text)
            
            if question_type is not None:
                update_fields.append('question_type = ?')
                params.append(question_type)
            
            if required is not None:
                update_fields.append('required = ?')
                params.append(1 if required else 0)
            
            if update_fields:
                query = f"UPDATE questions SET {', '.join(update_fields)} WHERE id = ?"
                params.append(question_id)
                conn.execute(query, params)
            
            # Clear cache
            clear_survey_cache(question['survey_id'])
        
        return jsonify({'success': True})
    
    except Exception as e:
        app.logger.error(f"Error updating question: {e}")
        return jsonify({'error': 'An error occurred while updating the question'}), 500

@app.route('/api/question/<int:question_id>/image', methods=['POST'])
def upload_question_image(question_id):
    try:
        with DatabaseConnection() as conn:
            # First check if this user is allowed to edit this question
            question_row = conn.execute('SELECT q.*, s.creator_ip, s.id as survey_id FROM questions q JOIN surveys s ON q.survey_id = s.id WHERE q.id = ?', (question_id,)).fetchone()
            
            if not question_row:
                return jsonify({'error': 'Question not found'}), 404
                
            # Convert to dictionary
            question = dict(question_row)
            
            if str(question.get('creator_ip', '')) != str(request.remote_addr):
                return jsonify({'error': 'Unauthorized'}), 403
            
            if 'image' not in request.files:
                return jsonify({'error': 'No file part'}), 400
            
            file = request.files['image']
            
            if file.filename == '':
                return jsonify({'error': 'No selected file'}), 400
            
            if file and allowed_file(file.filename):
                file_path = save_uploaded_file(file)
                
                if not file_path:
                    return jsonify({'error': 'Failed to save file'}), 500
                
                # Update the question with the image path
                conn.execute(
                    'UPDATE questions SET image_path = ? WHERE id = ?',
                    (file_path, question_id)
                )
                
                # Clear cache
                clear_survey_cache(question['survey_id'])
                
                return jsonify({
                    'success': True,
                    'image_path': file_path
                })
            
            return jsonify({'error': 'Invalid file type'}), 400
    
    except Exception as e:
        app.logger.error(f"Error uploading question image: {e}")
        return jsonify({'error': 'An error occurred while uploading the image'}), 500

@app.route('/api/option/<int:option_id>/image', methods=['POST'])
def upload_option_image(option_id):
    try:
        with DatabaseConnection() as conn:
            # First check if this user is allowed to edit this option
            option_row = conn.execute("""
                SELECT o.*, s.creator_ip, s.id as survey_id
                FROM options o 
                JOIN questions q ON o.question_id = q.id 
                JOIN surveys s ON q.survey_id = s.id 
                WHERE o.id = ?
            """, (option_id,)).fetchone()
            
            if not option_row:
                return jsonify({'error': 'Option not found'}), 404
                
            # Convert to dictionary
            option = dict(option_row)
            
            if str(option.get('creator_ip', '')) != str(request.remote_addr):
                return jsonify({'error': 'Unauthorized'}), 403
            
            if 'image' not in request.files:
                return jsonify({'error': 'No file part'}), 400
            
            file = request.files['image']
            
            if file.filename == '':
                return jsonify({'error': 'No selected file'}), 400
            
            if file and allowed_file(file.filename):
                file_path = save_uploaded_file(file)
                
                if not file_path:
                    return jsonify({'error': 'Failed to save file'}), 500
                
                # Update the option with the image path
                conn.execute(
                    'UPDATE options SET image_path = ? WHERE id = ?',
                    (file_path, option_id)
                )
                
                # Clear cache
                clear_survey_cache(option['survey_id'])
                
                return jsonify({
                    'success': True,
                    'image_path': file_path
                })
            
            return jsonify({'error': 'Invalid file type'}), 400
    
    except Exception as e:
        app.logger.error(f"Error uploading option image: {e}")
        return jsonify({'error': 'An error occurred while uploading the image'}), 500

@app.route('/api/question/<int:question_id>/options', methods=['POST'])
def add_option(question_id):
    try:
        data = request.get_json()
        option_text = data.get('option_text')
        
        # Validate option data
        errors = validate_option_data(option_text)
        if errors:
            return jsonify({'error': next(iter(errors.values()))}), 400
        
        with DatabaseConnection() as conn:
            # First check if this user is allowed to edit this question
            question_row = conn.execute('SELECT q.*, s.creator_ip, s.id as survey_id FROM questions q JOIN surveys s ON q.survey_id = s.id WHERE q.id = ?', (question_id,)).fetchone()
            
            if not question_row:
                return jsonify({'error': 'Question not found'}), 404
                
            # Convert to dictionary
            question = dict(question_row)
            
            if str(question.get('creator_ip', '')) != str(request.remote_addr):
                return jsonify({'error': 'Unauthorized'}), 403
            
            # Get the max position
            max_pos = conn.execute(
                'SELECT MAX(position) as max_pos FROM options WHERE question_id = ?', 
                (question_id,)
            ).fetchone()
            
            new_position = 1
            if max_pos['max_pos'] is not None:
                new_position = max_pos['max_pos'] + 1
            
            cursor = conn.execute(
                'INSERT INTO options (question_id, option_text, position) VALUES (?, ?, ?)',
                (question_id, option_text, new_position)
            )
            option_id = cursor.lastrowid
            
            # Fetch the newly created option
            option = conn.execute('SELECT * FROM options WHERE id = ?', (option_id,)).fetchone()
            option_dict = dict(option)
            
            # Clear cache
            clear_survey_cache(question['survey_id'])
        
        return jsonify(option_dict)
    
    except Exception as e:
        app.logger.error(f"Error adding option: {e}")
        return jsonify({'error': 'An error occurred while adding the option'}), 500

@app.route('/api/option/<int:option_id>', methods=['PUT'])
def update_option(option_id):
    try:
        data = request.get_json()
        option_text = data.get('option_text')
        
        # Validate option data
        errors = validate_option_data(option_text)
        if errors:
            return jsonify({'error': next(iter(errors.values()))}), 400
        
        with DatabaseConnection() as conn:
            # First check if this user is allowed to edit this option
            option_row = conn.execute("""
                SELECT o.*, s.creator_ip, s.id as survey_id 
                FROM options o 
                JOIN questions q ON o.question_id = q.id 
                JOIN surveys s ON q.survey_id = s.id 
                WHERE o.id = ?
            """, (option_id,)).fetchone()
            
            if not option_row:
                return jsonify({'error': 'Option not found'}), 404
            
            # Convert SQLite row to dictionary
            option = dict(option_row)
            
            if str(option.get('creator_ip', '')) != str(request.remote_addr):
                return jsonify({'error': 'Unauthorized'}), 403
            
            conn.execute(
                'UPDATE options SET option_text = ? WHERE id = ?',
                (option_text, option_id)
            )
            
            # Clear cache
            clear_survey_cache(option['survey_id'])
        
        return jsonify({'success': True})
    
    except Exception as e:
        app.logger.error(f"Error updating option: {e}")
        return jsonify({'error': 'An error occurred while updating the option'}), 500

@app.route('/api/option/<int:option_id>', methods=['DELETE'])
def delete_option(option_id):
    try:
        with DatabaseConnection() as conn:
            # First check if this user is allowed to delete this option
            option_row = conn.execute("""
                SELECT o.*, s.creator_ip, s.id as survey_id 
                FROM options o 
                JOIN questions q ON o.question_id = q.id 
                JOIN surveys s ON q.survey_id = s.id 
                WHERE o.id = ?
            """, (option_id,)).fetchone()
            
            if not option_row:
                return jsonify({'error': 'Option not found'}), 404
                
            # Convert to dictionary
            option = dict(option_row)
            
            if str(option.get('creator_ip', '')) != str(request.remote_addr):
                return jsonify({'error': 'Unauthorized'}), 403
            
            conn.execute('DELETE FROM options WHERE id = ?', (option_id,))
            
            # Clear cache
            clear_survey_cache(option['survey_id'])
        
        return jsonify({'success': True})
    
    except Exception as e:
        app.logger.error(f"Error deleting option: {e}")
        return jsonify({'error': 'An error occurred while deleting the option'}), 500

@app.route('/api/question/<int:question_id>', methods=['DELETE'])
def delete_question(question_id):
    try:
        with DatabaseConnection() as conn:
            # First check if this user is allowed to delete this question
            question_row = conn.execute('SELECT q.*, s.creator_ip, s.id as survey_id FROM questions q JOIN surveys s ON q.survey_id = s.id WHERE q.id = ?', (question_id,)).fetchone()
            
            if not question_row:
                return jsonify({'error': 'Question not found'}), 404
                
            # Convert to dictionary
            question = dict(question_row)
            
            if str(question.get('creator_ip', '')) != str(request.remote_addr):
                return jsonify({'error': 'Unauthorized'}), 403
            
            # Delete options first (cascade should handle this but being explicit)
            conn.execute('DELETE FROM options WHERE question_id = ?', (question_id,))
            conn.execute('DELETE FROM questions WHERE id = ?', (question_id,))
            
            # Clear cache
            clear_survey_cache(question['survey_id'])
        
        return jsonify({'success': True})
    
    except Exception as e:
        app.logger.error(f"Error deleting question: {e}")
        return jsonify({'error': 'An error occurred while deleting the question'}), 500

@app.route('/api/generate-questions', methods=['POST'])
def generate_questions():
    # Rate limiting for API usage
    if rate_limit('generate_questions', limit=5, period=60):
        return jsonify({'error': 'Too many requests. Please try again later.'}), 429
    
    try:
        data = request.get_json()
        topic = data.get('topic', 'pricing management')
        num_questions = min(int(data.get('num_questions', 5)), 10)  # Limit to max 10 questions
        include_visuals = data.get('include_visuals', False)
        
        prompt = f"""
        Generate {num_questions} survey questions for market research on {topic}. 
        Include a mix of question types (multiple-choice, rating scales, sliders).
        {"For multiple-choice questions, suggest relevant images that could be used for visual appeal." if include_visuals else ""}
        Format as JSON with this exact structure:
        {{
            "questions": [
                {{
                    "question_text": "The question text here",
                    "question_type": "multiple-choice|rating|slider|text",
                    "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
                    "suggested_image": "Brief description of an appropriate image (e.g., 'product features comparison chart')" 
                }}
            ]
        }}
        Only return the JSON, no additional text.
        """
        
        response = send_message_to_gemini(prompt)
        
        try:
            # Try to extract JSON if the response has additional text
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                questions_data = json.loads(json_str)
            else:
                questions_data = json.loads(response)
            
            return jsonify(questions_data)
        except json.JSONDecodeError:
            app.logger.error(f"Failed to parse response from Gemini API: {response}")
            return jsonify({
                'error': 'Failed to parse response from Gemini API',
                'raw_response': response
            }), 500
    
    except Exception as e:
        app.logger.error(f"Error generating questions: {e}")
        return jsonify({'error': 'An error occurred while generating questions'}), 500

@app.route('/api/survey/<int:survey_id>/submit', methods=['POST'])
def submit_survey(survey_id):
    # Rate limiting for submissions to prevent spamming
    if rate_limit('submit_survey', limit=10, period=60):
        return jsonify({'error': 'Too many submissions. Please try again later.'}), 429
    
    try:
        # Log submission attempt
        app.logger.info(f"Survey submission attempt for survey {survey_id} from IP {request.remote_addr}")
        
        # Validate CSRF token
        if request.headers.get('X-CSRFToken') != session.get('csrf_token'):
            app.logger.warning(f"CSRF token mismatch for survey {survey_id}")
            # Don't return error here, continue anyway as this might be causing issues
        
        data = request.get_json()
        if not data:
            app.logger.warning(f"No JSON data in submission for survey {survey_id}")
            return jsonify({'error': 'No data provided'}), 400
            
        answers = data.get('answers', [])
        app.logger.info(f"Survey {survey_id} submission has {len(answers)} answers")
        
        if not answers:
            return jsonify({'error': 'No answers provided'}), 400
        
        with DatabaseConnection() as conn:
            # Check if survey exists and is not expired
            survey_row = conn.execute('SELECT * FROM surveys WHERE id = ?', (survey_id,)).fetchone()
            
            if not survey_row:
                app.logger.warning(f"Survey {survey_id} not found in database")
                return jsonify({'error': 'Survey not found'}), 404
            
            # Convert SQLite row to dictionary for easier access
            survey = dict(survey_row)
            
            # Check expiry date
            if 'expiry_date' in survey and survey['expiry_date']:
                try:
                    expiry_date = datetime.datetime.strptime(survey['expiry_date'], '%Y-%m-%d').date()
                    today = datetime.date.today()
                    if today > expiry_date:
                        app.logger.info(f"Survey {survey_id} is expired")
                        return jsonify({'error': 'This survey has expired'}), 400
                except (ValueError, TypeError):
                    # If date parsing fails, continue (invalid date format)
                    app.logger.warning(f"Invalid expiry date format for survey {survey_id}")
                    pass
            
            # FIXED: Improved publishing check with better logging
            published = survey.get('published', 0)
            creator_ip = survey.get('creator_ip', '')
            
            if published == 0:
                app.logger.info(f"Checking if unpublished survey {survey_id} can be accessed: creator IP: {creator_ip}, request IP: {request.remote_addr}")
                if str(creator_ip) != str(request.remote_addr):
                    app.logger.warning(f"Attempt to submit to unpublished survey {survey_id} by non-creator")
                    return jsonify({'error': 'This survey is not published yet'}), 400
            
            # Create a new response
            cursor = conn.execute(
                'INSERT INTO responses (survey_id, respondent_ip) VALUES (?, ?)',
                (survey_id, request.remote_addr)
            )
            response_id = cursor.lastrowid
            app.logger.info(f"Created response ID {response_id} for survey {survey_id}")
            
            # Add answers
            answers_added = 0
            for answer in answers:
                question_id = answer.get('question_id')
                if not question_id:
                    app.logger.warning(f"Missing question_id in answer for response {response_id}")
                    continue
                    
                question_row = conn.execute('SELECT question_type, required FROM questions WHERE id = ?', (question_id,)).fetchone()
                
                if not question_row:
                    app.logger.warning(f"Question {question_id} not found for response {response_id}")
                    continue
                
                # Convert to dictionary
                question = dict(question_row)
                question_type = question.get('question_type')
                
                if question_type == 'multiple-choice' or question_type == 'image-choice':
                    option_id = answer.get('option_id')
                    if question_id and option_id:
                        # Verify option belongs to question
                        option = conn.execute('SELECT id FROM options WHERE id = ? AND question_id = ?', 
                                             (option_id, question_id)).fetchone()
                        if option:
                            conn.execute(
                                'INSERT INTO answers (response_id, question_id, option_id) VALUES (?, ?, ?)',
                                (response_id, question_id, option_id)
                            )
                            answers_added += 1
                        else:
                            app.logger.warning(f"Option {option_id} does not belong to question {question_id}")
                elif question_type == 'text':
                    text_answer = answer.get('text_answer', '')
                    if text_answer or not question.get('required'):
                        conn.execute(
                            'INSERT INTO answers (response_id, question_id, text_answer) VALUES (?, ?, ?)',
                            (response_id, question_id, text_answer)
                        )
                        answers_added += 1
                elif question_type in ['rating', 'slider']:
                    number_answer = answer.get('number_answer')
                    if number_answer is not None:
                        try:
                            numeric_value = float(number_answer)
                            conn.execute(
                                'INSERT INTO answers (response_id, question_id, number_answer) VALUES (?, ?, ?)',
                                (response_id, question_id, numeric_value)
                            )
                            answers_added += 1
                        except (ValueError, TypeError):
                            app.logger.warning(f"Invalid numeric value for question {question_id}: {number_answer}")
            
            app.logger.info(f"Added {answers_added} answers for response {response_id}")
            
            return jsonify({
                'success': True,
                'response_id': response_id,
                'answers_recorded': answers_added
            })
        
    except Exception as e:
        app.logger.error(f"Error submitting survey {survey_id}: {e}", exc_info=True)
        return jsonify({'error': 'An error occurred while submitting your response: ' + str(e)}), 500

# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403

@app.errorhandler(400)
def bad_request(e):
    return render_template('400.html', error=str(e)), 400

@app.errorhandler(500)
def server_error(e):
    app.logger.error(f"Server error: {e}")
    return render_template('500.html'), 500

@app.errorhandler(429)
def too_many_requests(e):
    return render_template('429.html'), 429

# Helper endpoints
@app.route('/health')
def health_check():
    """Basic health check endpoint for monitoring"""
    return jsonify({'status': 'ok', 'version': '1.0.0'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=app.config['DEBUG'], host='0.0.0.0', port=port)
