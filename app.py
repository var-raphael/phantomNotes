import os
import json
import io
from pathlib import Path
from flask import Flask, request, render_template_string, jsonify, send_file
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
Path("exports").mkdir(exist_ok=True)

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


def extract_text_from_pdf(file_bytes):
    """Extract text from PDF"""
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n\n"
        return text.strip()
    except Exception as e:
        raise Exception(f"Error extracting PDF: {str(e)}")


def extract_text_from_image(file_bytes):
    """Extract text from image using OCR"""
    try:
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

        # Direct API call to Groq
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
            }
        )
        
        response.raise_for_status()
        data = response.json()
        
        summary_text = data["choices"][0]["message"]["content"]
        
        # Parse the response
        parts = summary_text.split("## Overall Summary")
        chapter_summaries = parts[0].replace("## Chapter/Section Summaries", "").strip()
        overall_summary = parts[1].strip() if len(parts) > 1 else "No overall summary available"
        
        return {
            "chapter_summaries": chapter_summaries,
            "overall_summary": overall_summary,
            "full_text": summary_text
        }
    except Exception as e:
        raise Exception(f"Error generating summary: {str(e)}")


def export_to_txt(summary):
    """Export summary to TXT"""
    filepath = "exports/summary.txt"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("PHANTOMNOTES SUMMARY\n")
        f.write("=" * 50 + "\n\n")
        f.write(summary["full_text"])
    return filepath


def export_to_json(summary):
    """Export summary to JSON"""
    filepath = "exports/summary.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    return filepath


def export_to_html(summary):
    """Export summary to HTML"""
    filepath = "exports/summary.html"
    
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
            <h1>📝 PhantomNotes Summary</h1>
            <div class="summary-section">{{ full_text }}</div>
            <div class="footer">Generated by PhantomNotes</div>
        </div>
    </body>
    </html>
    """
    
    html_content = html_template.replace("{{ full_text }}", summary["full_text"])
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
    return filepath


def export_to_pdf(summary):
    """Export summary to PDF"""
    filepath = "exports/summary.pdf"
    
    doc = SimpleDocTemplate(filepath, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor='#2c3e50',
        spaceAfter=30
    )
    story.append(Paragraph("PhantomNotes Summary", title_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Content
    content_style = ParagraphStyle(
        'CustomBody',
        parent=styles['BodyText'],
        fontSize=11,
        leading=16
    )
    
    # Split by lines and add to PDF
    for line in summary["full_text"].split('\n'):
        if line.strip():
            if line.startswith('##'):
                # It's a heading
                story.append(Spacer(1, 0.2*inch))
                story.append(Paragraph(line.replace('##', '').strip(), styles['Heading2']))
            else:
                story.append(Paragraph(line, content_style))
                story.append(Spacer(1, 0.1*inch))
    
    doc.build(story)
    return filepath


def export_to_jpg(summary):
    """Export summary to JPG"""
    filepath = "exports/summary.jpg"
    
    # Create an image with text
    img_width = 1200
    img_height = 1600
    img = Image.new('RGB', (img_width, img_height), color='white')
    draw = ImageDraw.Draw(img)
    
    # Try to use a better font, fall back to default
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
    
    # Draw title
    draw.text((40, 40), "PhantomNotes Summary", fill='black', font=title_font)
    draw.line([(40, 80), (img_width - 40, 80)], fill='#3498db', width=3)
    
    # Draw content
    y_position = 120
    max_width = img_width - 80
    
    for line in summary["full_text"][:3000].split('\n'):
        if y_position > img_height - 100:
            break
        
        if line.strip():
            # Word wrap
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
    
    # Footer
    draw.text((40, img_height - 60), "Generated by PhantomNotes", fill='#7f8c8d', font=body_font)
    
    img.save(filepath, 'JPEG', quality=95)
    return filepath


HOME_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>PhantomNotes</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        h1 {
            color: #2c3e50;
            margin-bottom: 10px;
            font-size: 2.5em;
        }
        .subtitle {
            color: #7f8c8d;
            margin-bottom: 30px;
            font-size: 1.1em;
        }
        .form-group {
            margin-bottom: 25px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            color: #34495e;
            font-weight: 600;
        }
        input[type="file"], select {
            width: 100%;
            padding: 12px;
            border: 2px solid #ddd;
            border-radius: 8px;
            font-size: 16px;
        }
        input[type="file"]:focus, select:focus {
            outline: none;
            border-color: #667eea;
        }
        .btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px 40px;
            border: none;
            border-radius: 8px;
            font-size: 18px;
            cursor: pointer;
            width: 100%;
            font-weight: 600;
            transition: transform 0.2s;
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(102, 126, 234, 0.4);
        }
        .btn:disabled {
            background: #ccc;
            cursor: not-allowed;
            transform: none;
        }
        .loading {
            display: none;
            text-align: center;
            margin-top: 20px;
            color: #667eea;
            font-weight: 600;
        }
        .result {
            margin-top: 40px;
            display: none;
        }
        .summary-box {
            background: #f8f9fa;
            padding: 25px;
            border-radius: 10px;
            margin-bottom: 20px;
            border-left: 4px solid #667eea;
        }
        .summary-box h3 {
            color: #2c3e50;
            margin-bottom: 15px;
        }
        .summary-content {
            white-space: pre-wrap;
            line-height: 1.6;
            color: #34495e;
        }
        .export-buttons {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-top: 20px;
        }
        .export-btn {
            flex: 1;
            min-width: 120px;
            padding: 10px 20px;
            background: white;
            border: 2px solid #667eea;
            color: #667eea;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.2s;
        }
        .export-btn:hover {
            background: #667eea;
            color: white;
        }
        .error {
            background: #fee;
            color: #c33;
            padding: 15px;
            border-radius: 8px;
            margin-top: 20px;
            display: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>👻 PhantomNotes</h1>
        <p class="subtitle">Extract and summarize your documents instantly</p>
        
        <form id="uploadForm" enctype="multipart/form-data">
            <div class="form-group">
                <label for="files">Upload PDF or Images (Max 5)</label>
                <input type="file" id="files" name="files" multiple accept=".pdf,image/*" required>
            </div>
            
            <div class="form-group">
                <label for="userType">I am a...</label>
                <select id="userType" name="user_type" required>
                    <option value="student">Student</option>
                    <option value="novel_reader">Novel Reader</option>
                    <option value="researcher">Researcher</option>
                    <option value="professional">Professional/Business</option>
                    <option value="legal">Legal Document Reader</option>
                    <option value="technical">Technical Documentation Reader</option>
                    <option value="news">News Article Reader</option>
                    <option value="meeting">Meeting Notes</option>
                    <option value="quick">Quick Overview</option>
                    <option value="detailed">Detailed Analysis</option>
                </select>
            </div>
            
            <button type="submit" class="btn" id="submitBtn">Generate Summary</button>
        </form>
        
        <div class="loading" id="loading">
            <p>⚡ Processing your document...</p>
        </div>
        
        <div class="error" id="error"></div>
        
        <div class="result" id="result">
            <div class="summary-box">
                <h3>📋 Chapter/Section Summaries</h3>
                <div class="summary-content" id="chapterSummary"></div>
            </div>
            
            <div class="summary-box">
                <h3>📝 Overall Summary</h3>
                <div class="summary-content" id="overallSummary"></div>
            </div>
            
            <div class="export-buttons">
                <button class="export-btn" onclick="downloadFile('txt')">📄 TXT</button>
                <button class="export-btn" onclick="downloadFile('json')">📊 JSON</button>
                <button class="export-btn" onclick="downloadFile('html')">🌐 HTML</button>
                <button class="export-btn" onclick="downloadFile('pdf')">📕 PDF</button>
                <button class="export-btn" onclick="downloadFile('jpg')">🖼️ JPG</button>
            </div>
        </div>
    </div>
    
    <script>
        let currentSummary = null;
        
        document.getElementById('uploadForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const formData = new FormData();
            const files = document.getElementById('files').files;
            const userType = document.getElementById('userType').value;
            
            if (files.length > 5) {
                showError('Maximum 5 files allowed');
                return;
            }
            
            for (let file of files) {
                formData.append('files', file);
            }
            formData.append('user_type', userType);
            
            document.getElementById('submitBtn').disabled = true;
            document.getElementById('loading').style.display = 'block';
            document.getElementById('result').style.display = 'none';
            document.getElementById('error').style.display = 'none';
            
            try {
                const response = await fetch('/summarize', {
                    method: 'POST',
                    body: formData
                });
                
                const data = await response.json();
                
                if (!response.ok) {
                    throw new Error(data.error || 'Error processing files');
                }
                
                currentSummary = data;
                displaySummary(data);
            } catch (error) {
                showError(error.message);
            } finally {
                document.getElementById('submitBtn').disabled = false;
                document.getElementById('loading').style.display = 'none';
            }
        });
        
        function displaySummary(data) {
            document.getElementById('chapterSummary').textContent = data.chapter_summaries;
            document.getElementById('overallSummary').textContent = data.overall_summary;
            document.getElementById('result').style.display = 'block';
        }
        
        function showError(message) {
            const errorDiv = document.getElementById('error');
            errorDiv.textContent = message;
            errorDiv.style.display = 'block';
        }
        
        async function downloadFile(format) {
            if (!currentSummary) return;
            
            try {
                const response = await fetch('/export/' + format, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(currentSummary)
                });
                
                if (!response.ok) throw new Error('Export failed');
                
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'summary.' + format;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            } catch (error) {
                showError('Error downloading file: ' + error.message);
            }
        }
    </script>
</body>
</html>
"""


@app.route('/')
def home():
    """Serve the main page"""
    return render_template_string(HOME_HTML)


@app.route('/summarize', methods=['POST'])
def summarize():
    """Process uploaded files and generate summary"""
    try:
        files = request.files.getlist('files')
        user_type = request.form.get('user_type')
        
        if len(files) > 5:
            return jsonify({"error": "Maximum 5 files allowed"}), 400
        
        if user_type not in USER_TYPES:
            return jsonify({"error": "Invalid user type"}), 400
        
        # Extract text from all files
        all_text = ""
        
        for file in files:
            if file.filename.endswith('.pdf'):
                content = file.read()
                text = extract_text_from_pdf(content)
                all_text += text + "\n\n"
            elif file.content_type and file.content_type.startswith('image/'):
                content = file.read()
                text = extract_text_from_image(content)
                all_text += text + "\n\n"
            else:
                return jsonify({"error": f"Unsupported file type: {file.filename}"}), 400
        
        if not all_text.strip():
            return jsonify({"error": "No text could be extracted from files"}), 400
        
        # Generate summary
        summary = generate_summary(all_text, user_type)
        
        return jsonify(summary)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/export/<format>', methods=['POST'])
def export_summary(format):
    """Export summary in specified format"""
    try:
        summary = request.get_json()
        
        if format == 'txt':
            filepath = export_to_txt(summary)
        elif format == 'json':
            filepath = export_to_json(summary)
        elif format == 'html':
            filepath = export_to_html(summary)
        elif format == 'pdf':
            filepath = export_to_pdf(summary)
        elif format == 'jpg':
            filepath = export_to_jpg(summary)
        else:
            return jsonify({"error": "Invalid export format"}), 400
        
        return send_file(filepath, as_attachment=True, download_name=f"summary.{format}")
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)