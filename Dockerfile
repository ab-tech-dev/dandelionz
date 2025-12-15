FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files (THIS MUST COME FIRST)
COPY . .

# Collect static files AFTER project exists
RUN python manage.py collectstatic --noinput

# Default command for Django
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
