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
import prawcore

init(autoreset=True)

# Email credentials
email_address = "____"
email_password = "____"

# Email recipient
recipient = "____"

# Reddit API credentials
reddit_client_id = "____"
reddit_client_secret = "____"
reddit_username = "___"
reddit_password = "____"
reddit_user_agent = "___"

# OpenAI API key
openai_api_key = "____"

# File path to track scanned posts
scanned_posts_file = "___"
scanned_comments_file = "___"

# Initialise Reddit and OpenAI
reddit = praw.Reddit(
    client_id=reddit_client_id,
    client_secret=reddit_client_secret,
    username=reddit_username,
    password=reddit_password,
    user_agent=reddit_user_agent
)
openai.api_key = openai_api_key

# Load the set of already scanned post IDs from file. If empty returns nothing
def load_scanned_posts():
    if not os.path.exists(scanned_posts_file):
        return set()
    with open(scanned_posts_file, "r") as f:
        return set(line.strip() for line in f.readlines())

# Save a post ID to the file
def save_scanned_post(post_id):
    os.makedirs(os.path.dirname(scanned_posts_file), exist_ok=True)
    with open(scanned_posts_file, "a") as f:
        f.write(post_id + "\n")
        
# Load the set of already scanned comment IDs from file. If empty returns nothing
def load_scanned_comments():
    if not os.path.exists(scanned_comments_file):
        return set()
    with open(scanned_comments_file, "r") as f:
        return set(line.strip() for line in f.readlines())
        
# Save a comment ID to the file
def save_scanned_comment(comment_id):
    os.makedirs(os.path.dirname(scanned_comments_file), exist_ok=True)
    with open(scanned_comments_file, "a") as f:
        f.write(comment_id + "\n")
        # print(Fore.YELLOW + f"[LOG] Saved comment ID: {comment_id}")

# Filter obviously irrelevant posts, to reduce openai costs
def post_filtering(title, body):
    text = f"{title} {body}".lower()
    keywords = [
        "motor", "motors", "spin", "spinning", "throttle", "arming", "arm",
        "prop", "props", "propeller","flip", "flips", "flipping", "flipped", "flip out", "flips out", "roll", "yaw spin", 
        "jump", "tumbles", "unstable on takeoff", "disarms on takeoff", "crash", "flips on arming",
        "disarm", "uncontrollable", "flip takeoff", "won't takeoff", "getting started", "beginner", 
        "newbie", "advice", "setup", "help", "fpv", "aliexpress", "ali", "coupons", "code", "discount"]

    return any(keyword in text for keyword in keywords)

# Initialise OpenAI, set parameters, error management
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
            break
            
# Send email
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

# Prompt for flip posts
def flip_post(title, body, submission):
    prompt = f"""A user posted this in r/fpv:
    Title: "{title}"
    Body: "{body}"
    Is this post asking how to fix a drone (also called quad, kwad, quadcopter, tinywhoop, cinewhoop, whoop) that is experiencing a flip-out on takeoff?  
    Only answer "Yes" if ALL of the following are true:
    - The drone is flipping, spinning, jumping, or disarming right after arming or throttle-up.
    - The user is seeking help or trying to fix the problem.
    - It happens at or immediately after takeoff (not mid-flight or after flying normally).
    - It is unintentional (not a trick, flip mode, or freestyle).

    Answer "No" if:
    - The drone flies normally first before flipping or crashing.
    - The flip/spin is part of a trick or a stunt.
    - The post is vague or you're unsure.
    - The user is not asking for help.

    Reply only with "Yes" or "No".
    """
    return ask_openai(prompt) == "yes"

def soldering_help(title, body, submission):
    prompt = f"""
    You are checking if someone is asking for help with soldering in this Reddit post.

    Title: "{title}"
    Body: "{body}"

    Reply "Yes" only if:
    - The user is clearly asking how to solder something.
    - Or they want feedback on their soldering work.
    - Example: "why won't this wire stick?", "rate my soldering", "is this a cold joint?"

    Reply "No" if:
    - They just mention soldering.
    - They are only talking about tools or gear.
    - They arent asking for help specifically with soldering.
    - Or you're not sure.

    Answer only "Yes" or "No".
    """
    return ask_openai(prompt) == "yes"
    
def aliexpress_promo(title, body, submission):
    prompt = f"""
    A user ported this in r/fpv:
    Title: "{title}"
    Body: "{body}"
    
    Is this user promoting aliexpress (also shortened to Ali) discount codes/coupon codes?
    
    Reply "Yes" only if:
    - The user is offering Aliexpress (or Ali) discount codes (even if they say they randomly found the codes (which is not true)).
    - They mention Ali (Aliexpress) and coupon codes/discounts in the post.

    Reply "No" if:
    - You are not sure.
    
    The user may not directly offer the codes, they often suggest that they randomly discovered them which is not true (reply "Yes" to these posts)
    
    Only answer "Yes" or "No"
    """
    return ask_openai(prompt) == "yes"
    

# Scan the past 20 (unless already scanned) in r/fpv, reply if gpt prompt returns as a "yes".
def scan_fpv_subreddit():
    subreddit = reddit.subreddit("fpv")
    scanned_posts = load_scanned_posts()
    max_retries = 15
    for submission in subreddit.new(limit=20):
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
                if flip_post(title, body, submission):
                    print(Fore.GREEN + f"[REPLIED] Flip issue detected: {post_url}")
                    response = (
                        "It seems like you're experiencing a drone flip/yaw spin on takeoff.\n\n"
                        "[This](https://www.youtube.com/watch?v=7sSYwzVCJdA) video should help troubleshoot the issue.\n\n"
                        "---\n"
                        "^I ^am ^a ^bot, ^this ^action ^was ^done ^automatically."
                    )
                    submission.reply(response)
                    submission.report("Suspected FAQ (bot flagged)")
                    email_subject = "Bot Reply - Flip Detected"
                    email_body = f"Title: {title}\n\nLink: {post_url}"
                    send_email(email_address, email_password, email_subject, email_body, recipient)
                    
                elif aliexpress_promo(title, body, submission):
                    print(Fore.GREEN + f"[REMOVED] Possible Aliexpress promo: {post_url}")
                    # submission.report("Suspected Aliexpress Spam (bot flagged)")
                    submission.mod.remove(spam=True, mod_note="Auto-removed suspected Aliexpress spam.")
                    email_subject = "Bot Reply - Aliexpress Spam"
                    email_body = f"Title: {title}\n\nLink: {post_url}"
                    send_email(email_address, email_password, email_subject, email_body, recipient)
           
                elif soldering_help(title, body, submission):
                    print(Fore.GREEN + f"[REPLIED] Soldering help post detected: {post_url}")
                    response = (
                        "It seems like you're asking for soldering help or for feedback on your soldering (or just mentioned the word *soldering* — i'm not the smartest XD).\n\n"
                        "[This video by Joshua Bardwell](https://www.youtube.com/watch?v=GoPT69y98pY) is an excellent guide on how to solder properly for FPV builds and includes tips for tinning, cleaning pads, and avoiding cold joints.\n\n"
                        "[This written guide by Oscar Liang](https://oscarliang.com/soldering-guide/) also goes through gear, technique, and common issues in a beginner-friendly way.\n\n"
                        "---\n"
                        "^I ^am ^a ^bot, ^this ^action ^was ^done ^automatically."
                    )
                    submission.reply(response)
                    # submission.report("Suspected FAQ (bot flagged)")
                    email_subject = "Bot Reply - Soldering Help Post"
                    email_body = f"Title: {title}\n\nLink: {post_url}"
                    send_email(email_address, email_password, email_subject, email_body, recipient)
                else:
                    print(Fore.YELLOW + f"[SCANNED] No clear issue matched: {post_url}")

                break  # Success, so exit retry loop

            except prawcore.exceptions.ServerError as e:
                retries += 1
                print(Fore.RED + f"[ERROR] Internal Server Error: {e} (Retrying, attempt: {retries}/{max_retries})")
                time.sleep(10)

            except Exception as e:
                print(Fore.RED + f"[ERROR] Exception during reply or email: {e}")
                break  # Don't retry on unknown errors

        save_scanned_post(submission.id)
        time.sleep(20)

# Scan comments for summons such as !flippost and replies such as "good bot" and "bad bot".
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
                
        elif "!soldering" in body:
            print(Fore.CYAN + f"[SUMMONED] !soldering in comment: {post_url}")
            try:
                submission.reply(
                    "It seems like you're asking for soldering help or for feedback on your soldering.\n\n"
                    "[This video by Joshua Bardwell](https://www.youtube.com/watch?v=GoPT69y98pY) is an excellent guide on how to solder properly for FPV builds and includes tips for tinning, cleaning pads, and avoiding cold joints.\n\n"
                    "[This written guide by Oscar Liang](https://oscarliang.com/soldering-guide/) also goes through gear, technique, and common issues in a beginner-friendly way.\n\n"
                    "---\n"
                    "^I ^am ^a ^bot, ^this ^response ^was ^triggered ^by ^!soldering ^in ^the ^comments."
                )
                send_email(
                    email_address,
                    email_password,
                    "Bot Summoned - Soldering",
                    f"!soldering used in comment.\n\nPost title: {submission.title}\n\nLink: {post_url}",
                    recipient
                )
            except Exception as e:
                print(Fore.RED + f"[ERROR] Error replying to summoned soldering: {e}")
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
        if comment.parent_id.startswith("t1_"):  
            try:
                parent_comment = reddit.comment(id=comment.parent_id[3:])
                if parent_comment.author and parent_comment.author.name == reddit.user.me().name:
                
                    if "good bot" in body:
                        if comment.author and comment.author.name.lower() != "_________": # Nice user replies "Good bot" whenever the bot responds
                            print(Fore.GREEN + f"[REPLIED] Good bot detected: https://www.reddit.com{comment.permalink}")
                            comment.reply("Good human.")
                        else:
                            print(Fore.YELLOW + f"[Fav Human]: {comment.author.name}")
                            comment.reply("My favorite human <3")
                            
                        save_scanned_comment(comment.id)
                        continue
                        
                    elif "bad bot" in body:
                        if comment.author and comment.author.name.lower() != "______":  # Troublesome username
                            print(Fore.RED + f"[DELETED] Bad bot detected: https://www.reddit.com{parent_comment.permalink}")
                            parent_comment.delete()
                            comment.reply("Sorry for the mistake, I've deleted my comment.")
                        else:
                            print(Fore.YELLOW + f"[IGNORED] 'Bad bot' from ignored user: {comment.author.name}")
                            comment.reply("Bad human, you misused this function too many times, i'm ignoring you now :p")
                save_scanned_comment(comment.id)
            except Exception as e:
                print(Fore.RED + f"[ERROR] Checking replies: {e}")
                
                
# Main loop
if __name__ == "__main__":
    print(Fore.MAGENTA + "[STATUS] Bot is starting...")
    time.sleep(1)
    print(Fore.MAGENTA + "[STATUS] Scanning r/fpv...")
    def run_post_scanner():
        while True:
            try:
                scan_fpv_subreddit()
            except Exception as e:
                # print(Fore.RED + f"[ERROR] Post scanner crash: {e}")
                time.sleep(5)  


    def run_comment_scanner():
        while True:
            try:
                scan_fpv_comments()
                time.sleep(20)
            except Exception as e:
                # print(Fore.RED + f"[ERROR] Comment scanner crash: {e}")
                time.sleep(5)
    post_thread = threading.Thread(target=run_post_scanner)
    comment_thread = threading.Thread(target=run_comment_scanner)

    post_thread.start()
    comment_thread.start()
