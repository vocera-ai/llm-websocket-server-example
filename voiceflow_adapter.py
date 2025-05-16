import asyncio
import json
import logging
import uuid
import websockets
import requests
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Store sessions for different connections
voiceflow_sessions = {}

# Check API key
api_key = os.getenv("VOICEFLOW_API_KEY")
if not api_key:
    logger.error("VOICEFLOW_API_KEY environment variable is not set")
    exit(1)

# Version ID to use - use "production" for the production version
version_id = os.getenv("VOICEFLOW_VERSION_ID", "production")

async def process_traces(websocket, traces, session_id):
    """Process traces received from Voiceflow and send to client"""
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
            await websocket.send(json.dumps({
                "type": "end",
                "content": "Conversation ended"
            }))
        
        # Ignore all other trace types (visual, choice, etc.)
        # as we only support text-based interaction
    
    # Send combined text responses
    if responses:
        combined_response = " ".join(responses)
        await websocket.send(json.dumps({
            "content": combined_response
        }))
        return combined_response
    return None

async def start_conversation(websocket, session_id):
    """Start a conversation with Voiceflow"""
    user_id = voiceflow_sessions[session_id]['user_id']
    
    # Initialize Voiceflow session
    headers = {
        "Authorization": api_key,
        "versionID": version_id,
        "Content-Type": "application/json"
    }
    
    url = f"https://general-runtime.voiceflow.com/state/user/{user_id}/interact"
    
    data = {
        "action": {
            "type": "launch"
        },
    }
    
    try:
        logger.info(f"Starting conversation with Voiceflow. URL: {url}")
        response = requests.post(url, headers=headers, json=data)
        
        # Log request and response details for debugging
        logger.info(f"Request headers: {headers}")
        logger.info(f"Request data: {data}")
        
        if response.status_code != 200:
            logger.error(f"Error response from Voiceflow: {response.status_code} - {response.text}")
            
        response.raise_for_status()
        
        traces = response.json()
        
        # Process and send traces to client
        result = await process_traces(websocket, traces, session_id)
        if not result:
            # Send initial greeting if no response from Voiceflow
            greeting = "Hi! How can I help you today?"
            await websocket.send(json.dumps({"content": greeting}))
            return greeting
        return result
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error starting conversation: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status: {e.response.status_code}")
            logger.error(f"Response body: {e.response.text}")
        
        greeting = "Hi! How can I help you today?"
        await websocket.send(json.dumps({"content": greeting}))
        return greeting

async def voiceflow_response(message, session_id):
    """Send a user message to Voiceflow and get response"""
    try:
        websocket = voiceflow_sessions[session_id]['websocket']
        user_id = voiceflow_sessions[session_id]['user_id']
        
        headers = {
            "Authorization": api_key,
            "versionID": version_id,
            "Content-Type": "application/json"
        }
        
        url = f"https://general-runtime.voiceflow.com/state/user/{user_id}/interact"
        
        data = {
            "action": {
                "type": "text",
                "payload": message
            },
        }
        
        
        logger.info(f"Sending message to Voiceflow: {message}")
        response = requests.post(url, headers=headers, json=data)
        
        # Log response status for debugging
        if response.status_code != 200:
            logger.error(f"Error response from Voiceflow: {response.status_code} - {response.text}")
            
        response.raise_for_status()
        
        traces = response.json()
        # logger.info(f"Traces: {traces}")
        
        # Process traces
        assistant_response = await process_traces(websocket, traces, session_id)

        print(f"Assistant response: {assistant_response=}")
        
        
        return json.dumps({"content": assistant_response or ""})
    
    except requests.exceptions.RequestException as e:
        error_msg = f"Error: {str(e)}"
        logger.error(error_msg)
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status: {e.response.status_code}")
            logger.error(f"Response body: {e.response.text}")
        return json.dumps({"content": "Sorry, I couldn't process your message. Please try again later."})
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        logger.error(error_msg)
        return json.dumps({"content": "Sorry, I couldn't process your message. Please try again later."})

async def handle_websocket(websocket, path):
    """Handle WebSocket connection and messages"""
    # Generate unique session ID for this connection
    session_id = id(websocket)
    user_id = f"user-{uuid.uuid4()}"
    
    logger.info(f"Session ID: {session_id=}")
    
    # Initialize session data
    voiceflow_sessions[session_id] = {
        'user_id': user_id,
        'websocket': websocket,
    }
    
    try:
        # Send initial greeting
        await start_conversation(websocket, session_id)
        
        # Handle incoming messages
        async for message in websocket:
            try:
                message_data = json.loads(message)
                content = message_data.get('content', '').strip()
                
                if not content:
                    continue
                
                logger.info(f"Received message: {content}")
                
                # Get response from Voiceflow
                response = await voiceflow_response(content, session_id)
                
                # Send response back to client (handled in voiceflow_response)
                logger.info(f"Sent response: {response}")
                
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON received from client: {message}")
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
    
    except websockets.exceptions.ConnectionClosed:
        logger.info(f"WebSocket connection closed: {session_id}")
        # Clean up session when connection closes
        if session_id in voiceflow_sessions:
            del voiceflow_sessions[session_id]
    except Exception as e:
        logger.error(f"Error: {str(e)}")

async def main():
    """Start the WebSocket server"""
    
    server = await websockets.serve(
        handle_websocket,
        "0.0.0.0",
        8765
    )
    
    logger.info(f"WebSocket server started on ws://0.0.0.0:8765")
    await server.wait_closed()

if __name__ == "__main__":
    # Run the server
    asyncio.run(main()) 