from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, session, abort, Response, stream_with_context
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, PasswordField
from wtforms.validators import DataRequired, Email, Length
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import Integer, String, Date, Time, JSON, Boolean, DateTime, Text, TypeDecorator, Float, and_, or_, func, inspect, text, update
from sqlalchemy.types import TEXT
from datetime import datetime, time as dt_time, timedelta
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import random
import stripe
import os
import sys
import smtplib
import json
import re
import logging
import time
import uuid
import secrets
import csv
from flask_ckeditor import CKEditorField
from datetime import date
from functools import wraps
from urllib.parse import urlparse, quote

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from authlib.integrations.flask_client import OAuth
from werkzeug.middleware.proxy_fix import ProxyFix

try:
    from pathlib import Path
    from dotenv import load_dotenv

    # Load .env from this project directory whenever main is imported (web OR worker).
    # Without this, `python worker.py` often had an empty env while Flask had keys from elsewhere.
    load_dotenv(Path(__file__).resolve().parent / '.env')
    load_dotenv()
except ImportError:
    pass

APP_NAME = 'Scoreboard'
stripe.api_key = os.environ.get('STRIPE_API')

# ============================================================================
# DigitalOcean Spaces Configuration
# ============================================================================
DO_SPACES_KEY = os.environ.get('DO_SPACES_KEY')
DO_SPACES_SECRET = os.environ.get('DO_SPACES_SECRET')
DO_SPACES_REGION = os.environ.get('DO_SPACES_REGION', 'nyc3')
DO_SPACES_NAME = os.environ.get('DO_SPACES_NAME')
DO_SPACES_ENDPOINT = (
    f'https://{DO_SPACES_NAME}.{DO_SPACES_REGION}.cdn.digitaloceanspaces.com'
    if DO_SPACES_NAME
    else ''
)
DO_SPACES_BUCKET = DO_SPACES_NAME


app = Flask(__name__)
ckeditor = CKEditor(app)
Bootstrap5(app)


def _start_league_cache_warmup() -> None:
    import threading

    def _warm() -> None:
        try:
            from league_player_averages import warm_league_cache_for_today

            warm_league_cache_for_today()
        except Exception:
            logging.getLogger(__name__).exception("League cache warm-up failed")

    threading.Thread(
        target=_warm,
        name="league-cache-warmup",
        daemon=True,
    ).start()


_start_league_cache_warmup()


@app.template_filter('linkify_players')
def linkify_players_filter(text, player_map=None):
    from espn_mlb import linkify_player_names

    return linkify_player_names(text, player_map)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')

# Bulk list validation + DigitalOcean Spaces (worker + web)
bulk_email_logger = logging.getLogger('clawpod.bulk_email')
_spaces_logger = logging.getLogger('clawpod.spaces')

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
#os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
#os.environ.get('GOOGLE_CLIENT_SECRET', '')
DOMAIN = os.environ.get('DOMAIN', 'http://127.0.0.1:5000')
CANONICAL_BASE_URL = os.environ.get('CANONICAL_BASE_URL', DOMAIN)
SUPPORT_EMAIL = os.environ.get('SUPPORT_EMAIL', 'support@example.com')

#done on max@emailsconfirmed.com
#os.environ.get('DOMAIN', 'http://127.0.0.1:5002')
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.config["PREFERRED_URL_SCHEME"] = "https"
# Initialize OAuth
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return db.get_or_404(User, user_id)


def _safe_internal_redirect_path(url):
    """Allow relative in-app paths only (no scheme, no open redirects)."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not url.startswith('/') or url.startswith('//'):
        return None
    return url


# Session key for post-OAuth return (e.g. free tools landing with Google sign-in).
OAUTH_NEXT_SESSION_KEY = 'oauth_next'


# Decorator to require premium access
def premium_required(f):
    """Decorator to require premium_level > 0 for a route"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in to access this page.")
            return redirect(url_for('login'))
        
        if current_user.premium_level <= 0:
            return redirect(url_for('price_page'))
        
        return f(*args, **kwargs)
    return decorated_function

class Base(DeclarativeBase):
    pass

# Custom JSON type that handles empty strings and invalid JSON gracefully
# This wraps SQLAlchemy's JSON type to handle invalid data
class SafeJSON(JSON):
    """A JSON type that handles empty strings and invalid JSON gracefully."""
    
    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            if value == '' or value == 'null':
                return None
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                # If JSON parsing fails, return None instead of raising an error
                return None
        # If it's already parsed (dict/list), return as-is
        return value

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DB_URI", 'sqlite:///users.db')
_db_uri = app.config['SQLALCHEMY_DATABASE_URI'] or ''
if _db_uri.startswith('sqlite'):
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'connect_args': {'check_same_thread': False}}
else:
    # Postgres (e.g. Render): recycle before server SSL idle cutoff; pre-ping avoids
    # "SSL error: decryption failed or bad record mac" on stale pooled connections.
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 280,
    }
db = SQLAlchemy(model_class=Base)
db.init_app(app)


@app.context_processor
def inject_support_contact():
    return {
        'support_email': SUPPORT_EMAIL,
        'help_mailto_subject': quote('Scoreboard - Help request', safe=''),
    }


# ============================================================================
# DigitalOcean Spaces Helper Functions
# ============================================================================

def get_spaces_client():
    """Create and return a boto3 S3 client configured for DigitalOcean Spaces"""
    session = boto3.session.Session()
    client = session.client('s3',
                            region_name=DO_SPACES_REGION,
                            endpoint_url=f'https://{DO_SPACES_REGION}.digitaloceanspaces.com',
                            aws_access_key_id=DO_SPACES_KEY,
                            aws_secret_access_key=DO_SPACES_SECRET)
    return client

def upload_file_to_spaces(file_path, spaces_key, content_type=None):
    """
    Upload a file to DigitalOcean Spaces.
    
    Args:
        file_path: Local path to the file to upload
        spaces_key: Key (path) in Spaces (e.g., 'clips/user_id/episode_guid/{episode_title}_1.mp4')
        content_type: MIME type of the file (optional, will be guessed if not provided)
    
    Returns:
        str: URL of the uploaded file, or None if upload failed
    """
    try:
        client = get_spaces_client()
        
        # Determine content type if not provided
        if not content_type:
            if file_path.endswith('.mp4'):
                content_type = 'video/mp4'
            elif file_path.endswith('.mp3'):
                content_type = 'audio/mpeg'
            elif file_path.endswith('.jpg') or file_path.endswith('.jpeg'):
                content_type = 'image/jpeg'
            elif file_path.endswith('.png'):
                content_type = 'image/png'
            else:
                content_type = 'application/octet-stream'
        
        # Upload file
        with open(file_path, 'rb') as file_data:
            client.upload_fileobj(
                file_data,
                DO_SPACES_BUCKET,
                spaces_key,
                ExtraArgs={'ContentType': content_type, 'ACL': 'private'}
            )
        
        # Return the CDN URL (for reference, but files are private)
        return f"{DO_SPACES_ENDPOINT}/{spaces_key}"
    except Exception as e:
        print(f"Error uploading file to Spaces: {str(e)}")
        return None

def generate_signed_url(spaces_key, expiration=3600, download=False, filename=None):
    """
    Generate a signed URL for a private file in DigitalOcean Spaces.
    
    Args:
        spaces_key: Key (path) in Spaces (e.g., 'clips/user_id/episode_guid/{episode_title}_1.mp4')
        expiration: URL expiration time in seconds (default: 1 hour)
        download: If True, add Content-Disposition header to force download
        filename: Filename for download (if None, extracts from spaces_key)
    
    Returns:
        str: Signed URL, or None if generation failed
    """
    try:
        client = get_spaces_client()
        
        params = {'Bucket': DO_SPACES_BUCKET, 'Key': spaces_key}
        
        # Add download headers if requested
        if download:
            if not filename:
                # Extract filename from spaces_key
                filename = os.path.basename(spaces_key)
            params['ResponseContentDisposition'] = f'attachment; filename="{filename}"'
        
        url = client.generate_presigned_url(
            'get_object',
            Params=params,
            ExpiresIn=expiration
        )
        return url
    except Exception as e:
        print(f"Error generating signed URL: {str(e)}")
        return None

def file_exists_in_spaces(spaces_key):
    """
    Check if a file exists in DigitalOcean Spaces.
    
    Args:
        spaces_key: Key (path) in Spaces
    
    Returns:
        bool: True if file exists, False otherwise
    """
    try:
        client = get_spaces_client()
        client.head_object(Bucket=DO_SPACES_BUCKET, Key=spaces_key)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False
        raise
    except Exception as e:
        print(f"Error checking file existence in Spaces: {str(e)}")
        return False

def delete_file_from_spaces(spaces_key):
    """
    Delete a file from DigitalOcean Spaces.
    
    Args:
        spaces_key: Key (path) in Spaces
    
    Returns:
        bool: True if deletion was successful, False otherwise
    """
    try:
        client = get_spaces_client()
        client.delete_object(Bucket=DO_SPACES_BUCKET, Key=spaces_key)
        return True
    except Exception as e:
        _spaces_logger.warning("🗑️ delete_object failed | key=%r | %s", spaces_key, e)
        return False


def upload_bytes_to_spaces_public(file_bytes, spaces_key, content_type='application/octet-stream'):
    """
    Upload raw bytes with public-read ACL when a URL must be fetchable without signing (e.g. CDN assets).
    Falls back to put_object without ACL if the bucket rejects ACLs (Bucket owner enforced).
    """
    if not DO_SPACES_KEY or not DO_SPACES_SECRET or not DO_SPACES_BUCKET:
        return None
    try:
        client = get_spaces_client()
        try:
            client.put_object(
                Bucket=DO_SPACES_BUCKET,
                Key=spaces_key,
                Body=file_bytes,
                ContentType=content_type,
                ACL='public-read',
            )
        except ClientError as e:
            err = (e.response.get('Error') or {}).get('Code') or ''
            if err in ('AccessControlListNotSupported', 'InvalidRequest'):
                client.put_object(
                    Bucket=DO_SPACES_BUCKET,
                    Key=spaces_key,
                    Body=file_bytes,
                    ContentType=content_type,
                )
            else:
                raise
        return f"{DO_SPACES_ENDPOINT}/{spaces_key}"
    except Exception as e:
        _spaces_logger.warning("☁️ Public upload failed | key=%r | %s", spaces_key, e)
        return None


def upload_bytes_to_spaces_private(file_bytes, spaces_key, content_type='application/octet-stream'):
    """Upload raw bytes with private ACL (same pattern as upload_file_to_spaces)."""
    if not DO_SPACES_KEY or not DO_SPACES_SECRET or not DO_SPACES_BUCKET:
        _spaces_logger.warning(
            "🔑 Private upload skipped — missing Spaces env | key=%r",
            spaces_key,
        )
        return None
    try:
        client = get_spaces_client()
        try:
            client.put_object(
                Bucket=DO_SPACES_BUCKET,
                Key=spaces_key,
                Body=file_bytes,
                ContentType=content_type,
                ACL='private',
            )
        except ClientError as e:
            err = (e.response.get('Error') or {}).get('Code') or ''
            if err in ('AccessControlListNotSupported', 'InvalidRequest'):
                client.put_object(
                    Bucket=DO_SPACES_BUCKET,
                    Key=spaces_key,
                    Body=file_bytes,
                    ContentType=content_type,
                )
            else:
                raise
        return f"{DO_SPACES_ENDPOINT}/{spaces_key}"
    except Exception as e:
        _spaces_logger.warning("☁️ Private upload failed | key=%r | %s", spaces_key, e)
        return None


def get_object_bytes_from_spaces(spaces_key: str) -> tuple[bytes | None, str | None]:
    """
    Download object body from Spaces.
    Returns (data, None) on success, (None, error_message) on failure.
    """
    if not (spaces_key and str(spaces_key).strip()):
        _spaces_logger.error("📭 get_object called with empty key")
        return None, '📭 Missing file location for this job (internal error).'
    if not DO_SPACES_KEY or not DO_SPACES_SECRET or not DO_SPACES_BUCKET:
        _spaces_logger.error(
            "🔑 Spaces env incomplete | has_key=%s has_secret=%s has_bucket=%s",
            bool(DO_SPACES_KEY),
            bool(DO_SPACES_SECRET),
            bool(DO_SPACES_BUCKET),
        )
        return None, (
            '🔑 Cloud storage isn’t configured here (need DO_SPACES_KEY, DO_SPACES_SECRET, DO_SPACES_NAME). '
            'Your background worker must use the same variables as the web app.'
        )
    try:
        client = get_spaces_client()
        obj = client.get_object(Bucket=DO_SPACES_BUCKET, Key=spaces_key)
        data = obj['Body'].read()
        bulk_email_logger.debug("☁️ Downloaded %s bytes from Spaces | key=%r", len(data), spaces_key)
        return data, None
    except ClientError as e:
        err = e.response.get('Error') or {}
        code = err.get('Code', '')
        msg = err.get('Message', str(e))
        tech = f'{code}: {msg} | region={DO_SPACES_REGION!r} bucket={DO_SPACES_BUCKET!r} key={spaces_key!r}'
        _spaces_logger.error("☁️ Spaces get_object failed | %s", tech)
        user = f'☁️ Couldn’t download your list from storage ({code}). If the file was just uploaded, check worker credentials and region.'
        if code == 'NoSuchKey':
            user = '☁️ That list file is no longer in storage (it may have been deleted or the path is wrong).'
        return None, f'{user} — {msg}'[:2000]
    except Exception as e:
        tech = f'{e!s} | region={DO_SPACES_REGION!r} bucket={DO_SPACES_BUCKET!r} key={spaces_key!r}'
        _spaces_logger.exception("☁️ Spaces download unexpected error | %s", tech)
        return None, f'☁️ Unexpected error reading your file from storage: {e!s}'[:2000]

# Create a form to register new users
class RegisterForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired() ])
    password = PasswordField("Password", validators=[DataRequired()])
    name = StringField("Name", validators=[DataRequired()])
    submit = SubmitField("Sign Me Up!")

# Create a form to login existing users
class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Let Me In!")

class ChangePassword(FlaskForm):
    email = StringField("Email", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    new_password = PasswordField("New Password", validators=[DataRequired()])
    submit = SubmitField("Change Password")

class Feedback_Form(FlaskForm):
    title = StringField("Short Title", validators=[DataRequired()])
    feedback = StringField("Feedback", validators=[DataRequired()])
    submit = SubmitField("Provide Feedback")

class BlogForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired()])
    content = CKEditorField("Content", validators=[DataRequired()])
    submit = SubmitField("Publish Blog Post")

class DiscountForm(FlaskForm):
    discount_code = StringField("Discount Code", validators=[DataRequired()])
    discount_percentage = StringField("Discount Percentage", validators=[DataRequired()])
    discount_start_date = StringField("Start Date (YYYY-MM-DD)", validators=[])
    discount_end_date = StringField("End Date (YYYY-MM-DD)", validators=[DataRequired()])
    submit = SubmitField("Save Discount")

#user DB
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(100), unique=True)
    password: Mapped[str] = mapped_column(String(100), nullable=True)  # Nullable for OAuth users
    name: Mapped[str] = mapped_column(String(100))
    premium_level: Mapped[int] = mapped_column(Integer, default=0)
    date_of_signup: Mapped[Date] = mapped_column(Date)
    end_date_premium: Mapped[Date] = mapped_column(Date, nullable=True)
    stripe_customer_id: Mapped[str] = mapped_column(String(200), nullable=True)
    stripe_active_subscription: Mapped[bool] = mapped_column(Boolean, default=False)
    rss_feeds: Mapped[JSON] = mapped_column(JSON, default=lambda: [], nullable=True)
    last_episode_guid: Mapped[str] = mapped_column(String(500), nullable=True)
    last_episode_date: Mapped[Date] = mapped_column(Date, nullable=True)
    last_rss_check: Mapped[Date] = mapped_column(Date, nullable=True)
    episodes_processed: Mapped[int] = mapped_column(Integer, default=0)
    # OAuth fields
    auth_provider: Mapped[str] = mapped_column(String(50), nullable=True)  # 'google' or None for password
    oauth_id: Mapped[str] = mapped_column(String(200), nullable=True)  # Google user ID

# Add new association table for upvotes
class FeedbackUpvote(db.Model):
    __tablename__ = "feedback_upvotes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))
    feedback_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("feedback.id"))

# Update Feedback class to include relationship
class Feedback(db.Model):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(50))
    feedback: Mapped[str] = mapped_column(String())
    upvote_count: Mapped[int] = mapped_column(Integer)
    # Add relationship to track upvoters
    upvoters = relationship('User', secondary='feedback_upvotes', backref='upvoted_feedback')

class blog_posts(db.Model):
    __tablename__ = "blog_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    subtitle: Mapped[str] = mapped_column(String(200))
    date: Mapped[Date] = mapped_column(Date)
    content: Mapped[str] = mapped_column(String())
    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))

# Bulk Upload Queue - async jobs (e.g. email list validation); file staged on DO Spaces
# Statuses: pending -> processing -> completed | failed
class BulkUploadQueue(db.Model):
    __tablename__ = "bulk_upload_queue"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))
    file_name: Mapped[str] = mapped_column(String(500))
    file_url: Mapped[str] = mapped_column(String(1000))
    spaces_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    job_type: Mapped[str] = mapped_column(String(50), default='email_list')
    job_metadata: Mapped[dict | None] = mapped_column(SafeJSON, nullable=True)
    progress_processed: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(SafeJSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default='pending')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)


class Notification(db.Model):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))
    message: Mapped[str] = mapped_column(String(500))
    type: Mapped[str] = mapped_column(String(50), default="episode_ready")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

class Preferences(db.Model):
    __tablename__ = "preferences"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"), unique=True)
    background_color: Mapped[str] = mapped_column(String(7), nullable=True)  # Hex color like #xxxxxx

class Blog(db.Model):
    __tablename__ = "blogs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    author = relationship("User", backref="blogs")

# Stripe Log - for tracking Stripe API interactions
class StripeLog(db.Model):
    __tablename__ = "stripe_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100))
    user_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"), nullable=True)
    stripe_customer_id: Mapped[str] = mapped_column(String(200), nullable=True)
    request_data: Mapped[str] = mapped_column(Text, nullable=True)
    response_data: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default='pending')
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

class Discounts(db.Model):
    __tablename__ = "discounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    discount_code: Mapped[str] = mapped_column(String(100), nullable=True)
    discount_percentage: Mapped[float] = mapped_column(Float, nullable=True, default=0.0)
    discount_start_date: Mapped[Date] = mapped_column(Date, nullable=True, default=None) 
    discount_end_date: Mapped[Date] = mapped_column(Date, nullable=True, default=None) 
    Filler1: Mapped[str] = mapped_column(String(500), nullable=True, default=None) 
    Filler2: Mapped[str] = mapped_column(String(500), nullable=True, default=None) 
    Filler3: Mapped[str] = mapped_column(String(500), nullable=True, default=None) 


class EmailValidationRun(db.Model):
    __tablename__ = "email_validation_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"), nullable=True)
    email: Mapped[str] = mapped_column(String(500), nullable=False)  # single email or literal "LIST"
    valid_count: Mapped[int] = mapped_column(Integer, default=0)
    invalid_count: Mapped[int] = mapped_column(Integer, default=0)
    other_count: Mapped[int] = mapped_column(Integer, default=0)  # e.g. risky
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    run_time: Mapped[dt_time] = mapped_column(Time, nullable=False)
    misc1: Mapped[str] = mapped_column(String(500), nullable=True, default=None)
    misc2: Mapped[str] = mapped_column(String(500), nullable=True, default=None)
    misc3: Mapped[str] = mapped_column(String(500), nullable=True, default=None)
    misc4: Mapped[str] = mapped_column(String(500), nullable=True, default=None)
    misc5: Mapped[str] = mapped_column(String(500), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


def _record_email_validation_run(
    email_value: str,
    valid_count: int,
    invalid_count: int,
    other_count: int,
    total_count: int,
    user_id: int | None = None,
):
    """Persist one validation run stats row without breaking API responses on failure."""
    try:
        now = datetime.now()
        uid = user_id
        if uid is None and current_user.is_authenticated:
            uid = current_user.id
        rec = EmailValidationRun(
            user_id=uid,
            email=(email_value or "").strip()[:500],
            valid_count=max(0, int(valid_count)),
            invalid_count=max(0, int(invalid_count)),
            other_count=max(0, int(other_count)),
            total_count=max(0, int(total_count)),
            run_date=now.date(),
            run_time=now.time(),
        )
        db.session.add(rec)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error recording email validation run: {str(e)}")


def _detect_list_delimiter(sample_lines: list[str]) -> str | None:
    candidates = [',', '\t', ';']
    best = None
    best_score = 0
    for delim in candidates:
        score = 0
        for line in sample_lines:
            score += line.count(delim)
        if score > best_score:
            best_score = score
            best = delim
    return best if best_score > 0 else None


def _parse_email_list_file_text(text: str) -> list[list[str]]:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    delim = _detect_list_delimiter(lines[:8])
    if delim is None:
        return [[ln.strip()] for ln in lines]
    rows = []
    reader = csv.reader(lines, delimiter=delim)
    for row in reader:
        rows.append([c.strip() for c in row])
    return [r for r in rows if any(c.strip() for c in r)]


def _extract_emails_for_bulk_validation(
    rows: list[list[str]],
    has_header: bool,
    col_index: int,
    max_batch: int,
):
    start = 1 if has_header else 0
    raw_count = 0
    cleaned = []
    for i in range(start, len(rows)):
        row = rows[i]
        if col_index >= len(row):
            continue
        v = row[col_index].strip()
        if not v:
            continue
        raw_count += 1
        if len(cleaned) < max_batch:
            cleaned.append(v)
    truncated = raw_count > len(cleaned)
    return cleaned, raw_count, truncated


def _validate_cleaned_email_list(cleaned_emails: list[str]):
    from email_validation import validate_single_email

    results = []
    counts = {'valid': 0, 'risky': 0, 'invalid': 0}
    for email in cleaned_emails:
        result = validate_single_email(email)
        status = result.get('report', {}).get('status', 'invalid')
        if status == 'valid':
            counts['valid'] += 1
        elif status == 'risky':
            counts['risky'] += 1
        else:
            counts['invalid'] += 1
        results.append({
            'input_email': email,
            'status': status,
            'summary': result.get('summary', ''),
            'normalized_email': result.get('normalized_email'),
            'result': result,
        })
    return counts, results


# After each failed run, retry_count increments; retry while retry_count <= this (5 retries after first failure).
EMAIL_LIST_BULK_MAX_RETRIES = 5


def _fail_email_list_bulk_job(job: BulkUploadQueue, message: str) -> None:
    job.retry_count = int(job.retry_count or 0) + 1
    base = (message or 'Unknown error').strip()
    rc = job.retry_count
    if rc > EMAIL_LIST_BULK_MAX_RETRIES:
        retry_note = (
            f"\n\n🛑 Max automatic retries reached ({EMAIL_LIST_BULK_MAX_RETRIES}). "
            "Please upload your list again or contact support if this keeps happening."
        )
        bulk_email_logger.error(
            "🛑 Bulk job #%s permanent failure | user=%s | failures=%s | %s",
            job.id,
            job.user_id,
            rc,
            base[:800],
        )
    else:
        retry_note = (
            f"\n\n🔁 We’ll retry automatically (failure #{rc}; up to {EMAIL_LIST_BULK_MAX_RETRIES} retries)."
        )
        bulk_email_logger.warning(
            "⚠️ Bulk job #%s failed | user=%s | failure #%s | %s",
            job.id,
            job.user_id,
            rc,
            base[:800],
        )
    _bulk_msg_prefixes = ('❌', '⚠️', '🔑', '☁️', '📭', '📧', '📄', '🛑', '🔁', '✅', 'ℹ️', '🔒', '⭐', '⏳', '📎', '⚙️')
    if base and not base.startswith(_bulk_msg_prefixes):
        base = f"❌ {base}"
    job.error_message = (base + retry_note)[:2000]
    job.completed_at = datetime.now()
    job.status = 'failed'
    job.result_json = None
    flag_modified(job, 'result_json')
    db.session.commit()


def claim_next_email_list_job() -> int | None:
    """
    Atomically claim the next email_list job: pending first, then failed rows eligible for retry.
    Returns job id, or None if no job was available or lost a race to another worker.
    """
    pending_id = db.session.execute(
        db.select(BulkUploadQueue.id)
        .where(BulkUploadQueue.job_type == 'email_list', BulkUploadQueue.status == 'pending')
        .order_by(BulkUploadQueue.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()
    if pending_id is not None:
        res = db.session.execute(
            update(BulkUploadQueue)
            .where(BulkUploadQueue.id == pending_id, BulkUploadQueue.status == 'pending')
            .values(status='processing', progress_processed=0)
        )
        db.session.commit()
        if res.rowcount == 1:
            bulk_email_logger.info("📥 Claimed NEW bulk email job #%s (was pending)", pending_id)
            return pending_id

    failed_id = db.session.execute(
        db.select(BulkUploadQueue.id)
        .where(
            BulkUploadQueue.job_type == 'email_list',
            BulkUploadQueue.status == 'failed',
            BulkUploadQueue.retry_count <= EMAIL_LIST_BULK_MAX_RETRIES,
        )
        .order_by(BulkUploadQueue.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()
    if failed_id is None:
        return None
    res = db.session.execute(
        update(BulkUploadQueue)
        .where(
            BulkUploadQueue.id == failed_id,
            BulkUploadQueue.status == 'failed',
            BulkUploadQueue.retry_count <= EMAIL_LIST_BULK_MAX_RETRIES,
        )
        .values(
            status='processing',
            progress_processed=0,
            progress_total=None,
            error_message=None,
            completed_at=None,
            result_json=None,
        )
    )
    db.session.commit()
    if res.rowcount != 1:
        return None
    bulk_email_logger.info("🔁 Claimed RETRY bulk email job #%s (was failed, still eligible)", failed_id)
    return failed_id


def process_email_list_bulk_job(job_id: int) -> None:
    """
    Run bulk email validation for a queue row already claimed (status=processing).
    Must be called inside Flask application context.
    """
    sk = None
    job = db.session.get(BulkUploadQueue, job_id)
    if not job or job.job_type != 'email_list':
        bulk_email_logger.warning("⏭️ Skip job #%s — missing row or wrong job_type", job_id)
        return
    if job.status != 'processing':
        bulk_email_logger.debug("⏭️ Skip job #%s — status=%r (expected processing)", job_id, job.status)
        return
    sk = job.spaces_key
    if not sk:
        bulk_email_logger.error("📭 Job #%s has no spaces_key | user=%s", job_id, job.user_id)
        _fail_email_list_bulk_job(job, '📭 Missing file reference for this job (nothing to download).')
        return
    bulk_email_logger.info(
        "▶️ Processing bulk job #%s | user=%s | file=%r | spaces_key=%r",
        job_id,
        job.user_id,
        job.file_name,
        sk,
    )
    meta = job.job_metadata or {}
    has_header = bool(meta.get('has_header'))
    col_index = int(meta.get('email_column_index', 0))
    max_batch_size = 5000
    try:
        raw, dl_err = get_object_bytes_from_spaces(sk)
        if raw is None:
            raise RuntimeError(dl_err or '☁️ Could not download list file from storage.')
        file_text = raw.decode('utf-8-sig', errors='replace')
        rows = _parse_email_list_file_text(file_text)
        if not rows:
            raise ValueError('📄 Your file has no usable rows. Check the format and try again.')
        emails, _raw_n, truncated = _extract_emails_for_bulk_validation(
            rows, has_header, col_index, max_batch_size
        )
        if not emails:
            raise ValueError(
                '📧 No email addresses found in the column you mapped. Choose the column that contains emails.'
            )
        job.progress_total = len(emails)
        job.progress_processed = 0
        db.session.commit()

        from email_validation import validate_single_email

        counts = {'valid': 0, 'risky': 0, 'invalid': 0}
        results = []
        for idx, email in enumerate(emails):
            result = validate_single_email(email)
            status = result.get('report', {}).get('status', 'invalid')
            if status == 'valid':
                counts['valid'] += 1
            elif status == 'risky':
                counts['risky'] += 1
            else:
                counts['invalid'] += 1
            results.append({
                'input_email': email,
                'status': status,
                'summary': result.get('summary', ''),
                'normalized_email': result.get('normalized_email'),
                'result': result,
            })
            if (idx + 1) % 25 == 0 or (idx + 1) == len(emails):
                job.progress_processed = idx + 1
                db.session.commit()

        export_rows = [list(r) for r in rows]
        job.result_json = {
            'processed': len(emails),
            'truncated': truncated,
            'max_batch_size': max_batch_size,
            'counts': counts,
            'results': results,
            'export_rows': export_rows,
            'export_has_header': has_header,
            'export_email_column_index': col_index,
        }
        job.status = 'completed'
        job.retry_count = 0
        job.completed_at = datetime.now()
        job.progress_processed = len(emails)
        flag_modified(job, 'result_json')
        db.session.commit()

        _record_email_validation_run(
            email_value='LIST',
            valid_count=counts['valid'],
            invalid_count=counts['invalid'],
            other_count=counts['risky'],
            total_count=len(emails),
            user_id=job.user_id,
        )
        bulk_email_logger.info(
            "✅ Bulk job #%s finished | user=%s | processed=%s | valid=%s | invalid=%s | risky=%s",
            job_id,
            job.user_id,
            len(emails),
            counts['valid'],
            counts['invalid'],
            counts['risky'],
        )
    except Exception as e:
        db.session.rollback()
        job = db.session.get(BulkUploadQueue, job_id)
        if job:
            _fail_email_list_bulk_job(job, str(e))
    finally:
        if not sk:
            return
        job_final = db.session.get(BulkUploadQueue, job_id)
        if not job_final:
            delete_file_from_spaces(sk)
            return
        rc = int(job_final.retry_count or 0)
        if job_final.status == 'completed':
            if delete_file_from_spaces(sk):
                bulk_email_logger.info("🗑️ Removed staged list from Spaces | job=%s | key=%r", job_id, sk)
            else:
                bulk_email_logger.warning("🗑️ Could not delete staged list from Spaces | job=%s | key=%r", job_id, sk)
        elif job_final.status == 'failed' and rc > EMAIL_LIST_BULK_MAX_RETRIES:
            if delete_file_from_spaces(sk):
                bulk_email_logger.info("🗑️ Removed staged list after max retries | job=%s | key=%r", job_id, sk)
            else:
                bulk_email_logger.warning("🗑️ Could not delete staged list after failure | job=%s | key=%r", job_id, sk)


with app.app_context():
    db.create_all()
    if inspect(db.engine).has_table("bulk_upload_queue"):
        bulk_cols = {c["name"] for c in inspect(db.engine).get_columns("bulk_upload_queue")}
        bulk_alters = []
        if "spaces_key" not in bulk_cols:
            bulk_alters.append("ALTER TABLE bulk_upload_queue ADD COLUMN spaces_key VARCHAR(1000)")
        if "job_type" not in bulk_cols:
            bulk_alters.append("ALTER TABLE bulk_upload_queue ADD COLUMN job_type VARCHAR(50) DEFAULT 'email_list'")
        if "job_metadata" not in bulk_cols:
            bulk_alters.append("ALTER TABLE bulk_upload_queue ADD COLUMN job_metadata TEXT")
        if "progress_processed" not in bulk_cols:
            bulk_alters.append("ALTER TABLE bulk_upload_queue ADD COLUMN progress_processed INTEGER DEFAULT 0")
        if "progress_total" not in bulk_cols:
            bulk_alters.append("ALTER TABLE bulk_upload_queue ADD COLUMN progress_total INTEGER")
        if "result_json" not in bulk_cols:
            bulk_alters.append("ALTER TABLE bulk_upload_queue ADD COLUMN result_json TEXT")
        for stmt in bulk_alters:
            try:
                db.session.execute(text(stmt))
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"bulk_upload_queue migration skip: {stmt} ({e})")

@app.route('/', methods=["GET"])
def home_page():
    from espn_mlb import fetch_standings, scoreboard_snapshot

    snapshot = scoreboard_snapshot()
    return render_template(
        "scoreboard.html",
        today=snapshot["today"],
        yesterday=snapshot["yesterday"],
        today_games=snapshot["today_games"],
        yesterday_games=snapshot["yesterday_games"],
        upcoming_date=snapshot["upcoming_date"],
        upcoming_games=snapshot["upcoming_games"],
        standings=fetch_standings(),
    )


@app.route('/api/mlb/search', methods=['GET'], endpoint='api_mlb_search')
def api_mlb_search():
    from mlb_search import search_mlb

    query = request.args.get('q', '')
    return jsonify(search_mlb(query))


@app.route('/api/mlb/scoreboard', methods=['GET'])
def api_mlb_scoreboard():
    from espn_mlb import fetch_scoreboard

    date_param = request.args.get('date')
    if date_param:
        try:
            game_date = datetime.strptime(date_param, '%Y%m%d').date()
        except ValueError:
            return jsonify({'error': 'date must be YYYYMMDD'}), 400
    else:
        game_date = date.today()

    games = fetch_scoreboard(game_date)
    return jsonify({
        'date': game_date.isoformat(),
        'games': games,
    })


@app.route('/api/mlb/scoreboard/today', methods=['GET'], endpoint='api_mlb_scoreboard_today')
def api_mlb_scoreboard_today():
    from espn_mlb import fetch_scoreboard

    today = date.today()
    games = fetch_scoreboard(today, force_refresh=True)
    return jsonify({
        'date': today.isoformat(),
        'games': games,
        'has_live': any(game.get('status_state') == 'in' for game in games),
    })


@app.route('/game/<game_id>', methods=['GET'], endpoint='mlb_game_page')
def mlb_game_page(game_id):
    from espn_mlb import fetch_game_summary, fetch_scoreboard, strip_initial_page

    try:
        game = fetch_game_summary(str(game_id))
    except (requests.RequestException, ValueError):
        abort(404)

    strip_games = fetch_scoreboard(date.today())

    template = "game_live.html"
    return render_template(
        template,
        game=game,
        strip_games=strip_games,
        current_game_id=str(game_id),
        strip_initial_page=strip_initial_page(strip_games, str(game_id)),
    )


@app.route('/api/mlb/game/<game_id>', methods=['GET'], endpoint='api_mlb_game')
def api_mlb_game(game_id):
    from espn_mlb import fetch_game_summary, fetch_scoreboard

    try:
        game = fetch_game_summary(str(game_id), force_refresh=True)
    except (requests.RequestException, ValueError):
        return jsonify({'error': 'Game not found'}), 404

    strip_games = fetch_scoreboard(date.today(), force_refresh=True)
    return jsonify({'game': game, 'strip_games': strip_games})


@app.route('/api/mlb/game/<game_id>/preview', methods=['GET'], endpoint='api_mlb_game_preview')
def api_mlb_game_preview(game_id):
    from espn_mlb import attach_preview_team_panels, fetch_game_summary

    try:
        game = fetch_game_summary(str(game_id))
    except (requests.RequestException, ValueError):
        return jsonify({'error': 'Game not found'}), 404

    if game.get('status_state') != 'pre':
        return jsonify({'error': 'Not a preview game'}), 404

    game.setdefault('preview', {})
    attach_preview_team_panels(game)

    matchup_leaders = game.get('preview', {}).get('matchup_leaders')
    team_panels = game.get('preview', {}).get('team_panels')

    return jsonify({
        'leaders_html': (
            render_template('partials/game_preview_team_leaders.html', game=game)
            if matchup_leaders
            else ''
        ),
        'rosters_html': (
            render_template('partials/game_preview_team_rosters.html', game=game)
            if team_panels
            else ''
        ),
    })


@app.route(
    '/api/mlb/game/<game_id>/preview/pitchers',
    methods=['GET'],
    endpoint='api_mlb_game_preview_pitchers',
)
def api_mlb_game_preview_pitchers(game_id):
    from espn_mlb import attach_preview_probable_pitchers, fetch_game_summary

    try:
        game = fetch_game_summary(str(game_id))
    except (requests.RequestException, ValueError):
        return jsonify({'error': 'Game not found'}), 404

    if game.get('status_state') != 'pre':
        return jsonify({'error': 'Not a preview game'}), 404

    has_probables = (game.get('away') or {}).get('probable_pitcher') or (
        game.get('home') or {}
    ).get('probable_pitcher')
    if has_probables:
        attach_preview_probable_pitchers(game)

    return jsonify({
        'probable_stats_html': (
            render_template('partials/game_probable_pitchers_stats.html', game=game)
            if has_probables
            else ''
        ),
    })


@app.route(
    '/api/mlb/game/<game_id>/preview/team-stats',
    methods=['GET'],
    endpoint='api_mlb_game_preview_team_stats',
)
def api_mlb_game_preview_team_stats(game_id):
    from espn_mlb import attach_preview_season_team_stats, fetch_game_summary

    try:
        game = fetch_game_summary(str(game_id))
    except (requests.RequestException, ValueError):
        return jsonify({'error': 'Game not found'}), 404

    if game.get('status_state') != 'pre':
        return jsonify({'error': 'Not a preview game'}), 404

    game.setdefault('preview', {})
    attach_preview_season_team_stats(game)

    matchup = game.get('preview', {}).get('season_team_matchup')
    return jsonify({
        'team_stats_html': (
            render_template('partials/game_preview_team_stats.html', game=game)
            if matchup
            else ''
        ),
    })


@app.route('/team/<team_id>', methods=['GET'], endpoint='mlb_team_page')
def mlb_team_page(team_id):
    from espn_mlb import fetch_scoreboard, fetch_team, strip_initial_page_for_team

    try:
        team = fetch_team(str(team_id), include_stats=False)
    except (requests.RequestException, ValueError):
        abort(404)

    strip_games = fetch_scoreboard(date.today())

    return render_template(
        'team.html',
        team=team,
        strip_games=strip_games,
        strip_initial_page=strip_initial_page_for_team(strip_games, str(team_id)),
        current_game_id='',
    )


@app.route('/api/mlb/team/<team_id>/stats', methods=['GET'], endpoint='api_mlb_team_stats')
def api_mlb_team_stats(team_id):
    from espn_mlb import fetch_team, fetch_team_stats, fetch_team_team_stats_panel

    try:
        team = fetch_team(str(team_id), include_stats=False)
    except (requests.RequestException, ValueError):
        return jsonify({'error': 'Team not found'}), 404

    stats_table = fetch_team_stats(team_id, team.get('season_year'))
    stat_panels: list = []
    team_stats_panel = fetch_team_team_stats_panel(
        str(team_id),
        season_year=team.get('season_year'),
    )
    if team_stats_panel:
        stat_panels.append(team_stats_panel)
    if not stats_table and not stat_panels:
        return jsonify({'error': 'Stats unavailable'}), 404

    return jsonify({
        'stats_table': stats_table,
        'stat_panels': stat_panels,
    })


@app.route('/api/mlb/team/<team_id>/stats/schedule', methods=['GET'], endpoint='api_mlb_team_stats_schedule')
def api_mlb_team_stats_schedule(team_id):
    from espn_mlb import fetch_team, fetch_team_schedule_stat_panel

    try:
        team = fetch_team(str(team_id), include_stats=False)
    except (requests.RequestException, ValueError):
        return jsonify({'error': 'Team not found'}), 404

    stat_panel = fetch_team_schedule_stat_panel(
        str(team_id),
        season_year=team.get('season_year'),
    )
    if not stat_panel:
        return jsonify({'error': 'Schedule unavailable'}), 404

    return jsonify({'stat_panel': stat_panel})


@app.route('/api/mlb/team/<team_id>/stats/roster', methods=['GET'], endpoint='api_mlb_team_stats_roster')
def api_mlb_team_stats_roster(team_id):
    from espn_mlb import fetch_team, fetch_team_roster_stat_panel

    try:
        team = fetch_team(str(team_id), include_stats=False)
    except (requests.RequestException, ValueError):
        return jsonify({'error': 'Team not found'}), 404

    stat_panel = fetch_team_roster_stat_panel(
        str(team_id),
        season_year=team.get('season_year'),
    )
    if not stat_panel:
        return jsonify({'error': 'Roster unavailable'}), 404

    return jsonify({'stat_panel': stat_panel})


@app.route('/api/mlb/team/<team_id>/stats/leaders', methods=['GET'], endpoint='api_mlb_team_stats_leaders')
def api_mlb_team_stats_leaders(team_id):
    from espn_mlb import fetch_team, fetch_team_leaders_stat_panel

    try:
        team = fetch_team(str(team_id), include_stats=False)
    except (requests.RequestException, ValueError):
        return jsonify({'error': 'Team not found'}), 404

    stat_panel = fetch_team_leaders_stat_panel(
        str(team_id),
        season_year=team.get('season_year'),
    )
    if not stat_panel:
        return jsonify({'error': 'Leaders unavailable'}), 404

    return jsonify({'stat_panel': stat_panel})


@app.route('/api/mlb/team/<team_id>', methods=['GET'], endpoint='api_mlb_team')
def api_mlb_team(team_id):
    from espn_mlb import fetch_team

    try:
        team = fetch_team(str(team_id), force_refresh=True)
    except (requests.RequestException, ValueError):
        return jsonify({'error': 'Team not found'}), 404

    return jsonify({'team': team})


@app.route('/player/<player_id>', methods=['GET'], endpoint='mlb_player_page')
def mlb_player_page(player_id):
    from espn_mlb import fetch_player, fetch_scoreboard, strip_initial_page_for_team
    from player_stats import is_pitcher_position

    try:
        player = fetch_player(str(player_id), include_stats=False)
    except (requests.RequestException, ValueError):
        abort(404)

    strip_games = fetch_scoreboard(date.today())
    team_id = str((player.get('team') or {}).get('id') or '')

    return render_template(
        'player.html',
        player=player,
        is_pitcher=is_pitcher_position(player.get('position')),
        strip_games=strip_games,
        strip_initial_page=strip_initial_page_for_team(strip_games, team_id) if team_id else 0,
        current_game_id='',
    )


@app.route('/api/mlb/player/<player_id>/stats', methods=['GET'], endpoint='api_mlb_player_stats')
def api_mlb_player_stats(player_id):
    from espn_mlb import fetch_player, fetch_player_extra_stat_panels

    try:
        player = fetch_player(str(player_id), include_stats=False)
    except (requests.RequestException, ValueError):
        return jsonify({'error': 'Player not found'}), 404

    stat_panels = fetch_player_extra_stat_panels(
        str(player_id),
        player_name=player.get('name') or '',
        position=player.get('position'),
        season_year=player.get('season_year'),
    )
    if not stat_panels:
        return jsonify({'error': 'Stats unavailable'}), 404

    return jsonify({'stat_panels': stat_panels})


@app.route(
    '/api/mlb/player/<player_id>/stats/league',
    methods=['GET'],
    endpoint='api_mlb_player_stats_league',
)
def api_mlb_player_stats_league(player_id):
    from espn_mlb import fetch_player, fetch_player_league_bundle

    try:
        player = fetch_player(str(player_id), include_stats=False)
    except (requests.RequestException, ValueError):
        return jsonify({'error': 'Player not found'}), 404

    bundle = fetch_player_league_bundle(
        str(player_id),
        player_name=player.get('name') or '',
        position=player.get('position'),
        season_year=player.get('season_year'),
    )
    if not bundle or not bundle.get('stat_panel'):
        return jsonify({'error': 'Stats unavailable'}), 404

    return jsonify(bundle)


@app.route(
    '/api/mlb/player/<player_id>/stats/season',
    methods=['GET'],
    endpoint='api_mlb_player_stats_season',
)
def api_mlb_player_stats_season(player_id):
    from espn_mlb import fetch_player, fetch_player_season_stats_view

    try:
        player = fetch_player(str(player_id), include_stats=False)
    except (requests.RequestException, ValueError):
        return jsonify({'error': 'Player not found'}), 404

    view = fetch_player_season_stats_view(
        str(player_id),
        player_name=player.get('name') or '',
        position=player.get('position'),
        season_year=player.get('season_year'),
    )
    if not view:
        return jsonify({'error': 'Season stats unavailable'}), 404

    return jsonify({'view': view})


@app.route(
    '/api/mlb/player/<player_id>/stats/summary',
    methods=['GET'],
    endpoint='api_mlb_player_stats_summary',
)
def api_mlb_player_stats_summary(player_id):
    from espn_mlb import fetch_player, fetch_player_stats

    try:
        player = fetch_player(str(player_id), include_stats=False)
    except (requests.RequestException, ValueError):
        return jsonify({'error': 'Player not found'}), 404

    stats_table = fetch_player_stats(
        player.get('name') or '',
        player.get('season_year'),
        position=player.get('position'),
        espn_player_id=str(player_id),
    )
    if not stats_table:
        return jsonify({'error': 'Summary unavailable'}), 404

    return jsonify({'stats_table': stats_table})


@app.route(
    '/api/mlb/player/<player_id>/stats/percentiles',
    methods=['GET'],
    endpoint='api_mlb_player_stats_percentiles',
)
def api_mlb_player_stats_percentiles(player_id):
    from espn_mlb import fetch_player, fetch_player_percentile_stat_panel

    try:
        player = fetch_player(str(player_id), include_stats=False)
    except (requests.RequestException, ValueError):
        return jsonify({'error': 'Player not found'}), 404

    stat_panel = fetch_player_percentile_stat_panel(
        str(player_id),
        player_name=player.get('name') or '',
        position=player.get('position'),
        season_year=player.get('season_year'),
    )
    if not stat_panel:
        return jsonify({'error': 'Percentiles unavailable'}), 404

    return jsonify({'stat_panel': stat_panel})


@app.route(
    '/api/mlb/player/<player_id>/stats/splits',
    methods=['GET'],
    endpoint='api_mlb_player_stats_splits',
)
def api_mlb_player_stats_splits(player_id):
    from espn_mlb import fetch_player, fetch_player_splits_stat_panel

    try:
        player = fetch_player(str(player_id), include_stats=False)
    except (requests.RequestException, ValueError):
        return jsonify({'error': 'Player not found'}), 404

    stat_panel = fetch_player_splits_stat_panel(
        str(player_id),
        player_name=player.get('name') or '',
        position=player.get('position'),
        season_year=player.get('season_year'),
    )
    if not stat_panel:
        return jsonify({'error': 'Splits unavailable'}), 404

    return jsonify({'stat_panel': stat_panel})


@app.route(
    '/api/mlb/player/<player_id>/percentile-ranks',
    methods=['GET'],
    endpoint='api_mlb_player_percentile_ranks',
)
def api_mlb_player_percentile_ranks(player_id):
    from espn_mlb import fetch_player, fetch_player_percentile_ranks

    try:
        player = fetch_player(str(player_id), include_stats=False)
    except (requests.RequestException, ValueError):
        return jsonify({'error': 'Player not found'}), 404

    season_year = request.args.get('season_year')
    panel = fetch_player_percentile_ranks(
        player.get('name') or '',
        position=player.get('position'),
        season_year=season_year or player.get('season_year'),
    )
    return jsonify(panel)


@app.route('/api/mlb/player/<player_id>', methods=['GET'], endpoint='api_mlb_player')
def api_mlb_player(player_id):
    from espn_mlb import fetch_player

    try:
        player = fetch_player(str(player_id), force_refresh=True)
    except (requests.RequestException, ValueError):
        return jsonify({'error': 'Player not found'}), 404

    return jsonify({'player': player})


@app.route('/api/mlb/scoreboard/yesterday', methods=['GET'])
def api_mlb_scoreboard_yesterday():
    from espn_mlb import fetch_scoreboard

    yesterday = date.today() - timedelta(days=1)
    games = fetch_scoreboard(yesterday)
    return jsonify({
        'date': yesterday.isoformat(),
        'games': games,
    })

@app.route('/dashboard', methods=["GET", "POST"])
def dashboard():
    if not current_user.is_authenticated:
        flash("Please log in to access this page.")
        return redirect(url_for('login'))

    premium_level = current_user.premium_level

    # Check for active discounts (only for user 1)
    active_discount = None
    if current_user.id == 1:
        today = date.today()
        active_discount = db.session.execute(
            db.select(Discounts).where(
                Discounts.discount_end_date >= today,
                Discounts.discount_code.isnot(None),
                Discounts.discount_percentage.isnot(None),
                or_(Discounts.discount_start_date.is_(None), Discounts.discount_start_date <= today)
            ).order_by(Discounts.discount_end_date.asc())
        ).scalar()

    validation_stats_row = db.session.execute(
        db.select(
            func.coalesce(func.sum(EmailValidationRun.total_count), 0),
            func.coalesce(func.sum(EmailValidationRun.valid_count), 0),
            func.coalesce(func.sum(EmailValidationRun.invalid_count), 0),
            func.coalesce(func.sum(EmailValidationRun.other_count), 0),
        )
        .where(EmailValidationRun.user_id == current_user.id)
    ).first()
    validation_stats = {
        "total": int(validation_stats_row[0] or 0),
        "valid": int(validation_stats_row[1] or 0),
        "invalid": int(validation_stats_row[2] or 0),
        "other": int(validation_stats_row[3] or 0),
    }
    total_validation_used = int(validation_stats["total"])
    validation_limit = 100
    total_validation_remaining = max(0, validation_limit - total_validation_used)
    # Per request: show 0 for premium levels in the plan strip counter.
    plan_limit_counter = total_validation_remaining if premium_level == 0 else 0
    
    return render_template(
        "dashboard.html",
        premium_level=premium_level,
        active_discount=active_discount,
        validation_stats=validation_stats,
        total_validation_used=total_validation_used,
        validation_limit=validation_limit,
        total_validation_remaining=total_validation_remaining,
        plan_limit_counter=plan_limit_counter,
        today=date.today(),
    )


@app.route('/email-list-validation', methods=['GET'])
def email_list_validation():
    if not current_user.is_authenticated:
        flash("Please log in to access this page.")
        return redirect(url_for('login', next='/email-list-validation'))
    active_bulk = None
    if current_user.premium_level > 0:
        active_bulk = _active_email_list_bulk_job(current_user.id)
    return render_template(
        'email_list_validation.html',
        email_list_locked=(current_user.premium_level == 0),
        email_list_resume_job_id=(active_bulk.id if active_bulk else None),
    )


@app.route('/preferences', methods=["GET", "POST"])
def preferences():
    if not current_user.is_authenticated:
        flash("Please log in to view your preferences.")
        return redirect(url_for('login'))
    
    # Get current user
    user = db.session.execute(db.select(User).where(User.id == current_user.id)).scalar()
    
    # Get today's date for comparison
    from datetime import date
    today = date.today()
    
    # Get or create preferences for user
    preferences = db.session.execute(
        db.select(Preferences).where(Preferences.user_id == user.id)
    ).scalar_one_or_none()
    
    if not preferences:
        preferences = Preferences(user_id=user.id)
        db.session.add(preferences)
        db.session.commit()

    if request.method == "POST":
        field = request.form.get('field')
        value = request.form.get('value')
        
        if field == 'name' and value:
            user.name = value.strip()
            db.session.commit()
            flash('✓ Name updated successfully', 'success')
            return redirect(url_for('preferences'))
        elif field == 'email' and value:
            if '@' in value and '.' in value:
                user.email = value.strip()
                db.session.commit()
                flash('✓ Email updated successfully', 'success')
                return redirect(url_for('preferences'))
            else:
                flash('Invalid email format', 'error')
                return redirect(url_for('preferences'))
    return render_template(
        "preferences.html",
        user=user,
        today=today,
    )


@app.route('/price-page', methods=["GET", "POST"])
def price_page():
    if not current_user.is_authenticated:
        flash("Please log in to view pricing.", "info")
        return redirect(url_for("login", next="/price-page"))
    # Check for active discounts
    today = date.today()
    active_discount = db.session.execute(
        db.select(Discounts).where(
            Discounts.discount_end_date >= today,
            Discounts.discount_code.isnot(None),
            Discounts.discount_percentage.isnot(None),
            or_(Discounts.discount_start_date.is_(None), Discounts.discount_start_date <= today)
        ).order_by(Discounts.discount_end_date.asc())
    ).scalar()
    
    return render_template("price_page.html", active_discount=active_discount)


@app.route('/register', methods=["GET", "POST"])
def register():
    form = RegisterForm()
    register_next = _safe_internal_redirect_path(request.form.get('next') or request.args.get('next'))
    if form.validate_on_submit():
        try:
            # Check if user email is already present in the database.
            result = db.session.execute(db.select(User).where(User.email == form.email.data.lower()))
            user = result.scalar()
            if user:
                if user.auth_provider == 'google':
                    flash("An account with this email already exists using Google sign-in. Please use the 'Sign in with Google' button.", 'error')
                else:
                    flash("You've already signed up with that email, log in instead!")
                return redirect(url_for('login', next=register_next) if register_next else url_for('login'))

            hash_and_salted_password = generate_password_hash(
                form.password.data,
                method='pbkdf2:sha256',
                salt_length=8
            )
            new_user = User(
                email=form.email.data.lower(),
                name=form.name.data,
                password=hash_and_salted_password,
                date_of_signup=date.today(),
                end_date_premium=None,
                premium_level=0,
                stripe_customer_id=None,
                stripe_active_subscription=False,
                episodes_processed=0,
            )

            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)  # Automatically log in the new user
            if register_next:
                return redirect(register_next)
            return redirect(url_for('dashboard'))
                
        except Exception as e:
            print(f"Registration error: {str(e)}")
            flash("An error occurred during registration. Please try again.")
            return redirect(url_for('register', next=register_next) if register_next else url_for("register"))
            
    return render_template(
        "register.html",
        form=form,
        current_user=current_user,
        google_enabled=bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
        register_next=register_next,
    )

@app.route('/login/google')
def google_login():
    """Initiate Google OAuth login"""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        flash("Google authentication is not configured. Please use email/password login.", 'error')
        return redirect(url_for('login'))

    next_path = _safe_internal_redirect_path(request.args.get('next'))
    if next_path:
        session[OAUTH_NEXT_SESSION_KEY] = next_path
    else:
        session.pop(OAUTH_NEXT_SESSION_KEY, None)

    redirect_uri = url_for('google_callback', _external=True)
    # Debug: Log the redirect URI to verify it's correct
    print(f"Google OAuth redirect URI: {redirect_uri}")
    print(f"Request scheme: {request.scheme}, Host: {request.host}")
    return google.authorize_redirect(redirect_uri)

@app.route('/login/google/callback')
def google_callback():
    """Handle Google OAuth callback"""
    try:
        token = google.authorize_access_token()
        user_info = token.get('userinfo')
        
        if not user_info:
            # Fetch user info if not in token
            resp = google.get('userinfo')
            user_info = resp.json()
        
        google_id = user_info.get('sub')
        email = user_info.get('email', '').lower()
        name = user_info.get('name', user_info.get('given_name', 'User'))
        
        if not email:
            flash("Unable to retrieve email from Google account.", 'error')
            return redirect(url_for('login'))
        
        # Check if user exists
        result = db.session.execute(db.select(User).where(User.email == email))
        user = result.scalar()
        
        if user:
            # User exists - check if they're using Google auth
            if user.auth_provider == 'google' or user.oauth_id == google_id:
                # Update OAuth info if needed
                if not user.oauth_id:
                    user.oauth_id = google_id
                    user.auth_provider = 'google'
                    db.session.commit()
                login_user(user)
                oauth_next = _safe_internal_redirect_path(session.pop(OAUTH_NEXT_SESSION_KEY, None))
                if oauth_next:
                    return redirect(oauth_next)
                return redirect(url_for('dashboard'))
            else:
                # User exists with password auth - ask them to use password login
                flash("An account with this email already exists. Please log in with your password.", 'error')
                return redirect(url_for('login'))
        else:
            # New user - create account (preserve oauth_next for return e.g. free tools)
            new_user = User(
                email=email,
                name=name,
                password=None,  # No password for OAuth users
                date_of_signup=date.today(),
                end_date_premium=None,
                premium_level=0,
                stripe_customer_id=None,
                stripe_active_subscription=False,
                episodes_processed=0,
                auth_provider='google',
                oauth_id=google_id
            )

            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
            oauth_next = _safe_internal_redirect_path(session.pop(OAUTH_NEXT_SESSION_KEY, None))
            if oauth_next:
                return redirect(oauth_next)
            return redirect(url_for('dashboard'))
            
    except Exception as e:
        print(f"Google OAuth error: {str(e)}")
        flash("An error occurred during Google authentication. Please try again.", 'error')
        return redirect(url_for('login'))

@app.route('/login', methods=["GET", "POST"])
def login():
    form = LoginForm()
    login_next = _safe_internal_redirect_path(request.form.get('next') or request.args.get('next'))
    if form.validate_on_submit():
        password = form.password.data
        result = db.session.execute(db.select(User).where(User.email == form.email.data.lower()))
        user = result.scalar()
        
        if not user:
            flash("That email does not exist, please try again.")
            return redirect(url_for('login', next=login_next) if login_next else url_for('login'))
        elif user.auth_provider == 'google':
            flash("This account uses Google sign-in. Please use the 'Sign in with Google' button.", 'error')
            return redirect(url_for('login', next=login_next) if login_next else url_for('login'))
        elif not user.password or not check_password_hash(user.password, password):
            flash('Password incorrect, please try again.')
            return redirect(url_for('login', next=login_next) if login_next else url_for('login'))
        else:
            login_user(user)
            if login_next:
                return redirect(login_next)
            return redirect(url_for('dashboard'))

    return render_template(
        "login.html",
        form=form,
        current_user=current_user,
        google_enabled=bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
        login_next=login_next,
    )

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home_page'))

@app.route('/notifications', methods=["GET"])
def get_notifications():
    if not current_user.is_authenticated:
        return jsonify({"error": "Unauthorized"}), 401
    
    # Get unread notifications for current user
    notifications = db.session.execute(
        db.select(Notification)
        .where(Notification.user_id == current_user.id, Notification.is_read == False)
        .order_by(Notification.created_at.desc())
    ).scalars().all()
    
    notifications_data = []
    for notif in notifications:
        notifications_data.append({
            "id": notif.id,
            "message": notif.message,
            "type": notif.type,
            "created_at": notif.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        })
    
    return jsonify({"notifications": notifications_data, "count": len(notifications_data)})

@app.route('/notifications/<int:notification_id>/mark-read', methods=["POST"])
def mark_notification_read(notification_id):
    if not current_user.is_authenticated:
        return jsonify({"error": "Unauthorized"}), 401
    
    notification = db.session.execute(
        db.select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id
        )
    ).scalar_one_or_none()
    
    if notification:
        notification.is_read = True
        db.session.commit()
        return jsonify({"success": True})
    
    return jsonify({"error": "Notification not found"}), 404


@app.route('/api/validate-email', methods=['POST'], endpoint='validate_email_api')
def validate_email_api():
    from email_validation import validate_single_email

    if not current_user.is_authenticated:
        return jsonify({'error': 'Unauthorized'}), 401
    if current_user.premium_level == 0:
        total_used = db.session.execute(
            db.select(func.coalesce(func.sum(EmailValidationRun.total_count), 0))
            .where(EmailValidationRun.user_id == current_user.id)
        ).scalar() or 0
        if int(total_used) >= 100:
            return jsonify({
                'error': 'Free plan total email validation limit reached (100). Please upgrade to continue.',
                'limit_reached': True,
            }), 403
    payload = request.get_json(silent=True) or {}
    raw = payload.get('email', '')
    result = validate_single_email(raw if isinstance(raw, str) else '')
    status = result.get('report', {}).get('status', 'invalid')
    valid_count = 1 if status == 'valid' else 0
    invalid_count = 1 if status == 'invalid' else 0
    other_count = 1 if status not in ('valid', 'invalid') else 0
    _record_email_validation_run(
        email_value=(raw if isinstance(raw, str) else ''),
        valid_count=valid_count,
        invalid_count=invalid_count,
        other_count=other_count,
        total_count=1,
    )
    return jsonify(result)


@app.route('/api/validate-email-list', methods=['POST'], endpoint='validate_email_list_api')
def validate_email_list_api():
    if not current_user.is_authenticated:
        return jsonify({'error': 'Unauthorized'}), 401

    payload = request.get_json(silent=True) or {}
    raw_emails = payload.get('emails')
    if not isinstance(raw_emails, list):
        return jsonify({'error': 'Invalid payload: emails must be a list.'}), 400

    max_batch_size = 5000
    cleaned_emails = []
    for item in raw_emails:
        if len(cleaned_emails) >= max_batch_size:
            break
        if isinstance(item, str):
            val = item.strip()
            if val:
                cleaned_emails.append(val)

    if not cleaned_emails:
        return jsonify({'error': 'No valid email addresses were provided.'}), 400

    counts, results = _validate_cleaned_email_list(cleaned_emails)

    _record_email_validation_run(
        email_value='LIST',
        valid_count=counts['valid'],
        invalid_count=counts['invalid'],
        other_count=counts['risky'],
        total_count=len(cleaned_emails),
    )

    return jsonify({
        'processed': len(cleaned_emails),
        'truncated': len(raw_emails) > len(cleaned_emails),
        'max_batch_size': max_batch_size,
        'counts': counts,
        'results': results,
    })


def _active_email_list_bulk_job(user_id: int) -> BulkUploadQueue | None:
    """One open email list job per user: pending, processing, or failed-but-still-retrying."""
    return db.session.execute(
        db.select(BulkUploadQueue)
        .where(
            BulkUploadQueue.user_id == user_id,
            BulkUploadQueue.job_type == 'email_list',
            or_(
                BulkUploadQueue.status.in_(('pending', 'processing')),
                and_(
                    BulkUploadQueue.status == 'failed',
                    BulkUploadQueue.retry_count <= EMAIL_LIST_BULK_MAX_RETRIES,
                ),
            ),
        )
        .order_by(BulkUploadQueue.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()


@app.route('/api/email-list-validation/enqueue', methods=['POST'], endpoint='email_list_validation_enqueue_api')
def email_list_validation_enqueue_api():
    if not current_user.is_authenticated:
        return jsonify({'error': '🔒 Please sign in to validate a list.'}), 401
    if current_user.premium_level <= 0:
        return jsonify({'error': '⭐ Bulk list validation needs a paid plan. Upgrade to continue.'}), 403
    existing = _active_email_list_bulk_job(current_user.id)
    if existing:
        return jsonify({
            'error': '⏳ You already have a list validating or waiting to retry. Wait for it to finish, then try again.',
            'active_job_id': existing.id,
        }), 409

    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'error': '📎 Choose a CSV or TXT file to upload.'}), 400
    has_header = request.form.get('has_header') in ('1', 'true', 'True', 'on', 'yes')
    try:
        col_index = int(request.form.get('email_column_index', '0'))
    except ValueError:
        return jsonify({'error': '⚙️ Invalid column index. Refresh the page and try again.'}), 400
    if col_index < 0:
        return jsonify({'error': '⚙️ That email column isn’t valid. Pick a column in the preview.'}), 400

    raw_bytes = f.read()
    if not raw_bytes:
        return jsonify({'error': '📄 That file looks empty. Use a non-empty CSV or TXT list.'}), 400

    safe_name = re.sub(r'[^a-zA-Z0-9._-]+', '_', f.filename)[:180]
    key = f"email-list-queue/{current_user.id}/{uuid.uuid4().hex}_{secrets.token_hex(4)}_{safe_name}"
    url = upload_bytes_to_spaces_private(raw_bytes, key, content_type=f.mimetype or 'text/csv')
    if not url:
        bulk_email_logger.error("☁️ Enqueue failed — private upload returned None | user=%s | key=%r", current_user.id, key)
        return jsonify({
            'error': '☁️ Couldn’t upload your list to cloud storage. Check Spaces credentials or try again shortly.',
        }), 503

    job = BulkUploadQueue(
        user_id=current_user.id,
        file_name=f.filename[:500],
        file_url=url,
        spaces_key=key,
        job_type='email_list',
        job_metadata={'has_header': has_header, 'email_column_index': col_index},
        status='pending',
    )
    db.session.add(job)
    db.session.commit()

    bulk_email_logger.info(
        "📬 List queued | job=%s | user=%s | file=%r | key=%r",
        job.id,
        current_user.id,
        job.file_name,
        key,
    )
    return jsonify({'job_id': job.id, 'status': job.status})


def _email_list_job_to_dict(job: BulkUploadQueue) -> dict:
    retry_count = int(job.retry_count or 0)
    will_retry = (job.status == 'failed' and retry_count <= EMAIL_LIST_BULK_MAX_RETRIES)
    out = {
        'job_id': job.id,
        'status': job.status,
        'file_name': job.file_name,
        'created_at': job.created_at.isoformat() if job.created_at else None,
        'completed_at': job.completed_at.isoformat() if job.completed_at else None,
        'progress_processed': job.progress_processed or 0,
        'progress_total': job.progress_total,
        'error_message': job.error_message,
        'retry_count': retry_count,
        'max_retries': EMAIL_LIST_BULK_MAX_RETRIES,
        'will_retry': will_retry,
    }
    if job.status == 'completed' and job.result_json:
        out['result'] = job.result_json
    return out


@app.route('/api/email-list-validation/jobs/<int:job_id>/stream', methods=['GET'], endpoint='email_list_validation_job_stream_api')
def email_list_validation_job_stream_api(job_id):
    """Server-Sent Events: push job row from DB whenever it changes (worker updates same row)."""
    if not current_user.is_authenticated:
        return jsonify({'error': '🔒 Sign in to view this job.'}), 401
    job = db.session.get(BulkUploadQueue, job_id)
    if not job or job.user_id != current_user.id or job.job_type != 'email_list':
        return jsonify({'error': '🔍 That validation job was not found.'}), 404

    owner_id = current_user.id

    @stream_with_context
    def event_stream():
        last_blob = None
        while True:
            db.session.expire_all()
            job = db.session.get(BulkUploadQueue, job_id)
            if not job or job.user_id != owner_id or job.job_type != 'email_list':
                yield 'event: job_error\ndata: {"error":"not_found"}\n\n'
                break
            payload = _email_list_job_to_dict(job)
            blob = json.dumps(payload, separators=(',', ':'))
            if blob != last_blob:
                last_blob = blob
                yield f'data: {blob}\n\n'
            if payload.get('status') == 'completed' or (payload.get('status') == 'failed' and not payload.get('will_retry')):
                break
            time.sleep(1.5)

    return Response(
        event_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )


@app.route('/api/email-list-validation/jobs/<int:job_id>', methods=['GET'], endpoint='email_list_validation_job_api')
def email_list_validation_job_api(job_id):
    if not current_user.is_authenticated:
        return jsonify({'error': '🔒 Sign in to view this job.'}), 401
    job = db.session.get(BulkUploadQueue, job_id)
    if not job or job.user_id != current_user.id or job.job_type != 'email_list':
        return jsonify({'error': '🔍 That validation job was not found.'}), 404
    return jsonify(_email_list_job_to_dict(job))


# Stripe Price IDs - centralized constants
PRICE_ID = 'price_1TUxqdRBNfjMvbUVfwd1UksX'  # Paid plan (one-time)

def get_first_line_item_price_id(checkout_session):
    """Stripe Price id from Checkout Session line_items (retrieve with expand=['line_items.data.price'])."""
    try:
        line_items = checkout_session['line_items']
        items_data = line_items['data'] if line_items else []
        if not items_data:
            return None
        price = items_data[0]['price']
        if isinstance(price, dict):
            return price.get('id')
        if isinstance(price, str):
            return price
        return getattr(price, 'id', None)
    except (KeyError, TypeError, AttributeError, IndexError) as e:
        print(f"Error reading checkout line item price: {e}")
        return None

def get_subscription_price_id(subscription):
    """
    Helper function to get price ID from subscription object.
    Works with both webhook events (dict) and retrieved Stripe objects.
    """
    try:
        # Method 1: Dictionary access (works for both webhook events and Stripe objects)
        # This is the most reliable method since webhook events are dicts
        if 'items' in subscription:
            items = subscription['items']
            if items and 'data' in items and len(items['data']) > 0:
                first_item = items['data'][0]
                # Try price.id first (new API format)
                if 'price' in first_item and first_item['price'] and 'id' in first_item['price']:
                    price_id = first_item['price']['id']
                    print(f"Found price ID: {price_id}")
                    return price_id
                # Fallback to plan.id (old API format)
                elif 'plan' in first_item and first_item['plan'] and 'id' in first_item['plan']:
                    price_id = first_item['plan']['id']
                    print(f"Found price ID (via plan): {price_id}")
                    return price_id
        
        # Method 2: Old API format - direct plan.id (for backward compatibility)
        if 'plan' in subscription and subscription['plan']:
            plan = subscription['plan']
            if isinstance(plan, dict) and 'id' in plan:
                price_id = plan['id']
                print(f"Found price ID (direct plan): {price_id}")
                return price_id
            elif hasattr(plan, 'id'):
                price_id = plan.id
                print(f"Found price ID (plan attribute): {price_id}")
                return price_id
        
        print("WARNING: Could not find price ID in subscription")
        return None
        
    except (KeyError, TypeError, IndexError, AttributeError) as e:
        print(f"Error getting price ID: {str(e)}")
        return None

@app.route('/create-checkout-session', methods=['POST', 'GET'])
def create_checkout_session():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))

    plan = request.args.get('plan')
    try:
        # Log the initial request
        log_entry = StripeLog(
            event_type='create_checkout_session',
            user_id=current_user.id,
            stripe_customer_id=current_user.stripe_customer_id,
            request_data=json.dumps({'plan': plan}),
            status='pending'
        )
        db.session.add(log_entry)
        db.session.commit()

        if plan == 'paid':
            price_id = PRICE_ID  # Your Basic Plan Price ID
        else:
            return "Invalid plan selected", 400

        # Create or get Stripe Customer
        if current_user.stripe_customer_id:  # Assuming misc1 stores Stripe customer ID
            customer = stripe.Customer.retrieve(current_user.stripe_customer_id)
        else:
            customer = stripe.Customer.create(
                email=current_user.email,
                metadata={
                    'user_id': current_user.id
                }
            )
            # Store Stripe customer ID in user record
            current_user.stripe_customer_id = customer.id
            db.session.commit()

        checkout_session = stripe.checkout.Session.create(
            customer=customer.id,  # Use the customer ID
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='payment',
            allow_promotion_codes=True,
            success_url=DOMAIN + f'/success?plan={plan}&session_id={{CHECKOUT_SESSION_ID}}',
            cancel_url=DOMAIN + '/cancel',
            metadata={
                'user_id': str(current_user.id)
            }
        )

        # Update log with success response
        log_entry.status = 'success'
        log_entry.response_data = json.dumps({
            'checkout_session_id': checkout_session.id,
            'url': checkout_session.url
        })
        db.session.commit()

        return redirect(checkout_session.url, code=303)

    except Exception as e:
        # Log the error
        if log_entry:
            log_entry.status = 'error'
            log_entry.error_message = str(e)
            db.session.commit()
        print(f"Error creating checkout session: {str(e)}")
        return str(e)

@app.route('/webhook', methods=['POST'])
def webhook():
    print("Webhook endpoint hit!")
    
    # Create initial log entry before any processing
    initial_log = StripeLog(
        event_type='webhook_received',
        request_data=request.data.decode('utf-8'),
        status='received'
    )
    db.session.add(initial_log)
    db.session.commit()
    
    try:
        payload = request.data
        sig_header = request.headers.get('STRIPE_SIGNATURE')
        
        if not sig_header:
            print("No Stripe signature found in headers!")
            initial_log.status = 'error'
            initial_log.error_message = 'No Stripe signature in headers'
            db.session.commit()
            return 'No signature', 400
            
        print(f"Received payload: {payload.decode('utf-8')[:200]}...")  # Print first 200 chars
        print(f"Signature header: {sig_header}")
        
        event = stripe.Webhook.construct_event(
            payload, sig_header, os.environ.get('STRIPE_WEBHOOK_SECRET')
        )
        
        print(f"Event type: {event['type']}")
        
        # Update log with full parsed event data for better debugging
        initial_log.request_data = json.dumps({
            'event_type': event['type'],
            'event_id': event.get('id'),
            'event_data': event
        })
        initial_log.event_type = event['type']  # Update event type from parsed event
        db.session.commit()  # Save the updated log entry
        
        # Add handling for subscription cancellation/deletion
        if event['type'] in ['customer.subscription.deleted', 'customer.subscription.canceled']:
            subscription = event['data']['object']  # This is a dict from webhook
            customer_id = subscription['customer']
            user = User.query.filter_by(stripe_customer_id=customer_id).first()
            if user:
                # Reset user's subscription status
                user.premium_level = 0
                user.stripe_active_subscription = False
                # Set end_date to current period end (subscription remains active until end of period)
                if 'current_period_end' in subscription and subscription['current_period_end']:
                    user.end_date_premium = datetime.fromtimestamp(subscription['current_period_end']).date()
                db.session.commit()
                initial_log.status = 'success'
                initial_log.response_data = json.dumps({
                    'subscription_id': subscription['id'],
                    'customer_id': customer_id,
                    'user_id': user.id if user else None,
                    'action': 'subscription_cancelled'
                })

        # Handle different event types...
        if event['type'] == 'customer.subscription.created':
            subscription_data = event['data']['object']  # This is a dict from webhook
            subscription_id = subscription_data['id']
            customer_id = subscription_data['customer']
            
            print(f"Processing subscription.created webhook for subscription {subscription_id}")
            
            user = User.query.filter_by(stripe_customer_id=customer_id).first()
            if user:
                subscription = subscription_data
                price_id = get_subscription_price_id(subscription)
                if price_id:
                    user.premium_level = 1 if price_id == PRICE_ID else 2
                else:
                    print("WARNING: Could not determine price ID, defaulting to premium_level 1")
                    user.premium_level = 1
                
                user.stripe_active_subscription = True
                db.session.commit()
                initial_log.status = 'success'
                initial_log.response_data = json.dumps({
                    'subscription_id': subscription_id,
                    'customer_id': customer_id,
                    'user_id': user.id if user else None,
                    'action': 'subscription_created',
                    'subscription_data': subscription_data
                })
                db.session.commit()

        elif event['type'] == 'customer.subscription.updated':
            subscription = event['data']['object']  # This is a dict from webhook
            customer_id = subscription['customer']
            
            # Enhanced logging
            print(f"Processing subscription update for customer {customer_id}")
            print(f"Subscription status: {subscription['status']}")
            price_id = get_subscription_price_id(subscription)
            if price_id:
                print(f"Subscription price ID: {price_id}")
            
            user = User.query.filter_by(stripe_customer_id=customer_id).first()
            
            if not user:
                print(f"No user found for customer_id: {customer_id}")
                initial_log.status = 'error'
                initial_log.error_message = f'No user found for customer_id: {customer_id}'
                db.session.commit()
                return jsonify({'error': 'User not found'}), 400
            
            print(f"Found user: {user.id} ({user.email})")
            
            try:
                # Update user subscription status based on subscription status
                if subscription['status'] == 'active':
                    if price_id:
                        user.premium_level = 1 if price_id == PRICE_ID else 2
                    else:
                        print("WARNING: Could not determine price ID, defaulting to premium_level 1")
                        user.premium_level = 1
                    user.stripe_active_subscription = True
                    print(f"Updated user {user.id} to premium_level: {user.premium_level}")
                elif subscription['status'] in ['canceled', 'unpaid', 'past_due']:
                    user.stripe_active_subscription = False
                    print(f"Marked subscription as inactive for user {user.id}")
                
                # Update log entry
                initial_log.status = 'success'
                initial_log.response_data = json.dumps({
                    'subscription_id': subscription['id'],
                    'customer_id': customer_id,
                    'user_id': user.id,
                    'action': 'subscription_updated',
                    'subscription_status': subscription['status'],
                    'premium_level': user.premium_level,
                    'end_date': user.end_date_premium.isoformat() if user.end_date_premium else None,
                    'subscription_data': subscription
                })
                
                db.session.commit()
                print(f"Successfully processed subscription update for user {user.id}")
                
            except Exception as e:
                db.session.rollback()
                error_msg = f"Error processing subscription update: {str(e)}"
                print(error_msg)
                initial_log.status = 'error'
                initial_log.error_message = error_msg
                db.session.commit()
                return jsonify({'error': error_msg}), 500

        elif event['type'] == 'invoice.payment_succeeded':
            invoice = event['data']['object']  # This is a dict from webhook
            # Only handle subscription-related invoices
            if invoice.get('subscription'):
                subscription = stripe.Subscription.retrieve(invoice['subscription'])
                customer_id = invoice['customer']
                user = User.query.filter_by(stripe_customer_id=customer_id).first()
                if user and subscription['status'] == 'active':
                    user.stripe_active_subscription = True
                    db.session.commit()
                    initial_log.status = 'success'
                    initial_log.response_data = json.dumps({
                        'invoice_id': invoice['id'],
                        'subscription_id': subscription['id'] if invoice.get('subscription') else None,
                        'customer_id': customer_id,
                        'user_id': user.id if user else None,
                        'action': 'payment_succeeded',
                        'invoice_data': invoice,
                        'subscription_data': subscription
                    })

        elif event['type'] == 'checkout.session.completed':
            sess = event['data']['object']
            checkout_sess = stripe.checkout.Session.retrieve(
                sess['id'],
                expand=['line_items.data.price'],
            )
            if checkout_sess.get('mode') == 'payment' and checkout_sess.get('payment_status') == 'paid':
                meta = checkout_sess.get('metadata') or {}
                uid = meta.get('user_id')
                user = None
                if uid is not None:
                    try:
                        user = db.session.get(User, int(uid))
                    except (TypeError, ValueError):
                        user = None
                if not user:
                    cust = checkout_sess.get('customer')
                    if cust:
                        user = User.query.filter_by(stripe_customer_id=cust).first()
                if user:
                    price_id = get_first_line_item_price_id(checkout_sess)
                    if price_id:
                        user.premium_level = 1 if price_id == PRICE_ID else 2
                    else:
                        print("WARNING: Could not determine price ID from checkout session, defaulting to premium_level 1")
                        user.premium_level = 1
                    user.stripe_active_subscription = True
                    initial_log.status = 'success'
                    initial_log.response_data = json.dumps({
                        'checkout_session_id': checkout_sess['id'],
                        'customer_id': checkout_sess.get('customer'),
                        'user_id': user.id,
                        'action': 'checkout_payment_completed',
                        'premium_level': user.premium_level,
                    })
                    db.session.commit()

        db.session.commit()
        return 'Success', 200

    except Exception as e:
        initial_log.status = 'error'
        initial_log.error_message = str(e)
        db.session.commit()
        return str(e), 400

@app.route('/cancel', methods=['POST', 'GET'])
def cancel_session():
    return redirect(url_for('price_page'))

@app.route('/success', methods=['GET'])
def success_session():
    session_id = request.args.get('session_id')
    if not session_id:
        return redirect(url_for('price_page'))
        
    try:
        checkout_session = stripe.checkout.Session.retrieve(
            session_id,
            expand=['line_items.data.price'],
        )
        print(f"Checkout session retrieved: {checkout_session['id']}")
        print(f"Payment status: {checkout_session.get('payment_status')}")

        if checkout_session.get('payment_status') != 'paid':
            print("Checkout session is not paid")
            flash('Payment was not completed. Please try again or contact support.', 'error')
            return redirect(url_for('price_page'))

        # Store customer ID if not already stored
        if not current_user.stripe_customer_id and checkout_session.get('customer'):
            current_user.stripe_customer_id = checkout_session['customer']
            db.session.commit()

        price_id = get_first_line_item_price_id(checkout_session)
        print(f"Price ID from checkout line items: {price_id}")

        if price_id:
            current_user.premium_level = 1 if price_id == PRICE_ID else 2
            print(f"Set premium_level to: {current_user.premium_level}")
        else:
            print("WARNING: Could not determine price ID, defaulting to premium_level 1")
            current_user.premium_level = 1

        current_user.stripe_active_subscription = True
        db.session.commit()
        print(f"Successfully updated user {current_user.id} after checkout payment")

        return redirect(url_for('dashboard'))

    except Exception as e:
        import traceback
        print(f"Error processing checkout payment: {str(e)}")
        print(traceback.format_exc())
        flash('There was an error processing your payment. Please contact support.', 'error')
        return redirect(url_for('price_page'))

@app.route('/manage-membership', methods=['POST', 'GET'])
def manage_membership():
    if not current_user.stripe_customer_id:
        flash('No active subscription found.', 'warning')
        return redirect(url_for('price_page'))
        
    try:
        # Create Stripe billing portal session
        session = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url=DOMAIN + '/preferences',
        )
        
        # Redirect to Stripe billing portal
        return redirect(session.url)
        
    except stripe.error.StripeError as e:
        print(f"Stripe error: {str(e)}")
        flash('Error accessing subscription information. Please try again later.', 'error')
        return redirect(url_for('profile'))
    except Exception as e:
        print(f"Error: {str(e)}")
        flash('An unexpected error occurred. Please try again later.', 'error')
        return redirect(url_for('profile'))

@app.route('/privacy-policy', methods=['POST', 'GET'])
def privacy_policy():
    return render_template("privacy_policy.html")

@app.route('/terms-and-conditions', methods=['POST', 'GET'])
def terms_and_conditions():
    return render_template("terms_and_conditions.html")

@app.route('/change-password', methods=["GET", "POST"])
def change_password():
    if not current_user.is_authenticated:
        flash("Please log in to change your password.")
        return redirect(url_for('login'))
    
    # Check if user is using OAuth (no password to change)
    if current_user.auth_provider == 'google':
        flash('Password changes are not available for Google sign-in accounts.', 'error')
        return redirect(url_for('preferences'))
    
    if request.method == "POST":
        email = request.form.get('email')
        password = request.form.get('password')
        new_password = request.form.get('new_password')
        
        if email and password and new_password:
            # Get current user
            user = db.session.execute(db.select(User).where(User.id == current_user.id)).scalar()
            
            if user and user.email.lower() == email.lower():
                # Check if user has a password (not OAuth user)
                if not user.password:
                    flash('This account uses Google sign-in. Password changes are not available.', 'error')
                    return redirect(url_for('preferences'))
                
                # Verify current password
                if check_password_hash(user.password, password):
                    # Update password
                    user.password = generate_password_hash(new_password, method='pbkdf2:sha256', salt_length=8)
                    db.session.commit()
                    flash('✓ Password changed successfully!', 'success')
                    return redirect(url_for('preferences'))
                else:
                    flash('Current password is incorrect.', 'error')
                    return redirect(url_for('preferences'))
            else:
                flash('Email does not match your account.', 'error')
                return redirect(url_for('preferences'))
        else:
            flash('Please fill in all fields.', 'error')
            return redirect(url_for('preferences'))
    
    # If GET request, redirect to preferences
    return redirect(url_for('preferences'))

@app.route('/feedback', methods=['POST', 'GET'])
def feedback():
    if not current_user.is_authenticated:
        flash("Please log in to access this page.")
        return redirect(url_for('login'))
    form=Feedback_Form()
    if form.validate_on_submit():
        new_feedback = Feedback(
            user_id=current_user.id,
            title=form.title.data,
            feedback=form.feedback.data,
            upvote_count=0,
        )
        db.session.add(new_feedback)
        db.session.commit()
        # Redirect to clear the form (POST-REDIRECT-GET pattern)
        return redirect(url_for('feedback'))
    feedback_list = Feedback.query.all()
    # Get list of feedback IDs user has upvoted
    upvoted_feedback_ids = []
    if current_user.is_authenticated:
        upvoted_feedback_ids = [f.id for f in current_user.upvoted_feedback]
    return render_template("feedback.html", form=form, feedback_list=feedback_list, upvoted_feedback_ids=upvoted_feedback_ids)


@app.route('/delete-feedback/<feedback_id>', methods=['POST'])
@premium_required
def delete_feedback(feedback_id):
    feedback = Feedback.query.get_or_404(feedback_id)
    db.session.delete(feedback)
    db.session.commit()
    return jsonify({'success': True})

# Add new route to handle upvotes
@app.route('/upvote/<int:feedback_id>', methods=['POST'])
def upvote_feedback(feedback_id):
    if not current_user.is_authenticated:
        return jsonify({'error': 'Please log in to vote.'}), 401

    feedback = Feedback.query.get_or_404(feedback_id)
    
    # Check if user already upvoted
    existing_upvote = FeedbackUpvote.query.filter_by(
        user_id=current_user.id,
        feedback_id=feedback_id
    ).first()
    
    if existing_upvote:
        # Remove upvote if already voted
        db.session.delete(existing_upvote)
        feedback.upvote_count -= 1
    else:
        # Add new upvote
        new_upvote = FeedbackUpvote(user_id=current_user.id, feedback_id=feedback_id)
        db.session.add(new_upvote)
        feedback.upvote_count += 1
    
    db.session.commit()
    return jsonify({'upvote_count': feedback.upvote_count})

# Blog Routes
def generate_slug(title):
    """Generate a URL-friendly slug from a blog title"""
    # Convert to lowercase
    slug = title.lower()
    # Replace spaces and underscores with hyphens
    slug = re.sub(r'[\s_]+', '-', slug)
    # Remove all non-alphanumeric characters except hyphens
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    # Remove multiple consecutive hyphens
    slug = re.sub(r'-+', '-', slug)
    # Remove leading/trailing hyphens
    slug = slug.strip('-')
    # Limit length
    if len(slug) > 200:
        slug = slug[:200].rstrip('-')
    # If empty, use default
    if not slug:
        slug = "blog-post"
    return slug

def get_unique_slug(title, exclude_id=None):
    """Generate a unique slug, appending a number if necessary"""
    base_slug = generate_slug(title)
    slug = base_slug
    counter = 1
    
    while True:
        query = db.select(Blog).where(Blog.slug == slug)
        if exclude_id:
            query = query.where(Blog.id != exclude_id)
        existing = db.session.execute(query).scalar_one_or_none()
        
        if not existing:
            return slug
        
        slug = f"{base_slug}-{counter}"
        counter += 1

@app.route('/blog', methods=['GET'])
def blog_list():
    """Display all blog posts"""
    blogs = db.session.execute(db.select(Blog).order_by(Blog.created_at.desc())).scalars().all()
    return render_template("blog_list.html", blogs=blogs)

@app.route('/blog/<slug>', methods=['GET'])
def blog_post(slug):
    """Display a single blog post"""
    blog = db.session.execute(db.select(Blog).where(Blog.slug == slug)).scalar_one_or_none()
    if not blog:
        flash("Blog post not found.", "error")
        return redirect(url_for('blog_list'))
    
    # Get 3 most recent posts excluding the current one
    related_posts = db.session.execute(
        db.select(Blog)
        .where(Blog.id != blog.id)
        .order_by(Blog.created_at.desc())
        .limit(3)
    ).scalars().all()
    return render_template("blog_post.html", blog=blog, related_posts=related_posts)

@app.route('/blog/add', methods=['GET', 'POST'])
def add_blog():
    """Add a new blog post - restricted to user id 1"""
    if not current_user.is_authenticated or current_user.id != 1:
        flash("You don't have permission to add blog posts.", "error")
        return redirect(url_for('blog_list'))
    
    form = BlogForm()
    if form.validate_on_submit():
        slug = get_unique_slug(form.title.data)
        new_blog = Blog(
            title=form.title.data,
            slug=slug,
            content=form.content.data,
            author_id=current_user.id
        )
        db.session.add(new_blog)
        db.session.commit()
        flash("Blog post published successfully!", "success")
        return redirect(url_for('blog_post', slug=new_blog.slug))
    
    return render_template("blog_form.html", form=form, blog=None)

@app.route('/blog/<slug>/edit', methods=['GET', 'POST'])
def edit_blog(slug):
    """Edit a blog post - restricted to user id 1"""
    if not current_user.is_authenticated or current_user.id != 1:
        flash("You don't have permission to edit blog posts.", "error")
        return redirect(url_for('blog_list'))
    
    blog = db.session.execute(db.select(Blog).where(Blog.slug == slug)).scalar_one_or_none()
    if not blog:
        flash("Blog post not found.", "error")
        return redirect(url_for('blog_list'))
    
    form = BlogForm(obj=blog)
    
    if form.validate_on_submit():
        # Update slug if title changed
        if form.title.data != blog.title:
            blog.slug = get_unique_slug(form.title.data, exclude_id=blog.id)
        blog.title = form.title.data
        blog.content = form.content.data
        blog.updated_at = datetime.now()
        db.session.commit()
        flash("Blog post updated successfully!", "success")
        return redirect(url_for('blog_post', slug=blog.slug))
    
    return render_template("blog_form.html", form=form, blog=blog)

@app.route('/sitemap.xml', methods=['GET'])
def sitemap():
    """Generate XML sitemap for SEO"""
    from flask import Response
    from xml.etree.ElementTree import Element, SubElement, tostring
    from xml.dom import minidom
    
    # Create root element
    urlset = Element('urlset')
    urlset.set('xmlns', 'http://www.sitemaps.org/schemas/sitemap/0.9')
    
    # Static pages with their priorities and change frequencies
    static_pages = [
        {'url': '/', 'priority': '1.0', 'changefreq': 'weekly'},
        {'url': '/blog', 'priority': '0.8', 'changefreq': 'weekly'},
        {'url': url_for('price_page'), 'priority': '0.75', 'changefreq': 'monthly'},
        {'url': '/privacy-policy', 'priority': '0.3', 'changefreq': 'yearly'},
        {'url': '/terms-and-conditions', 'priority': '0.3', 'changefreq': 'yearly'},
    ]
    
    # Add static pages to sitemap
    for page in static_pages:
        url_elem = SubElement(urlset, 'url')
        loc = SubElement(url_elem, 'loc')
        loc.text = f"{CANONICAL_BASE_URL}{page['url']}"
        priority = SubElement(url_elem, 'priority')
        priority.text = page['priority']
        changefreq = SubElement(url_elem, 'changefreq')
        changefreq.text = page['changefreq']
        lastmod = SubElement(url_elem, 'lastmod')
        lastmod.text = datetime.now().strftime('%Y-%m-%d')

    # Add all blog posts dynamically
    blogs = db.session.execute(db.select(Blog).order_by(Blog.created_at.desc())).scalars().all()
    for blog in blogs:
        url_elem = SubElement(urlset, 'url')
        loc = SubElement(url_elem, 'loc')
        loc.text = f"{CANONICAL_BASE_URL}{url_for('blog_post', slug=blog.slug)}"
        priority = SubElement(url_elem, 'priority')
        priority.text = '0.7'
        changefreq = SubElement(url_elem, 'changefreq')
        changefreq.text = 'monthly'
        lastmod = SubElement(url_elem, 'lastmod')
        # Use updated_at if available, otherwise created_at
        lastmod_date = blog.updated_at if blog.updated_at else blog.created_at
        lastmod.text = lastmod_date.strftime('%Y-%m-%d')

    # Convert to pretty XML string
    xml_string = tostring(urlset, encoding='unicode')
    xml_pretty = minidom.parseString(xml_string).toprettyxml(indent='  ')
    
    # Return as XML response
    return Response(xml_pretty, mimetype='application/xml')

@app.route('/get-all-users', methods=['GET'])
def get_all_users():
    """Get all users - restricted to user id 1"""
    if not current_user.is_authenticated or current_user.id != 1:
        return jsonify({"error": "Unauthorized"}), 403
    
    users = db.session.execute(db.select(User).order_by(User.id)).scalars().all()
    users_data = []
    for user in users:
        users_data.append({
            "id": user.id,
            "name": user.name,
            "email": user.email
        })
    
    return jsonify({"users": users_data})

@app.route('/send-message-to-users', methods=['POST'])
def send_message_to_users():
    """Send message to selected users - restricted to user id 1"""
    if not current_user.is_authenticated or current_user.id != 1:
        return jsonify({"error": "Unauthorized"}), 403
    
    data = request.get_json()
    user_ids = data.get('user_ids', [])
    message = data.get('message', '').strip()
    
    if not user_ids:
        return jsonify({"error": "No users selected"}), 400
    
    if not message:
        return jsonify({"error": "Message cannot be empty"}), 400
    
    # Convert user_ids to integers if they're strings
    try:
        user_ids = [int(uid) for uid in user_ids]
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid user IDs"}), 400
    
    # Validate that all user IDs exist
    users = db.session.execute(
        db.select(User).where(User.id.in_(user_ids))
    ).scalars().all()
    
    if len(users) != len(user_ids):
        return jsonify({"error": "Some user IDs are invalid"}), 400
    
    # Create notifications for each selected user
    notifications_created = 0
    for user in users:
        notification = Notification(
            user_id=user.id,
            message=message,
            type="admin_message",
            is_read=False
        )
        db.session.add(notification)
        notifications_created += 1
    
    db.session.commit()
    
    return jsonify({
        "success": True,
        "count": notifications_created,
        "message": f"Message sent to {notifications_created} user(s)"
    })

@app.route('/admin/users', methods=['GET'])
def admin_users():
    """Users admin - restricted to user id 1"""
    if not current_user.is_authenticated or current_user.id != 1:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dashboard'))

    users = db.session.execute(db.select(User).order_by(User.id)).scalars().all()
    user_ids = [u.id for u in users]
    user_admin_metrics = {
        uid: {'run_count': 0, 'emails_validated': 0, 'bulk_jobs_completed': 0}
        for uid in user_ids
    }
    if user_ids:
        run_rows = db.session.execute(
            db.select(
                EmailValidationRun.user_id,
                func.count(EmailValidationRun.id),
                func.coalesce(func.sum(EmailValidationRun.total_count), 0),
            )
            .where(EmailValidationRun.user_id.in_(user_ids))
            .group_by(EmailValidationRun.user_id)
        ).all()
        for uid, run_count, total_validated in run_rows:
            if uid in user_admin_metrics:
                user_admin_metrics[uid]['run_count'] = int(run_count)
                user_admin_metrics[uid]['emails_validated'] = int(total_validated)
        bulk_rows = db.session.execute(
            db.select(BulkUploadQueue.user_id, func.count(BulkUploadQueue.id))
            .where(
                BulkUploadQueue.user_id.in_(user_ids),
                BulkUploadQueue.job_type == 'email_list',
                BulkUploadQueue.status == 'completed',
            )
            .group_by(BulkUploadQueue.user_id)
        ).all()
        for uid, bulk_n in bulk_rows:
            if uid in user_admin_metrics:
                user_admin_metrics[uid]['bulk_jobs_completed'] = int(bulk_n)

    queue_cutoff = datetime.now() - timedelta(days=7)
    recent_queue_rows = db.session.execute(
        db.select(BulkUploadQueue, User.email, User.name)
        .join(User, BulkUploadQueue.user_id == User.id)
        .where(
            BulkUploadQueue.created_at >= queue_cutoff,
            BulkUploadQueue.job_type == 'email_list',
        )
        .order_by(BulkUploadQueue.created_at.desc())
    ).all()
    recent_queue_jobs = [
        {'job': j, 'user_email': em, 'user_name': nm}
        for j, em, nm in recent_queue_rows
    ]

    return render_template(
        "admin_users.html",
        users=users,
        user_admin_metrics=user_admin_metrics,
        recent_queue_jobs=recent_queue_jobs,
    )


@app.route('/manage-discounts', methods=['GET', 'POST'])
def manage_discounts():
    """Manage discounts - restricted to user id 1"""
    if not current_user.is_authenticated or current_user.id != 1:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dashboard'))
    
    # Get all discounts
    all_discounts = db.session.execute(
        db.select(Discounts).order_by(Discounts.discount_end_date.desc())
    ).scalars().all()
    
    # Handle form submission
    form = DiscountForm()
    if form.validate_on_submit():
        discount_code = form.discount_code.data.strip()
        discount_percentage = float(form.discount_percentage.data)
        discount_start_date_str = form.discount_start_date.data.strip()
        discount_end_date_str = form.discount_end_date.data.strip()
        
        # Parse dates
        discount_start_date = None
        if discount_start_date_str:
            try:
                discount_start_date = datetime.strptime(discount_start_date_str, "%Y-%m-%d").date()
            except ValueError:
                flash("Invalid start date format. Use YYYY-MM-DD.", "danger")
                today = date.today()
                return render_template("manage_discounts.html", form=form, discounts=all_discounts, today=today)
        
        try:
            discount_end_date = datetime.strptime(discount_end_date_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid end date format. Use YYYY-MM-DD.", "danger")
            today = date.today()
            return render_template("manage_discounts.html", form=form, discounts=all_discounts, today=today)
        
        # Validate dates
        if discount_start_date and discount_start_date > discount_end_date:
            flash("Start date must be before or equal to end date.", "danger")
            today = date.today()
            return render_template("manage_discounts.html", form=form, discounts=all_discounts, today=today)
        
        # Create new discount
        new_discount = Discounts(
            discount_code=discount_code,
            discount_percentage=discount_percentage,
            discount_start_date=discount_start_date,
            discount_end_date=discount_end_date
        )
        db.session.add(new_discount)
        db.session.commit()
        flash(f"Discount '{discount_code}' created successfully!", "success")
        return redirect(url_for('manage_discounts'))
    
    today = date.today()
    return render_template("manage_discounts.html", form=form, discounts=all_discounts, today=today)

@app.route('/delete-discount/<int:discount_id>', methods=['POST'])
def delete_discount(discount_id):
    """Delete a discount - restricted to user id 1"""
    if not current_user.is_authenticated or current_user.id != 1:
        return jsonify({"error": "Unauthorized"}), 403
    
    discount = db.session.get(Discounts, discount_id)
    if not discount:
        return jsonify({"error": "Discount not found"}), 404
    
    db.session.delete(discount)
    db.session.commit()
    flash(f"Discount '{discount.discount_code}' deleted successfully!", "success")
    return jsonify({"success": True})

if __name__ == "__main__":
    app.run(debug=True, port=5002)





