# Import required libraries
import praw  # Reddit API wrapper
import openai  # OpenAI API for language processing
import time  # Used to add delays (rate limiting, retries)
import os  # For checking file existence and file paths
from openai import OpenAIError  # Error handling for OpenAI API

# Reddit API credentials 
REDDIT_CLIENT_ID = "CLientID"
REDDIT_CLIENT_SECRET = "CLientSecret"
REDDIT_USERNAME = "Username"
REDDIT_PASSWORD = "Password"
REDDIT_USER_AGENT = "UserAgent"

# OpenAI API Key 
OPENAI_API_KEY = "APIKey"

# File path to keep track of posts already replied to
SCANNED_POSTS_FILE = "RedditBots/FPVNoobBot/scanned_posts.txt"

# Initialise Reddit and OpenAI API clients 
reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    username=REDDIT_USERNAME,
    password=REDDIT_PASSWORD,
    user_agent=REDDIT_USER_AGENT
)
openai.api_key = OPENAI_API_KEY

# Load a list of post IDs the bot has already replied to 
def load_scanned_posts():
    if not os.path.exists(SCANNED_POSTS_FILE):
        return set()
    with open(SCANNED_POSTS_FILE, "r") as f:
        return set(line.strip() for line in f.readlines())

# Save a post ID after replying so we don’t reply again 
def save_replied_post(post_id):
    with open(SCANNED_POSTS_FILE, "a") as f:
        f.write(post_id + "\n")

# Basic filtering to reduce API usage 
def post_filtering(title, body):
    text = f"{title} {body}".lower()
    # Looks for common keywords that might suggest a takeoff or motor spin issue
    keywords = [
        "motor", "motors", "spin", "spinning", "throttle", "arming", "arm", "props off", "bench test",
        "prop", "props", "propeller", "ramps up", "motor idle", "motor output", "motor increase",
        "flip", "flips", "flipping", "flipped", "flip out", "flips out", "roll", "yaw spin", 
        "jump", "tumbles", "unstable on takeoff", "disarms on takeoff", "crash", "flips on arming",
        "disarm throttle", "flip takeoff", "won't takeoff"
    ]
    return any(keyword in text for keyword in keywords)

# Define chatgpt settings
def ask_openai(prompt):
    while True:
        try:
            response = openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are an FPV drone expert."},
                    {"role": "user", "content": prompt}
                ]
            )
            return response.choices[0].message.content.strip().lower()
            
        # API Error Handling
        except OpenAIError as e:
            # If API rate limit is hit, wait and retry
            wait_time = 60
            if "Please try again in" in str(e):
                try:
                    wait_time = int(float(str(e).split("in ")[-1].split("s")[0])) + 5
                except ValueError:
                    pass
            print(f"Rate limit reached. Waiting {wait_time} seconds...")
            time.sleep(wait_time)
            
        # Other errors
        except Exception as e:
            print(f"OpenAI API error: {e}")
            return "no"

# Ask OpenAI if each post is about flip-out on takeoff
def is_flip_post(title, body):
    # Skip posts with a lack of context
    if len(title.split()) + len(body.split()) < 4:
        print("Skipping post: Not enough context")
        return False
    
    # Prompt
    prompt = f"""A user posted this in r/fpv:
    Title: "{title}"
    Body: "{body}"

    Does this post describe a drone (also called quad, kwad, quadcopter, tinywhoop, cinewhoop, whoop) experiencing a flip-out on takeoff?  
    This includes issues where the drone disarms, flips, jumps, or spins out after arming when throttle is raised.  
    **Answer "No" to posts about intentional flips, freestyle tricks, or pilots describing how many flips they can do.**  
    **Answer "No" to posts that mention or imply the drone flying normally before crashing/flipping out**
    Only answer "Yes" if you are 100% certain that the post is describing a drone flipping, disarming, or spinning out on takeoff or throttle up — not while flying. If you're even slightly unsure, answer "No".
    Always answer with only "Yes" or "No", no extra text."""
    return ask_openai(prompt) == "yes"

# Ask OpenAI if the post is about motor spin when props are off
def is_motor_spin_post(title, body):
    # Skip posts with a lack of context
    if len(title.split()) + len(body.split()) < 4:
        print("Skipping post: Not enough context")
        return False
        
    # Prompt
    prompt = f"""A user posted this in r/fpv:
    Title: "{title}"
    Body: "{body}"

    Is this post asking why motors start to spin up or increase throttle *only* when props are off, for example, when testing on the bench or after arming without props?
    This is a common issue caused by the PID controller not getting feedback from the props, causing it to increase motor output thinking the drone isn't moving.
    Only answer "Yes" if the post is *clearly* about motors speeding up uncontrollably when there are NO props on. Answer "No" if props are on, if it's about idle throttle spin, or if you are not 100% sure.
    Answer only "Yes" or "No"."""
    return ask_openai(prompt) == "yes"

# Main function: scans new posts in r/fpv
def scan_fpv_subreddit():
    subreddit = reddit.subreddit("fpv")
    scanned_posts = load_scanned_posts()
    
    # Scans the 5 latest post, skipping any already scanned
    for submission in subreddit.new(limit=5):
        if submission.id in scanned_posts:
            continue 
        # Defining the title and body of the post
        title = submission.title
        body = submission.selftext
        
        #Skip posts the dont meet the filtering criteria
        if not post_filtering(title, body):
            print(f"Skipping irrelevant post: {title}")
            continue

        # If the post is about flip-out on takeoff
        if is_flip_post(title, body):
            print(f"Flip issue found: {title}")
            response = (
                "It seems like you're experiencing a drone flip on takeoff.\n\n"
                "[Here's](https://www.youtube.com/watch?v=7sSYwzVCJdA) a video that should help troubleshoot the issue\n\n" # JBardwell's video
                "---\n"
                "^I ^am ^a ^bot, ^this ^action ^was ^done ^automatically." 
            )
        # If the post is about motors accelerating with no props
        elif is_motor_spin_post(title, body):
            print(f"Motor spin post found: {title}")
            response = (
                "It seems like your quads motors are throttling up on their own when arming without props. This is totally normal.\n\n"
                "The flight controller expects the drone to react to motor output. Without props, there’s no movement, so the flight controller keeps increasing throttle trying to 'correct' what it thinks is an error.\n\n"
                "This doesn’t happen in the air or with props on, it’s just feedback loss.\n\n"
                "---\n"
                "^I ^am ^a ^bot, ^this ^action ^was ^done ^automatically. ^This ^feature ^is ^still ^being ^tested, ^if ^this ^reply ^seems ^wrong, ^please ^report ^it ^by ^replying ^to ^the ^bot."
            )
        else:
            continue  # Skip if neither category matched

        # Reply to post
        try:
            submission.reply(response)
            print("Replied to the post!")
            save_replied_post(submission.id) # Save the post ID to prevent repeat scanning and reduce OpenAI API costs
        # Error handling
        except Exception as e:
            print(f"Error replying to post: {e}")

        # Pause briefly to avoid spam or rate limits
        time.sleep(10)

# Main loop: run the bot every 10 minutes
if __name__ == "__main__":
    while True:
        scan_fpv_subreddit()
        print("Sleeping for 10 minutes...")
        time.sleep(600)

