from flask import Flask, request, send_file, jsonify, render_template
from pdf2image import convert_from_path
import pytesseract
import google.generativeai as genai
import os
import re
import pandas as pd

app = Flask(__name__, template_folder='templates')
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Configure Gemini AI
genai.configure(api_key="AIzaSyA686Ls27VmlfmNqYl80U5f9F9GJiMrSLI")
model = genai.GenerativeModel("gemini-1.5-pro-latest")

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    contract_name = os.path.splitext(file.filename)[0]
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    try:
        # Convert PDF to images
        images = convert_from_path(filepath)
        image_paths = []
        for i, img in enumerate(images):
            image_path = os.path.join(UPLOAD_FOLDER, f'page_{i+1}.png')
            img.save(image_path, 'PNG')
            image_paths.append(image_path)

        # Extract text from images
        full_text = ""
        for path in image_paths:
            text = pytesseract.image_to_string(path)
            full_text += text + "\n"

        text_path = os.path.join(UPLOAD_FOLDER, "extracted_text.txt")
        with open(text_path, "w") as f:
            f.write(full_text)

        # Segment into clauses using numbered headings
        clauses = re.split(r'\n\s*(\d+\.\s.*?)\s*\n', full_text)
        data = []

        if len(clauses) > 1:
            for i in range(1, len(clauses), 2):
                heading = clauses[i].strip()
                content = clauses[i+1].strip() if i+1 < len(clauses) else ""
                data.append({
                    'contract_name': contract_name,
                    'clause': heading,
                    'text': content
                })

        # Save to CSV
        df = pd.DataFrame(data)
        csv_path = os.path.join(UPLOAD_FOLDER, 'contract_clauses.csv')
        df.to_csv(csv_path, index=False)

        return jsonify({
            'message': 'File processed successfully', 
            'csv_path': csv_path,
            'contract_name': contract_name
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/analyze', methods=['GET'])
def analyze_contract():
    csv_path = os.path.join(UPLOAD_FOLDER, 'contract_clauses.csv')
    if not os.path.exists(csv_path):
        return jsonify({"error": "CSV not found. Upload contract first."}), 400

    try:
        df = pd.read_csv(csv_path)
        contract_data = df.to_string(index=False)

        prompt = f"""
        Analyze the following contract terms:

        {contract_data}

        For each clause, provide:
        1. Risky Clauses
        2. Overall Recommendations 

        Format your response with clear headings for each section.
        Include markdown formatting for better readability.
        """

        response = model.generate_content(prompt)
        result_text = response.text

        response_path = os.path.join(UPLOAD_FOLDER, 'gemini_response.txt')
        with open(response_path, 'w') as f:
            f.write(result_text)

        return jsonify({
            'message': 'Analysis complete', 
            'response': result_text,
            'contract_name': df.iloc[0]['contract_name']
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download_report', methods=['GET'])
def download_report():
    response_path = os.path.join(UPLOAD_FOLDER, 'gemini_response.txt')
    if os.path.exists(response_path):
        return send_file(
            response_path,
            as_attachment=True,
            mimetype='text/plain',
            download_name='contract_analysis_report.txt'
        )
    return jsonify({"error": "No report found. Analyze first."}), 404

if __name__ == '__main__':
    app.run(debug=True)