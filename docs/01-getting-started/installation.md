# Installation Guide

This guide walks you through setting up TravelAI on your local machine.

---

## Prerequisites

### System Requirements

- **Python**: 3.11 or higher
- **Operating System**: macOS, Linux, or Windows (WSL recommended)
- **RAM**: Minimum 8GB (16GB recommended for Whisper transcription)
- **Storage**: 5GB free space for dependencies and local cache

### Required Accounts & API Keys

1. **AWS Account** with S3 access
2. **YouTube Data API key** (Google Cloud)
3. **LLM API key** - Choose at least one:
   - **Gemini** (recommended - cheapest, good quality)
   - **DeepSeek** (good balance)
   - **OpenAI** (higher cost, good quality)
4. **Optional**: Google Maps Geocoding API (for Stage 3 geocoding fallback)

---

## Step 1: Clone Repository

```bash
git clone <your-repo-url>
cd TravelAI
```

---

## Step 2: Automated Setup (Recommended)

Run the automated setup script:

```bash
./setup.sh
```

**The script will:**
- Verify Python 3.11+ installation
- Create virtual environment
- Install all dependencies
- Create necessary directories
- Set up `.env` file from template
- Verify AWS credentials

---

## Step 3: Manual Setup (Alternative)

If you prefer manual setup or automated script fails:

### 3.1 Create Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

### 3.2 Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**Key dependencies:**
- `boto3` - AWS S3 integration
- `google-api-python-client` - YouTube Data API
- `yt-dlp` - YouTube audio download
- `openai-whisper` - Speech-to-text transcription
- `openai` - OpenAI API (also used by DeepSeek)
- `google-genai` - Gemini API
- `pydantic` - Data validation
- `chromadb` - Vector database
- `sentence-transformers` - Local embeddings
- `streamlit` - Dashboard UI

### 3.3 Install Whisper Models

Whisper models are downloaded automatically on first use. To pre-download:

```bash
python -c "import whisper; whisper.load_model('small')"
```

**Available models:**
- `tiny` - Fastest, lowest quality (39M params)
- `base` - Fast, decent quality (74M params)
- `small` - Balanced (244M params) - **Default**
- `medium` - Slower, better quality (769M params)
- `large` - Slowest, best quality (1.5B params)

---

## Step 4: Configure Environment Variables

### 4.1 Copy Template

```bash
cp .env.example .env
```

### 4.2 Edit .env File

Open `.env` in your text editor and fill in the required values:

```bash
# ==================================================
# AWS Configuration (REQUIRED)
# ==================================================
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_key_here
AWS_REGION=us-east-1
S3_BUCKET_NAME=your-travel-ai-data

# ==================================================
# YouTube API (REQUIRED for Stage 1)
# ==================================================
YOUTUBE_API_KEY=your_youtube_api_key_here

# ==================================================
# LLM Provider (REQUIRED for Stage 2, 3, 5)
# ==================================================
LLM_PROVIDER=gemini  # Options: gemini, openai, deepseek

# Gemini API (Recommended - cheapest)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash-lite

# OpenAI API (Optional - for fallback)
OPENAI_API_KEY=your_openai_api_key_here

# DeepSeek API (Optional - for fallback)
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_MODEL=deepseek-chat

# ==================================================
# ChromaDB (REQUIRED for Stage 4)
# ==================================================
CHROMADB_MODE=local  # Options: local, cloud
# For cloud mode, see chromadb.md for Chroma Cloud setup

# ==================================================
# Optional Configuration
# ==================================================
# Google Maps Geocoding (fallback for Stage 3)
GOOGLE_MAPS_API_KEY=your_google_maps_api_key_here

# Logging
LOG_LEVEL=INFO  # Options: DEBUG, INFO, WARNING, ERROR
```

---

## Step 5: Obtain API Keys

### AWS Credentials

1. Log in to [AWS Console](https://console.aws.amazon.com/)
2. Navigate to **IAM** → **Users** → **Your User** → **Security Credentials**
3. Click **Create Access Key**
4. Save `Access Key ID` and `Secret Access Key`
5. Create S3 bucket:
   ```bash
   aws s3 mb s3://your-travel-ai-data
   ```

**Required IAM Permissions:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::your-travel-ai-data",
        "arn:aws:s3:::your-travel-ai-data/*"
      ]
    }
  ]
}
```

### YouTube Data API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable **YouTube Data API v3**:
   - Navigate to **APIs & Services** → **Library**
   - Search for "YouTube Data API v3"
   - Click **Enable**
4. Create credentials:
   - Go to **APIs & Services** → **Credentials**
   - Click **Create Credentials** → **API Key**
   - Copy the API key

**Quota**: 10,000 units/day (free tier) = ~3,000 videos/day

### Gemini API Key (Recommended)

1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Click **Create API Key**
3. Copy the API key

**Free Tier:**
- 15 requests/minute
- 1 million tokens/minute
- 1,500 requests/day

**Pricing** (Gemini 2.5 Flash Lite):
- Input: $0.075 per 1M tokens
- Output: $0.30 per 1M tokens

### OpenAI API Key (Optional)

1. Go to [OpenAI Platform](https://platform.openai.com/api-keys)
2. Sign in or create account
3. Click **Create new secret key**
4. Copy the API key

**Pricing** (GPT-4o-mini):
- Input: $0.150 per 1M tokens
- Output: $0.600 per 1M tokens

### DeepSeek API Key (Optional)

1. Go to [DeepSeek Platform](https://platform.deepseek.com/)
2. Sign up or log in
3. Navigate to **API Keys**
4. Create new API key
5. Copy the API key

**Pricing**:
- Input: $0.14 per 1M tokens
- Output: $0.28 per 1M tokens

---

## Step 6: Verify Installation

Run the verification commands:

```bash
# Activate virtual environment
source venv/bin/activate

# Check Python version
python --version  # Should be 3.11+

# Check dependencies
pip list | grep -E "boto3|whisper|openai|chromadb"

# Test AWS credentials
aws s3 ls

# Test crawler script
./crawl.sh --help

# Check pipeline status (should return empty initially)
./crawl.sh status
```

**Expected output:**
```
Pipeline Status:
✅ Configuration loaded successfully
✅ AWS credentials valid
✅ S3 bucket accessible: your-travel-ai-data
📊 Total videos: 0
📋 Stage 1 complete: 0
📋 Stage 2 complete: 0
```

---

## Step 7: Create Test URLs File

Create a test file with YouTube video URLs:

```bash
cat > test_urls.txt << EOF
https://www.youtube.com/watch?v=UEDeptPVNQA
https://www.youtube.com/watch?v=8m8ReerO060
EOF
```

---

## Step 8: Run First Pipeline Test

Test each pipeline stage:

```bash
# Stage 1: Crawl 2 videos
./crawl.sh youtube --input test_urls.txt --limit 2

# Check status
./crawl.sh status

# Stage 2: Extract entities
./crawl.sh process-stage2 --limit 2

# View extracted entities
./crawl.sh view-stage2 youtube_UEDeptPVNQA

# Stage 3: Deduplicate
./crawl.sh process-stage3

# Stage 4: Generate embeddings
./crawl.sh process-stage4 --embedding-types all

# Stage 5: Generate itinerary
./crawl.sh generate-itinerary -q "5 days Bangkok solo budget"
```

---

## Troubleshooting

### Python Version Issues

```bash
# Check Python version
python3 --version

# If version is < 3.11, install Python 3.11+
# On macOS with Homebrew:
brew install python@3.11

# On Ubuntu/Debian:
sudo apt update
sudo apt install python3.11 python3.11-venv
```

### AWS Credentials Not Found

```bash
# Configure AWS CLI
aws configure
# Enter Access Key ID, Secret Access Key, Region (us-east-1), Format (json)

# Or set environment variables directly
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_DEFAULT_REGION=us-east-1
```

### Module Not Found Errors

```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Reinstall dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Use crawl.sh helper script (sets PYTHONPATH automatically)
./crawl.sh youtube --input urls.txt
```

### Whisper Installation Issues

```bash
# Whisper requires ffmpeg
# On macOS:
brew install ffmpeg

# On Ubuntu/Debian:
sudo apt install ffmpeg

# On Windows:
# Download from https://ffmpeg.org/download.html
```

---

## Next Steps

- **Quickstart**: [quickstart.md](quickstart.md) - End-to-end example
- **Project Structure**: [project-structure.md](project-structure.md) - Understand codebase organization
- **Configuration**: [../04-reference/configuration.md](../04-reference/configuration.md) - Advanced configuration options
- **CLI Commands**: [../04-reference/cli-commands.md](../04-reference/cli-commands.md) - Complete command reference

---

## Optional: Chroma Cloud Setup

For cloud-based ChromaDB (recommended for production):

See [chromadb.md](../05-infrastructure/chromadb.md) for detailed Chroma Cloud setup instructions.

---

## Cost Estimates

**Setup costs**: FREE

**Ongoing costs (per 100 videos):**
- S3 storage: ~$0.001/month
- YouTube API: FREE (within quota)
- LLM API (Gemini): ~$0.22 for entity extraction
- Geocoding: ~$0 (90% free Nominatim, 10% Google Maps)
- **Total**: ~$0.25 for 100 videos end-to-end

---

**Installation complete!** Proceed to [Quickstart](quickstart.md).
