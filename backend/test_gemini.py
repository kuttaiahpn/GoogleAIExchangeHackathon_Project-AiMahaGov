import vertexai
from vertexai.generative_models import GenerativeModel

PROJECT_ID = "wildcardchallenge-aimahagov"
LOCATION = "us-central1"

print(f"Testing Vertex AI Generative AI access...")
print(f"Project: {PROJECT_ID}")
print(f"Location: {LOCATION}")

try:
    # Initialize
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    print("✅ Vertex AI initialized")
    
    # Try different model names
    models_to_test = [
        "gemini-1.0-pro-002",
        "gemini-1.0-pro",
        "gemini-pro",
        "gemini-1.5-flash-001",
    ]
    
    for model_name in models_to_test:
        try:
            print(f"Testing model: {model_name}...")
            model = GenerativeModel(model_name)
            
            response = model.generate_content("Say 'Hello' if you can read this")
            print(f"✅ SUCCESS with {model_name}")
            print(f"Response: {response.text}")
            print(f"🎉 USE THIS MODEL: {model_name}")
            break
            
        except Exception as e:
            print(f"❌ Failed with {model_name}: {str(e)[:100]}")
            continue
    
except Exception as e:
    print(f"❌ CRITICAL ERROR: {e}")
    import traceback
    traceback.print_exc()