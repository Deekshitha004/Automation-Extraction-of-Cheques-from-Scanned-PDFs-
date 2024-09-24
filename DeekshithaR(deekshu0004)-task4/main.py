from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
import fitz
import cv2
import openpyxl
import zipfile
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
import numpy as np
import pytesseract
import regex as re
import csv
import pandas as pd
from flask import abort
from flask_migrate import Migrate

app = Flask(__name__)

# Configuration settings
app.config['SECRET_KEY'] = '895a2e4ae2c6e1768b9876d028ddf7c5'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'

# Initialize database
db = SQLAlchemy(app)

# Initialize login manager
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# User model representing users in the database
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    @property
    def password(self):
        raise AttributeError('Password is not a readable attribute')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    user = User.query.get_or_404(int(user_id))
    if user:
        return user
    else:
        abort(404)

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('upload'))
    else:
        return redirect(url_for('register'))
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Check if the username already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose a different username.', 'danger')
            return redirect(url_for('register'))
        
        # If the username does not exist, create a new user
        user = User(username=username)
        user.password = password
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful. Please log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.verify_password(password):
            login_user(user)
            flash('Logged in successfully.', 'success')
            return redirect(url_for('upload'))  # Redirect to upload page after login
        else:
            flash('Login unsuccessful. Please check username and password.', 'danger')
    return render_template('login.html')

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        if 'pdf_file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        
        pdf_file = request.files['pdf_file']
        
        if pdf_file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
        
        if pdf_file and pdf_file.filename.endswith('.pdf'):
            uploads_dir = os.path.join('uploads')
            
            if not os.path.exists(uploads_dir):
                os.makedirs(uploads_dir)

            pdf_path = os.path.join(uploads_dir, pdf_file.filename)
            pdf_file.save(pdf_path)

            # Attempt to extract text from the PDF
            extracted_text = extract_text_from_cheque(pdf_path, 'path_to_tesseract')

            if extracted_text == "":
                flash("There is no cheque.", 'warning')
            elif extracted_text == "The uploaded PDF does not contain any cheque images.":
                flash(extracted_text, 'warning')
            else:
                # Process the extracted text to get the required fields
                cheque_data = process_cheque_text(extracted_text)
                save_cheque_data_to_csv(cheque_data)
                flash("Data saved to cheque_data.csv", 'success')
            
            return redirect(url_for('upload'))
        else:
            flash("Please upload a PDF file.", 'danger')
            return redirect(url_for('upload'))
    
    return render_template('upload.html')

@app.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    if request.method == 'POST':
        logout_user()
        flash('You have been logged out.', 'success')
        return redirect(url_for('login'))
    return render_template('logout.html')


def deskew_image(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    angles = [cv2.minAreaRect(cnt)[-1] for cnt in contours]
    deskewed_image = image.copy()
    for angle in angles:
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        (h, w) = deskewed_image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        deskewed_image = cv2.warpAffine(deskewed_image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return deskewed_image

def extract_text_from_cheque(pdf_path, tesseract_path):
    doc = fitz.open(pdf_path)
    extracted_text = ""

    try:
        from pytesseract import image_to_string
        pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    except ImportError:
        print("Tesseract OCR not found. Please install it.")
        return ""

    # Check if the PDF contains scanned images
    contains_images = False
    for page_index in range(len(doc)):
        page = doc[page_index]
        image_list = page.get_images()
        if image_list:
            contains_images = True
            break

    if not contains_images:
        return "The uploaded PDF does not contain any cheque images."

    found_cheque = False
    for page_index in range(len(doc)):
        page = doc[page_index]
        image_matrix = fitz.Matrix(2, 2)
        page_image = page.get_pixmap(matrix=image_matrix, alpha=False)
        image_bytes = page_image.tobytes()

        image_np = np.frombuffer(image_bytes, dtype=np.uint8)
        image_cv2 = cv2.imdecode(image_np, cv2.IMREAD_COLOR)

        image_cv2 = cv2.resize(image_cv2, None, fx=1.2, fy=1.2, interpolation=cv2.INTER_CUBIC)

        gray = cv2.cvtColor(image_cv2, cv2.COLOR_BGR2GRAY)
        gray = cv2.medianBlur(gray, 3)
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            aspect_ratio = w / h

            if 0.7 < aspect_ratio < 1.5 and w * h > 5000:
                cheque_image = image_cv2[y:y + h, x:x + w]
                deskewed_cheque_image = deskew_image(cheque_image)
                custom_config = r'--oem 3 --psm 6'
                extracted_text = pytesseract.image_to_string(deskewed_cheque_image, lang='eng', config=custom_config)
                found_cheque = True
                break

        if found_cheque:
            print(f"Cheque text found on page {page_index + 1}:")
            break

    if not found_cheque:
        print("No cheque found in the PDF document.")
        return ""

    return extracted_text



def process_cheque_text(extracted_text):
    if extracted_text == "No cheque found in the PDF document.":
        return {}  # Return an empty dictionary

    # Improved regex patterns
    name_regex = r"pay\s+(.*?)\s*(?:OR BEARER|BERRIEN|$)"
    amount_regex = r"(?:f\s*)?rupees\s+(.*?(?:Rupee|Rs).*?Only)"
    date_regex = r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b"

    # Extract name
    name_match = re.search(name_regex, extracted_text, re.IGNORECASE)
    payee_name = name_match.group(1).strip() if name_match else ""

    
    amount_match = re.search(amount_regex, extracted_text, re.IGNORECASE | re.DOTALL)
    amount = amount_match.group(1).strip() if amount_match else ""

    

   
    amount = re.sub(r'\s+', ' ', amount)  
    amount = amount.replace('|', '')  
    amount = amount.replace('_', '')  

    cheque_data = {
        'payee_name': payee_name,
        'amount': amount,
        
    }

    print("Extracted data:", cheque_data)
    print("Full extracted text:", extracted_text)

    return cheque_data

def save_cheque_data_to_csv(cheque_data):
    # Define the CSV file path
    csv_file_path = 'cheque_data.csv'
    
    
    with open(csv_file_path, mode='a', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=['payee_name', 'amount'])
        if file.tell() == 0:  
            writer.writeheader()  
        
       
        writer.writerow(cheque_data)


if __name__ == "__main__":
    app.run(debug=True)