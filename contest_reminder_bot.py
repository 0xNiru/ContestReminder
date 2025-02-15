from telethon import TelegramClient, events, Button
from datetime import datetime, timedelta
import asyncio
import requests
import json
import os
from dotenv import load_dotenv
import sqlite3

# Load environment variables
load_dotenv()

# Telegram API credentials
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Initialize the client
client = TelegramClient('contest_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Contest platforms APIs
CODEFORCES_API = "https://codeforces.com/api/contest.list"
CODECHEF_API = "https://www.codechef.com/api/list/contests/all"
LEETCODE_API = "https://leetcode.com/graphql"
HACKERRANK_API = "https://www.hackerrank.com/rest/contests"

# Database setup
def setup_database():
    conn = sqlite3.connect('contest_bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  platforms TEXT,
                  reminder_hours INTEGER DEFAULT 24,
                  is_subscribed BOOLEAN DEFAULT 1)''')
    conn.commit()
    conn.close()

async def subscribe_user(user_id, platforms=None, reminder_hours=24):
    if platforms is None:
        platforms = ['codeforces', 'codechef', 'leetcode', 'hackerrank']
    
    conn = sqlite3.connect('contest_bot.db')
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO users (user_id, platforms, reminder_hours, is_subscribed)
                 VALUES (?, ?, ?, 1)''', (user_id, ','.join(platforms), reminder_hours))
    conn.commit()
    conn.close()

async def unsubscribe_user(user_id):
    conn = sqlite3.connect('contest_bot.db')
    c = conn.cursor()
    c.execute('UPDATE users SET is_subscribed = 0 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

async def get_codeforces_contests():
    try:
        response = requests.get(CODEFORCES_API)
        data = response.json()
        upcoming_contests = [
            contest for contest in data['result']
            if contest['phase'] == 'BEFORE'
        ]
        return upcoming_contests
    except Exception as e:
        print(f"Error fetching Codeforces contests: {e}")
        return []

async def get_codechef_contests():
    try:
        response = requests.get(CODECHEF_API)
        data = response.json()
        upcoming_contests = data.get('future_contests', [])
        return upcoming_contests
    except Exception as e:
        print(f"Error fetching CodeChef contests: {e}")
        return []

async def get_leetcode_contests():
    try:
        query = """
        {
            allContests {
                title
                startTime
                duration
            }
        }
        """
        response = requests.post(LEETCODE_API, json={'query': query})
        data = response.json()
        current_time = datetime.now().timestamp()
        upcoming_contests = [
            contest for contest in data['data']['allContests']
            if contest['startTime'] > current_time
        ]
        return upcoming_contests
    except Exception as e:
        print(f"Error fetching LeetCode contests: {e}")
        return []

async def get_hackerrank_contests():
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(HACKERRANK_API, params={'offset': 0, 'limit': 10}, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data.get('models', [])
        return []
    except Exception as e:
        print(f"Error fetching HackerRank contests: {e}")
        return []

# Custom keyboard layouts
def get_main_keyboard():
    return [
        [Button.text("🎯 Upcoming Contests", resize=True)],
        [Button.text("⚙️ Settings", resize=True)],
        [Button.text("📊 My Subscriptions", resize=True)]
    ]

def get_settings_keyboard():
    return [
        [
            Button.inline("⏰ Reminder Time", data="set_reminder"),
            Button.inline("🎯 Platforms", data="set_platforms")
        ],
        [
            Button.inline("✅ Subscribe", data="subscribe"),
            Button.inline("❌ Unsubscribe", data="unsubscribe")
        ],
        [Button.inline("🔙 Back to Main Menu", data="main_menu")]
    ]

def get_reminder_keyboard():
    return [
        [
            Button.inline("12 Hours", data="remind_12"),
            Button.inline("24 Hours", data="remind_24"),
            Button.inline("48 Hours", data="remind_48")
        ],
        [Button.inline("🔙 Back to Settings", data="back_settings")]
    ]

def get_platforms_keyboard():
    return [
        [
            Button.inline("Codeforces", data="platform_cf"),
            Button.inline("CodeChef", data="platform_cc")
        ],
        [
            Button.inline("LeetCode", data="platform_lc"),
            Button.inline("HackerRank", data="platform_hr")
        ],
        [Button.inline("🔙 Back to Settings", data="back_settings")]
    ]

def format_contest_message(platform, contests):
    message = f"🏆 *{platform} Contests*\n\n"
    for contest in contests[:3]:
        if platform == "Codeforces":
            start_time = datetime.fromtimestamp(contest['startTimeSeconds'])
            duration = timedelta(seconds=contest['durationSeconds'])
            message += (
                f"📌 *{contest['name']}*\n"
                f"⏰ {start_time.strftime('%Y-%m-%d %H:%M UTC')}\n"
                f"⌛️ Duration: {int(duration.total_seconds()/3600)}h\n\n"
            )
        elif platform == "CodeChef":
            try:
                # Handle different date formats
                try:
                    start_time = datetime.strptime(contest['contest_start_date'], '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    start_time = datetime.strptime(contest['contest_start_date'], '%d %b %Y %H:%M:%S')
                message += (
                    f"📌 *{contest['contest_name']}*\n"
                    f"⏰ {start_time.strftime('%Y-%m-%d %H:%M UTC')}\n"
                    f"⌛️ Duration: {contest['contest_duration']}h\n\n"
                )
            except Exception as e:
                print(f"Error formatting CodeChef contest: {e}")
                continue
        elif platform == "LeetCode":
            start_time = datetime.fromtimestamp(contest['startTime'])
            message += (
                f"📌 *{contest['title']}*\n"
                f"⏰ {start_time.strftime('%Y-%m-%d %H:%M UTC')}\n"
                f"⌛️ Duration: {contest.get('duration', 'N/A')}h\n\n"
            )
        elif platform == "HackerRank":
            try:
                start_time = datetime.fromisoformat(contest['start_time'].replace('Z', '+00:00'))
                message += (
                    f"📌 *{contest['name']}*\n"
                    f"⏰ {start_time.strftime('%Y-%m-%d %H:%M UTC')}\n"
                    f"⌛️ Duration: {contest.get('duration', 'N/A')}h\n\n"
                )
            except Exception as e:
                print(f"Error formatting HackerRank contest: {e}")
                continue
    return message

@client.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    welcome_message = (
        "👋 *Welcome to the Coding Contest Reminder Bot!*\n\n"
        "I'll help you stay updated with upcoming coding contests.\n"
        "Use the buttons below to navigate:"
    )
    await event.respond(welcome_message, buttons=get_main_keyboard(), parse_mode='markdown')

@client.on(events.NewMessage(func=lambda e: e.text == "🎯 Upcoming Contests"))
async def upcoming_contests_handler(event):
    loading_message = await event.respond("🔄 Fetching contests...")
    
    platforms = {
        "Codeforces": await get_codeforces_contests(),
        "CodeChef": await get_codechef_contests(),
        "LeetCode": await get_leetcode_contests(),
        "HackerRank": await get_hackerrank_contests()
    }
    
    message = "*📅 Upcoming Coding Contests*\n\n"
    for platform, contests in platforms.items():
        if contests:
            message += format_contest_message(platform, contests)
            message += "─" * 30 + "\n"
    
    await loading_message.delete()
    await event.respond(message, buttons=get_main_keyboard(), parse_mode='markdown')

@client.on(events.NewMessage(func=lambda e: e.text == "⚙️ Settings"))
async def settings_handler(event):
    message = (
        "*⚙️ Contest Reminder Settings*\n\n"
        "Configure your preferences:\n"
        "• Set reminder timing\n"
        "• Choose contest platforms\n"
        "• Manage subscription"
    )
    await event.respond(message, buttons=get_settings_keyboard(), parse_mode='markdown')

@client.on(events.CallbackQuery(pattern='set_reminder'))
async def set_reminder_callback(event):
    message = (
        "*⏰ Choose Reminder Time*\n\n"
        "How many hours before the contest would you like to be reminded?"
    )
    await event.edit(message, buttons=get_reminder_keyboard(), parse_mode='markdown')

@client.on(events.CallbackQuery(pattern='set_platforms'))
async def set_platforms_callback(event):
    conn = sqlite3.connect('contest_bot.db')
    c = conn.cursor()
    c.execute('SELECT platforms FROM users WHERE user_id = ?', (event.sender_id,))
    result = c.fetchone()
    
    current_platforms = set(result[0].split(',')) if result and result[0] else set()
    
    message = (
        "*🎯 Platform Selection*\n\n"
        "Current platforms:\n"
        f"{'• ' + '\n• '.join(sorted(current_platforms)) if current_platforms else 'No platforms selected'}\n\n"
        "Click on a platform to toggle selection:"
    )
    await event.edit(message, buttons=get_platforms_keyboard(), parse_mode='markdown')

@client.on(events.CallbackQuery(pattern='subscribe'))
async def subscribe_callback(event):
    await subscribe_user(event.sender_id)
    await event.answer("✅ Successfully subscribed to contest reminders!")
    message = (
        "*✅ Subscription Status*\n\n"
        "You are now subscribed to contest reminders!\n"
        "Use the buttons below to customize your preferences."
    )
    await event.edit(message, buttons=get_settings_keyboard(), parse_mode='markdown')

@client.on(events.CallbackQuery(pattern='unsubscribe'))
async def unsubscribe_callback(event):
    await unsubscribe_user(event.sender_id)
    await event.answer("❌ Successfully unsubscribed from contest reminders!")
    message = (
        "*❌ Subscription Status*\n\n"
        "You are now unsubscribed from contest reminders.\n"
        "You can resubscribe at any time using the Subscribe button."
    )
    await event.edit(message, buttons=get_settings_keyboard(), parse_mode='markdown')

@client.on(events.CallbackQuery(pattern='back_settings'))
async def back_settings_callback(event):
    message = (
        "*⚙️ Contest Reminder Settings*\n\n"
        "Configure your preferences:\n"
        "• Set reminder timing\n"
        "• Choose contest platforms\n"
        "• Manage subscription"
    )
    await event.edit(message, buttons=get_settings_keyboard(), parse_mode='markdown')

@client.on(events.CallbackQuery(pattern=r'remind_(\d+)'))
async def reminder_callback(event):
    hours = int(event.pattern_match.group(1))
    await subscribe_user(event.sender_id, reminder_hours=hours)
    await event.answer(f"✅ Reminders set to {hours} hours!")
    message = (
        f"*⏰ Reminder Settings Updated*\n\n"
        f"You will be notified {hours} hours before contests start."
    )
    await event.edit(message, buttons=get_settings_keyboard(), parse_mode='markdown')

@client.on(events.CallbackQuery(pattern=r'platform_(.+)'))
async def platform_callback(event):
    # Convert bytes to string if needed
    platform = event.data.decode() if isinstance(event.data, bytes) else event.data
    platform = platform.replace('platform_', '')  # Remove the 'platform_' prefix

    conn = sqlite3.connect('contest_bot.db')
    c = conn.cursor()
    c.execute('SELECT platforms FROM users WHERE user_id = ?', (event.sender_id,))
    result = c.fetchone()
    
    current_platforms = set(result[0].split(',')) if result else set()
    platform_map = {
        'cf': 'codeforces',
        'cc': 'codechef',
        'lc': 'leetcode',
        'hr': 'hackerrank'
    }
    
    platform_name = platform_map.get(platform)
    if not platform_name:
        await event.answer("Invalid platform selection!")
        return
    
    if platform_name in current_platforms:
        current_platforms.remove(platform_name)
        status = "removed from"
    else:
        current_platforms.add(platform_name)
        status = "added to"
    
    await subscribe_user(event.sender_id, platforms=list(current_platforms))
    await event.answer(f"✅ {platform_name.title()} {status} your platforms!")
    
    # Show updated platform selection
    message = (
        "*🎯 Platform Selection*\n\n"
        "Your current platforms:\n"
        f"{'• ' + '\n• '.join(sorted(current_platforms)) if current_platforms else 'No platforms selected'}"
    )
    await event.edit(message, buttons=get_platforms_keyboard(), parse_mode='markdown')

async def check_and_send_reminders():
    while True:
        try:
            conn = sqlite3.connect('contest_bot.db')
            c = conn.cursor()
            c.execute('SELECT user_id, platforms, reminder_hours FROM users WHERE is_subscribed = 1')
            subscribed_users = c.fetchall()
            conn.close()

            all_contests = {
                'codeforces': await get_codeforces_contests(),
                'codechef': await get_codechef_contests(),
                'leetcode': await get_leetcode_contests(),
                'hackerrank': await get_hackerrank_contests()
            }

            for user_id, platforms, reminder_hours in subscribed_users:
                user_platforms = platforms.split(',')
                reminder_time = datetime.now() + timedelta(hours=reminder_hours)
                
                for platform, contests in all_contests.items():
                    if platform not in user_platforms:
                        continue
                    
                    for contest in contests:
                        start_time = None
                        if platform == 'codeforces':
                            start_time = datetime.fromtimestamp(contest['startTimeSeconds'])
                        elif platform == 'codechef':
                            try:
                                # Handle different CodeChef date formats
                                date_str = contest['contest_start_date']
                                try:
                                    start_time = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                                except ValueError:
                                    try:
                                        start_time = datetime.strptime(date_str, '%d %b %Y %H:%M:%S')
                                    except ValueError:
                                        start_time = datetime.strptime(date_str.strip(), '%d %b %Y  %H:%M:%S')
                            except Exception as e:
                                print(f"Error parsing CodeChef date: {e}")
                                continue
                        elif platform == 'leetcode':
                            start_time = datetime.fromtimestamp(contest['startTime'])
                        elif platform == 'hackerrank':
                            start_time = datetime.fromisoformat(contest['start_time'].replace('Z', '+00:00'))
                        
                        if start_time and abs((start_time - reminder_time).total_seconds()) < 3600:
                            message = f"🔔 Reminder: {contest.get('name', contest.get('title', 'Upcoming contest'))}\n"
                            message += f"Platform: {platform.title()}\n"
                            message += f"Starts at: {start_time.strftime('%Y-%m-%d %H:%M UTC')}"
                            
                            try:
                                await client.send_message(user_id, message)
                            except Exception as e:
                                print(f"Error sending reminder to user {user_id}: {e}")
            
            await asyncio.sleep(3600)  # Check every hour
        except Exception as e:
            print(f"Error in reminder system: {e}")
            await asyncio.sleep(3600)

def main():
    print("Bot started...")
    setup_database()
    
    # Start the reminder system
    client.loop.create_task(check_and_send_reminders())
    
    # Run the bot
    client.run_until_disconnected()

if __name__ == '__main__':
    main() 