import asyncio
import os
import re
import json
import logging
from datetime import datetime
from pyrogram import Client, filters, idle

# Environment variables
API_ID = int(os.environ['API_ID'])
API_HASH = os.environ['API_HASH']
TARGET_GROUP = os.environ['TARGET_GROUP']

SOURCE_CHANNELS = [
    int(os.environ['CHANNEL_1']),
    int(os.environ['CHANNEL_2'])
]

WAIT_FOR_REPLY = int(os.environ.get('WAIT_FOR_REPLY', '15'))
NEXT_POST_DELAY = int(os.environ.get('NEXT_POST_DELAY', '10'))

PROCESSED_FILE = 'processed_messages.json'
posted_count = 0
pinned_count = 0

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class FileStorage:
    @staticmethod
    def load_json(filename):
        try:
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except:
            return {}
    
    @staticmethod
    def save_json(filename, data):
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except:
            return False

def init_storage():
    if not os.path.exists(PROCESSED_FILE):
        FileStorage.save_json(PROCESSED_FILE, {})

def extract_cc_details(text):
    if not text:
        return None
    cc_pattern = r'\b(\d{16}\|\d{2}\|\d{2}\|\d{3})\b'
    match = re.search(cc_pattern, text)
    return match.group(1) if match else None

def is_message_processed(message_signature):
    processed = FileStorage.load_json(PROCESSED_FILE)
    return message_signature in processed

def mark_message_processed(message_signature, cc_details, status):
    processed = FileStorage.load_json(PROCESSED_FILE)
    processed[message_signature] = {
        'cc_details': cc_details,
        'status': status,
        'timestamp': datetime.now().isoformat(),
        'pinned': status == 'approved'
    }
    FileStorage.save_json(PROCESSED_FILE, processed)

def print_stats():
    print(f"📊 Posted: {posted_count} | Pinned: {pinned_count}")

async def pin_approved_message(client, message_id):
    global pinned_count
    try:
        await client.pin_chat_message(TARGET_GROUP, message_id)
        pinned_count += 1
        print("✅ Message pinned")
        print_stats()
        return True
    except Exception as e:
        print(f"❌ Pin error: {e}")
        return False

async def cleanup_group_messages(client):
    try:
        deleted_count = 0
        print("🔄 Cleaning up group messages...")
        
        async for message in client.get_chat_history(TARGET_GROUP, limit=200):
            if not message.pinned:
                try:
                    await message.delete()
                    deleted_count += 1
                    await asyncio.sleep(0.3)
                except Exception:
                    continue
        
        print(f"✅ Cleanup completed. Deleted {deleted_count} messages")
    except Exception as e:
        print(f"❌ Cleanup error: {e}")

async def send_and_wait_for_reply(client, cc_details):
    global posted_count
    
    try:
        print(f"🔄 Sending CC: {cc_details}")
        
        sent_message = await client.send_message(TARGET_GROUP, f".chk {cc_details}")
        posted_count += 1
        print_stats()
        
        await asyncio.sleep(WAIT_FOR_REPLY)
        
        async for message in client.get_chat_history(TARGET_GROUP, limit=50):
            if message.reply_to_message_id == sent_message.id:
                message_text = message.text or ""
                print(f"🤖 Bot reply: {message_text[:100]}...")
                
                if any(approved in message_text for approved in ["Approved ✅", "Status: Approved", "APPROVED", "Approved", "Card added", "Response: Card added", "Status: Approved ✅", "✅ Approved", "APPROVED ✅"]):
                    print("🎯 APPROVED detected!")
                    await pin_approved_message(client, message.id)
                    return "approved"
                
                elif any(declined in message_text for declined in ["Declined", "DECLINED", "declined", "❌"]):
                    print("❌ DECLINED detected")
                    return "declined"
        
        return "no_reply"
        
    except Exception as e:
        print(f"❌ Send error: {e}")
        return "error"

async def process_source_channel(client, channel_id):
    try:
        print(f"🔄 Processing channel: {channel_id}")
        message_count = 0
        
        async for message in client.get_chat_history(channel_id, limit=500):
            text = message.text or message.caption
            if not text:
                continue
            
            message_signature = f"{channel_id}_{message.id}"
            cc_details = extract_cc_details(text)
            
            if cc_details and not is_message_processed(message_signature):
                print(f"🎯 Found CC: {cc_details}")
                result = await send_and_wait_for_reply(client, cc_details)
                mark_message_processed(message_signature, cc_details, result)
                await asyncio.sleep(NEXT_POST_DELAY)
                message_count += 1
        
        print(f"✅ Channel {channel_id} processed. Found {message_count} messages")
        return True
        
    except Exception as e:
        print(f"❌ Channel error: {e}")
        return False

async def start_monitoring():
    """Start monitoring with the provided session file"""
    try:
        session_file = "user_5464535422.session"  # Tumhara received session file
        
        if not os.path.exists(session_file):
            print(f"❌ Session file {session_file} not found!")
            return
        
        print("🚀 Starting monitoring with provided session file...")
        
        # Create user client from session file
        user_client = Client(session_file, api_id=API_ID, api_hash=API_HASH)
        await user_client.start()
        
        me = await user_client.get_me()
        print(f"🔍 Monitoring started for: {me.first_name} (@{me.username})")
        
        init_storage()
        
        print("🎯 Target Group:", TARGET_GROUP)
        print("📡 Source Channels:", SOURCE_CHANNELS)
        print("📊 Posted: 0 | Pinned: 0")
        
        # Cleanup
        await cleanup_group_messages(user_client)
        
        # Process channels
        for channel_id in SOURCE_CHANNELS:
            await process_source_channel(user_client, channel_id)
        
        print(f"\n✅ Ready | Posted: {posted_count} | Pinned: {pinned_count}")
        print("🔍 Monitoring for new messages...")
        
        # Message handler for new messages
        @user_client.on_message(filters.chat(SOURCE_CHANNELS))
        async def handle_message(client, message):
            text = message.text or message.caption
            if not text:
                return
            
            signature = f"{message.chat.id}_{message.id}"
            if is_message_processed(signature):
                return
            
            cc = extract_cc_details(text)
            if cc:
                print(f"🆕 New CC: {cc}")
                result = await send_and_wait_for_reply(client, cc)
                mark_message_processed(signature, cc, result)
                await asyncio.sleep(NEXT_POST_DELAY)
        
        # Keep monitoring running
        await idle()
        
    except Exception as e:
        print(f"❌ Monitoring error: {e}")

async def main():
    try:
        await start_monitoring()
    except Exception as e:
        logger.error(f"Main function error: {e}")

if __name__ == "__main__":
    print("🚀 Starting CC Monitor with provided session file...")
    asyncio.run(main())
