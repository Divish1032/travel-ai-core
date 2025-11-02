# Travel AI

An intelligent travel planning system that crawls YouTube travel vlogs, processes them with LLMs, and generates personalized travel plans.

## 🎯 Project Overview

Travel AI is a multi-stage pipeline that:
1. **Stage 1 (Current)**: Crawls YouTube travel vlogs and extracts metadata + transcripts
2. **Stage 2 (Future)**: Chunks transcripts and extracts structured travel information with LLMs
3. **Stage 3 (Future)**: Generates personalized travel itineraries based on user preferences

This README covers **Stage 1: YouTube Crawling** - a production-ready system for collecting travel vlog data at scale.

## ✨ Stage 1 Features

- 🎥 **YouTube Video Crawler** - Fetches metadata and transcripts from travel vlogs
- 📊 **Pydantic Validation** - Ensures data quality with strict schema validation
- ☁️ **S3 Storage** - Stores crawled data in structured S3 paths
- 🔄 **Rate Limiting & Retries** - Respects API limits and handles failures gracefully
- 📈 **Progress Tracking** - Real-time progress bars and detailed logging
- ✅ **Resume Capability** - Skips already-crawled videos on restart
- 🧪 **Comprehensive Testing** - Unit tests, integration tests, and Jupyter notebooks
- 🎨 **Beautiful CLI** - Rich terminal output with colors and tables

## 📋 Prerequisites

- **Python 3.11+** ([Download](https://www.python.org/downloads/))
- **AWS Account** with S3 access ([Sign up](https://aws.amazon.com/))
- **Git** (optional but recommended) ([Download](https://git-scm.com/downloads))
- **pip** (comes with Python 3.11+)

## 🚀 Installation

### Option 1: Automated Setup (Recommended for Mac)

```bash
# Clone the repository
git clone <your-repo-url>
cd TravelAI

# Run automated setup script
./setup.sh
```

The setup script will:
- ✅ Check Python version (3.11+ required)
- ✅ Create virtual environment
- ✅ Install all dependencies
- ✅ Create necessary directories
- ✅ Set up `.env` file
- ✅ Verify AWS credentials
- ✅ Create sample data files
- ✅ Run basic tests

### Option 2: Manual Setup

```bash
# Clone the repository
git clone <your-repo-url>
cd TravelAI

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Setup configuration
cp .env.example .env
# Edit .env with your AWS credentials (see Configuration section)

# Create directories
mkdir -p data/raw data/processed data/cache logs
```

## ⚙️ Configuration

### Environment Variables

Edit `.env` file with your settings:

```bash
# AWS Configuration (Required for S3 upload)
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_key_here
AWS_REGION=us-east-1
S3_BUCKET_NAME=your-travel-ai-bucket

# Application Configuration (Optional - has defaults)
LOG_LEVEL=INFO                 # DEBUG, INFO, WARNING, ERROR, CRITICAL
CRAWLER_RATE_LIMIT=2           # Seconds between requests (default: 2)
MAX_RETRIES=3                  # Maximum retry attempts (default: 3)
```

### Getting AWS Credentials

1. Log in to [AWS Console](https://console.aws.amazon.com/)
2. Navigate to: IAM → Users → Your User → Security Credentials
3. Click "Create Access Key"
4. Copy the Access Key ID and Secret Access Key to `.env`
5. Create an S3 bucket for your data (or use existing one)

### S3 Bucket Setup

```bash
# Create S3 bucket (or use AWS Console)
aws s3 mb s3://your-travel-ai-bucket --region us-east-1

# Verify access
aws s3 ls s3://your-travel-ai-bucket
```

**Note:** You can skip AWS setup for now and use local storage only. Just use `--output local` instead of `--output s3` when crawling.

## 🎬 Quick Start

### 1. Activate Environment

```bash
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Test with Sample Videos

```bash
# Crawl 3 sample videos and save locally
python cli/crawl.py youtube \
  --input data/sample_urls.txt \
  --output local \
  --limit 3
```

### 3. View Results

```bash
# List crawled files
ls -lh data/raw/

# Validate JSONL file
python cli/crawl.py validate \
  --input data/raw/youtube_batch_*.jsonl \
  --verbose
```

### 4. Check Logs

```bash
# View application logs
tail -f logs/app_*.log

# View crawler-specific logs
tail -f logs/crawler_*.log

# View errors only
tail -f logs/errors_*.log
```

## 📖 Usage Examples

### CLI Commands

#### Crawl Videos

```bash
# Crawl videos and save locally
python cli/crawl.py youtube \
  --input urls.txt \
  --output local

# Crawl and upload to S3
python cli/crawl.py youtube \
  --input urls.txt \
  --output s3

# Test with first 10 videos
python cli/crawl.py youtube \
  --input urls.txt \
  --output local \
  --limit 10

# Dry run (preview without crawling)
python cli/crawl.py youtube \
  --input urls.txt \
  --dry-run

# Resume previous crawl (skip already crawled)
python cli/crawl.py youtube \
  --input urls.txt \
  --output s3 \
  --resume
```

#### Validate Data

```bash
# Validate JSONL file
python cli/crawl.py validate \
  --input data/raw/batch.jsonl

# Show detailed validation errors
python cli/crawl.py validate \
  --input data/raw/batch.jsonl \
  --verbose
```

#### Using Make Commands

```bash
# Show all available commands
make help

# Setup environment
make setup

# Crawl sample videos
make crawl-sample

# Run tests
make test

# Start Jupyter Lab
make jupyter

# Clean cache and logs
make clean
```

### Python API

```python
from src.crawlers.youtube import crawl_video, crawl_videos
from src.storage.s3 import S3Storage

# Crawl single video
video = crawl_video("https://youtube.com/watch?v=abc123")
if video:
    print(f"Title: {video.title}")
    print(f"Duration: {video.duration_seconds}s")
    print(f"Transcript segments: {len(video.transcript)}")

# Crawl multiple videos
urls = ["https://youtube.com/watch?v=abc123", ...]
successful, failed = crawl_videos(urls, rate_limit=2.0)

# Upload to S3
storage = S3Storage()
video_dicts = [v.to_dict() for v in successful]
s3_uri = storage.upload_jsonl(
    data=video_dicts,
    source="youtube",
    data_type="videos"
)
print(f"Uploaded to: {s3_uri}")
```

### Jupyter Notebook

```bash
# Start Jupyter Lab
make jupyter

# Or manually
jupyter lab
```

Then open `notebooks/01_test_youtube_crawler.ipynb` for interactive testing.

## 📁 Project Structure

```
TravelAI/
├── .env                          # Environment variables (create from .env.example)
├── .env.example                  # Environment template
├── .gitignore                    # Git ignore rules
├── requirements.txt              # Python dependencies
├── Makefile                      # Useful commands
├── setup.sh                      # Automated setup script (Mac)
├── README.md                     # This file
│
├── src/                          # Source code
│   ├── crawlers/                 # Crawler implementations
│   │   ├── base.py              # Abstract base crawler
│   │   └── youtube.py           # YouTube crawler (Stage 1)
│   ├── processors/              # Data processors (Stage 2)
│   ├── storage/                 # Storage handlers
│   │   └── s3.py               # S3 storage manager
│   ├── llm/                     # LLM integrations (Stage 2)
│   └── utils/                   # Utilities
│       ├── config.py           # Configuration manager
│       ├── logging.py          # Logging setup
│       └── schemas.py          # Pydantic data models
│
├── cli/                         # Command-line interface
│   └── crawl.py                # Main CLI tool
│
├── api/                         # REST API (future)
│   └── main.py                 # FastAPI app stub
│
├── tests/                       # Test suite
│   └── test_crawler.py         # Crawler tests
│
├── notebooks/                   # Jupyter notebooks
│   └── 01_test_youtube_crawler.ipynb
│
├── data/                        # Data storage (gitignored)
│   ├── raw/                    # Raw crawled data
│   ├── processed/              # Processed data
│   ├── cache/                  # Cache files
│   └── sample_urls.txt         # Sample YouTube URLs
│
├── logs/                        # Application logs (gitignored)
│   ├── app_YYYY-MM-DD.log     # General logs
│   ├── errors_YYYY-MM-DD.log  # Error logs
│   └── crawler_YYYY-MM-DD.log # Crawler logs
│
├── configs/                     # Configuration files
└── scripts/                     # Utility scripts
    └── test_stage1_complete.py # Stage 1 integration test
```

## 🔧 Troubleshooting

### AWS Credentials Issues

**Error**: `AWS credentials not found or incomplete`

**Solution**:
1. Check `.env` file has correct AWS credentials
2. Verify credentials work: `aws s3 ls` (requires AWS CLI)
3. Ensure IAM user has S3 permissions
4. Try using `--output local` to test without AWS

### Videos Without Transcripts

**Error**: Video skipped - no transcript available

**Solution**:
- Not all YouTube videos have transcripts
- Auto-generated transcripts are only available for some videos
- The crawler automatically skips videos without transcripts
- Failed URLs are saved to `data/raw/failed_urls_*.txt` for review

### Rate Limiting

**Error**: Too many requests / 429 errors

**Solution**:
1. Increase `CRAWLER_RATE_LIMIT` in `.env` (e.g., `CRAWLER_RATE_LIMIT=5`)
2. Reduce number of concurrent requests
3. Add delays between batches
4. YouTube's transcript API is generally permissive, but respect limits

### Permission Denied on setup.sh

**Error**: `Permission denied: ./setup.sh`

**Solution**:
```bash
chmod +x setup.sh
./setup.sh
```

### Import Errors

**Error**: `ModuleNotFoundError: No module named 'src'`

**Solution**:
1. Ensure virtual environment is activated: `source venv/bin/activate`
2. Reinstall dependencies: `pip install -r requirements.txt`
3. Run from project root directory, not subdirectory

### Python Version Too Old

**Error**: `Python 3.10 is too old (>= 3.11 required)`

**Solution**:
1. Install Python 3.11+ from [python.org](https://www.python.org/downloads/)
2. Update your PATH to use Python 3.11
3. Recreate virtual environment: `python3.11 -m venv venv`

## ✅ Stage 1 Complete Checklist

Before moving to Stage 2, verify everything works:

- [ ] Environment setup complete (`./setup.sh` runs successfully)
- [ ] AWS credentials configured (or local storage working)
- [ ] Sample crawl successful (`python cli/crawl.py youtube --input data/sample_urls.txt --limit 3`)
- [ ] Data validation passes (`python cli/crawl.py validate --input data/raw/*.jsonl`)
- [ ] Logs are being written to `logs/` directory
- [ ] S3 upload works (if using AWS) or local storage confirmed
- [ ] Tests pass (`pytest tests/test_crawler.py`)
- [ ] Jupyter notebook runs (`notebooks/01_test_youtube_crawler.ipynb`)

**Run full integration test**:
```bash
python scripts/test_stage1_complete.py
```

If you see `✅ STAGE 1 COMPLETE`, you're ready for Stage 2!

## 🎯 Next Steps: Stage 2 Preview

Once Stage 1 is complete, Stage 2 will add:

1. **Transcript Chunking**
   - Split long transcripts into semantic chunks
   - Maintain context across chunk boundaries
   - Optimize chunk sizes for LLM processing

2. **Information Extraction**
   - Extract locations, activities, costs, tips
   - Identify travel highlights and recommendations
   - Structure data for travel planning

3. **LLM Integration**
   - Use OpenAI/Anthropic APIs for extraction
   - Prompt engineering for travel-specific data
   - Batch processing for efficiency

4. **Data Pipeline**
   - Process crawled videos through LLM
   - Store structured travel information
   - Build searchable travel knowledge base

Stay tuned for Stage 2 implementation guide!

## 🤝 Contributing

This is a learning project. Contributions from teammates are welcome!

### Development Workflow

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Make changes and test thoroughly
3. Run tests: `pytest tests/`
4. Update documentation if needed
5. Commit with clear messages: `git commit -m "Add: feature description"`
6. Push and create pull request

### Code Style

- Follow PEP 8 Python style guide
- Use type hints for all functions
- Add docstrings to public functions
- Write tests for new features
- Keep functions focused and small

### Adding New Features

- Add tests in `tests/`
- Update `README.md` if user-facing
- Add configuration options to `.env.example`
- Log important operations
- Handle errors gracefully

## 📄 License

MIT License

Copyright (c) 2024 Travel AI Project

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## 📞 Support

For questions or issues:
- Check the [Troubleshooting](#-troubleshooting) section
- Review logs in `logs/` directory
- Run `python scripts/test_stage1_complete.py` for diagnostics
- Open an issue on GitHub (if available)

## 🎉 Acknowledgments

Built with:
- [pytube](https://github.com/pytube/pytube) - YouTube video metadata
- [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api) - Transcript extraction
- [Pydantic](https://docs.pydantic.dev/) - Data validation
- [boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html) - AWS S3 integration
- [Click](https://click.palletsprojects.com/) - CLI framework
- [Rich](https://rich.readthedocs.io/) - Beautiful terminal output

---

**Happy Crawling!** 🚀 Start with `./setup.sh` and follow the Quick Start guide above.
