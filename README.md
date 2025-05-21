# LLM Websocket Server Example

## Getting Started

### Requirements

- Python 3.9+
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

Update OpenAI API key and prompt in `main.py`

```py
...

api_key = 'YOUR-OPENAI-API-KEY'

...

SYSTEM_PROMPT = {
    "role": "system",
    "content": """Your system prompt"""
}

...
```

### Starting the application

```bash
python main.py
```

## Adapters

### Retell Adapter

The RetellVoceraAdapter connects Vocera WebSocket clients to the Retell integration.

- Default client WebSocket port: 8766

#### Running the Adapter

```bash
python retell_adaptor.py
```

### VoiceFlow Adapter

The VoiceFlowAdapter connects client WebSocket connections to the VoiceFlow API.

#### Environment Variables

- `VOICEFLOW_API_KEY`: Required. Your VoiceFlow API key.
- `VOICEFLOW_VERSION_ID`: Optional. Defaults to "production".
- Default client WebSocket port: 8766

#### Running the Adapter

```bash
python voiceflow_adapter.py
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

```bash
ngrok http 127.0.0.1:8765
```
