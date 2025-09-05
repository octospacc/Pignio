# Use the official Python image as the base image
FROM python:3.11-slim

# Install necessary system dependencies and Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    bash \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*


# Install Tesseract dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir pytesseract pillow

# TODO: Install additional Tesseract language packs (Italian)
# RUN apt-get install -y tesseract-ocr-ita

# Copy the rest of the application code into the container
COPY . /app

# Set the working directory in the container
WORKDIR /app

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt
# Install Node.js dependencies
RUN npm install

# Expose the port the app runs on
EXPOSE 5000

ENTRYPOINT ["python", "app.py"]