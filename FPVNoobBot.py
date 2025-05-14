# Import required libraries
import praw
import openai
import time
import os
from openai import OpenAIError
import smtplib
from email.mime.text import MIMEText

# Email credentials
email_address = "____"
email_password = "____"

# Email recipient
recipient = "____"

# Reddit API credentials
reddit_client_id = "____"
reddit_client_secret = "____"
reddit_username = "____"
reddit_password = "____"
reddit_user_agent = "____"

# OpenAI API key
openai_api_key = "____"

# File path to track scanned posts
scanned_posts_file = "____"

# Initialise Reddit and OpenAI
reddit = praw.Reddit(
    client_id=reddit_client_id,
    client_secret=reddit_client_secret,
    username=reddit_username,
    password=reddit_password,
    user_agent=reddit_user_agent
)
openai.api_key = openai_api_key

def load_scanned_posts():
    if not os.path.exists(scanned_posts_file):
        return set()
    with open(scanned_posts_file, "r") as f:
        return set(line.strip() for line in f.readlines())

def save_scanned_post(post_id):
    os.makedirs(os.path.dirname(scanned_posts_file), exist_ok=True)
    with open(scanned_posts_file, "a") as f:
        f.write(post_id + "\n")

def post_filtering(title, body):
    text = f"{title} {body}".lower()
    keywords = [
        "motor", "motors", "spin", "spinning", "throttle", "arming", "arm", "props off", "bench test",
        "prop", "props", "propeller", "ramps up", "motor idle", "motor output", "motor increase",
        "flip", "flips", "flipping", "flipped", "flip out", "flips out", "roll", "yaw spin", 
        "jump", "tumbles", "unstable on takeoff", "disarms on takeoff", "crash", "flips on arming",
        "disarms", "uncontrollable", "flip takeoff", "won't takeoff"
    ]
    return any(keyword in text for keyword in keywords)

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
        except OpenAIError as e:
            wait_time = 60
            if "Please try again in" in str(e):
                try:
                    wait_time = int(float(str(e).split("in ")[-1].split("s")[0])) + 5
                except ValueError:
                    pass
            print(f"Rate limit reached. Waiting {wait_time} seconds...")
            time.sleep(wait_time)
        except Exception as e:
            print(f"OpenAI API error: {e}")
            return "no"

def send_email(email_address, email_password, email_subject, email_body, recipient):
    msg = MIMEText(email_body)
    msg['Subject'] = email_subject
    msg['From'] = email_address
    msg['To'] = recipient

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(email_address, email_password)
            smtp.send_message(msg)
        print("Email sent successfully.")
    except Exception as e:
        print(f"Failed to send email: {e}")

def is_flip_post(title, body):
    if len(title.split()) + len(body.split()) < 4:
        print("Skipping post: Not enough context")
        return False
    
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

def is_motor_spin_post(title, body):
    if len(title.split()) + len(body.split()) < 4:
        print("Skipping post: Not enough context")
        return False
    
    prompt = f"""A user posted this in r/fpv:
    Title: "{title}"
    Body: "{body}"

    Is this post asking why motors start to spin up or increase throttle *only* when props are off, for example, when testing on the bench or after arming without props?
    This is a common issue caused by the PID controller not getting feedback from the props, causing it to increase motor output thinking the drone isn't moving.
    Only answer "Yes" if the post is *clearly* about motors speeding up uncontrollably when there are NO props on. Answer "No" if props are on, if it's about idle throttle spin, or if you are not 100% sure.
    Answer only "Yes" or "No"."""
    return ask_openai(prompt) == "yes"

def scan_fpv_subreddit():
    subreddit = reddit.subreddit("fpv")
    scanned_posts = load_scanned_posts()

    for submission in subreddit.new(limit=5):
        if submission.id in scanned_posts:
            continue

        title = submission.title
        body = submission.selftext

        if not post_filtering(title, body):
            print(f"Skipping post: {title}")
            save_scanned_post(submission.id)
            continue

        try:
            post_url = f"https://www.reddit.com{submission.permalink}"

            if is_flip_post(title, body):
                print(f"Flip issue found: {title}")
                response = (
                    "It seems like you're experiencing a drone flip on takeoff.\n\n"
                    "[Here's](https://www.youtube.com/watch?v=7sSYwzVCJdA) a video that should help troubleshoot the issue.\n\n"
                    "---\n"
                    "^I ^am ^a ^bot, ^this ^action ^was ^done ^automatically."
                )
                submission.reply(response)
                email_subject = "Bot Reply - Flip Dectected"
                email_body = f"Bot replied to a Reddit post:\n\nTitle: {title}\n\nLink: {post_url}"
                send_email(email_address, email_password, email_subject, email_body, recipient)

            elif is_motor_spin_post(title, body):
                print(f"Motor spin post found: {title}")
                response = (
                    "It seems like your quad's motors are throttling up on their own when arming without props. This is totally normal.\n\n"
                    "The flight controller expects the drone to react to motor output. Without props, there’s no movement, so the flight controller keeps increasing throttle trying to 'correct' what it thinks is an error.\n\n"
                    "This doesn’t happen in the air or with props on—it's just feedback loss.\n\n"
                    "---\n"
                    "^I ^am ^a ^bot, ^this ^action ^was ^done ^automatically. ^This ^feature ^is ^still ^being ^tested, ^if ^this ^reply ^seems ^wrong, ^please ^report ^it ^by ^replying ^to ^the ^bot."
                )
                submission.reply(response)
                email_subject = "Bot Reply - Motor Spin Issue"
                email_body = f"Bot replied to a Reddit post:\n\nTitle: {title}\n\nLink: {post_url}"
                send_email(email_address, email_password, email_subject, email_body, recipient)
            else:
                print (f"Scanned Post: {title}")

        except Exception as e:
            print(f"Error replying to post or sending email: {e}")

        save_scanned_post(submission.id)
        time.sleep(10)

if __name__ == "__main__":
    while True:
        scan_fpv_subreddit()
        print("Sleeping for 1 minute...")
        time.sleep(60)
