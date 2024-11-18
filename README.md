# LLM Websocket Server Example

## Getting Started

### Requirements
 - Python 3.12+
 - OpenAI API key
 - Ngrok

### Installation
```bash
# Clone the repository
git clone https://github.com/vocera-ai/llm-websocket-server-example.git

# Enter into the directory
cd llm-websocket-server-example/

# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Install the dependencies
pip install -r requirements.txt
```
### Starting the application
```
python main.py
```

## Serving LLM Websocket Server Over Internet

### Installing ngrok
Please refer: https://dashboard.ngrok.com/get-started/setup/linux
```bash
# Install ngrok
curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
	| sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null \
	&& echo "deb https://ngrok-agent.s3.amazonaws.com buster main" \
	| sudo tee /etc/apt/sources.list.d/ngrok.list \
	&& sudo apt update \
	&& sudo apt install ngrok

# Authenticate
# get your token from: https://dashboard.ngrok.com/get-started/your-authtoken
ngrok config add-authtoken <your-token>
```

### Forwarding port
```
ngrok http 127.0.0.1:8765
```