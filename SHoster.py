#!/usr/bin/env python3
"""
SIMPLE FILE HUB v1.0
A no-authentication file hosting server for local network sharing
Store and access files, text, photos, videos from any device
"""

import os
import sys
import json
import time
import socket
import threading
import mimetypes
import urllib.parse
from datetime import datetime
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

# ==================== CONFIGURATION ====================

class Config:
    """Preconfigured settings"""
    SERVER_NAME = "Hoster"
    SERVER_VERSION = "v1.0"
    
    # Network settings
    DEFAULT_PORT = 8080
    DEFAULT_HOST = "192.168.1.8"  # Listen on all interfaces
    
    # Storage paths
    STORAGE_DIR = Path.home() / "FileHub"
    UPLOADS_DIR = STORAGE_DIR / "uploads"
    TEXT_DIR = STORAGE_DIR / "text"
    PHOTOS_DIR = STORAGE_DIR / "photos"
    VIDEOS_DIR = STORAGE_DIR / "videos"
    ARCHIVE_DIR = STORAGE_DIR / "archive"
    
    # File settings
    MAX_UPLOAD_SIZE = 1024 * 1024 * 1024  # 1GB
    ALLOWED_EXTENSIONS = {
        # Images
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg',
        # Videos
        '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm',
        # Text/Documents
        '.txt', '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
        '.md', '.rst', '.rtf', '.odt',
        # Audio
        '.mp3', '.wav', '.flac', '.aac', '.ogg',
        # Archives
        '.zip', '.tar', '.gz', '.7z', '.rar',
        # Code
        '.py', '.js', '.html', '.css', '.php', '.java', '.c', '.cpp'
    }
    
    # Preview settings
    ENABLE_VIDEO_PREVIEW = True
    ENABLE_IMAGE_PREVIEW = True
    ENABLE_TEXT_PREVIEW = True
    
    # Gallery settings
    THUMBNAIL_SIZE = (200, 200)
    ITEMS_PER_PAGE = 50

# ==================== FILE STORAGE MANAGER ====================

class FileStorage:
    """Manages file storage and organization"""
    
    def __init__(self):
        # Create storage directories
        for dir_path in [Config.UPLOADS_DIR, Config.TEXT_DIR, Config.PHOTOS_DIR, 
                        Config.VIDEOS_DIR, Config.ARCHIVE_DIR]:
            dir_path.mkdir(parents=True, exist_ok=True)
            
        # Initialize file database
        self.db_file = Config.STORAGE_DIR / "files.json"
        self.files = self.load_database()
        
    def load_database(self):
        """Load file database"""
        if self.db_file.exists():
            try:
                with open(self.db_file, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def save_database(self):
        """Save file database"""
        with open(self.db_file, 'w') as f:
            json.dump(self.files, f, indent=2)
    
    def get_category(self, filename):
        """Determine file category based on extension"""
        ext = Path(filename).suffix.lower()
        
        if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
            return 'photos'
        elif ext in ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.webm']:
            return 'videos'
        elif ext in ['.txt', '.md', '.rst']:
            return 'text'
        elif ext in ['.zip', '.tar', '.gz', '.7z', '.rar']:
            return 'archive'
        else:
            return 'uploads'
    
    def get_storage_dir(self, category):
        """Get storage directory for category"""
        dirs = {
            'photos': Config.PHOTOS_DIR,
            'videos': Config.VIDEOS_DIR,
            'text': Config.TEXT_DIR,
            'archive': Config.ARCHIVE_DIR,
            'uploads': Config.UPLOADS_DIR
        }
        return dirs.get(category, Config.UPLOADS_DIR)
    
    def add_file(self, filepath, original_name, category=None):
        """Add file to database"""
        if not category:
            category = self.get_category(original_name)
            
        storage_dir = self.get_storage_dir(category)
        dest_path = storage_dir / filepath.name
        
        # Move file to category folder
        if filepath.parent != storage_dir:
            import shutil
            shutil.move(str(filepath), str(dest_path))
        
        file_info = {
            'id': str(int(time.time() * 1000)),
            'name': original_name,
            'filename': dest_path.name,
            'path': str(dest_path),
            'category': category,
            'size': dest_path.stat().st_size,
            'uploaded': time.time(),
            'downloads': 0,
            'mime_type': mimetypes.guess_type(original_name)[0] or 'application/octet-stream'
        }
        
        self.files.append(file_info)
        self.save_database()
        return file_info
    
    def get_file(self, file_id):
        """Get file info by ID"""
        for f in self.files:
            if f['id'] == file_id:
                return f
        return None
    
    def get_files(self, category=None, page=1):
        """Get files with pagination"""
        filtered = self.files
        if category:
            filtered = [f for f in self.files if f['category'] == category]
            
        # Sort by date (newest first)
        filtered.sort(key=lambda x: x['uploaded'], reverse=True)
        
        # Paginate
        start = (page - 1) * Config.ITEMS_PER_PAGE
        end = start + Config.ITEMS_PER_PAGE
        
        return {
            'files': filtered[start:end],
            'total': len(filtered),
            'page': page,
            'pages': (len(filtered) + Config.ITEMS_PER_PAGE - 1) // Config.ITEMS_PER_PAGE
        }
    
    def delete_file(self, file_id):
        """Delete file"""
        for i, f in enumerate(self.files):
            if f['id'] == file_id:
                # Delete actual file
                try:
                    os.remove(f['path'])
                except:
                    pass
                # Remove from database
                self.files.pop(i)
                self.save_database()
                return True
        return False
    
    def increment_download(self, file_id):
        """Increment download count"""
        for f in self.files:
            if f['id'] == file_id:
                f['downloads'] += 1
                self.save_database()
                break

# ==================== HTTP REQUEST HANDLER ====================

class FileHubHandler(BaseHTTPRequestHandler):
    """HTTP request handler for file hub"""
    
    storage = FileStorage()
    
    def do_GET(self):
        """Handle GET requests"""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        
        # Route to appropriate handler
        if path == '/' or path == '/index.html':
            self.serve_index()
        elif path == '/files':
            self.serve_file_list()
        elif path.startswith('/category/'):
            category = path.replace('/category/', '')
            self.serve_category(category)
        elif path.startswith('/view/'):
            file_id = path.replace('/view/', '')
            self.serve_file_view(file_id)
        elif path.startswith('/download/'):
            file_id = path.replace('/download/', '')
            self.serve_download(file_id)
        elif path.startswith('/thumb/'):
            file_id = path.replace('/thumb/', '')
            self.serve_thumbnail(file_id)
        elif path == '/upload':
            self.serve_upload_page()
        elif path == '/api/files':
            self.serve_api_files()
        elif path.startswith('/static/'):
            self.serve_static(path.replace('/static/', ''))
        else:
            self.send_error(404, "File not found")
    
    def do_POST(self):
        """Handle POST requests"""
        if self.path == '/upload':
            self.handle_upload()
        elif self.path == '/api/delete':
            self.handle_delete()
        elif self.path == '/api/text':
            self.handle_text_upload()
        else:
            self.send_error(404)
    
    def serve_index(self):
        """Serve main index page"""
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        html = self.get_index_html()
        self.wfile.write(html.encode())
    
    def serve_file_list(self):
        """Serve file list page"""
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        page = int(self.get_param('page', '1'))
        files = self.storage.get_files(page=page)
        
        html = self.get_file_list_html(files)
        self.wfile.write(html.encode())
    
    def serve_category(self, category):
        """Serve category page"""
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        page = int(self.get_param('page', '1'))
        files = self.storage.get_files(category, page)
        
        html = self.get_category_html(category, files)
        self.wfile.write(html.encode())
    
    def serve_file_view(self, file_id):
        """Serve single file view page"""
        file_info = self.storage.get_file(file_id)
        if not file_info:
            self.send_error(404)
            return
            
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        html = self.get_file_view_html(file_info)
        self.wfile.write(html.encode())
    
    def serve_download(self, file_id):
        """Serve file download"""
        file_info = self.storage.get_file(file_id)
        if not file_info:
            self.send_error(404)
            return
            
        file_path = Path(file_info['path'])
        if not file_path.exists():
            self.send_error(404)
            return
            
        # Increment download count
        self.storage.increment_download(file_id)
        
        # Serve file
        self.send_response(200)
        self.send_header('Content-type', file_info['mime_type'])
        self.send_header('Content-Disposition', f'attachment; filename="{file_info["name"]}"')
        self.send_header('Content-Length', str(file_path.stat().st_size))
        self.end_headers()
        
        with open(file_path, 'rb') as f:
            self.wfile.write(f.read())
    
    def serve_thumbnail(self, file_id):
        """Serve thumbnail for images"""
        file_info = self.storage.get_file(file_id)
        if not file_info or file_info['category'] != 'photos':
            self.send_error(404)
            return
            
        try:
            from PIL import Image
            
            file_path = Path(file_info['path'])
            thumb_dir = Config.STORAGE_DIR / 'thumbs'
            thumb_dir.mkdir(exist_ok=True)
            
            thumb_path = thumb_dir / f"{file_id}.jpg"
            
            # Create thumbnail if it doesn't exist
            if not thumb_path.exists():
                img = Image.open(file_path)
                img.thumbnail(Config.THUMBNAIL_SIZE)
                img.save(thumb_path, 'JPEG')
            
            # Serve thumbnail
            self.send_response(200)
            self.send_header('Content-type', 'image/jpeg')
            self.end_headers()
            
            with open(thumb_path, 'rb') as f:
                self.wfile.write(f.read())
                
        except Exception as e:
            self.send_error(500, str(e))
    
    def serve_upload_page(self):
        """Serve upload page"""
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        html = self.get_upload_html()
        self.wfile.write(html.encode())
    
    def serve_api_files(self):
        """Serve files API"""
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        
        category = self.get_param('category')
        page = int(self.get_param('page', '1'))
        
        files = self.storage.get_files(category, page)
        self.wfile.write(json.dumps(files).encode())
    
    def serve_static(self, filename):
        """Serve static files"""
        static_dir = Config.STORAGE_DIR / 'static'
        static_dir.mkdir(exist_ok=True)
        
        file_path = static_dir / filename
        if not file_path.exists():
            self.send_error(404)
            return
            
        mime_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        
        self.send_response(200)
        self.send_header('Content-type', mime_type)
        self.end_headers()
        
        with open(file_path, 'rb') as f:
            self.wfile.write(f.read())
    
    def handle_upload(self):
        """Handle file upload"""
        content_type = self.headers.get('Content-Type')
        
        if not content_type or 'multipart/form-data' not in content_type:
            self.send_error(400, "Invalid content type")
            return
            
        # Parse multipart form
        boundary = content_type.split('boundary=')[1].encode()
        content_length = int(self.headers.get('Content-Length', 0))
        
        if content_length > Config.MAX_UPLOAD_SIZE:
            self.send_error(413, "File too large")
            return
            
        # Read data
        data = self.rfile.read(content_length)
        
        # Parse multipart
        parts = data.split(b'--' + boundary)
        
        for part in parts:
            if b'Content-Disposition' in part:
                # Extract filename
                filename_match = re.search(b'filename="(.+?)"', part)
                if filename_match:
                    filename = filename_match.group(1).decode()
                    
                    # Find file data
                    file_data = part.split(b'\r\n\r\n', 1)[1].rsplit(b'\r\n', 1)[0]
                    
                    # Save file
                    temp_path = Config.STORAGE_DIR / 'temp' / filename
                    temp_path.parent.mkdir(exist_ok=True)
                    
                    with open(temp_path, 'wb') as f:
                        f.write(file_data)
                    
                    # Add to storage
                    category = self.get_category_from_filename(filename)
                    self.storage.add_file(temp_path, filename, category)
        
        # Redirect to file list
        self.send_response(302)
        self.send_header('Location', '/files')
        self.end_headers()
    
    def handle_delete(self):
        """Handle file deletion"""
        content_length = int(self.headers.get('Content-Length', 0))
        data = self.rfile.read(content_length).decode()
        
        try:
            req = json.loads(data)
            file_id = req.get('id')
            
            if file_id and self.storage.delete_file(file_id):
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
            else:
                self.send_error(404)
        except:
            self.send_error(400)
    
    def handle_text_upload(self):
        """Handle text upload"""
        content_length = int(self.headers.get('Content-Length', 0))
        data = self.rfile.read(content_length).decode()
        
        try:
            req = json.loads(data)
            text = req.get('text', '')
            title = req.get('title', f'text_{int(time.time())}.txt')
            
            if text:
                # Save text file
                temp_path = Config.STORAGE_DIR / 'temp' / title
                temp_path.parent.mkdir(exist_ok=True)
                
                with open(temp_path, 'w') as f:
                    f.write(text)
                
                # Add to storage
                self.storage.add_file(temp_path, title, 'text')
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
            else:
                self.send_error(400)
        except:
            self.send_error(400)
    
    def get_param(self, name, default=None):
        """Get query parameter"""
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        return params.get(name, [default])[0]
    
    def get_category_from_filename(self, filename):
        """Get category from filename"""
        ext = Path(filename).suffix.lower()
        
        if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
            return 'photos'
        elif ext in ['.mp4', '.avi', '.mkv', '.mov']:
            return 'videos'
        elif ext in ['.txt', '.md']:
            return 'text'
        elif ext in ['.zip', '.tar', '.gz']:
            return 'archive'
        else:
            return 'uploads'
    
    def log_message(self, format, *args):
        """Override logging"""
        pass  # Suppress default logging
    
    # ==================== HTML TEMPLATES ====================
    
    def get_index_html(self):
        """Get index page HTML"""
        return '''<!DOCTYPE html>
<html>
<head>
    <title>Hoster</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            color: #333;
            line-height: 1.6;
        }
        
        .header {
            background: #2196F3;
            color: white;
            padding: 2rem;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        .header h1 {
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
        }
        
        .header p {
            font-size: 1.1rem;
            opacity: 0.9;
        }
        
        .nav {
            background: white;
            padding: 1rem;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            position: sticky;
            top: 0;
            z-index: 100;
        }
        
        .nav ul {
            list-style: none;
            display: flex;
            justify-content: center;
            gap: 2rem;
            max-width: 1200px;
            margin: 0 auto;
        }
        
        .nav a {
            color: #333;
            text-decoration: none;
            padding: 0.5rem 1rem;
            border-radius: 4px;
            transition: background 0.3s;
        }
        
        .nav a:hover {
            background: #e3f2fd;
        }
        
        .nav a.active {
            background: #2196F3;
            color: white;
        }
        
        .container {
            max-width: 1200px;
            margin: 2rem auto;
            padding: 0 1rem;
        }
        
        .hero {
            text-align: center;
            padding: 3rem;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 2rem;
        }
        
        .hero h2 {
            font-size: 2rem;
            margin-bottom: 1rem;
            color: #2196F3;
        }
        
        .hero p {
            font-size: 1.2rem;
            color: #666;
            max-width: 600px;
            margin: 0 auto 2rem;
        }
        
        .features {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 2rem;
            margin-bottom: 3rem;
        }
        
        .feature-card {
            background: white;
            padding: 2rem;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            text-align: center;
        }
        
        .feature-icon {
            font-size: 3rem;
            margin-bottom: 1rem;
        }
        
        .feature-title {
            font-size: 1.3rem;
            font-weight: bold;
            margin-bottom: 0.5rem;
            color: #2196F3;
        }
        
        .categories {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
        }
        
        .category-card {
            background: white;
            padding: 2rem;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            text-align: center;
            text-decoration: none;
            color: #333;
            transition: transform 0.3s;
        }
        
        .category-card:hover {
            transform: translateY(-5px);
        }
        
        .category-icon {
            font-size: 2.5rem;
            margin-bottom: 1rem;
        }
        
        .category-name {
            font-size: 1.2rem;
            font-weight: bold;
            margin-bottom: 0.5rem;
        }
        
        .category-count {
            color: #666;
        }
        
        .btn {
            display: inline-block;
            padding: 1rem 2rem;
            background: #2196F3;
            color: white;
            text-decoration: none;
            border-radius: 4px;
            font-size: 1.1rem;
            transition: background 0.3s;
            border: none;
            cursor: pointer;
        }
        
        .btn:hover {
            background: #1976D2;
        }
        
        .footer {
            text-align: center;
            padding: 2rem;
            background: white;
            margin-top: 3rem;
            color: #666;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>📁 Hoster</h1>
        <p>Share files, photos, videos on your local network</p>
    </div>
    
    <div class="nav">
        <ul>
            <li><a href="/" class="active">Home</a></li>
            <li><a href="/files">All Files</a></li>
            <li><a href="/category/photos">Photos</a></li>
            <li><a href="/category/videos">Videos</a></li>
            <li><a href="/category/text">Text</a></li>
            <li><a href="/upload">Upload</a></li>
        </ul>
    </div>
    
    <div class="container">
        <div class="hero">
            <h2>Welcome to Your File Hub</h2>
            <p>Store and share files easily on your local network. No login required - just upload and share!</p>
            <a href="/upload" class="btn">📤 Upload Files</a>
        </div>
        
        <div class="features">
            <div class="feature-card">
                <div class="feature-icon">📸</div>
                <div class="feature-title">Photos</div>
                <p>Store and view your photos with automatic thumbnails</p>
            </div>
            
            <div class="feature-card">
                <div class="feature-icon">🎥</div>
                <div class="feature-title">Videos</div>
                <p>Share videos that play directly in the browser</p>
            </div>
            
            <div class="feature-card">
                <div class="feature-icon">📝</div>
                <div class="feature-title">Text</div>
                <p>Create and share text notes instantly</p>
            </div>
            
            <div class="feature-card">
                <div class="feature-icon">📦</div>
                <div class="feature-title">Any File</div>
                <p>Upload any file type up to 1GB</p>
            </div>
        </div>
        
        <h2 style="text-align: center; margin-bottom: 1.5rem;">Browse by Category</h2>
        
        <div class="categories">
            <a href="/category/photos" class="category-card">
                <div class="category-icon">📸</div>
                <div class="category-name">Photos</div>
                <div class="category-count">View Gallery</div>
            </a>
            
            <a href="/category/videos" class="category-card">
                <div class="category-icon">🎥</div>
                <div class="category-name">Videos</div>
                <div class="category-count">Watch Videos</div>
            </a>
            
            <a href="/category/text" class="category-card">
                <div class="category-icon">📝</div>
                <div class="category-name">Text</div>
                <div class="category-count">Read Notes</div>
            </a>
            
            <a href="/category/archive" class="category-card">
                <div class="category-icon">📦</div>
                <div class="category-name">Archives</div>
                <div class="category-count">Download ZIPs</div>
            </a>
            
            <a href="/category/uploads" class="category-card">
                <div class="category-icon">📁</div>
                <div class="category-name">All Files</div>
                <div class="category-count">Everything</div>
            </a>
        </div>
        
        <div style="text-align: center; margin-top: 3rem;">
            <h3>Quick Text Upload</h3>
            <p style="margin-bottom: 1rem;">Paste text and save it instantly</p>
            <textarea id="quick-text" style="width: 100%; max-width: 500px; height: 100px; padding: 0.5rem; border: 1px solid #ddd; border-radius: 4px; margin-bottom: 1rem;" placeholder="Paste your text here..."></textarea>
            <br>
            <button onclick="uploadText()" class="btn" style="padding: 0.5rem 2rem;">Save Text</button>
        </div>
    </div>
    
    <div class="footer">
        <p>Simple File Hub - Share files on your local network</p>
        <p style="font-size: 0.9rem; margin-top: 0.5rem;">Server: ''' + Config.SERVER_NAME + ''' ''' + Config.SERVER_VERSION + '''</p>
    </div>
    
    <script>
        function uploadText() {
            const text = document.getElementById('quick-text').value;
            if (!text) {
                alert('Please enter some text');
                return;
            }
            
            const title = prompt('Enter a title for this text:', `note_${Date.now()}.txt`);
            if (!title) return;
            
            fetch('/api/text', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({text, title})
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert('Text saved successfully!');
                    document.getElementById('quick-text').value = '';
                }
            })
            .catch(error => {
                alert('Error saving text: ' + error);
            });
        }
    </script>
</body>
</html>
'''
    
    def get_file_list_html(self, files_data):
        """Get file list page HTML"""
        files = files_data['files']
        page = files_data['page']
        pages = files_data['pages']
        
        html = '''<!DOCTYPE html>
<html>
<head>
    <title>All Files - Hoster</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            color: #333;
        }
        
        .header {
            background: #2196F3;
            color: white;
            padding: 1rem;
            text-align: center;
        }
        
        .nav {
            background: white;
            padding: 1rem;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            position: sticky;
            top: 0;
            z-index: 100;
        }
        
        .nav ul {
            list-style: none;
            display: flex;
            justify-content: center;
            gap: 2rem;
            max-width: 1200px;
            margin: 0 auto;
        }
        
        .nav a {
            color: #333;
            text-decoration: none;
            padding: 0.5rem 1rem;
            border-radius: 4px;
        }
        
        .nav a:hover {
            background: #e3f2fd;
        }
        
        .nav a.active {
            background: #2196F3;
            color: white;
        }
        
        .container {
            max-width: 1200px;
            margin: 2rem auto;
            padding: 0 1rem;
        }
        
        .files-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
        }
        
        .files-header h2 {
            color: #333;
        }
        
        .upload-btn {
            display: inline-block;
            padding: 0.75rem 1.5rem;
            background: #4CAF50;
            color: white;
            text-decoration: none;
            border-radius: 4px;
        }
        
        .file-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 1.5rem;
        }
        
        .file-card {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            overflow: hidden;
            transition: transform 0.3s;
        }
        
        .file-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        }
        
        .file-preview {
            height: 150px;
            background: #f9f9f9;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 3rem;
            color: #666;
        }
        
        .file-info {
            padding: 1rem;
        }
        
        .file-name {
            font-weight: bold;
            margin-bottom: 0.5rem;
            word-break: break-all;
        }
        
        .file-meta {
            font-size: 0.9rem;
            color: #666;
            margin-bottom: 1rem;
        }
        
        .file-actions {
            display: flex;
            gap: 0.5rem;
        }
        
        .btn {
            flex: 1;
            padding: 0.5rem;
            text-align: center;
            text-decoration: none;
            border-radius: 4px;
            font-size: 0.9rem;
        }
        
        .btn-view {
            background: #2196F3;
            color: white;
        }
        
        .btn-download {
            background: #4CAF50;
            color: white;
        }
        
        .btn-delete {
            background: #f44336;
            color: white;
            border: none;
            cursor: pointer;
        }
        
        .pagination {
            display: flex;
            justify-content: center;
            gap: 1rem;
            margin-top: 2rem;
        }
        
        .page-link {
            padding: 0.5rem 1rem;
            background: white;
            color: #333;
            text-decoration: none;
            border-radius: 4px;
            border: 1px solid #ddd;
        }
        
        .page-link.active {
            background: #2196F3;
            color: white;
            border-color: #2196F3;
        }
        
        .empty-state {
            text-align: center;
            padding: 3rem;
            background: white;
            border-radius: 8px;
            color: #666;
        }
        
        .empty-icon {
            font-size: 4rem;
            margin-bottom: 1rem;
        }
        
        .footer {
            text-align: center;
            padding: 2rem;
            background: white;
            margin-top: 3rem;
            color: #666;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>📁 Hoster - All Files</h1>
    </div>
    
    <div class="nav">
        <ul>
            <li><a href="/">Home</a></li>
            <li><a href="/files" class="active">All Files</a></li>
            <li><a href="/category/photos">Photos</a></li>
            <li><a href="/category/videos">Videos</a></li>
            <li><a href="/category/text">Text</a></li>
            <li><a href="/upload">Upload</a></li>
        </ul>
    </div>
    
    <div class="container">
        <div class="files-header">
            <h2>All Files</h2>
            <a href="/upload" class="upload-btn">📤 Upload New File</a>
        </div>
        
        <div class="file-grid">
        '''
        
        if not files:
            html += '''
            <div class="empty-state">
                <div class="empty-icon">📂</div>
                <h3>No files yet</h3>
                <p>Upload your first file to get started</p>
                <a href="/upload" class="btn upload-btn" style="display: inline-block; margin-top: 1rem;">Upload File</a>
            </div>
            '''
        else:
            for f in files:
                size_mb = f['size'] / (1024 * 1024)
                date = datetime.fromtimestamp(f['uploaded']).strftime('%Y-%m-%d %H:%M')
                
                # Choose icon based on category
                icons = {
                    'photos': '📸',
                    'videos': '🎥',
                    'text': '📝',
                    'archive': '📦',
                    'uploads': '📁'
                }
                icon = icons.get(f['category'], '📄')
                
                html += f'''
                <div class="file-card">
                    <div class="file-preview">{icon}</div>
                    <div class="file-info">
                        <div class="file-name">{f['name']}</div>
                        <div class="file-meta">
                            {size_mb:.2f} MB • {date}<br>
                            Downloads: {f['downloads']}
                        </div>
                        <div class="file-actions">
                            <a href="/view/{f['id']}" class="btn btn-view">View</a>
                            <a href="/download/{f['id']}" class="btn btn-download">Download</a>
                            <button onclick="deleteFile('{f['id']}')" class="btn btn-delete">Delete</button>
                        </div>
                    </div>
                </div>
                '''
        
        html += '''
        </div>
        
        <div class="pagination">
        '''
        
        if pages > 1:
            for p in range(1, pages + 1):
                active = 'active' if p == page else ''
                html += f'<a href="/files?page={p}" class="page-link {active}">{p}</a>'
        
        html += '''
        </div>
    </div>
    
    <div class="footer">
        <p>Simple File Hub - Share files on your local network</p>
    </div>
    
    <script>
        function deleteFile(id) {
            if (confirm('Are you sure you want to delete this file?')) {
                fetch('/api/delete', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({id})
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        location.reload();
                    } else {
                        alert('Failed to delete file');
                    }
                })
                .catch(error => {
                    alert('Error: ' + error);
                });
            }
        }
    </script>
</body>
</html>
'''
        return html
    
    def get_category_html(self, category, files_data):
        """Get category page HTML"""
        files = files_data['files']
        page = files_data['page']
        pages = files_data['pages']
        
        # Category display names
        cat_names = {
            'photos': 'Photos',
            'videos': 'Videos',
            'text': 'Text Notes',
            'archive': 'Archives',
            'uploads': 'Other Files'
        }
        
        cat_icons = {
            'photos': '📸',
            'videos': '🎥',
            'text': '📝',
            'archive': '📦',
            'uploads': '📁'
        }
        
        cat_name = cat_names.get(category, category.capitalize())
        cat_icon = cat_icons.get(category, '📄')
        
        html = f'''<!DOCTYPE html>
<html>
<head>
    <title>{cat_name} - Hoster</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            color: #333;
        }}
        
        .header {{
            background: #2196F3;
            color: white;
            padding: 1rem;
            text-align: center;
        }}
        
        .nav {{
            background: white;
            padding: 1rem;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            position: sticky;
            top: 0;
            z-index: 100;
        }}
        
        .nav ul {{
            list-style: none;
            display: flex;
            justify-content: center;
            gap: 2rem;
            max-width: 1200px;
            margin: 0 auto;
        }}
        
        .nav a {{
            color: #333;
            text-decoration: none;
            padding: 0.5rem 1rem;
            border-radius: 4px;
        }}
        
        .nav a:hover {{
            background: #e3f2fd;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 2rem auto;
            padding: 0 1rem;
        }}
        
        .category-header {{
            text-align: center;
            margin-bottom: 2rem;
        }}
        
        .category-icon {{
            font-size: 4rem;
            margin-bottom: 1rem;
        }}
        
        .category-title {{
            font-size: 2rem;
            color: #333;
        }}
        '''
        
        # Add category-specific styles
        if category == 'photos':
            html += '''
        .photo-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 1rem;
        }
        
        .photo-card {
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: transform 0.3s;
        }
        
        .photo-card:hover {
            transform: scale(1.05);
        }
        
        .photo-preview {
            height: 200px;
            background: #f9f9f9;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .photo-preview img {
            max-width: 100%;
            max-height: 100%;
            object-fit: cover;
        }
        
        .photo-info {
            padding: 0.75rem;
        }
        
        .photo-name {
            font-size: 0.9rem;
            word-break: break-all;
        }
        '''
        elif category == 'videos':
            html += '''
        .video-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 1.5rem;
        }
        
        .video-card {
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        .video-preview {
            background: #000;
            height: 200px;
        }
        
        .video-preview video {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        
        .video-info {
            padding: 1rem;
        }
        '''
        
        html += f'''
        .file-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}
        
        .file-card {{
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            overflow: hidden;
            transition: transform 0.3s;
        }}
        
        .file-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        }}
        
        .file-preview {{
            height: 150px;
            background: #f9f9f9;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 3rem;
            color: #666;
        }}
        
        .file-info {{
            padding: 1rem;
        }}
        
        .file-name {{
            font-weight: bold;
            margin-bottom: 0.5rem;
            word-break: break-all;
        }}
        
        .file-meta {{
            font-size: 0.9rem;
            color: #666;
            margin-bottom: 1rem;
        }}
        
        .file-actions {{
            display: flex;
            gap: 0.5rem;
        }}
        
        .btn {{
            flex: 1;
            padding: 0.5rem;
            text-align: center;
            text-decoration: none;
            border-radius: 4px;
            font-size: 0.9rem;
        }}
        
        .btn-view {{
            background: #2196F3;
            color: white;
        }}
        
        .btn-download {{
            background: #4CAF50;
            color: white;
        }}
        
        .btn-delete {{
            background: #f44336;
            color: white;
            border: none;
            cursor: pointer;
        }}
        
        .pagination {{
            display: flex;
            justify-content: center;
            gap: 1rem;
            margin-top: 2rem;
        }}
        
        .page-link {{
            padding: 0.5rem 1rem;
            background: white;
            color: #333;
            text-decoration: none;
            border-radius: 4px;
            border: 1px solid #ddd;
        }}
        
        .page-link.active {{
            background: #2196F3;
            color: white;
            border-color: #2196F3;
        }}
        
        .empty-state {{
            text-align: center;
            padding: 3rem;
            background: white;
            border-radius: 8px;
            color: #666;
        }}
        
        .upload-link {{
            display: inline-block;
            margin-top: 1rem;
            padding: 0.75rem 1.5rem;
            background: #4CAF50;
            color: white;
            text-decoration: none;
            border-radius: 4px;
        }}
        
        .footer {{
            text-align: center;
            padding: 2rem;
            background: white;
            margin-top: 3rem;
            color: #666;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{cat_icon} {cat_name}</h1>
    </div>
    
    <div class="nav">
        <ul>
            <li><a href="/">Home</a></li>
            <li><a href="/files">All Files</a></li>
            <li><a href="/category/photos">Photos</a></li>
            <li><a href="/category/videos">Videos</a></li>
            <li><a href="/category/text">Text</a></li>
            <li><a href="/upload">Upload</a></li>
        </ul>
    </div>
    
    <div class="container">
        <div class="category-header">
            <div class="category-icon">{cat_icon}</div>
            <h1 class="category-title">{cat_name}</h1>
        </div>
        
        <div class="file-grid">
        '''
        
        if not files:
            html += f'''
            <div class="empty-state">
                <div class="empty-icon">{cat_icon}</div>
                <h3>No {cat_name} yet</h3>
                <p>Upload your first {cat_name.lower()} to get started</p>
                <a href="/upload" class="upload-link">Upload {cat_name}</a>
            </div>
            '''
        else:
            for f in files:
                size_mb = f['size'] / (1024 * 1024)
                date = datetime.fromtimestamp(f['uploaded']).strftime('%Y-%m-%d')
                
                if category == 'photos':
                    html += f'''
                    <div class="photo-card">
                        <div class="photo-preview">
                            <img src="/thumb/{f['id']}" alt="{f['name']}">
                        </div>
                        <div class="photo-info">
                            <div class="photo-name">{f['name']}</div>
                            <div style="font-size: 0.8rem; color: #666;">{size_mb:.2f} MB • {date}</div>
                            <div class="file-actions" style="margin-top: 0.5rem;">
                                <a href="/view/{f['id']}" class="btn btn-view">View</a>
                                <a href="/download/{f['id']}" class="btn btn-download">Download</a>
                            </div>
                        </div>
                    </div>
                    '''
                elif category == 'videos':
                    html += f'''
                    <div class="video-card">
                        <div class="video-preview">
                            <video controls>
                                <source src="/download/{f['id']}" type="{f['mime_type']}">
                                Your browser does not support video.
                            </video>
                        </div>
                        <div class="video-info">
                            <div class="file-name">{f['name']}</div>
                            <div class="file-meta">{size_mb:.2f} MB • {date}</div>
                            <div class="file-actions">
                                <a href="/view/{f['id']}" class="btn btn-view">Details</a>
                                <a href="/download/{f['id']}" class="btn btn-download">Download</a>
                            </div>
                        </div>
                    </div>
                    '''
                else:
                    html += f'''
                    <div class="file-card">
                        <div class="file-preview">{cat_icon}</div>
                        <div class="file-info">
                            <div class="file-name">{f['name']}</div>
                            <div class="file-meta">{size_mb:.2f} MB • {date}</div>
                            <div class="file-actions">
                                <a href="/view/{f['id']}" class="btn btn-view">View</a>
                                <a href="/download/{f['id']}" class="btn btn-download">Download</a>
                                <button onclick="deleteFile('{f['id']}')" class="btn btn-delete">Delete</button>
                            </div>
                        </div>
                    </div>
                    '''
        
        html += '''
        </div>
        
        <div class="pagination">
        '''
        
        if pages > 1:
            for p in range(1, pages + 1):
                active = 'active' if p == page else ''
                html += f'<a href="/category/{category}?page={p}" class="page-link {active}">{p}</a>'
        
        html += '''
        </div>
    </div>
    
    <div class="footer">
        <p>Hoster - Share files on your local network</p>
    </div>
    
    <script>
        function deleteFile(id) {
            if (confirm('Are you sure you want to delete this file?')) {
                fetch('/api/delete', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({id})
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        location.reload();
                    } else {
                        alert('Failed to delete file');
                    }
                })
                .catch(error => {
                    alert('Error: ' + error);
                });
            }
        }
    </script>
</body>
</html>
'''
        return html
    
    def get_file_view_html(self, file_info):
        """Get file view page HTML"""
        category = file_info['category']
        size_mb = file_info['size'] / (1024 * 1024)
        date = datetime.fromtimestamp(file_info['uploaded']).strftime('%Y-%m-%d %H:%M')
        
        html = f'''<!DOCTYPE html>
<html>
<head>
    <title>{file_info['name']} - Hoster</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            color: #333;
        }}
        
        .header {{
            background: #2196F3;
            color: white;
            padding: 1rem;
            text-align: center;
        }}
        
        .nav {{
            background: white;
            padding: 1rem;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        
        .nav ul {{
            list-style: none;
            display: flex;
            justify-content: center;
            gap: 2rem;
            max-width: 1200px;
            margin: 0 auto;
        }}
        
        .nav a {{
            color: #333;
            text-decoration: none;
            padding: 0.5rem 1rem;
            border-radius: 4px;
        }}
        
        .nav a:hover {{
            background: #e3f2fd;
        }}
        
        .container {{
            max-width: 900px;
            margin: 2rem auto;
            padding: 0 1rem;
        }}
        
        .file-card {{
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        
        .file-preview {{
            padding: 2rem;
            background: #f9f9f9;
            text-align: center;
            border-bottom: 1px solid #eee;
        }}
        
        .file-info {{
            padding: 2rem;
        }}
        
        .file-name {{
            font-size: 1.5rem;
            font-weight: bold;
            margin-bottom: 1rem;
            color: #2196F3;
        }}
        
        .file-details {{
            background: #f5f5f5;
            padding: 1rem;
            border-radius: 4px;
            margin-bottom: 1.5rem;
        }}
        
        .detail-row {{
            display: flex;
            margin-bottom: 0.5rem;
        }}
        
        .detail-label {{
            width: 100px;
            font-weight: bold;
            color: #666;
        }}
        
        .detail-value {{
            flex: 1;
        }}
        
        .file-actions {{
            display: flex;
            gap: 1rem;
        }}
        
        .btn {{
            flex: 1;
            padding: 1rem;
            text-align: center;
            text-decoration: none;
            border-radius: 4px;
            font-size: 1rem;
            border: none;
            cursor: pointer;
        }}
        
        .btn-download {{
            background: #4CAF50;
            color: white;
        }}
        
        .btn-delete {{
            background: #f44336;
            color: white;
        }}
        
        .btn-back {{
            background: #2196F3;
            color: white;
            display: inline-block;
            padding: 0.75rem 1.5rem;
            text-decoration: none;
            border-radius: 4px;
            margin-bottom: 1rem;
        }}
        
        .footer {{
            text-align: center;
            padding: 2rem;
            background: white;
            margin-top: 3rem;
            color: #666;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📁 Hoster - File Details</h1>
    </div>
    
    <div class="nav">
        <ul>
            <li><a href="/">Home</a></li>
            <li><a href="/files">All Files</a></li>
            <li><a href="/category/photos">Photos</a></li>
            <li><a href="/category/videos">Videos</a></li>
            <li><a href="/category/text">Text</a></li>
        </ul>
    </div>
    
    <div class="container">
        <a href="javascript:history.back()" class="btn-back">← Back</a>
        
        <div class="file-card">
            <div class="file-preview">
        '''
        
        # Add preview based on category
        if category == 'photos':
            html += f'<img src="/download/{file_info["id"]}" style="max-width: 100%; max-height: 400px;" alt="{file_info["name"]}">'
        elif category == 'videos':
            html += f'''
            <video controls style="max-width: 100%; max-height: 400px;">
                <source src="/download/{file_info['id']}" type="{file_info['mime_type']}">
                Your browser does not support video.
            </video>
            '''
        elif category == 'text':
            # For text files, fetch and display content
            html += f'''
            <iframe src="/download/{file_info['id']}" style="width: 100%; height: 400px; border: none;"></iframe>
            '''
        else:
            # Generic file icon
            html += '<div style="font-size: 5rem;">📄</div>'
        
        html += f'''
            </div>
            
            <div class="file-info">
                <h2 class="file-name">{file_info['name']}</h2>
                
                <div class="file-details">
                    <div class="detail-row">
                        <span class="detail-label">Size:</span>
                        <span class="detail-value">{size_mb:.2f} MB</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Uploaded:</span>
                        <span class="detail-value">{date}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Category:</span>
                        <span class="detail-value">{category}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Downloads:</span>
                        <span class="detail-value">{file_info['downloads']}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">MIME Type:</span>
                        <span class="detail-value">{file_info['mime_type']}</span>
                    </div>
                </div>
                
                <div class="file-actions">
                    <a href="/download/{file_info['id']}" class="btn btn-download">⬇️ Download File</a>
                    <button onclick="deleteFile()" class="btn btn-delete">🗑️ Delete File</button>
                </div>
            </div>
        </div>
    </div>
    
    <div class="footer">
        <p>Simple File Hub - Share files on your local network</p>
    </div>
    
    <script>
        function deleteFile() {{
            if (confirm('Are you sure you want to delete this file? This action cannot be undone.')) {{
                fetch('/api/delete', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json'
                    }},
                    body: JSON.stringify({{id: '{file_info['id']}'}})
                }})
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        alert('File deleted successfully');
                        window.location.href = '/files';
                    }} else {{
                        alert('Failed to delete file');
                    }}
                }})
                .catch(error => {{
                    alert('Error: ' + error);
                }});
            }}
        }}
    </script>
</body>
</html>
'''
        return html
    
    def get_upload_html(self):
        """Get upload page HTML"""
        return '''<!DOCTYPE html>
<html>
<head>
    <title>Upload Files - Hoster</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            color: #333;
        }
        
        .header {
            background: #2196F3;
            color: white;
            padding: 1rem;
            text-align: center;
        }
        
        .nav {
            background: white;
            padding: 1rem;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        .nav ul {
            list-style: none;
            display: flex;
            justify-content: center;
            gap: 2rem;
            max-width: 1200px;
            margin: 0 auto;
        }
        
        .nav a {
            color: #333;
            text-decoration: none;
            padding: 0.5rem 1rem;
            border-radius: 4px;
        }
        
        .nav a:hover {
            background: #e3f2fd;
        }
        
        .container {
            max-width: 600px;
            margin: 2rem auto;
            padding: 0 1rem;
        }
        
        .upload-card {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            padding: 2rem;
        }
        
        .upload-title {
            font-size: 1.5rem;
            font-weight: bold;
            margin-bottom: 1.5rem;
            color: #2196F3;
            text-align: center;
        }
        
        .upload-area {
            border: 2px dashed #2196F3;
            border-radius: 8px;
            padding: 3rem;
            text-align: center;
            margin-bottom: 1.5rem;
            cursor: pointer;
            transition: background 0.3s;
        }
        
        .upload-area:hover {
            background: #e3f2fd;
        }
        
        .upload-icon {
            font-size: 3rem;
            margin-bottom: 1rem;
            color: #2196F3;
        }
        
        .upload-text {
            font-size: 1.1rem;
            color: #666;
        }
        
        .upload-hint {
            font-size: 0.9rem;
            color: #999;
            margin-top: 0.5rem;
        }
        
        .file-input {
            display: none;
        }
        
        .selected-file {
            margin: 1rem 0;
            padding: 1rem;
            background: #f5f5f5;
            border-radius: 4px;
            display: none;
        }
        
        .selected-file.active {
            display: block;
        }
        
        .file-name {
            font-weight: bold;
            margin-bottom: 0.5rem;
        }
        
        .file-size {
            color: #666;
            font-size: 0.9rem;
        }
        
        .upload-btn {
            width: 100%;
            padding: 1rem;
            background: #4CAF50;
            color: white;
            border: none;
            border-radius: 4px;
            font-size: 1.1rem;
            cursor: pointer;
            transition: background 0.3s;
        }
        
        .upload-btn:hover {
            background: #45a049;
        }
        
        .upload-btn:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        
        .progress-bar {
            width: 100%;
            height: 20px;
            background: #f0f0f0;
            border-radius: 10px;
            overflow: hidden;
            margin: 1rem 0;
            display: none;
        }
        
        .progress-bar.active {
            display: block;
        }
        
        .progress-fill {
            height: 100%;
            background: #4CAF50;
            width: 0%;
            transition: width 0.3s;
        }
        
        .message {
            padding: 1rem;
            border-radius: 4px;
            margin: 1rem 0;
            display: none;
        }
        
        .message.success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        
        .message.error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        
        .or-divider {
            text-align: center;
            margin: 1.5rem 0;
            position: relative;
        }
        
        .or-divider::before,
        .or-divider::after {
            content: '';
            position: absolute;
            top: 50%;
            width: 45%;
            height: 1px;
            background: #ddd;
        }
        
        .or-divider::before {
            left: 0;
        }
        
        .or-divider::after {
            right: 0;
        }
        
        .or-text {
            background: white;
            padding: 0 0.5rem;
            color: #999;
            position: relative;
            z-index: 1;
        }
        
        .text-upload {
            margin-top: 2rem;
        }
        
        .text-upload textarea {
            width: 100%;
            height: 150px;
            padding: 0.5rem;
            border: 1px solid #ddd;
            border-radius: 4px;
            margin-bottom: 1rem;
            font-family: monospace;
        }
        
        .footer {
            text-align: center;
            padding: 2rem;
            background: white;
            margin-top: 3rem;
            color: #666;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>📤 Upload Files - Hoster</h1>
    </div>
    
    <div class="nav">
        <ul>
            <li><a href="/">Home</a></li>
            <li><a href="/files">All Files</a></li>
            <li><a href="/category/photos">Photos</a></li>
            <li><a href="/category/videos">Videos</a></li>
            <li><a href="/category/text">Text</a></li>
        </ul>
    </div>
    
    <div class="container">
        <div class="upload-card">
            <h2 class="upload-title">Upload Files</h2>
            
            <div class="upload-area" id="dropArea">
                <div class="upload-icon">📁</div>
                <div class="upload-text">Drag & drop files here or click to select</div>
                <div class="upload-hint">Supports any file type up to 1GB</div>
            </div>
            
            <input type="file" id="fileInput" class="file-input" multiple>
            
            <div class="selected-file" id="selectedFile">
                <div class="file-name" id="fileName">No file selected</div>
                <div class="file-size" id="fileSize"></div>
            </div>
            
            <div class="progress-bar" id="progressBar">
                <div class="progress-fill" id="progressFill"></div>
            </div>
            
            <div class="message" id="message"></div>
            
            <button class="upload-btn" id="uploadBtn" onclick="uploadFile()" disabled>Upload File</button>
            
            <div class="or-divider">
                <span class="or-text">OR</span>
            </div>
            
            <div class="text-upload">
                <h3 style="margin-bottom: 1rem; text-align: center;">Paste Text</h3>
                <textarea id="textContent" placeholder="Paste your text here..."></textarea>
                <input type="text" id="textTitle" placeholder="Filename (e.g., notes.txt)" style="width: 100%; padding: 0.5rem; border: 1px solid #ddd; border-radius: 4px; margin-bottom: 1rem;">
                <button class="upload-btn" onclick="uploadText()" style="background: #2196F3;">Save Text</button>
            </div>
        </div>
    </div>
    
    <div class="footer">
        <p>Simple File Hub - Share files on your local network</p>
    </div>
    
    <script>
        const dropArea = document.getElementById('dropArea');
        const fileInput = document.getElementById('fileInput');
        const selectedFile = document.getElementById('selectedFile');
        const fileName = document.getElementById('fileName');
        const fileSize = document.getElementById('fileSize');
        const uploadBtn = document.getElementById('uploadBtn');
        const progressBar = document.getElementById('progressBar');
        const progressFill = document.getElementById('progressFill');
        const message = document.getElementById('message');
        
        let selectedFiles = [];
        
        // Drag & drop handlers
        dropArea.addEventListener('click', () => fileInput.click());
        
        dropArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropArea.style.background = '#e3f2fd';
        });
        
        dropArea.addEventListener('dragleave', (e) => {
            e.preventDefault();
            dropArea.style.background = '';
        });
        
        dropArea.addEventListener('drop', (e) => {
            e.preventDefault();
            dropArea.style.background = '';
            handleFiles(e.dataTransfer.files);
        });
        
        fileInput.addEventListener('change', (e) => {
            handleFiles(e.target.files);
        });
        
        function handleFiles(files) {
            selectedFiles = Array.from(files);
            
            if (selectedFiles.length > 0) {
                const file = selectedFiles[0];
                fileName.textContent = file.name;
                fileSize.textContent = formatBytes(file.size);
                selectedFile.classList.add('active');
                uploadBtn.disabled = false;
            }
        }
        
        function formatBytes(bytes) {
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }
        
        function uploadFile() {
            if (selectedFiles.length === 0) return;
            
            const formData = new FormData();
            for (const file of selectedFiles) {
                formData.append('files', file);
            }
            
            uploadBtn.disabled = true;
            progressBar.classList.add('active');
            message.style.display = 'none';
            
            const xhr = new XMLHttpRequest();
            xhr.open('POST', '/upload', true);
            
            xhr.upload.onprogress = (e) => {
                if (e.lengthComputable) {
                    const percent = (e.loaded / e.total) * 100;
                    progressFill.style.width = percent + '%';
                }
            };
            
            xhr.onload = () => {
                if (xhr.status === 302) {
                    showMessage('Files uploaded successfully!', 'success');
                    setTimeout(() => {
                        window.location.href = '/files';
                    }, 2000);
                } else {
                    showMessage('Upload failed. Please try again.', 'error');
                    uploadBtn.disabled = false;
                    progressBar.classList.remove('active');
                }
            };
            
            xhr.onerror = () => {
                showMessage('Upload failed. Please try again.', 'error');
                uploadBtn.disabled = false;
                progressBar.classList.remove('active');
            };
            
            xhr.send(formData);
        }
        
        function uploadText() {
            const text = document.getElementById('textContent').value;
            const title = document.getElementById('textTitle').value || `text_${Date.now()}.txt`;
            
            if (!text) {
                showMessage('Please enter some text', 'error');
                return;
            }
            
            fetch('/api/text', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({text, title})
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showMessage('Text saved successfully!', 'success');
                    document.getElementById('textContent').value = '';
                    document.getElementById('textTitle').value = '';
                    setTimeout(() => {
                        window.location.href = '/category/text';
                    }, 2000);
                } else {
                    showMessage('Failed to save text', 'error');
                }
            })
            .catch(error => {
                showMessage('Error: ' + error, 'error');
            });
        }
        
        function showMessage(msg, type) {
            message.textContent = msg;
            message.className = 'message ' + type;
            message.style.display = 'block';
            
            setTimeout(() => {
                message.style.display = 'none';
            }, 3000);
        }
    </script>
</body>
</html>
'''

# ==================== GUI CONTROL PANEL ====================

class FileHubGUI:
    """GUI control panel for File Hub"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Hoster Control Panel")
        self.root.geometry("600x500")
        self.root.resizable(False, False)
        
        # Colors
        self.bg_color = '#f5f5f5'
        self.primary = '#2196F3'
        self.success = '#4CAF50'
        self.warning = '#FF9800'
        self.danger = '#f44336'
        
        self.root.configure(bg=self.bg_color)
        
        # Server variables
        self.server = None
        self.server_thread = None
        self.is_running = False
        self.port = tk.StringVar(value=str(Config.DEFAULT_PORT))
        self.host = tk.StringVar(value=Config.DEFAULT_HOST)
        
        # Create GUI
        self.create_widgets()
        
        # Load stats
        self.storage = FileStorage()
        self.update_stats()
        
    def create_widgets(self):
        """Create GUI widgets"""
        # Title
        title_frame = tk.Frame(self.root, bg=self.primary, height=80)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)
        
        title = tk.Label(title_frame, text="📁 Hoster", 
                        bg=self.primary, fg='white',
                        font=('Arial', 20, 'bold'))
        title.pack(expand=True)
        
        subtitle = tk.Label(title_frame, text="Local Network File Sharing - No Authentication Required",
                          bg=self.primary, fg='white', font=('Arial', 10))
        subtitle.pack()
        
        # Main container
        main_frame = tk.Frame(self.root, bg=self.bg_color, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Server controls
        server_frame = tk.LabelFrame(main_frame, text="Server Controls", 
                                     bg=self.bg_color, font=('Arial', 11, 'bold'),
                                     padx=10, pady=10)
        server_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Host and port
        host_frame = tk.Frame(server_frame, bg=self.bg_color)
        host_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(host_frame, text="Host:", bg=self.bg_color, width=10, anchor='w').pack(side=tk.LEFT)
        host_entry = tk.Entry(host_frame, textvariable=self.host, width=20, state='readonly')
        host_entry.pack(side=tk.LEFT, padx=5)
        
        tk.Label(host_frame, text="Port:", bg=self.bg_color, width=10, anchor='w').pack(side=tk.LEFT, padx=(20,0))
        port_entry = tk.Entry(host_frame, textvariable=self.port, width=10)
        port_entry.pack(side=tk.LEFT, padx=5)
        
        # Server status
        status_frame = tk.Frame(server_frame, bg=self.bg_color)
        status_frame.pack(fill=tk.X, pady=10)
        
        self.status_label = tk.Label(status_frame, text="⏹️ Server Stopped", 
                                    bg=self.warning, fg='white', padx=10, pady=5)
        self.status_label.pack(side=tk.LEFT)
        
        # Start/Stop buttons
        btn_frame = tk.Frame(server_frame, bg=self.bg_color)
        btn_frame.pack(fill=tk.X)
        
        self.start_btn = tk.Button(btn_frame, text="▶ Start Server", 
                                   bg=self.success, fg='white',
                                   font=('Arial', 10, 'bold'),
                                   padx=20, pady=5, command=self.start_server)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = tk.Button(btn_frame, text="⏹ Stop Server", 
                                  bg=self.danger, fg='white',
                                  font=('Arial', 10, 'bold'),
                                  padx=20, pady=5, command=self.stop_server,
                                  state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="🌐 Open in Browser", 
                 bg=self.primary, fg='white',
                 font=('Arial', 10, 'bold'),
                 padx=20, pady=5, command=self.open_browser).pack(side=tk.LEFT, padx=5)
        
        # Server info
        info_frame = tk.LabelFrame(main_frame, text="Server Information",
                                    bg=self.bg_color, font=('Arial', 11, 'bold'),
                                    padx=10, pady=10)
        info_frame.pack(fill=tk.X, pady=10)
        
        self.url_label = tk.Label(info_frame, text="URL: Not running", 
                                   bg=self.bg_color, anchor='w', justify=tk.LEFT)
        self.url_label.pack(fill=tk.X, pady=2)
        
        self.network_label = tk.Label(info_frame, text="Network: " + self.get_network_info(),
                                      bg=self.bg_color, anchor='w', justify=tk.LEFT)
        self.network_label.pack(fill=tk.X, pady=2)
        
        # Storage stats
        stats_frame = tk.LabelFrame(main_frame, text="Storage Statistics",
                                     bg=self.bg_color, font=('Arial', 11, 'bold'),
                                     padx=10, pady=10)
        stats_frame.pack(fill=tk.X, pady=10)
        
        self.stats_text = tk.Text(stats_frame, bg='white', height=6, width=50, font=('Courier', 10))
        self.stats_text.pack(fill=tk.X, pady=5)
        
        # Quick actions
        actions_frame = tk.LabelFrame(main_frame, text="Quick Actions",
                                       bg=self.bg_color, font=('Arial', 11, 'bold'),
                                       padx=10, pady=10)
        actions_frame.pack(fill=tk.X, pady=10)
        
        tk.Button(actions_frame, text="📁 Open Storage Folder", 
                 command=self.open_storage,
                 bg=self.primary, fg='white', padx=20, pady=5).pack(side=tk.LEFT, padx=5)
        
        tk.Button(actions_frame, text="🔄 Refresh Stats", 
                 command=self.update_stats,
                 bg=self.primary, fg='white', padx=20, pady=5).pack(side=tk.LEFT, padx=5)
        
        tk.Button(actions_frame, text="📋 Copy URL", 
                 command=self.copy_url,
                 bg=self.primary, fg='white', padx=20, pady=5).pack(side=tk.LEFT, padx=5)
        
        # Log
        log_frame = tk.LabelFrame(main_frame, text="Activity Log",
                                   bg=self.bg_color, font=('Arial', 11, 'bold'),
                                   padx=10, pady=10)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, bg='white', height=8)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
    def get_network_info(self):
        """Get network interface information"""
        interfaces = []
        try:
            import netifaces
            for iface in netifaces.interfaces():
                addrs = netifaces.ifaddresses(iface)
                if netifaces.AF_INET in addrs:
                    for addr in addrs[netifaces.AF_INET]:
                        if addr['addr'] != '127.0.0.1':
                            interfaces.append(f"{iface}: {addr['addr']}")
        except:
            pass
            
        if not interfaces:
            interfaces = ["No network interfaces found"]
            
        return " | ".join(interfaces)
    
    def update_stats(self):
        """Update storage statistics"""
        self.stats_text.delete(1.0, tk.END)
        
        files = self.storage.files
        total_size = sum(f['size'] for f in files)
        
        # Count by category
        categories = {}
        for f in files:
            cat = f['category']
            categories[cat] = categories.get(cat, 0) + 1
            
        stats = f"Total Files: {len(files)}\n"
        stats += f"Total Size: {total_size / (1024*1024):.2f} MB\n"
        stats += f"\nBy Category:\n"
        for cat, count in categories.items():
            stats += f"  {cat.capitalize()}: {count}\n"
            
        self.stats_text.insert(1.0, stats)
    
    def log(self, message):
        """Add message to log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
    
    def start_server(self):
        """Start the file hub server"""
        try:
            port = int(self.port.get())
            
            # Create server
            self.server = HTTPServer((self.host.get(), port), FileHubHandler)
            
            # Start in thread
            self.server_thread = threading.Thread(target=self.server.serve_forever)
            self.server_thread.daemon = True
            self.server_thread.start()
            
            self.is_running = True
            
            # Update UI
            self.status_label.config(text="▶️ Server Running", bg=self.success)
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            
            # Get local IPs
            urls = []
            try:
                hostname = socket.gethostname()
                local_ip = socket.gethostbyname(hostname)
                urls.append(f"http://localhost:{port}")
                urls.append(f"http://127.0.0.1:{port}")
                urls.append(f"http://{local_ip}:{port}")
            except:
                urls.append(f"http://localhost:{port}")
            
            self.url_label.config(text="URL:\n" + "\n".join(urls))
            
            self.log(f"Server started on port {port}")
            self.log("Access from:")
            for url in urls:
                self.log(f"  {url}")
                
        except Exception as e:
            self.log(f"Error starting server: {e}")
    
    def stop_server(self):
        """Stop the file hub server"""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
            
        self.is_running = False
        
        # Update UI
        self.status_label.config(text="⏹️ Server Stopped", bg=self.warning)
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.url_label.config(text="URL: Not running")
        
        self.log("Server stopped")
    
    def open_browser(self):
        """Open browser to server URL"""
        import webbrowser
        webbrowser.open(f"http://localhost:{self.port.get()}")
    
    def open_storage(self):
        """Open storage folder in file explorer"""
        import subprocess
        storage_path = Config.STORAGE_DIR
        
        if sys.platform == 'win32':
            os.startfile(storage_path)
        elif sys.platform == 'darwin':
            subprocess.run(['open', storage_path])
        else:
            subprocess.run(['xdg-open', storage_path])
    
    def copy_url(self):
        """Copy server URL to clipboard"""
        self.root.clipboard_clear()
        self.root.clipboard_append(f"http://localhost:{self.port.get()}")
        self.log("URL copied to clipboard")
    
    def run(self):
        """Run the GUI"""
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.mainloop()
    
    def on_closing(self):
        """Handle window closing"""
        if self.is_running:
            self.stop_server()
        self.root.destroy()

# ==================== MAIN ====================

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Hoster - Local file sharing server")
    parser.add_argument("--port", type=int, default=Config.DEFAULT_PORT, help="Port to run on")
    parser.add_argument("--host", default=Config.DEFAULT_HOST, help="Host to bind to")
    parser.add_argument("--nogui", action="store_true", help="Run without GUI (command line only)")
    
    args = parser.parse_args()
    
    if args.nogui:
        # Command line mode
        print(f"Starting Hoster on {args.host}:{args.port}")
        print(f"Storage directory: {Config.STORAGE_DIR}")
        print("\nPress Ctrl+C to stop\n")
        
        server = HTTPServer((args.host, args.port), FileHubHandler)
        
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped")
    else:
        # GUI mode
        app = FileHubGUI()
        app.port.set(str(args.port))
        app.host.set(args.host)
        app.run()

if __name__ == "__main__":
    # Create storage directories
    Config.STORAGE_DIR.mkdir(exist_ok=True)
    Config.UPLOADS_DIR.mkdir(exist_ok=True)
    Config.TEXT_DIR.mkdir(exist_ok=True)
    Config.PHOTOS_DIR.mkdir(exist_ok=True)
    Config.VIDEOS_DIR.mkdir(exist_ok=True)
    Config.ARCHIVE_DIR.mkdir(exist_ok=True)
    
    main()