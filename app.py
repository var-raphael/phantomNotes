import os
import io
import json
import uuid
import time
from datetime import datetime, timedelta
from pathlib import Path
from threading import Thread

from flask import Flask, request, render_template, jsonify, make_response
from dotenv import load_dotenv
import requests
import PyPDF2
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import inch

load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

EXPORT_DIR = Path("exports")
EXPORT_DIR.mkdir(exist_ok=True)

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
    while True:
        try:
            cutoff = datetime.now() - timedelta(hours=1)
            for f in EXPORT_DIR.glob("*"):
                if f.is_file() and datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                    f.unlink()
                    print(f"Cleaned up: {f.name}")
        except Exception as e:
            print(f"Cleanup error: {e}")
        time.sleep(1800)


Thread(target=cleanup_old_files, daemon=True).start()


def extract_text_from_pdf(file_bytes):
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n\n"
        
        if not text.strip():
            raise Exception("No text could be extracted from this PDF. It may be scanned or image-based.")
        
        return text.strip()
    except Exception as e:
        raise Exception(f"PDF extraction failed: {str(e)}")


def generate_summary(text, user_type):
    system_instruction = USER_TYPES.get(user_type, USER_TYPES["quick"])
    
    prompt = f"""{system_instruction}

Analyze the following text and provide:
1. Individual chapter/section summaries (identify logical sections if applicable)
2. An overall compressed summary

Format:
## Chapter/Section Summaries
[summaries here]

## Overall Summary
[overall summary here]

Text to summarize:
{text[:15000]}"""

    try:
        print("Calling Groq API...")
        resp = requests.post(
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
            timeout=60
        )
        
        if resp.status_code != 200:
            error_msg = f"API error ({resp.status_code})"
            try:
                error_data = resp.json()
                error_msg += f": {error_data.get('error', {}).get('message', 'Unknown')}"
            except:
                error_msg += f": {resp.text[:200]}"
            raise Exception(error_msg)
        
        data = resp.json()
        if 'choices' not in data or not data['choices']:
            raise Exception("Empty response from AI")
        
        summary_text = data["choices"][0]["message"]["content"]
        parts = summary_text.split("## Overall Summary")
        
        chapter_summaries = parts[0].replace("## Chapter/Section Summaries", "").strip()
        overall_summary = parts[1].strip() if len(parts) > 1 else "No overall summary generated"
        
        return {
            "chapter_summaries": chapter_summaries,
            "overall_summary": overall_summary,
            "full_text": summary_text
        }
    except requests.exceptions.Timeout:
        raise Exception("Request timed out")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Network error: {str(e)}")
    except Exception as e:
        print(f"Summary generation error: {str(e)}")
        raise


def export_to_txt(summary):
    content = f"PHANTOMNOTES SUMMARY\n{'=' * 50}\n\n{summary['full_text']}"
    return content.encode('utf-8')


def export_to_json(summary):
    return json.dumps(summary, indent=2, ensure_ascii=False).encode('utf-8')


def export_to_html(summary):
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>PhantomNotes Summary</title>
    <style>
        body {{
            font-family: 'Segoe UI', sans-serif;
            max-width: 800px;
            margin: 40px auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #667eea;
            padding-bottom: 10px;
        }}
        .content {{
            margin: 20px 0;
            line-height: 1.6;
            white-space: pre-wrap;
        }}
        .footer {{
            text-align: center;
            margin-top: 40px;
            color: #7f8c8d;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>PhantomNotes Summary</h1>
        <div class="content">{summary['full_text']}</div>
        <div class="footer">Generated by PhantomNotes</div>
    </div>
</body>
</html>"""
    return html.encode('utf-8')


def export_to_pdf(summary):
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
    
    with open(filepath, 'rb') as f:
        pdf_data = f.read()
    
    try:
        filepath.unlink()
    except:
        pass
    
    return pdf_data


def export_to_jpg(summary):
    unique_id = uuid.uuid4().hex[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = EXPORT_DIR / f"summary_{unique_id}_{timestamp}.jpg"
    
    img = Image.new('RGB', (1200, 1600), color='white')
    draw = ImageDraw.Draw(img)
    
    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        body_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()
    
    draw.text((40, 40), "PhantomNotes Summary", fill='black', font=title_font)
    draw.line([(40, 80), (1160, 80)], fill='#667eea', width=3)
    
    y = 120
    max_width = 1120
    
    for line in summary["full_text"][:3000].split('\n'):
        if y > 1500:
            break
        
        if line.strip():
            words = line.split()
            current = ""
            
            for word in words:
                test = current + word + " "
                bbox = draw.textbbox((0, 0), test, font=body_font)
                if bbox[2] - bbox[0] <= max_width:
                    current = test
                else:
                    if current:
                        draw.text((40, y), current.strip(), fill='black', font=body_font)
                        y += 25
                    current = word + " "
            
            if current and y < 1500:
                draw.text((40, y), current.strip(), fill='black', font=body_font)
                y += 25
        
        y += 10
    
    draw.text((40, 1540), "Generated by PhantomNotes", fill='#7f8c8d', font=body_font)
    img.save(str(filepath), 'JPEG', quality=95)
    
    with open(filepath, 'rb') as f:
        jpg_data = f.read()
    
    try:
        filepath.unlink()
    except:
        pass
    
    return jpg_data


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/summarize', methods=['POST'])
def summarize():
    try:
        print("=== Summarize Request ===")
        
        if not GROQ_API_KEY:
            print("ERROR: Missing API key")
            return jsonify({"error": "API key not configured"}), 500
        
        user_type = request.form.get('user_type')
        text_input = request.form.get('text_input', '').strip()
        file = request.files.get('file')
        
        print(f"User type: {user_type}")
        print(f"Text input: {len(text_input)} chars" if text_input else "No text input")
        print(f"File: {file.filename if file else 'None'}")
        
        if user_type not in USER_TYPES:
            return jsonify({"error": "Invalid user type"}), 400
        
        text = ""
        
        # Handle text input
        if text_input:
            text = text_input
            print(f"Using text input: {len(text)} characters")
        
        # Handle PDF upload
        elif file and file.filename:
            if not file.filename.lower().endswith('.pdf'):
                return jsonify({"error": "Only PDF files are supported"}), 400
            
            content = file.read()
            print(f"PDF size: {len(content)} bytes")
            text = extract_text_from_pdf(content)
            print(f"Extracted {len(text)} characters from PDF")
        
        else:
            return jsonify({"error": "Please provide either text or a PDF file"}), 400
        
        if not text.strip():
            return jsonify({"error": "No text found to summarize"}), 400
        
        print("Generating summary...")
        summary = generate_summary(text, user_type)
        
        print("Summary complete")
        return jsonify(summary)
    
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/export/<format>', methods=['POST'])
def export_summary(format):
    try:
        summary = request.get_json()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        exporters = {
            'txt': (export_to_txt, 'text/plain', 'txt'),
            'json': (export_to_json, 'application/json', 'json'),
            'html': (export_to_html, 'text/html', 'html'),
            'pdf': (export_to_pdf, 'application/pdf', 'pdf'),
            'jpg': (export_to_jpg, 'image/jpeg', 'jpg')
        }
        
        if format not in exporters:
            return jsonify({"error": "Invalid format"}), 400
        
        exporter, mimetype, ext = exporters[format]
        data = exporter(summary)
        filename = f'phantomnotes_{timestamp}.{ext}'
        
        resp = make_response(data)
        resp.headers['Content-Type'] = mimetype
        resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        resp.headers['Cache-Control'] = 'no-cache'
        
        print(f"Exported as {filename}")
        return resp
    
    except Exception as e:
        print(f"Export error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "service": "PhantomNotes"
    })


if __name__ == '__main__':
    print("PhantomNotes starting...")
    print("Cleanup: Files older than 1 hour auto-deleted")
    app.run(host='0.0.0.0', port=8000, debug=True)