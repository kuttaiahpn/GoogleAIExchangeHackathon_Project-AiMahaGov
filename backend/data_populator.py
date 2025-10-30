import os
import json
import random
from uuid import uuid4
from google.cloud import firestore
from google.oauth2 import service_account

# --- CONFIGURATION ---
# IMPORTANT: This assumes your 'key.json' is in the 'backend' directory.
# Replace with your actual project ID
PROJECT_ID = "wildcardchallenge-aimahagov"
COLLECTION_NAME = "grievances"
SERVICE_ACCOUNT_FILE = 'key.json'
NUM_RECORDS = 50
# Mock data sources
LOCATIONS = ["Kothrud", "Hadapsar", "Wakad", "Viman Nagar", "Hinjewadi"]
DEPARTMENTS = ["Water Supply", "Roads & Transport", "Waste Management", "Public Health", "Property Tax"]
STATUSES = ["Open", "In-Progress", "Closed"]
GRIEVANCE_TEMPLATES = [
    "The {} in my area ({}) has been broken for 5 days. We need an immediate fix.",
    "I filed a complaint about poor {} services three weeks ago, and no one has responded.",
    "Frequent issues with the local {} near the {} crossing are causing significant disruption.",
    "Can someone from the {} department please inspect the overflowing bins at the corner of {}?",
    "The officials responsible for {} are unresponsive to citizen concerns regarding the damage in {}."
]

def generate_mock_document():
    """Generates a single mock document adhering to the confirmed schema."""
    location = random.choice(LOCATIONS)
    department = random.choice(DEPARTMENTS)
    grievance_text = random.choice(GRIEVANCE_TEMPLATES).format(department.lower(), location)

    return {
        'token_id': f"MH-G-{uuid4().hex[:8].upper()}",
        'timestamp': firestore.SERVER_TIMESTAMP,
        'location_ward': location,
        'department': department,
        'grievance_text': grievance_text,
        'status': random.choice(STATUSES),
        'risk_score': 0,
        'ai_suggested_action': ""
    }

def initialize_firestore_client():
    """Initializes and returns the Firestore client using the Service Account."""
    print(f"Initializing Firestore client for Project: {PROJECT_ID}")
    try:
        # Load credentials from key.json
        credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE)

        # Initialize the client
        db = firestore.Client(project=PROJECT_ID, credentials=credentials, database="grievances-log")
        print("✅ Firestore client initialized...")
        return db
    except Exception as e:
        print(f"Error initializing Firestore client: {e}")
        print("Please ensure your key.json file is correctly placed and configured.")
        return None

def populate_firestore(db):
    """Generates and uploads mock data to the Firestore collection."""
    if db is None:
        print("Cannot populate. Database client is not initialized.")
        return

    collection_ref = db.collection(COLLECTION_NAME)

    # Use a batch write for efficiency
    batch = db.batch()

    print(f"\nGenerating and queuing {NUM_RECORDS} mock documents...")

    for _ in range(NUM_RECORDS):
        data = generate_mock_document()
        # Use a document() call without an argument to auto-generate the Document ID
        doc_ref = collection_ref.document()
        batch.set(doc_ref, data)

    print("Committing batch write...")
    batch.commit()
    print(f"\n✅ Successfully populated {NUM_RECORDS} documents into the '{COLLECTION_NAME}' collection.")
    print("Check your Google Cloud Firestore Console to verify the data.")

if __name__ == '__main__':
    # 1. Check for key file
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        print(f"FATAL ERROR: Missing '{SERVICE_ACCOUNT_FILE}'.")
        print("Ensure 'key.json' is in the same directory as this script.")
    else:
        # 2. Get the Firestore Client
        db_client = initialize_firestore_client()

        # 3. Populate the data
        if db_client:
            populate_firestore(db_client)