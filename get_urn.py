import asyncio
import json
import os

import httpx

# Resolve absolute paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, "linkedin_token.json")
URN_PATH = os.path.join(BASE_DIR, "linkedin_urn.txt")


async def fetch_profile_urn():
    """Fetch the LinkedIn profile URN via the OIDC userinfo endpoint and save it locally."""
    try:
        with open(TOKEN_PATH, "r") as f:
            token_data = json.load(f)
            access_token = token_data.get("access_token")
    except FileNotFoundError:
        print("Error: linkedin_token.json not found. Run auth_server.py first.")
        return

    if not access_token:
        print("Error: access_token not found.")
        return

    # 2. Use the modern OIDC userinfo endpoint
    url = "https://api.linkedin.com/v2/userinfo"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    # 3. Call the API
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)

    if response.status_code == 200:
        profile_data = response.json()

        # The OIDC endpoint returns your full URN directly in the 'sub' field
        person_urn = profile_data.get("sub")
        name = profile_data.get("name")

        print("\n=== SUCCESS ===")
        print(f"Account Name: {name}")
        print(f"Your Profile URN: {person_urn}")
        print("===============\n")

        # Save this URN to a file so the scheduler can access it
        with open(URN_PATH, "w") as f:
            f.write(person_urn)

    else:
        print(f"Failed to fetch profile: {response.status_code}")
        print(response.json())


if __name__ == "__main__":
    asyncio.run(fetch_profile_urn())