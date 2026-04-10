# AWS Deployment Guide — NL→DB Agent

## Architecture on AWS

```
Internet
    ↓
[EC2 Instance]
    ├── FastAPI (port 8000)   ← agent backend
    └── Streamlit (port 8501) ← user interface
         ↓
    [SQLite on EC2]           ← dev/demo
    or
    [RDS PostgreSQL]          ← production
```

---

## Step 1: Launch EC2 Instance

1. Go to AWS Console → EC2 → Launch Instance
2. Choose: **Ubuntu Server 22.04 LTS**
3. Instance type: **t2.micro** (free tier) or **t2.small**
4. Key pair: Create new → download `.pem` file
5. Security group — open these ports:
   - 22 (SSH)
   - 8000 (FastAPI)
   - 8501 (Streamlit)
6. Launch instance

---

## Step 2: Connect to EC2

```bash
chmod 400 your-key.pem
ssh -i your-key.pem ubuntu@your-ec2-public-ip
```

---

## Step 3: Install dependencies on EC2

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv git

# Clone your repo
git clone https://github.com/SAMithila/nl-db-agent.git
cd nl-db-agent

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

---

## Step 4: Set environment variables

```bash
# Create .env on EC2
nano .env
```

Add:
```
OPENAI_API_KEY=sk-your-key-here
API_URL=http://your-ec2-public-ip:8000
```

---

## Step 5: Seed the database

```bash
python db/seed_data.py
```

---

## Step 6: Run FastAPI backend

```bash
# Run in background
nohup python api/main.py &

# Verify it's running
curl http://localhost:8000/health
```

---

## Step 7: Run Streamlit frontend

```bash
# Run in background
nohup streamlit run ui/app.py --server.port 8501 &
```

---

## Step 8: Access your app

- API docs: `http://your-ec2-ip:8000/docs`
- Streamlit UI: `http://your-ec2-ip:8501`

---

## Optional: Docker deployment

```bash
# Build image
docker build -t nl-db-agent .

# Run container
docker run -d \
  -p 8000:8000 \
  -e OPENAI_API_KEY=sk-your-key \
  nl-db-agent
```

---

## Optional: RDS PostgreSQL (production)

1. AWS Console → RDS → Create database
2. Choose PostgreSQL, Free tier
3. Note endpoint, username, password
4. Add to `.env`:
```
DATABASE_URL=postgresql://user:password@rds-endpoint:5432/dbname
```

---

## Cost estimate (Free Tier)

| Service | Cost |
|---------|------|
| EC2 t2.micro | Free (750hrs/month) |
| RDS t2.micro | Free (750hrs/month) |
| Data transfer | Minimal |
| **Total** | **~$0/month on free tier** |