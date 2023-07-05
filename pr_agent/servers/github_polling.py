import asyncio
import logging
import sys
from datetime import datetime, timezone

import aiohttp

from pr_agent.agent.pr_agent import PRAgent
from pr_agent.config_loader import settings

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
NOTIFICATION_URL = "https://api.github.com/notifications"


def now() -> str:
    now_utc = datetime.now(timezone.utc).isoformat()
    now_utc = now_utc.replace("+00:00", "Z")
    return now_utc


async def polling_loop():
    since = [now()]
    last_modified = [None]
    try:
        deployment_type = settings.github.deployment_type
        token = settings.github.user_token
    except AttributeError:
        deployment_type = 'none'
        token = None
    if deployment_type != 'user':
        raise ValueError("Deployment mode must be set to 'user' to get notifications")
    if not token:
        raise ValueError("User token must be set to get notifications")
    async with aiohttp.ClientSession() as session:
        while True:
            headers = {
                "Accept": "application/vnd.github.v3+json",
                "Authorization": f"Bearer {token}"
            }
            params = {
                "participating": "true"
            }
            if since[0]:
                params["since"] = since[0]
            if last_modified[0]:
                headers["If-Modified-Since"] = last_modified[0]
            async with session.get(NOTIFICATION_URL, headers=headers, params=params) as response:
                if response.status == 200:
                    if 'Last-Modified' in response.headers:
                        last_modified[0] = response.headers['Last-Modified']
                        since[0] = None
                    notifications = await response.json()
                    for notification in notifications:
                        if 'reason' in notification and notification['reason'] == 'mention':
                            if 'subject' in notification and notification['subject']['type'] == 'PullRequest':
                                pr_url = notification['subject']['url']
                                latest_comment = notification['subject']['latest_comment_url']
                                async with session.get(latest_comment, headers=headers) as comment_response:
                                    if comment_response.status == 200:
                                        comment = await comment_response.json()
                                        comment_body = comment['body'] if 'body' in comment else ''
                                        commenter_github_user = comment['user']['login'] if 'user' in comment else ''
                                        logging.info(f"Commenter: {commenter_github_user}\nComment: {comment_body}")
                                        if comment_body.strip().startswith("@"):
                                            agent = PRAgent()
                                            await agent.handle_request(pr_url, comment_body)
                elif response.status != 304:
                    print(f"Failed to fetch notifications. Status code: {response.status}")

            await asyncio.sleep(5)

if __name__ == '__main__':
    asyncio.run(polling_loop())