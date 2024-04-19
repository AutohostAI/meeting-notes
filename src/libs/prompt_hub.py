import os
import requests


def get_prompt(name: str) -> str:
    """
    Gets a prompt from the Prompt Hub

    :param name: Name of the prompt to get
    :return: Prompt text
    """
    url = f"https://api.ops.autohost.ai/prompt-hub/agents/{name}"
    api_key = os.getenv("PROMPT_HUB_API_KEY")
    headers = {
        "x-api-key": api_key,
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()["data"]["prompt"]
    except requests.RequestException as e:
        print(f"Error getting prompt from Prompt Hub: {e}")
        return ""
