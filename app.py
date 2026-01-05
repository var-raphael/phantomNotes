import os
import json
import io
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from threading import Thread
import time
from flask import Flask, request, render_template, jsonify, send_file
import PyPDF2
from PIL import Image, ImageDraw, ImageFont
import pytesseract
import requests
from dotenv import load_dotenv
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import inch

load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size

# Create temp directory for exports
EXPORT_DIR = Path("exports")
EXPORT_DIR.mkdir(exist_ok=True)

# Get Groq API key
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

USER_TYPES = {
    "student": "You are summarizing for a student. Provide chapter-by-chapter summaries with key definitions, main concepts, and important points for studying.",
    "novel_reader": "You are summarizing for a novel reader. Focus on plot summary, character analysis, themes, and narrative structure.",
    "researcher": "You are summarizing for a researcher. Focus on methodology, findings, key arguments, and research contributions.",
    "professional": "You are summarizing for a business professional. Extract action items, key decisions, strategic takeaways, and business implications.",
    "legal": "You are summarizing a legal document. Focus on key clauses, obligations, rights, terms, and legal implications.",
    "technical": "You are summarizing technical documentation. Focus on architecture, APIs, implementation steps, and technical specifications.",
    "news": "You are summarizing a news article. Use the 5W1H framework: Who, What, When, Where, Why, and How.",
    "meeting": "You are summarizing meeting notes. Extract decisions made, action items, responsibilities, and next steps.",
    "quick": "Provide an ultra-compressed summary with only the most essential bullet points.",
    "detailed": "Provide an in-depth, detailed analysis that preserves nuance and context."
}


def cleanup_old_files():
    """Background task to delete files older than 1 hour"""
    while True:
        try:
            now = datetime.now()
            for file_path in EXPORT_DIR.glob("*"):
                if file_path.is_file():
                    # Get file modification time
                    file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                    # Delete if older than 1 hour
                    if now - file_time > timedelta(hours=1):
                        file_path.unlink()
                        print(f"Cleaned up: {file_path.name}")
        except Exception as e:
            print(f"Cleanup error: {e}")
        
        # Run cleanup every 30 minutes
        time.sleep(1800)


# Start cleanup thread
cleanup_thread = Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()


def extract_text_from_pdf(file_bytes):
    """Extract text from PDF - with OCR fallback for scanned PDFs"""
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        text = ""
        
        # Try normal text extraction first
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n\n"
        
        # If no text found, it might be a scanned PDF - use OCR
        if not text.strip():
            print("PDF appears to be scanned - attempting OCR...")
            try:
                from pdf2image import convert_from_bytes
                
                # Convert PDF pages to images
                images = convert_from_bytes(file_bytes)
                
                print(f"Converting {len(images)} pages with OCR...")
                for i, image in enumerate(images):
                    print(f"OCR on page {i+1}/{len(images)}...")
                    page_text = pytesseract.image_to_string(image)
                    text += page_text + "\n\n"
                    
            except ImportError:
                raise Exception("This PDF contains scanned images. Please install pdf2image: pip install pdf2image")
            except Exception as ocr_error:
                raise Exception(f"PDF is image-based but OCR failed: {str(ocr_error)}")
        
        return text.strip()
    except Exception as e:
        raise Exception(f"Error extracting PDF: {str(e)}")


def extract_text_from_image(file_bytes):
    """Extract text from image using OCR"""
    try:
        # Check if tesseract is available
        try:
            import subprocess
            subprocess.run(['tesseract', '--version'], 
                         stdout=subprocess.DEVNULL, 
                         stderr=subprocess.DEVNULL, 
                         check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise Exception("Tesseract OCR is not installed. Please contact support.")
        
        image = Image.open(io.BytesIO(file_bytes))
        text = pytesseract.image_to_string(image)
        return text.strip()
    except Exception as e:
        raise Exception(f"Error extracting image text: {str(e)}")


def generate_summary(text, user_type):
    """Generate summary using Groq API via requests"""
    try:
        system_prompt = USER_TYPES.get(user_type, USER_TYPES["quick"])
        
        prompt = f"""{system_prompt}

Analyze the following text and provide:
1. Individual chapter/section summaries (if applicable, identify logical sections)
2. An overall compressed summary of the entire content

Format your response as:
## Chapter/Section Summaries
[Provide summaries here]

## Overall Summary
[Provide overall summary here]

Text to summarize:
{text[:15000]}"""

        print("Making request to Groq API...")
        
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": "You are an expert at creating clear, concise summaries."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 4000
            },
            timeout=60  # Add timeout
        )
        
        print(f"Groq API response status: {response.status_code}")
        
        if response.status_code != 200:
            error_msg = f"API returned status {response.status_code}"
            try:
                error_data = response.json()
                error_msg += f": {error_data.get('error', {}).get('message', 'Unknown error')}"
            except:
                error_msg += f": {response.text[:200]}"
            print(f"ERROR: {error_msg}")
            raise Exception(error_msg)
        
        response.raise_for_status()
        data = response.json()
        
        if 'choices' not in data or len(data['choices']) == 0:
            raise Exception("No response from AI model")
        
        summary_text = data["choices"][0]["message"]["content"]
        
        parts = summary_text.split("## Overall Summary")
        chapter_summaries = parts[0].replace("## Chapter/Section Summaries", "").strip()
        overall_summary = parts[1].strip() if len(parts) > 1 else "No overall summary available"
        
        return {
            "chapter_summaries": chapter_summaries,
            "overall_summary": overall_summary,
            "full_text": summary_text
        }
    except requests.exceptions.Timeout:
        raise Exception("API request timed out. Please try again.")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Network error: {str(e)}")
    except Exception as e:
        print(f"ERROR in generate_summary: {str(e)}")
        raise Exception(f"Error generating summary: {str(e)}")


def export_to_txt(summary):
    """Export summary to TXT - In Memory"""
    content = f"PHANTOMNOTES SUMMARY\n{'=' * 50}\n\n{summary['full_text']}"
    
    # Create in-memory file
    buffer = io.BytesIO()
    buffer.write(content.encode('utf-8'))
    buffer.seek(0)
    
    return buffer


def export_to_json(summary):
    """Export summary to JSON - In Memory"""
    content = json.dumps(summary, indent=2, ensure_ascii=False)
    
    # Create in-memory file
    buffer = io.BytesIO()
    buffer.write(content.encode('utf-8'))
    buffer.seek(0)
    
    return buffer


def export_to_html(summary):
    """Export summary to HTML - In Memory"""
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>PhantomNotes Summary</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                max-width: 800px;
                margin: 40px auto;
                padding: 20px;
                background: #f5f5f5;
            }
            .container {
                background: white;
                padding: 40px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1 {
                color: #2c3e50;
                border-bottom: 3px solid #3498db;
                padding-bottom: 10px;
            }
            h2 {
                color: #34495e;
                margin-top: 30px;
            }
            .summary-section {
                margin: 20px 0;
                line-height: 1.6;
                white-space: pre-wrap;
            }
            .footer {
                text-align: center;
                margin-top: 40px;
                color: #7f8c8d;
                font-size: 14px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>PhantomNotes Summary</h1>
            <div class="summary-section">{{ full_text }}</div>
            <div class="footer">Generated by PhantomNotes</div>
        </div>
    </body>
    </html>
    """
    
    html_content = html_template.replace("{{ full_text }}", summary["full_text"])
    
    # Create in-memory file
    buffer = io.BytesIO()
    buffer.write(html_content.encode('utf-8'))
    buffer.seek(0)
    
    return buffer


def export_to_pdf(summary):
    """Export summary to PDF - Unique filename with cleanup"""
    # Generate unique filename
    unique_id = uuid.uuid4().hex[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = EXPORT_DIR / f"summary_{unique_id}_{timestamp}.pdf"
    
    doc = SimpleDocTemplate(str(filepath), pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor='#2c3e50',
        spaceAfter=30
    )
    story.append(Paragraph("PhantomNotes Summary", title_style))
    story.append(Spacer(1, 0.2*inch))
    
    content_style = ParagraphStyle(
        'CustomBody',
        parent=styles['BodyText'],
        fontSize=11,
        leading=16
    )
    
    for line in summary["full_text"].split('\n'):
        if line.strip():
            if line.startswith('##'):
                story.append(Spacer(1, 0.2*inch))
                story.append(Paragraph(line.replace('##', '').strip(), styles['Heading2']))
            else:
                story.append(Paragraph(line, content_style))
                story.append(Spacer(1, 0.1*inch))
    
    doc.build(story)
    return filepath


def export_to_jpg(summary):
    """Export summary to JPG - Unique filename with cleanup"""
    # Generate unique filename
    unique_id = uuid.uuid4().hex[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = EXPORT_DIR / f"summary_{unique_id}_{timestamp}.jpg"
    
    img_width = 1200
    img_height = 1600
    img = Image.new('RGB', (img_width, img_height), color='white')
    draw = ImageDraw.Draw(img)
    
    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        body_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except:
        try:
            title_font = ImageFont.truetype("arial.ttf", 24)
            body_font = ImageFont.truetype("arial.ttf", 14)
        except:
            title_font = ImageFont.load_default()
            body_font = ImageFont.load_default()
    
    draw.text((40, 40), "PhantomNotes Summary", fill='black', font=title_font)
    draw.line([(40, 80), (img_width - 40, 80)], fill='#3498db', width=3)
    
    y_position = 120
    max_width = img_width - 80
    
    for line in summary["full_text"][:3000].split('\n'):
        if y_position > img_height - 100:
            break
        
        if line.strip():
            words = line.split()
            current_line = ""
            
            for word in words:
                test_line = current_line + word + " "
                bbox = draw.textbbox((0, 0), test_line, font=body_font)
                if bbox[2] - bbox[0] <= max_width:
                    current_line = test_line
                else:
                    if current_line:
                        draw.text((40, y_position), current_line.strip(), fill='black', font=body_font)
                        y_position += 25
                    current_line = word + " "
            
            if current_line and y_position < img_height - 100:
                draw.text((40, y_position), current_line.strip(), fill='black', font=body_font)
                y_position += 25
        
        y_position += 10
    
    draw.text((40, img_height - 60), "Generated by PhantomNotes", fill='#7f8c8d', font=body_font)
    
    img.save(str(filepath), 'JPEG', quality=95)
    return filepath


@app.route('/')
def home():
    """Serve the main page"""
    return render_template('index.html')


@app.route('/summarize', methods=['POST'])
def summarize():
    """Process uploaded files and generate summary"""
    try:
        print("=== Summarize Request Started ===")
        
        # Check if GROQ API key is set
        if not GROQ_API_KEY:
            print("ERROR: GROQ_API_KEY not found in environment")
            return jsonify({"error": "API key not configured. Please check .env file"}), 500
        
        files = request.files.getlist('files')
        user_type = request.form.get('user_type')
        
        print(f"Files received: {len(files)}")
        print(f"User type: {user_type}")
        
        if not files or len(files) == 0:
            print("ERROR: No files uploaded")
            return jsonify({"error": "No files uploaded"}), 400
        
        if len(files) > 5:
            print("ERROR: Too many files")
            return jsonify({"error": "Maximum 5 files allowed"}), 400
        
        if user_type not in USER_TYPES:
            print(f"ERROR: Invalid user type: {user_type}")
            return jsonify({"error": "Invalid user type"}), 400
        
        all_text = ""
        
        for file in files:
            print(f"Processing file: {file.filename}")
            
            if not file.filename:
                continue
                
            if file.filename.endswith('.pdf'):
                content = file.read()
                print(f"PDF size: {len(content)} bytes")
                text = extract_text_from_pdf(content)
                all_text += text + "\n\n"
            elif file.content_type and file.content_type.startswith('image/'):
                content = file.read()
                print(f"Image size: {len(content)} bytes")
                text = extract_text_from_image(content)
                all_text += text + "\n\n"
            else:
                print(f"ERROR: Unsupported file type: {file.filename}")
                return jsonify({"error": f"Unsupported file type: {file.filename}"}), 400
        
        print(f"Total text extracted: {len(all_text)} characters")
        
        if not all_text.strip():
            print("ERROR: No text could be extracted")
            return jsonify({"error": "No text could be extracted from files"}), 400
        
        print("Calling Groq API...")
        summary = generate_summary(all_text, user_type)
        
        print("Summary generated successfully")
        return jsonify(summary)
    
    except Exception as e:
        print(f"ERROR in summarize: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Server error: {str(e)}"}), 500


@app.route('/export/<format>', methods=['POST'])
def export_summary(format):
    """Export summary in specified format"""
    try:
        summary = request.get_json()
        
        # Generate timestamp for unique filenames
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if format == 'txt':
            buffer = export_to_txt(summary)
            return send_file(
                buffer,
                mimetype='text/plain',
                as_attachment=True,
                download_name=f'phantomnotes_summary_{timestamp}.txt'
            )
        
        elif format == 'json':
            buffer = export_to_json(summary)
            return send_file(
                buffer,
                mimetype='application/json',
                as_attachment=True,
                download_name=f'phantomnotes_summary_{timestamp}.json'
            )
        
        elif format == 'html':
            buffer = export_to_html(summary)
            return send_file(
                buffer,
                mimetype='text/html',
                as_attachment=True,
                download_name=f'phantomnotes_summary_{timestamp}.html'
            )
        
        elif format == 'pdf':
            filepath = export_to_pdf(summary)
            return send_file(
                filepath,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=f'phantomnotes_summary_{timestamp}.pdf'
            )
        
        elif format == 'jpg':
            filepath = export_to_jpg(summary)
            return send_file(
                filepath,
                mimetype='image/jpeg',
                as_attachment=True,
                download_name=f'phantomnotes_summary_{timestamp}.jpg'
            )
        
        else:
            return jsonify({"error": "Invalid export format"}), 400
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    print("🚀 PhantomNotes is starting...")
    print("📁 Export cleanup: Files older than 1 hour will be auto-deleted")
    app.run(host='0.0.0.0', port=8000, debug=True)