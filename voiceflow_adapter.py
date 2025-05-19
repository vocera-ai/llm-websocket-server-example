import json
import time
import logging
import threading
import uuid
import os
import websocket
import requests
from websocket_server import WebsocketServer

logger = logging.getLogger(__name__)

class VoiceFlowAdapter:
    """
    Adapter that listens for client WebSocket connections and forwards to VoiceFlow API
    """
    def __init__(self, client_port):
        self.client_port = client_port
        
        # WebSocket server
        self.client_server = None
        
        # State tracking
        self.client_data = {}  # Indexed by client_id
        self.sessions = {}  # Indexed by client_id
        
        # VoiceFlow API configuration
        self.api_key = os.getenv("VOICEFLOW_API_KEY")
        if not self.api_key:
            logger.error("VOICEFLOW_API_KEY environment variable is not set")
            raise ValueError("VOICEFLOW_API_KEY environment variable is not set")
            
        self.version_id = os.getenv("VOICEFLOW_VERSION_ID", "production")

    def start(self):
        """Start the adapter by setting up the WebSocket server"""
        
        # Set up client WebSocket server
        try:
            self.client_server = WebsocketServer(port=self.client_port, host='0.0.0.0')
            self.client_server.set_fn_new_client(self.on_client_connect)
            self.client_server.set_fn_client_left(self.on_client_disconnect)
            self.client_server.set_fn_message_received(self.on_client_message)
            
            # Start the server in a separate thread
            threading.Thread(target=self.client_server.run_forever).start()
            print(f"Client WebSocket server listening on port {self.client_port}")
            return True
        except Exception as e:
            print(f"Failed to start client WebSocket server: {str(e)}")
            return False
            
    def stop(self):
        """Stop the adapter and close all connections"""
        if self.client_server:
            self.client_server.shutdown_gracefully()

    # ===== Client WebSocket Handlers =====
    
    def on_client_connect(self, client, server):
        """Handle new client WebSocket connection"""
        print(f"New client connected: {client['id']}")
        
        # Generate unique user_id for this connection
        user_id = f"user-{uuid.uuid4()}"
        
        # Initialize session data
        self.sessions[client['id']] = {
            'user_id': user_id,
        }
        
        # Start conversation with VoiceFlow
        threading.Thread(target=self.start_conversation, args=(client,)).start()
    
    def on_client_disconnect(self, client, server):
        """Handle client WebSocket disconnection"""
        print(f"Client disconnected: {client['id']}")
        # Remove client from our tracking
        if client['id'] in self.sessions:
            del self.sessions[client['id']]

    def on_client_message(self, client, server, message_str):
        """Handle messages from client WebSocket"""
        try:
            message = json.loads(message_str)
            content = message.get('content', '').strip()
            
            if not content:
                return
                
            self.handle_client_message(client, content)
                
        except Exception as e:
            print(f"Error handling client message: {str(e)}")

    # ===== VoiceFlow API Handlers =====

    def start_conversation(self, client):
        """Start a conversation with VoiceFlow"""
        client_id = client['id']
        user_id = self.sessions[client_id]['user_id']
        
        # Initialize VoiceFlow session
        headers = {
            "Authorization": self.api_key,
            "versionID": self.version_id,
            "Content-Type": "application/json"
        }
        
        url = f"https://general-runtime.voiceflow.com/state/user/{user_id}/interact"
        
        data = {
            "action": {
                "type": "launch"
            },
        }
        
        try:
            logger.info(f"Starting conversation with VoiceFlow. URL: {url}")
            response = requests.post(url, headers=headers, json=data)
            
            # Log request and response details for debugging
            logger.info(f"Request headers: {headers}")
            logger.info(f"Request data: {data}")
            
            if response.status_code != 200:
                logger.error(f"Error response from VoiceFlow: {response.status_code} - {response.text}")
                
            response.raise_for_status()
            
            traces = response.json()
            
            # Process and send traces to client
            result = self.process_traces(client, traces)
            if not result:
                # Send initial greeting if no response from VoiceFlow
                greeting = "Hi! How can I help you today?"
                self.client_server.send_message(client, json.dumps({"content": greeting}))
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error starting conversation: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response body: {e.response.text}")
            
            greeting = "Hi! How can I help you today?"
            self.client_server.send_message(client, json.dumps({"content": greeting}))

    def handle_client_message(self, client, message):
        """Send a user message to VoiceFlow and get response"""
        try:
            client_id = client['id']
            user_id = self.sessions[client_id]['user_id']
            
            headers = {
                "Authorization": self.api_key,
                "versionID": self.version_id,
                "Content-Type": "application/json"
            }
            
            url = f"https://general-runtime.voiceflow.com/state/user/{user_id}/interact"
            
            data = {
                "action": {
                    "type": "text",
                    "payload": message
                },
            }
            
            logger.info(f"Sending message to VoiceFlow: {message}")
            response = requests.post(url, headers=headers, json=data)
            
            # Log response status for debugging
            if response.status_code != 200:
                logger.error(f"Error response from VoiceFlow: {response.status_code} - {response.text}")
                
            response.raise_for_status()
            
            traces = response.json()
            
            # Process traces and send response to client
            return self.process_traces(client, traces)
        
        except requests.exceptions.RequestException as e:
            error_msg = f"Error: {str(e)}"
            logger.error(error_msg)
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response body: {e.response.text}")
            self.client_server.send_message(client, json.dumps({"content": "Sorry, I couldn't process your message. Please try again later."}))
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            logger.error(error_msg)
            self.client_server.send_message(client, json.dumps({"content": "Sorry, I couldn't process your message. Please try again later."}))

    def process_traces(self, client, traces):
        """Process traces received from VoiceFlow and send to client"""
        responses = []
        
        for trace in traces:
            trace_type = trace.get('type')
            
            # Handle different trace types
            if trace_type == 'speak' or trace_type == 'text':
                # Text response - handle both 'speak' and 'text' trace types
                message = trace.get('payload', {}).get('message', '')
               
                if message:
                    responses.append(message)
                    
            # Only handle 'end' traces for conversation flow, ignore other types
            elif trace_type == 'end':
                # End of conversation
                self.client_server.send_message(client, json.dumps({
                    "type": "end",
                    "content": "Conversation ended"
                }))
        
        # Send combined text responses
        if responses:
            combined_response = " ".join(responses)
            self.client_server.send_message(client, json.dumps({
                "content": combined_response
            }))
            return combined_response
        return None

# Example usage
if __name__ == "__main__":
    # Configuration
    CLIENT_PORT = 8766  # Port to listen for client connections
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create and start adapter
    adapter = VoiceFlowAdapter(CLIENT_PORT)
    
    adapter.start()
    
    # Keep the main thread running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        adapter.stop()
        print("Adapter stopped")
