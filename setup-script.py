import os
import shutil

# Create the necessary directories
print("Creating directory structure...")
os.makedirs('templates', exist_ok=True)
os.makedirs('static/css', exist_ok=True)
os.makedirs('static/js', exist_ok=True)
os.makedirs('static/img', exist_ok=True)
os.makedirs('static/uploads', exist_ok=True)  # Directory for uploaded images
os.makedirs('logs', exist_ok=True)  # Added directory for application logs

# Function to write content to file
def write_file(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Created: {path}")

# Create error pages
write_file('templates/400.html', '''{% extends "base.html" %}

{% block title %}400 - Bad Request{% endblock %}

{% block content %}
<div class="text-center py-5">
    <h1 class="display-1">400</h1>
    <h2>Bad Request</h2>
    <p class="lead mt-3">{{ error|default("Your request could not be processed.") }}</p>
    <a href="{{ url_for('index') }}" class="btn btn-primary mt-3">
        <i class="fas fa-home mr-2"></i> Go Home
    </a>
</div>
{% endblock %}''')

write_file('templates/500.html', '''{% extends "base.html" %}

{% block title %}500 - Server Error{% endblock %}

{% block content %}
<div class="text-center py-5">
    <h1 class="display-1">500</h1>
    <h2>Server Error</h2>
    <p class="lead mt-3">Sorry, something went wrong on our end. Please try again later.</p>
    <a href="{{ url_for('index') }}" class="btn btn-primary mt-3">
        <i class="fas fa-home mr-2"></i> Go Home
    </a>
</div>
{% endblock %}''')

write_file('templates/429.html', '''{% extends "base.html" %}

{% block title %}429 - Too Many Requests{% endblock %}

{% block content %}
<div class="text-center py-5">
    <h1 class="display-1">429</h1>
    <h2>Too Many Requests</h2>
    <p class="lead mt-3">Please slow down and try again in a moment.</p>
    <a href="{{ url_for('index') }}" class="btn btn-primary mt-3">
        <i class="fas fa-home mr-2"></i> Go Home
    </a>
</div>
{% endblock %}''')

# Create survey-related templates
write_file('templates/survey_expired.html', '''{% extends "base.html" %}

{% block title %}Survey Expired - {{ survey.title }}{% endblock %}

{% block content %}
<div class="text-center py-5">
    <div class="mb-4">
        <i class="fas fa-calendar-times fa-5x text-danger"></i>
    </div>
    <h1>Survey Expired</h1>
    <p class="lead">Sorry, this survey is no longer accepting responses.</p>
    
    <div class="card mt-4 mx-auto" style="max-width: 600px;">
        <div class="card-body">
            <h5>{{ survey.title }}</h5>
            <p>{{ survey.description }}</p>
            <p class="text-danger">
                <i class="fas fa-exclamation-circle"></i> 
                This survey expired and is no longer accepting responses.
            </p>
        </div>
    </div>
    
    <a href="{{ url_for('index') }}" class="btn btn-primary mt-4">
        <i class="fas fa-home mr-2"></i> Return to Home
    </a>
</div>
{% endblock %}''')

write_file('templates/survey_not_published.html', '''{% extends "base.html" %}

{% block title %}Survey Not Published - {{ survey.title }}{% endblock %}

{% block content %}
<div class="text-center py-5">
    <div class="mb-4">
        <i class="fas fa-eye-slash fa-5x text-warning"></i>
    </div>
    <h1>Survey Not Published</h1>
    <p class="lead">This survey is not yet available to the public.</p>
    
    <div class="card mt-4 mx-auto" style="max-width: 600px;">
        <div class="card-body">
            <h5>{{ survey.title }}</h5>
            <p>{{ survey.description }}</p>
            <p class="text-warning">
                <i class="fas fa-exclamation-circle"></i> 
                This survey has not been published by the creator yet.
            </p>
        </div>
    </div>
    
    <a href="{{ url_for('index') }}" class="btn btn-primary mt-4">
        <i class="fas fa-home mr-2"></i> Return to Home
    </a>
</div>
{% endblock %}''')

write_file('templates/archived_surveys.html', '''{% extends "base.html" %}

{% block title %}Archived Surveys{% endblock %}

{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4">
    <h1>Archived Surveys</h1>
    <a href="{{ url_for('index') }}" class="btn btn-outline-primary">
        <i class="fas fa-arrow-left"></i> Back to Active Surveys
    </a>
</div>

{% if surveys %}
    <div class="row">
        {% for survey in surveys %}
            <div class="col-md-6 col-lg-4 mb-4">
                <div class="card h-100">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <h5 class="mb-0">{{ survey.title }}</h5>
                        <span class="badge bg-secondary">Archived</span>
                    </div>
                    <div class="card-body">
                        <p class="card-text">{{ survey.description or "No description provided." }}</p>
                        <div class="d-flex justify-content-between align-items-center">
                            <small class="text-muted">Created: {{ survey.created_at }}</small>
                            <small class="text-muted">
                                <i class="fas fa-palette"></i> {{ survey.theme|capitalize }} theme
                            </small>
                        </div>
                    </div>
                    <div class="card-footer">
                        <div class="btn-group w-100">
                            <a href="{{ url_for('view_survey', survey_id=survey.id) }}" class="btn btn-outline-primary">
                                <i class="fas fa-eye"></i> View
                            </a>
                            <form action="{{ url_for('toggle_archive_survey', survey_id=survey.id) }}" method="POST" class="d-inline">
                                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                                <button type="submit" class="btn btn-outline-success">
                                    <i class="fas fa-undo"></i> Restore
                                </button>
                            </form>
                            <form action="{{ url_for('delete_survey', survey_id=survey.id) }}" method="POST" class="d-inline" 
                                  onsubmit="return confirm('Are you sure you want to permanently delete this survey? This action cannot be undone.')">
                                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                                <button type="submit" class="btn btn-outline-danger">
                                    <i class="fas fa-trash-alt"></i> Delete
                                </button>
                            </form>
                        </div>
                    </div>
                </div>
            </div>
        {% endfor %}
    </div>
{% else %}
    <div class="alert alert-info">
        <i class="fas fa-info-circle me-2"></i> You don't have any archived surveys.
    </div>
{% endif %}
{% endblock %}''')

write_file('templates/survey_pdf.html', '''{% extends "base.html" %}

{% block title %}Print - {{ survey.title }}{% endblock %}

{% block styles %}
{{ super() }}
<style>
    @media print {
        .no-print {
            display: none !important;
        }
        body {
            background-color: white !important;
            color: black !important;
        }
        .card {
            border: 1px solid #ddd !important;
            color: black !important;
            background-color: white !important;
            box-shadow: none !important;
        }
        .card-header {
            background-color: #f8f9fa !important;
            color: black !important;
        }
        .container {
            max-width: 100% !important;
        }
    }
    
    .print-question {
        margin-bottom: 2rem;
        padding-bottom: 1rem;
        border-bottom: 1px dotted #ccc;
    }
    
    .print-options {
        margin-top: 0.5rem;
    }
    
    .print-option {
        margin-bottom: 0.5rem;
    }
    
    .checkbox-placeholder {
        display: inline-block;
        width: 20px;
        height: 20px;
        border: 1px solid #aaa;
        margin-right: 10px;
        vertical-align: middle;
    }
    
    .line-placeholder {
        display: block;
        height: 1px;
        border-bottom: 1px solid #aaa;
        margin: 15px 0;
    }
</style>
{% endblock %}

{% block content %}
<div class="container my-4">
    <!-- Print button - won't show in actual printout -->
    <div class="mb-4 no-print">
        <button class="btn btn-primary" onclick="window.print()">
            <i class="fas fa-print me-2"></i> Print Survey
        </button>
        <a href="{{ url_for('view_survey', survey_id=survey.id) }}" class="btn btn-outline-secondary ms-2">
            <i class="fas fa-arrow-left me-1"></i> Back to Survey
        </a>
    </div>
    
    <!-- Survey header -->
    <div class="text-center mb-5">
        {% if survey.logo_image %}
            <img src="{{ survey.logo_image }}" alt="Survey logo" style="max-height: 80px; margin-bottom: 1rem;">
        {% endif %}
        <h1 class="mb-3">{{ survey.title }}</h1>
        {% if survey.description %}
            <p class="lead">{{ survey.description }}</p>
        {% endif %}
    </div>
    
    <!-- Survey questions -->
    <div class="questions-container">
        {% for question in questions %}
            <div class="print-question">
                <h4>{{ loop.index }}. {{ question.question_text }} {% if question.required %}*{% endif %}</h4>
                
                {% if question.question_type == 'multiple-choice' %}
                    <div class="print-options">
                        {% for option in question.options %}
                            <div class="print-option">
                                <span class="checkbox-placeholder"></span>
                                {{ option.option_text }}
                            </div>
                        {% endfor %}
                    </div>
                {% elif question.question_type == 'text' %}
                    <div class="print-options">
                        <div class="line-placeholder"></div>
                        <div class="line-placeholder"></div>
                        <div class="line-placeholder"></div>
                    </div>
                {% elif question.question_type == 'rating' %}
                    <div class="print-options">
                        <div class="d-flex justify-content-between mt-3" style="width: 300px">
                            <span>1</span>
                            <span>2</span>
                            <span>3</span>
                            <span>4</span>
                            <span>5</span>
                        </div>
                        <div class="d-flex justify-content-between mt-1" style="width: 300px">
                            {% for i in range(5) %}
                                <span class="checkbox-placeholder"></span>
                            {% endfor %}
                        </div>
                    </div>
                {% elif question.question_type == 'slider' %}
                    <div class="print-options">
                        <div class="d-flex justify-content-between mt-3" style="width: 500px">
                            <span>0</span>
                            <span>1</span>
                            <span>2</span>
                            <span>3</span>
                            <span>4</span>
                            <span>5</span>
                            <span>6</span>
                            <span>7</span>
                            <span>8</span>
                            <span>9</span>
                            <span>10</span>
                        </div>
                        <div class="d-flex justify-content-between mt-1" style="width: 500px">
                            {% for i in range(11) %}
                                <span class="checkbox-placeholder"></span>
                            {% endfor %}
                        </div>
                    </div>
                {% endif %}
            </div>
        {% endfor %}
    </div>
    
    <!-- Footer -->
    <div class="text-center mt-5">
        <p class="text-muted">Thank you for completing this survey!</p>
        <p class="text-muted small">Printed from Survey App on {{ now().strftime('%Y-%m-%d') }}</p>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script>
    document.addEventListener('DOMContentLoaded', function() {
        // Auto-print when the page loads (after a short delay to ensure everything is rendered)
        setTimeout(function() {
            window.print();
        }, 500);
    });
</script>
{% endblock %}''')

# Create environment file
write_file('.env.example', '''# Survey App Environment Variables
# Rename this file to .env and fill in your values

# Flask settings
FLASK_APP=app.py
FLASK_ENV=development  # Change to 'production' for production deployment
SECRET_KEY=your_secure_secret_key_here

# Database settings
DATABASE=survey.db

# Gemini API settings
GEMINI_API_KEY=AIzaSyA8R_U1pHmh78Qs3q1PWbAJF_qTgsDFGBc  # Replace with your API key

# Security settings
SESSION_COOKIE_SECURE=False  # Set to True for HTTPS only
SESSION_LIFETIME=1800  # Session timeout in seconds (30 minutes)''')

# Create requirements file
write_file('requirements.txt', '''Flask==2.0.1
gunicorn==20.1.0
requests==2.26.0
matplotlib==3.5.1
numpy==1.22.0
python-dotenv==0.19.2
Flask-WTF==1.0.0
pytest==6.2.5''')

# Create Procfile
write_file('Procfile', '''web: gunicorn app:app''')

print("\nSetup complete! All new template files have been created.")
print("Now you need to copy the main app.py file to your project directory.")
print("\nTo get started:")
print("1. Copy .env.example to .env and configure your settings")
print("2. Install the requirements with: pip install -r requirements.txt")
print("3. Run the application with: python app.py")
