import json
import time
import logging
import threading
import socket
import uuid
import websocket
import requests
from websocket_server import WebsocketServer

logger = logging.getLogger(__name__)

class RetellVoceraAdapter:
    """
    Adapter that listens for Vocera WebSocket connections and forwards to Retell integration
    """
    def __init__(self, retell_url, vocera_port):
        self.retell_url = retell_url
        self.vocera_port = vocera_port
        
        # WebSocket servers
        self.vocera_server = None
        
        # State tracking
        self.vocera_data = {}  # Indexed by client_id
        self.retell_data = {}  # Indexed by websocket object

    def start(self):
        """Start the adapter by setting up both WebSocket servers"""
        
        # Set up Vocera WebSocket server
        try:
            self.vocera_server = WebsocketServer(port=self.vocera_port, host='127.0.0.1')
            self.vocera_server.set_fn_new_client(self.on_vocera_connect)
            self.vocera_server.set_fn_client_left(self.on_vocera_disconnect)
            self.vocera_server.set_fn_message_received(self.on_vocera_message)
            
            # Start the server in a separate thread
            threading.Thread(target=self.vocera_server.run_forever).start()
            print(f"Vocera WebSocket server listening on port {self.vocera_port}")
        except Exception as e:
            print(f"Failed to start Vocera WebSocket server: {str(e)}")
            return False
            
        return True
        
    def stop(self):
        """Stop the adapter and close all connections"""
        if self.vocera_server:
            self.vocera_server.shutdown_gracefully()

    def _get_response_id(self, transcript):
        cnt = 0
        for message in transcript:
            if message['role'] == 'user':
                cnt += 1
        return cnt-1
            
    # ===== Retell WebSocket Handlers =====

    def send_webhook(self, call_id):
        webhook_data = {
                "event": "call_started",
                "call": {
                    "call_id": call_id,
                    "from_number": "1122334455"  # You can modify this as needed
                }
            }
        # send webhook to retell
        # Define the webhook URL
        webhook_url = f"{'https' if secure else 'http'}://{url}/webhook"
        # Make the webhook POST request
        response = requests.post(webhook_url, json=webhook_data)
        if response.status_code == 200:
            print("Webhook notification sent successfully")
        else:
            print(f"Failed to send webhook notification: {response.status_code}")

    def on_retell_open(self, ws):
        """Handle successful connection to Retell WebSocket"""
        print("Connected to Retell WebSocket")
        self.send_webhook(self.retell_data[ws]['call_id'])

    def on_retell_close(self, ws, close_status_code, close_msg):
        """Handle Retell WebSocket disconnection"""
        print(f"Retell WebSocket connection closed: {close_status_code} - {close_msg}")
        if ws in self.retell_data:
            vocera_client = self.retell_data[ws]['vocera_client']
            client_id = vocera_client['id']

            # Close the Vocera connection
            for i in self.vocera_server.clients:
                if i['id'] == client_id:
                    i['handler'].connection.close()
                    break

            del self.retell_data[ws]

    def on_retell_error(self, ws, error):
        """Handle Retell WebSocket errors"""
        print(f"Retell WebSocket error: {error}")
    
    def on_retell_message(self, ws, message_str):
        """Handle messages from Retell WebSocket"""
        try:
            data = json.loads(message_str)
            response_type = data.get("response_type", "")

            if response_type == "tool_call_invocation":
                self.handle_retell_tool_call_invocation(ws, data)
            elif response_type == "tool_call_result":
                self.handle_retell_tool_call_result(ws, data)
            else:
                self.handle_retell_message(ws, data)
            
        except Exception as e:
            print(f"Error handling Retell message: {str(e)}")
    
    # ===== Vocera WebSocket Handlers =====
    
    def on_vocera_connect(self, client, server):
        """Handle new Vocera WebSocket connection"""
        print(f"New Vocera client connected: {client['id']}")
        call_id = create_call_id()
        url = self.retell_url + call_id

        try:
            # Setup WebSocket with callbacks
            retell_ws = websocket.WebSocketApp(
                url,
                on_open=self.on_retell_open,
                on_message=self.on_retell_message,
                on_error=self.on_retell_error,
                on_close=self.on_retell_close
            )
            
            self.retell_data[retell_ws] = {
                'call_id': call_id,
                'vocera_client': client,
                'transcript': [],
                'response_messages': {}  # Maps response_id to message parts
            }
            
            self.vocera_data[client['id']] = {
                'retell_ws': retell_ws
            }

            # Start the connection in a separate thread
            threading.Thread(target=retell_ws.run_forever).start()
            print(f"Connecting to Retell WebSocket at {url}")
        except Exception as e:
            print(f"Failed to start Retell WebSocket server: {str(e)}")
            return False
    
    def on_vocera_disconnect(self, client, server):
        """Handle Vocera WebSocket disconnection"""
        print(f"Vocera client disconnected: {client['id']}")
        # Remove client from our tracking
        if client['id'] in self.vocera_data:
            retell_ws = self.vocera_data[client['id']]['retell_ws']
            retell_ws.close()
            del self.vocera_data[client['id']]

    def on_vocera_message(self, client, server, message_str):
        """Handle messages from Vocera WebSocket"""
        try:
            message = json.loads(message_str)
            content = message.get('content', '').strip()
            
            if not content:
                return
                
            self.handle_vocera_message(client, message)
                
        except Exception as e:
            print(f"Error handling Vocera message: {str(e)}")

    # ===== Message Conversion Handlers =====

    def handle_retell_message(self, ws, data):
        """Handle messages from Retell"""

        # Merge content from multiple messages
        content = data.get("content", "").strip()
        content_complete = data.get("content_complete", True)
        response_id = data.get("response_id", None)

        content_merged = None
        if response_id is not None:
            response_messages = self.retell_data[ws]['response_messages']
            
            if response_id not in response_messages:
                response_messages[response_id] = []
            response_messages[response_id].append(content)

            if content_complete:
                content_merged = " ".join(response_messages.get(response_id, []))

        if not content_merged:
            return

        message = {
            "role": "agent",
            "content": content_merged,
        }
        
        # Add to transcript
        transcript = self.retell_data[ws]['transcript']
        transcript.append(message)
        
        # Get vocera client and send message
        vocera_client = self.retell_data[ws]['vocera_client']
        print(f"{message['role']}: {message['content']}")
        self.vocera_server.send_message(vocera_client, json.dumps(message))

    def handle_retell_tool_call_invocation(self, ws, data):
        message_data = {
            "id": data.get("tool_call_id", ""),
            "name": data.get("name", ""),
            "arguments": data.get("arguments", ""),
        }
        message = {
            "role": "Function Call",
            "data": message_data,
        }
        
        # Add to transcript
        data['role'] = 'tool_call_invocation'
        transcript = self.retell_data[ws]['transcript']
        transcript.append(data)
        
        # Get vocera client and send message
        vocera_client = self.retell_data[ws]['vocera_client']
        print(f"{message['role']}: {message['data']}")
        self.vocera_server.send_message(vocera_client, json.dumps(message))

    def handle_retell_tool_call_result(self, ws, data):
        message_data = {
            "id": data.get("tool_call_id", ""),
            "result": data.get("content", ""),
        }
        message = {
            "role": "Function Call Result",
            "data": message_data,
        }
        
        # Add to transcript
        data['role'] = 'tool_call_result'
        transcript = self.retell_data[ws]['transcript']
        transcript.append(data)
        
        # Get vocera client and send message
        vocera_client = self.retell_data[ws]['vocera_client']
        print(f"{message['role']}: {message['data']}")
        self.vocera_server.send_message(vocera_client, json.dumps(message))

    def handle_vocera_message(self, client, data):
        """Handle messages from Vocera"""
        content = data.get('content', '')
        retell_ws = self.vocera_data[client['id']]['retell_ws']
        
        # Add message to transcript
        message = {
            "role": "user",
            "content": content,
        }
        transcript = self.retell_data[retell_ws]['transcript']
        transcript.append(message)

        response_id = self._get_response_id(transcript)
        response = {
            "interaction_type": "response_required",
            "response_id":  response_id,
            "transcript_with_tool_calls": transcript,
        }
        print(f"[{response_id}] {message['role']}: {message['content']}")
        try:
            retell_ws.send(json.dumps(response))
        except Exception as e:
            time.sleep(1)  # Wait for the connection to be established
            retell_ws.send(json.dumps(response))

def create_call_id():
    return str(uuid.uuid4())

# Example usage
if __name__ == "__main__":
    # Configuration
    call_id = create_call_id()
    url = "localhost:8080"
    secure = False
    RETELL_URL = f"{'wss' if secure else 'ws'}://{url}/llm-websocket/"
    VOCERA_PORT = 8766  # Port to listen for Vocera connections
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create and start adapter
    adapter = RetellVoceraAdapter(
        RETELL_URL, 
        VOCERA_PORT,
    )
    
    adapter.start()
    
    # Keep the main thread running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        adapter.stop()
        print("Adapter stopped")