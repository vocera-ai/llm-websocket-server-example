import json
import time
import logging
import threading
import socket
import websocket
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
        
        # Client connections
        self.vocera_to_retell = {}  # map Vocera connections to Retell connections
        self.retell_to_vocera = {}  # map Retell connections to Vocera connections

        # State tracking
        self.retell_transcripts = {}  # map Retell connections to transcripts
        self.response_id_map = {}  # Maps Retell response_id to our message tracking

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
            
    # ===== Retell WebSocket Handlers =====

    def on_retell_open(self, ws):
        """Handle successful connection to Retell WebSocket"""
        print("Connected to Retell WebSocket")

    def on_retell_close(self, ws, close_status_code, close_msg):
        """Handle Retell WebSocket disconnection"""
        print(f"Retell WebSocket connection closed: {close_status_code} - {close_msg}")
        if ws in self.retell_to_vocera:
            vocera_client = self.retell_to_vocera[ws]

            for i in self.vocera_server.clients:
                if i['id'] == vocera_client['id']:
                    i['handler'].connection.close()
                    break

            del self.vocera_to_retell[vocera_client]
            del self.retell_to_vocera[ws]
            del self.retell_transcripts[ws]

    def on_retell_error(self, ws, error):
        """Handle Retell WebSocket errors"""
        print(f"Retell WebSocket error: {error}")
    
    def on_retell_message(self, ws, message_str):
        """Handle messages from Retell WebSocket"""
        try:
            data = json.loads(message_str)
            content = data.get("content", "").strip()
            content_complete = data.get("content_complete", True)
            response_id = data.get("response_id", None)

            message = None
            if response_id is not None:
                if response_id not in self.response_id_map:
                    self.response_id_map[response_id] = []
                self.response_id_map[response_id].append(content)

                if content_complete:
                    message = " ".join(self.response_id_map.get(response_id, []))

            if not message:
                return

            self.handle_retell_message(ws, data, message)
            
        except Exception as e:
            print(f"Error handling Retell message: {str(e)}")
    
    # ===== Vocera WebSocket Handlers =====
    
    def on_vocera_connect(self, client, server):
        """Handle new Vocera WebSocket connection"""
        print(f"New Vocera client connected: {client['id']}")
        try:
            # Setup WebSocket with callbacks
            retell_ws = websocket.WebSocketApp(
                self.retell_url,
                on_open=self.on_retell_open,
                on_message=self.on_retell_message,
                on_error=self.on_retell_error,
                on_close=self.on_retell_close
            )
            self.retell_to_vocera[retell_ws] = client    
            self.vocera_to_retell[client['id']] = retell_ws
            self.retell_transcripts[retell_ws] = []

            # Start the connection in a separate thread
            threading.Thread(target=retell_ws.run_forever).start()
            print(f"Connecting to Retell WebSocket at {self.retell_url}")
        except Exception as e:
            print(f"Failed to start Retell WebSocket server: {str(e)}")
            return False
    
    def on_vocera_disconnect(self, client, server):
        """Handle Vocera WebSocket disconnection"""
        print(f"Vocera client disconnected: {client['id']}")
        # Remove client from our tracking
        if client['id'] in self.vocera_to_retell:
            retell_ws = self.vocera_to_retell[client['id']]
            retell_ws.close()
            del self.retell_to_vocera[retell_ws]
            del self.vocera_to_retell[client['id']]
            del self.retell_transcripts[retell_ws]

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

    def handle_retell_message(self, ws, data, message_str):
        """Handle messages from Retell"""
        message = {
            "role": "agent",
            "content": message_str,
        }
        transcript = self.retell_transcripts[ws]
        transcript.append(message)
        vocera_client = self.retell_to_vocera[ws]
        print(f"{message['role']}: {message['content']}")
        self.vocera_server.send_message(vocera_client, json.dumps(message))

    def handle_vocera_message(self, client, data):
        """Handle messages from Vocera"""
        content = data.get('content', '')
        retell_ws = self.vocera_to_retell[client['id']]
        transcript = self.retell_transcripts[retell_ws]
        message = {
            "role": "user",
            "content": content,
        }
        transcript.append(message)
        response = {
            "interaction_type": "response_required",
            "response_id":  int(time.time() * 1000),  # Use timestamp as ID
            "transcript": transcript,
        }
        print(f"{message['role']}: {message['content']}")
        try:
            retell_ws.send(json.dumps(response))
        except Exception as e:
            time.sleep(1)  # Wait for the connection to be established
            retell_ws.send(json.dumps(response))

# Example usage
if __name__ == "__main__":
    # Configuration
    RETELL_URL = "ws://127.0.0.1:8080/llm-websocket/call-id"
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