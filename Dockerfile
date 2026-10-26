FROM python:3.10-bookworm

WORKDIR /infact

# Install requirements
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN python -c "import nltk; nltk.download('wordnet')"

# Copy project code
COPY . .

# Prevent Python from writing pyc files
ENV PYTHONDONTWRITEBYTECODE=1
# Unbuffered logs
ENV PYTHONUNBUFFERED=1

# Expose FastAPI port
EXPOSE 8000

# Start the API (adjust module path if needed)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
