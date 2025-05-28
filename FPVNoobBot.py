# Import required libraries
import praw
import openai
import time
import os
from openai import OpenAIError
import smtplib
from email.mime.text import MIMEText
from colorama import init, Fore
import threading

init(autoreset=True)

# Email credentials
email_address = "____"
email_password = "____"

# Email recipient
recipient = "____"

# Reddit API credentials
reddit_client_id = "____"
reddit_client_secret = "____-A"
reddit_username = "____"
reddit_password = "____"
reddit_user_agent = "____"

# OpenAI API key
openai_api_key = "____"

# File path to track scanned posts
scanned_posts_file = "RedditBots/FPVNoobBot/scanned_posts.txt"
scanned_comments_file = "RedditBots/FPVNoobBot/scanned_comments.txt"

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

def load_scanned_comments():
    if not os.path.exists(scanned_comments_file):
        return set()
    with open(scanned_comments_file, "r") as f:
        return set(line.strip() for line in f.readlines())

def save_scanned_comment(comment_id):
    os.makedirs(os.path.dirname(scanned_comments_file), exist_ok=True)
    with open(scanned_comments_file, "a") as f:
        f.write(comment_id + "\n")
        # print(Fore.YELLOW + f"[LOG] Saved comment ID: {comment_id}")

        
def post_filtering(title, body):
    text = f"{title} {body}".lower()
    keywords = [
        "motor", "motors", "spin", "spinning", "throttle", "arming", "arm", "props off", "bench test",
        "prop", "props", "propeller", "ramps up", "motor idle", "motor output", "motor increase",
        "flip", "flips", "flipping", "flipped", "flip out", "flips out", "roll", "yaw spin", 
        "jump", "tumbles", "unstable on takeoff", "disarms on takeoff", "crash", "flips on arming",
        "disarm", "uncontrollable", "flip takeoff", "won't takeoff"
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
            print(Fore.RED + f"[ERROR] Rate limit reached. Waiting {wait_time} seconds...")
            time.sleep(wait_time)
        except Exception as e:
            print(Fore.RED + f"[ERROR] OpenAI API error: {e}")
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
    except Exception as e:
        print(Fore.RED + f"[ERROR] Failed to send email: {e}")

def is_flip_post(title, body):
    if len(title.split()) + len(body.split()) < 4:
        print(Fore.CYAN + f"[SKIPPED] Not enough context: {post_url}")
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
        print(Fore.CYAN + f"[SKIPPED] Not enough context: {post_url}")
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
    max_retries = 15
    for submission in subreddit.new(limit=5):
        if submission.id in scanned_posts:
            continue

        title = submission.title
        body = submission.selftext
        post_url = f"https://www.reddit.com{submission.permalink}"

        if not post_filtering(title, body):
            print(Fore.BLUE + f"[SKIPPED] Irrelevant: {post_url}")
            save_scanned_post(submission.id)
            continue

        retries = 0
        while retries < max_retries:
            try:
                if is_flip_post(title, body):
                    print(Fore.GREEN + f"[REPLIED] Flip issue detected: {post_url}")
                    response = (
                        "It seems like you're experiencing a drone flip/yaw spin on takeoff.\n\n"
                        "[This](https://www.youtube.com/watch?v=7sSYwzVCJdA) video should help troubleshoot the issue.\n\n"
                        "---\n"
                        "^I ^am ^a ^bot, ^this ^action ^was ^done ^automatically."
                    )
                    submission.reply(response)
                    email_subject = "Bot Reply - Flip Detected"
                    email_body = f"Title: {title}\n\nLink: {post_url}"
                    send_email(email_address, email_password, email_subject, email_body, recipient)

                elif is_motor_spin_post(title, body):
                    print(Fore.GREEN + f"[REPLIED] Motor spin issue detected: {post_url}")
                    response = (
                        "It seems like your quad's motors are throttling up on their own when arming without props. This is totally normal.\n\n"
                        "The flight controller expects the drone to react to motor output. Without props, there’s no movement, so the flight controller keeps increasing throttle trying to 'correct' what it thinks is an error.\n\n"
                        "This shouldn't happen with props on.\n\n"
                        "---\n"
                        "^I ^am ^a ^bot, ^this ^action ^was ^done ^automatically."
                    )
                    submission.reply(response)
                    email_subject = "Bot Reply - Motor Spin Issue"
                    email_body = f"Title: {title}\n\nLink: {post_url}"
                    send_email(email_address, email_password, email_subject, email_body, recipient)

                else:
                    print(Fore.YELLOW + f"[SCANNED] No clear issue matched: {post_url}")

                break  # Success, so exit retry loop

            except prawcore.exceptions.ServerError as e:
                retries += 1
                print(Fore.RED + f"[ERROR] Internal Server Error: {e} (Retrying, attempt: {retries}/{max_retries})")
                time.sleep(RETRY_DELAY)

            except Exception as e:
                print(Fore.RED + f"[ERROR] Exception during reply or email: {e}")
                break  # Don't retry on unknown errors

        save_scanned_post(submission.id)
        time.sleep(10)
        
def scan_fpv_comments():
    subreddit = reddit.subreddit("fpv")
    scanned_comments = load_scanned_comments()

    for comment in subreddit.stream.comments(skip_existing=True):
        if comment.id in scanned_comments:
            continue
        if comment.author and comment.author.name == reddit.user.me().name:
            continue
        body = comment.body.lower()
        submission = comment.submission
        post_url = f"https://www.reddit.com{submission.permalink}"

        if "!flippost" in body:
            print(Fore.CYAN + f"[SUMMONED] !flippost in comment: {post_url}")
            try:
                submission.reply(
                    "It seems like you're experiencing a drone flip/yaw spin on takeoff.\n\n"
                    "[This](https://www.youtube.com/watch?v=7sSYwzVCJdA) video should help troubleshoot the issue.\n\n"
                    "---\n"
                    "^I ^am ^a ^bot, ^this ^response ^was ^triggered ^by ^!flippost ^in ^the ^comments."
                )
                send_email(
                    email_address,
                    email_password,
                    "Bot Summoned - FlipPost",
                    f"!flippost used in comment.\n\nPost title: {submission.title}\n\nLink: {post_url}",
                    recipient
                )
            except Exception as e:
                print(Fore.RED + f"[ERROR] Error replying to summoned flippost: {e}")
            finally:
                save_scanned_comment(comment.id)

        elif "!motorspin" in body:
            print(Fore.CYAN + f"[SUMMONED] !motorspin in comment: {post_url}")
            try:
                submission.reply(
                    "It seems like your quad's motors are throttling up on their own when arming without props. This is totally normal.\n\n"
                    "The flight controller expects the drone to react to motor output. Without props, there’s no movement, so the flight controller keeps increasing throttle trying to 'correct' what it thinks is an error.\n\n"
                    "This shouldn't happen with props on.\n\n"
                    "---\n"
                    "^I ^am ^a ^bot, ^this ^response ^was ^triggered ^by ^!motorspin ^in ^the ^comments."
                )
                send_email(
                    email_address,
                    email_password,
                    "Bot Summoned - MotorSpin",
                    f"!motorspin used in comment.\n\nPost title: {submission.title}\n\nLink: {post_url}",
                    recipient
                )
            except Exception as e:
                print(Fore.RED + f"[ERROR] Error replying to summoned motorspin: {e}")
            finally:
                save_scanned_comment(comment.id)

if __name__ == "__main__":
    print(Fore.MAGENTA + "[STATUS] Bot is launching...")
    time.sleep(1)
    print(Fore.MAGENTA + "[STATUS] Scanning r/fpv...")
    def run_post_scanner():
        while True:
            scan_fpv_subreddit()
            time.sleep(60)

    def run_comment_scanner():
        scan_fpv_comments()

    post_thread = threading.Thread(target=run_post_scanner)
    comment_thread = threading.Thread(target=run_comment_scanner)

    post_thread.start()
    comment_thread.start()
