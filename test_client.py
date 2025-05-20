#!/usr/bin/env python3
import asyncio
import json
import websockets
import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def connect_and_chat(uri):
    """Connect to a WebSocket server and start a chat session"""
    try:
        async with websockets.connect(uri) as websocket:
            logger.info(f"Connected to {uri}")
            
            # Receive initial greeting
            response = await websocket.recv()
            try:
                parsed = json.loads(response)
                if "content" in parsed:
                    logger.info(f"Server: {parsed['content']}")
                else:
                    logger.info(f"Server: {parsed}")
            except json.JSONDecodeError:
                logger.info(f"Server: {response}")
            
            # Chat loop
            while True:
                # Get user input
                user_message = input("You: ")
                
                if user_message.lower() in ["exit", "quit", "bye"]:
                    logger.info("Exiting chat...")
                    break
                
                # Send message to server
                await websocket.send(json.dumps({"content": user_message}))
                logger.info(f"Sent message: {user_message}")
                
                # Receive response
                response = await websocket.recv()
                try:
                    parsed = json.loads(response)
                    if "content" in parsed:
                        logger.info(f"Server: {parsed['content']}")
                    else:
                        logger.info(f"Server: {parsed}")
                except json.JSONDecodeError:
                    logger.info(f"Server: {response}")
    
    except websockets.exceptions.ConnectionClosed as e:
        logger.error(f"Connection closed: {e}")
    except Exception as e:
        logger.error(f"Error: {e}")

def main():
    parser = argparse.ArgumentParser(description="WebSocket Chat Client")
    parser.add_argument(
        "--server", 
        type=str, 
        default="ws://127.0.0.1:8765",
        help="WebSocket server URI (default: ws://127.0.0.1:8765)"
    )
    args = parser.parse_args()
    
    # Run the client
    asyncio.run(connect_and_chat(args.server))

if __name__ == "__main__":
    main() 