# Start with an official Python base image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies required by Playwright's browsers
RUN apt-get update && apt-get install -y \
    libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the image
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers and their OS dependencies
RUN playwright install --with-deps chromium

# Copy the entire application context into the image
# The .dockerignore file will exclude unnecessary files
COPY . .
# The frontend static files need to be accessible from a known path.
# We will rename the 'frontend' directory to 'static_frontend' to match the original setup.
RUN if [ -d frontend ]; then mv frontend static_frontend; fi

# Expose the port your API will run on
EXPOSE 8000

# Command to run your application when the container starts
# For FastAPI with Uvicorn:
CMD ["uvicorn", "app.main_api:app", "--host", "0.0.0.0", "--port", "8000"]
