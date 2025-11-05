# Use the official Python image as a base
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the dependency file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Set the environment variable for the port (required by Cloud Run)
ENV PORT 8080

# Run the web service using Gunicorn
# 'app' is the Python file (app.py), and 'app' is the Flask application instance (app = Flask(__name__))
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 app:app