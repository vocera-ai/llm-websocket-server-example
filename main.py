import asyncio
import websockets
import openai

# Configure your OpenAI API key
api_key = 'YOUR-OPENAI-API-KEY'

# Store chat histories for different connections
chat_histories = {}

# Define system prompt
SYSTEM_PROMPT = {
    "role": "system",
    "content": """Your system prompt"""
}

async def chat_response(message, session_id):
    try:
        # Get or create chat history for this session
        if session_id not in chat_histories:
            chat_histories[session_id] = [SYSTEM_PROMPT]
        
        # Add user message to history
        chat_histories[session_id].append({
            "role": "user",
            "content": message
        })
        # Get response from OpenAI with full context
        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-2024-08-06",
            messages=chat_histories[session_id],
            temperature=0.0,
            modalities=["text"]
        )
        
        # Add assistant's response to history
        assistant_response = response.choices[0].message.content
        chat_histories[session_id].append({
            "role": "assistant",
            "content": assistant_response
        })
        
        # Limit context window to last 10 messages (adjust as needed)
        if len(chat_histories[session_id]) > 12:  # system prompt + 10 exchanges
            chat_histories[session_id] = [
                chat_histories[session_id][0]  # Keep system prompt
            ] + chat_histories[session_id][-10:]  # Keep last 10 messages
        
        return assistant_response
    except Exception as e:
        return f"Error: {str(e)}"

async def handle_websocket(websocket, path):
    # Generate unique session ID for this connection
    session_id = id(websocket)
    
    try:
        await websocket.send('Hi! How can I help you today?')
        async for message in websocket:
            print(f"Received message: {message}")
            
            # Get response from OpenAI
            response = await chat_response(message, session_id)
            
            # Send response back to client
            await websocket.send(response)
            print(f"Sent response: {response}")

    except websockets.exceptions.ConnectionClosed:
        # Clean up chat history when connection closes
        if session_id in chat_histories:
            del chat_histories[session_id]
    except Exception as e:
        print(f"Error: {str(e)}")

async def main():
    server = await websockets.serve(
        handle_websocket,
        "localhost",
        8765
    )
    print("WebSocket server started on ws://localhost:8765")
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main()) 
