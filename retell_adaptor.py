import json
import time
import logging
import threading
import socket
from websocket_server import WebsocketServer

logger = logging.getLogger(__name__)

class RetellVoceraAdapter:
    """
    Adapter that listens for both Retell and Vocera WebSocket connections
    and converts messages between the two protocols.
    """
    def __init__(self, retell_port, vocera_port):
        self.retell_port = retell_port
        self.vocera_port = vocera_port
        
        # WebSocket servers
        self.retell_server = None
        self.vocera_server = None
        
        # Client connections
        self.retell_clients = {}  # Store Retell client connections by ID
        self.vocera_clients = {}  # Store Vocera client connections by ID
        
        # State tracking
        self.response_id_map = {}  # Maps Retell response_id to our message tracking
        self.tool_calls = {}  # Track tool calls by ID
        self.last_response_id = None
        self.is_running = False
        
    def start(self):
        """Start the adapter by setting up both WebSocket servers"""
        self.is_running = True
        
        # Set up Retell WebSocket server
        try:
            self.retell_server = WebsocketServer(port=self.retell_port, host='127.0.0.1')
            self.retell_server.set_fn_new_client(self.on_retell_connect)
            self.retell_server.set_fn_client_left(self.on_retell_disconnect)
            self.retell_server.set_fn_message_received(self.on_retell_message)
            
            # Start the server in a separate thread
            threading.Thread(target=self.retell_server.run_forever).start()
            print(f"Retell WebSocket server listening on port {self.retell_port}")
        except Exception as e:
            print(f"Failed to start Retell WebSocket server: {str(e)}")
            self.is_running = False
            return False
            
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
            self.is_running = False
            if self.retell_server:
                self.retell_server.shutdown_gracefully()
            return False
            
        return True
        
    def stop(self):
        """Stop the adapter and close all connections"""
        self.is_running = False
        if self.retell_server:
            self.retell_server.shutdown_gracefully()
        if self.vocera_server:
            self.vocera_server.shutdown_gracefully()
            
    # ===== Retell WebSocket Handlers =====
    
    def on_retell_connect(self, client, server):
        """Handle new Retell WebSocket connection"""
        print(f"New Retell client connected: {client['id']}")
        # Store client connection
        self.retell_clients[client['id']] = client
        
        # Send initial config to Retell
        config = {
            "response_type": "config",
            "config": {
                "auto_reconnect": True,
                "call_details": True,
                "transcript_with_tool_calls": True
            }
        }
        server.send_message(client, json.dumps(config))
    
    def on_retell_disconnect(self, client, server):
        """Handle Retell WebSocket disconnection"""
        print(f"Retell client disconnected: {client['id']}")
        # Remove client from our tracking
        if client['id'] in self.retell_clients:
            del self.retell_clients[client['id']]
    
    def on_retell_message(self, client, server, message_str):
        """Handle messages from Retell WebSocket"""
        try:
            data = json.loads(message_str)
            interaction_type = data.get("interaction_type")
            
            if interaction_type == "ping_pong":
                # Handle ping_pong to keep connection alive
                self.handle_retell_ping(client, data)
                
            elif interaction_type == "call_details":
                # Handle call details - can be logged or stored
                print(f"Received call details: {data.get('call', {}).get('id')}")
                
            elif interaction_type == "update_only":
                # Handle transcript updates
                self.handle_retell_update(data)
                
            elif interaction_type in ["response_required", "reminder_required"]:
                # Handle requests for agent responses
                self.handle_retell_response_request(client, data)
                
        except Exception as e:
            print(f"Error handling Retell message: {str(e)}")
    
    # ===== Vocera WebSocket Handlers =====
    
    def on_vocera_connect(self, client, server):
        """Handle new Vocera WebSocket connection"""
        print(f"New Vocera client connected: {client['id']}")
        # Store client connection
        self.vocera_clients[client['id']] = client
        
        # Note: In a real implementation, you would validate headers here
        # Since websocket_server doesn't expose headers directly, you might need
        # to implement a custom handshake validation
    
    def on_vocera_disconnect(self, client, server):
        """Handle Vocera WebSocket disconnection"""
        print(f"Vocera client disconnected: {client['id']}")
        # Remove client from our tracking
        if client['id'] in self.vocera_clients:
            del self.vocera_clients[client['id']]
    
    def on_vocera_message(self, client, server, message_str):
        """Handle messages from Vocera WebSocket"""
        try:
            message = json.loads(message_str)
            content = message.get('content', '').strip()
            
            if not content:
                return
                
            self.handle_vocera_regular_message(message)
                
        except Exception as e:
            print(f"Error handling Vocera message: {str(e)}")
    
    def send_to_vocera(self, message):
        """Send message to all connected Vocera clients"""
        if not self.vocera_clients:
            print("No Vocera clients connected to send message to")
            return
            
        # In a real implementation, you might want to target specific clients
        # For now, we'll broadcast to all connected clients
        for client_id, client in self.vocera_clients.items():
            try:
                self.vocera_server.send_message(client, json.dumps(message))
            except Exception as e:
                print(f"Error sending message to Vocera client {client_id}: {str(e)}")
    
    def send_to_retell(self, message):
        """Send message to all connected Retell clients"""
        if not self.retell_clients:
            print("No Retell clients connected to send message to")
            return
            
        # In a real implementation, you might want to target specific clients
        # For now, we'll broadcast to all connected clients
        for client_id, client in self.retell_clients.items():
            try:
                self.retell_server.send_message(client, json.dumps(message))
            except Exception as e:
                print(f"Error sending message to Retell client {client_id}: {str(e)}")
    
    # ===== Message Conversion Handlers =====
    
    def handle_retell_ping(self, client, data):
        """Handle ping_pong messages from Retell"""
        # Send ping_pong response back to Retell
        response = {
            "response_type": "ping_pong",
            "timestamp": int(time.time() * 1000)
        }
        self.retell_server.send_message(client, json.dumps(response))
    
    def handle_retell_update(self, data):
        """Handle update_only messages from Retell"""
        # These are just transcript updates, no response needed
        # You might want to log or process these updates
        transcript = data.get("transcript", [])
        turntaking = data.get("turntaking")
        
        if turntaking:
            print(f"Turn taking: {turntaking}")
            
        # You could forward this to Vocera if needed
        # For now, we'll just log it
        if transcript and len(transcript) > 0:
            last_utterance = transcript[-1]
            print(f"Transcript update: {last_utterance.get('role')} - {last_utterance.get('content')}")
    
    def handle_retell_response_request(self, client, data):
        """Handle response_required or reminder_required messages from Retell"""
        response_id = data.get("response_id")
        self.last_response_id = response_id
        
        # Convert to Vocera's format and send
        transcript = data.get("transcript", [])
        if transcript and len(transcript) > 0:
            last_utterance = transcript[-1]
            
            # Create a message in Vocera's format
            vocera_message = {
                'content': last_utterance.get('content', ''),
                'role': 'user'  # Assuming this is from the user
            }
            
            # Send to Vocera
            self.send_to_vocera(vocera_message)
    
    def handle_vocera_regular_message(self, message):
        """Handle regular messages from Vocera"""
        content = message.get('content', '')
        
        # Check if we have a pending response_id from Retell
        if self.last_response_id:
            # Convert to Retell response format
            response = {
                "response_type": "response",
                "response_id": self.last_response_id,
                "content": content,
                "content_complete": True
            }
            
            # Check if this message should end the call
            if "end call" in content.lower() or "goodbye" in content.lower():
                response["end_call"] = True
                
            self.send_to_retell(response)
        else:
            # No pending response request, send as agent_interrupt
            interrupt = {
                "response_type": "agent_interrupt",
                "interrupt_id": int(time.time() * 1000),  # Use timestamp as ID
                "content": content,
                "content_complete": True,
                "no_interruption_allowed": True  # Prevent interruption
            }
            self.send_to_retell(interrupt)


# Example usage
if __name__ == "__main__":
    # Configuration
    RETELL_PORT = 8765  # Port to listen for Retell connections
    VOCERA_PORT = 8766  # Port to listen for Vocera connections
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create and start adapter
    adapter = RetellVoceraAdapter(
        RETELL_PORT, 
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