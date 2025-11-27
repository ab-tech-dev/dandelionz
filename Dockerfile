
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache -r requirements.txt



# Copy project files
COPY . .

# Default command for Django
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
