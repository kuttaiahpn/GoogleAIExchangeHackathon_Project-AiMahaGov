import os
import json
import re
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, request, jsonify
from flask_cors import CORS
from google.cloud import firestore
import traceback

# ==================== INITIALIZATION ====================

app = Flask(__name__)
CORS(app)

# Configuration
PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "wildcardchallenge-aimahagov")
CLOUD_RUN_REGION = os.environ.get("REGION", "asia-south1")
VERTEX_AI_REGION = "us-central1"
GRIEVANCE_COLLECTION = 'grievances'

print(f"🚀 Initializing AiMahaGov API")
print(f"📍 Project: {PROJECT_ID}")
print(f"🌍 Region: {CLOUD_RUN_REGION}")

# Initialize Firestore
db = None
try:
    db = firestore.Client(project=PROJECT_ID, database='(default)')
    test_collection = db.collection('_health_check')
    test_doc = test_collection.document('init_test')
    test_doc.set({'initialized_at': datetime.now(timezone.utc)}, merge=True)
    print(f"✅ Firestore connected successfully")
except Exception as e:
    print(f"❌ CRITICAL: Firestore initialization failed: {e}")
    traceback.print_exc()
    db = None

# Initialize Vertex AI with Text-Bison (PaLM 2)
ai_model = None
try:
    import vertexai
    from vertexai.language_models import TextGenerationModel
    
    vertexai.init(project=PROJECT_ID, location=VERTEX_AI_REGION)
    ai_model = TextGenerationModel.from_pretrained("text-bison@002")
    
    print(f"✅ Vertex AI initialized successfully")
    print(f"✅ Model: text-bison@002 (PaLM 2) loaded")
    
except Exception as e:
    print(f"❌ CRITICAL: Vertex AI initialization failed: {e}")
    traceback.print_exc()
    ai_model = None

# ==================== AUTHENTICATION ====================

def auth_required(f):
    """Decorator to enforce authentication via Google Identity Token"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        
        if not auth_header or 'Bearer' not in auth_header:
            return jsonify({"error": "Missing or invalid Authorization header"}), 401
        
        try:
            token = auth_header.split(' ')[1]
            
            if len(token) < 50:
                raise ValueError("Token too short - invalid format")
            
            print(f"✅ Authentication successful")
            return f(*args, **kwargs)
            
        except ValueError as e:
            print(f"❌ Authentication failed: {e}")
            return jsonify({"error": "Authentication failed. Invalid token."}), 403
        except Exception as e:
            print(f"❌ Authentication check error: {e}")
            return jsonify({"error": "Internal error during authentication check."}), 500

    return decorated_function

# ==================== HEALTH CHECK ====================

@app.route('/', methods=['GET'])
@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    status = {
        "status": "ok" if (db is not None and ai_model is not None) else "degraded",
        "service": "AiMahaGov Grievance API",
        "project_id": PROJECT_ID,
        "region": CLOUD_RUN_REGION,
        "vertex_ai_region": VERTEX_AI_REGION,
        "firestore": "connected" if db is not None else "disconnected",
        "vertex_ai": "connected" if ai_model is not None else "disconnected",
        "ai_model": "text-bison@002 (PaLM 2)",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "5.1.0-final"
    }
    
    http_code = 200 if (db is not None and ai_model is not None) else 503
    return jsonify(status), http_code

# ==================== CLASSIFY & SUBMIT GRIEVANCE ====================

@app.route('/classify', methods=['POST'])
@auth_required
def classify_and_submit_grievance():
    """
    Main endpoint: Accept grievance, classify with Google AI, store in Firestore
    """
    
    if db is None:
        return jsonify({
            "error": "Database unavailable. Please contact administrator.",
            "hint": "Firestore connection failed"
        }), 503
    
    if ai_model is None:
        return jsonify({
            "error": "AI service unavailable. Please contact administrator.",
            "hint": "Vertex AI initialization failed"
        }), 503

    # Parse request
    try:
        data = request.get_json()
        grievance_text = data.get('text', '').strip()
        
        if not grievance_text:
            return jsonify({"error": "Missing 'text' field in request body"}), 400
            
        if len(grievance_text) < 10:
            return jsonify({"error": "Grievance text must be at least 10 characters long"}), 400
            
        print(f"📝 Processing grievance: {grievance_text[:100]}...")
        
    except Exception as e:
        print(f"❌ Request parsing error: {e}")
        return jsonify({"error": "Invalid JSON request format"}), 400

    # ==================== AI CLASSIFICATION (IMPROVED) ====================
    
    # Simplified, more reliable prompt
    prompt = f"""Classify this Maharashtra government grievance.

Grievance: {grievance_text}

Respond with ONLY this exact JSON format (no other text):
{{"department": "Water Resources", "risk_score": 5, "ai_suggested_action": "Send emergency team to restore water supply immediately"}}

Choose department from: Public Works Department (PWD), Water Resources, Energy, Health & Family Welfare, Education, Transport, Agriculture, Rural Development, Urban Development, Home Department, Revenue & Land Records, Environment, Social Justice, Other

Risk score: 1=low, 2-3=medium, 4-5=critical emergency

JSON:"""

    ai_result = None
    ai_classification_worked = False
    
    try:
        print(f"🤖 Calling text-bison@002...")
        
        # Call AI with more conservative settings
        response = ai_model.predict(
            prompt,
            temperature=0.1,
            max_output_tokens=256,
            top_k=20,
            top_p=0.8
        )
        
        raw_text = response.text.strip()
        print(f"🤖 Raw AI Response: {raw_text}")
        
        # Try to extract JSON more aggressively
        json_match = re.search(r'\{[^{}]*"department"[^{}]*"risk_score"[^{}]*"ai_suggested_action"[^{}]*\}', raw_text, re.DOTALL)
        
        if not json_match:
            json_match = re.search(r'\{.*?\}', raw_text, re.DOTALL)
        
        if not json_match:
            if '{' in raw_text and '}' in raw_text:
                start = raw_text.index('{')
                end = raw_text.rindex('}') + 1
                json_str = raw_text[start:end]
                ai_result = json.loads(json_str)
            else:
                raise ValueError("No JSON structure found in response")
        else:
            ai_result = json.loads(json_match.group(0))
        
        # Validate required fields
        if 'department' not in ai_result or 'risk_score' not in ai_result or 'ai_suggested_action' not in ai_result:
            raise ValueError(f"Missing required fields. Got: {list(ai_result.keys())}")
        
        # Ensure risk_score is valid integer 1-5
        ai_result['risk_score'] = max(1, min(5, int(float(ai_result['risk_score']))))
        
        # Clean up strings
        ai_result['department'] = str(ai_result['department']).strip()
        ai_result['ai_suggested_action'] = str(ai_result['ai_suggested_action']).strip()
        
        ai_classification_worked = True
        print(f"✅ AI Classification SUCCESS: {ai_result['department']} | Risk: {ai_result['risk_score']}")
        
    except json.JSONDecodeError as e:
        print(f"⚠️ AI returned invalid JSON: {e}")
        print(f"⚠️ Raw response was: {raw_text[:500] if 'raw_text' in locals() else 'N/A'}")
    except Exception as e:
        print(f"⚠️ AI classification failed: {type(e).__name__}: {e}")
        traceback.print_exc()
    
    # Fallback classification if AI failed
    if not ai_classification_worked or ai_result is None:
        print(f"⚠️ Using rule-based fallback classification")
        
        text_lower = grievance_text.lower()
        
        # Check ELECTRICITY first (before water to avoid "supply" confusion)
        if any(word in text_lower for word in ['electricity', 'power', 'electric', 'outage', 'transformer', 'voltage', 'msedcl', 'current', 'blackout']):
            dept = "Energy"
            action = "Contact MSEDCL for emergency power restoration and grid inspection"
            risk = 5 if any(word in text_lower for word in ['week', 'day', 'no power']) else 4
            
        elif any(word in text_lower for word in ['road', 'pothole', 'highway', 'bridge', 'pavement', 'street']):
            dept = "Public Works Department (PWD)"
            action = "Dispatch road repair crew to inspect and fix infrastructure damage"
            risk = 4
            
        elif any(word in text_lower for word in ['water', 'tap', 'drinking', 'pipeline', 'tanker', 'well']):
            dept = "Water Resources"
            action = "Dispatch water department team to investigate supply disruption and restore service"
            risk = 5 if any(word in text_lower for word in ['week', 'day']) else 4
            
        elif any(word in text_lower for word in ['hospital', 'doctor', 'medicine', 'health', 'clinic', 'ambulance']):
            dept = "Health & Family Welfare"
            action = "Forward to district health officer for immediate medical review"
            risk = 5 if 'emergency' in text_lower else 4
            
        elif any(word in text_lower for word in ['school', 'teacher', 'student', 'education', 'college']):
            dept = "Education"
            action = "Forward to district education officer for facility review"
            risk = 3
            
        elif any(word in text_lower for word in ['garbage', 'waste', 'sewage', 'drain', 'sanitation']):
            dept = "Urban Development"
            action = "Forward to municipal corporation for sanitation action"
            risk = 4
            
        elif any(word in text_lower for word in ['police', 'crime', 'theft', 'safety']):
            dept = "Home Department"
            action = "Forward to local police station for investigation"
            risk = 5
            
        else:
            dept = "Other"
            action = "Requires manual review by admin to assign appropriate department"
            risk = 3
        
        ai_result = {
            "department": dept,
            "risk_score": risk,
            "ai_suggested_action": action
        }
        print(f"✅ Fallback Classification: {dept} | Risk: {risk}")

    # ==================== STORE IN FIRESTORE ====================
    
    try:
        grievance_data = {
            'grievance_text': grievance_text,
            'submitted_by_email': 'citizen@demo.com',
            'status': 'Pending Review',
            'timestamp': firestore.SERVER_TIMESTAMP,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'department': ai_result['department'],
            'risk_score': ai_result['risk_score'],
            'ai_suggested_action': ai_result['ai_suggested_action'],
            'ai_classification_used': ai_classification_worked
        }
        
        update_time, doc_ref = db.collection(GRIEVANCE_COLLECTION).add(grievance_data)
        token_id = doc_ref.id
        
        print(f"✅ Grievance saved to Firestore: {token_id}")
        
        return jsonify({
            "message": "Grievance classified and submitted successfully.",
            "token_id": token_id,
            "department": ai_result['department'],
            "risk_score": ai_result['risk_score'],
            "ai_suggested_action": ai_result['ai_suggested_action']
        }), 201
        
    except Exception as e:
        print(f"❌ Firestore save failed: {e}")
        traceback.print_exc()
        return jsonify({
            "error": "Failed to save grievance to database",
            "details": str(e)
        }), 500

# ==================== GET ALL GRIEVANCES ====================

@app.route('/grievances', methods=['GET'])
@auth_required
def get_all_grievances():
    """Fetch all grievances for admin dashboard"""
    
    if db is None:
        return jsonify({"error": "Database connection unavailable"}), 503

    try:
        docs = db.collection(GRIEVANCE_COLLECTION).order_by(
            'timestamp', direction=firestore.Query.DESCENDING
        ).limit(100).stream()

        grievance_list = []
        for doc in docs:
            data = doc.to_dict()
            data['token_id'] = doc.id
            
            # Convert timestamp
            if 'timestamp' in data and data['timestamp']:
                try:
                    if hasattr(data['timestamp'], 'isoformat'):
                        data['timestamp'] = data['timestamp'].isoformat()
                    else:
                        data['timestamp'] = str(data['timestamp'])
                except:
                    pass
            
            grievance_list.append(data)

        print(f"📊 Fetched {len(grievance_list)} grievances")
        return jsonify(grievance_list), 200

    except Exception as e:
        print(f"❌ Fetch grievances failed: {e}")
        traceback.print_exc()
        return jsonify({
            "error": "Failed to fetch grievances",
            "details": str(e)
        }), 500

# ==================== UPDATE GRIEVANCE STATUS ====================

@app.route('/grievances/<token_id>/status', methods=['PATCH'])
@auth_required
def update_grievance_status(token_id):
    """Update the status of a specific grievance"""
    
    if db is None:
        return jsonify({"error": "Database unavailable"}), 503
    
    try:
        data = request.get_json()
        new_status = data.get('status', '').strip()
        admin_notes = data.get('admin_notes', '').strip()
        
        valid_statuses = ['Pending Review', 'In Progress', 'Resolved', 'Rejected']
        if not new_status or new_status not in valid_statuses:
            return jsonify({"error": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"}), 400
        
        doc_ref = db.collection(GRIEVANCE_COLLECTION).document(token_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return jsonify({"error": f"Grievance with token_id '{token_id}' not found"}), 404
        
        update_data = {
            'status': new_status,
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'last_updated_by': 'admin@demo.com'
        }
        
        if admin_notes:
            update_data['admin_notes'] = admin_notes
        
        doc_ref.update(update_data)
        
        print(f"✅ Updated grievance {token_id}: {new_status}")
        
        return jsonify({
            "message": "Status updated successfully",
            "token_id": token_id,
            "new_status": new_status
        }), 200
        
    except Exception as e:
        print(f"❌ Status update failed: {e}")
        traceback.print_exc()
        return jsonify({"error": "Failed to update status", "details": str(e)}), 500

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({"error": "Method not allowed"}), 405

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

# ==================== MAIN ====================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f"{'='*60}")
    print(f"🚀 AiMahaGov Grievance API Ready")
    print(f"🤖 AI Model: Google PaLM 2 (text-bison@002)")
    print(f"{'='*60}")
    app.run(host='0.0.0.0', port=port, debug=False);