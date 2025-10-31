import os
import json
import uuid
from datetime import datetime
from flask import Flask, jsonify, request
# 1. Google Cloud Imports
from google.cloud import firestore
from vertexai.preview.generative_models import GenerativeModel, Part, Content

# --- CONSTANTS and INITIALIZATION ---

# CONSOLIDATED SYSTEM INSTRUCTION FOR STRUCTURED JSON OUTPUT
SYSTEM_INSTRUCTION_TEXT = """
You are an expert government grievance processor and classifier. 
Analyze the following grievance and return a valid JSON object ONLY. 
Your response must strictly contain these three keys: 
'department' (string, category name, e.g., 'Health', 'Infrastructure', 'Finance'), 
'risk_score' (integer from 1 to 5, where 5 is the highest risk and requires immediate attention), 
and 'ai_suggested_action' (a brief, specific next step to resolve the issue).
"""

# CRITICAL: AUTHENTICATION SETUP
# This tells the script where to find your service account key.
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'key.json'

# Define the Google Cloud Project ID (UPDATE IF NEEDED)
PROJECT_ID = "wildcardchallenge-aimahagov" 

# Initialize App and Clients
app = Flask(__name__)
# Note: Using the project ID and database name as specified by the user
db = firestore.Client(project=PROJECT_ID, database="grievances-log")
ai_model = GenerativeModel("gemini-2.5-pro")


# --- HELPER FUNCTION ---
def generate_token_id():
    """Generates a unique token ID for the grievance."""
    unique_part = uuid.uuid4().hex[:8].upper()
    return f"MHG-{unique_part}"


# --- Task 1, Step 2: Health Check Route ---
@app.route('/health', methods=['GET'])
def health_check():
    """Confirms the Flask server is running and provides service status."""
    return jsonify({"status": "healthy", "service": "Grievance AI Hub API"}), 200


# --- Task 2: Core AI Classification and Processing Endpoint ---
@app.route('/classify', methods=['POST'])
def classify_grievance():
    """Receives a grievance, classifies/enriches it using Vertex AI, and saves it to Firestore."""

    # 1. Input Validation
    data = request.get_json()
    grievance_text = data.get('text', '')

    if not grievance_text:
        return jsonify({"error": "Missing 'text' field with grievance content in the request body."}), 400

    # 2. AI Logic: Generate Structured Content
    # Initialize response to None to avoid the Pylance 'possibly unbound' warning.
    response = None 
    try:
        # Combine System Instruction with grievance text into one prompt.
        # We rely on the strong instruction to force JSON, bypassing problematic 'config' or 'system_instruction' keywords.
        full_prompt = f"{SYSTEM_INSTRUCTION_TEXT}\n\nGrievance: {grievance_text}"

        response = ai_model.generate_content(
            contents=[full_prompt]
            # No 'config' or 'response_mime_type' to avoid SDK version errors.
        )

       # 1. Clean the response text: Remove Markdown code block wrappers
        raw_text = response.text.strip()
        
        # Check for and remove the JSON Markdown wrapper
        if raw_text.startswith("```json"):
            raw_text = raw_text[len("```json"):].strip()
        if raw_text.endswith("```"):
            raw_text = raw_text[:-len("```")].strip()
            
        # 2. Parse the cleaned JSON output
        ai_result = json.loads(raw_text)

    except json.JSONDecodeError as e:
        print(f"AI Response Parsing Error: {e}")
        # Check if response is defined before trying to access its text property
        if response and hasattr(response, 'text'):
            print(f"Raw AI Response Text: {response.text}") 
        else:
             print(f"Raw AI Response Text: N/A - AI model call failed before response assignment.") 
        return jsonify({"error": "AI service returned invalid JSON and failed to parse."}), 500

    except Exception as e:
        print(f"Vertex AI Error: {e}")
        return jsonify({"error": "AI service failed to classify grievance."}), 500

    # 3. Firestore Save & Schema Mapping (Day 2 Final Schema)
    new_token_id = generate_token_id()

    document = {
        # Core Fields
        "grievance_text": grievance_text,
        "timestamp": datetime.now(),
        "status": "Pending Review",
        "token_id": new_token_id,

        # AI-Generated Fields (Mapped from parsed JSON)
        # Using .get() for safety in case the model misses a key
        "department": ai_result.get('department', 'Other'),
        "risk_score": ai_result.get('risk_score', 1),
        "ai_suggested_action": ai_result.get('ai_suggested_action', 'No action suggested.'),

        # Placeholder/Metric Fields (for schema alignment)
        "location_ward": "Unspecified",
    }

    # 4. Implement Final Save
    try:
        # Use .set() with the generated token ID as the document ID for easy lookup
        db.collection('grievances').document(new_token_id).set(document)
    except Exception as e:
        print(f"Firestore Save Error: {e}")
        return jsonify({"error": "Failed to save data to Firestore."}), 500

    # 5. Success Response
    return jsonify({
        "message": "Grievance fully processed and saved.",
        "token_id": new_token_id,
        "department": document['department'],
        "risk_score": document['risk_score']
    }), 201


# --- Run Block ---
if __name__ == '__main__':
    # Use environment PORT if available, otherwise 8080 (standard for local dev)
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
