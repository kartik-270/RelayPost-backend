import os
import google.generativeai as genai
from tavily import TavilyClient
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from typing import List, Optional
import json

# --- Tavily Tool ---
class TavilyTool:
    def __init__(self):
        self.api_key = os.getenv("TAVILY_API_KEY")
        if self.api_key:
            self.client = TavilyClient(api_key=self.api_key)
        else:
            self.client = None

    async def search(self, query: str, topic: str = "news", max_results: int = 5):
        if not self.client:
            print("Tavily API key missing. Skipping search.")
            return []
        
        try:
            response = self.client.search(
                query=query,
                topic=topic,
                search_depth="basic",
                max_results=max_results
            )
            return response.get("results", [])
        except Exception as e:
            print(f"Tavily Search Error: {e}")
            return []

    async def extract(self, urls: List[str]):
        if not self.client:
            return []
        try:
            # Note: Tavily SDK might have extract or we use search with include_content=True
            # For simplicity, we'll assume the search results already have enough content 
            # or we can use the extract client if available in the SDK version.
            return self.client.extract(urls=urls)
        except Exception as e:
            print(f"Tavily Extract Error: {e}")
            return []

# --- Gemini Tool ---
class GeminiTool:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if self.api_key:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemma-3-27b-it')
        else:
            self.model = None

    async def generate_structured(self, prompt: str, temperature: float = 0.7, top_p: float = 0.95, max_retries: int = 3):
        import asyncio
        if not self.model:
            raise Exception("Gemini API key missing")
        
        generation_config = {
            "temperature": temperature,
            "top_p": top_p,
        }
        
        for attempt in range(max_retries):
            try:
                response = await self.model.generate_content_async(prompt, generation_config=generation_config)
                text = response.text
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0].strip()
                
                return json.loads(text)
            except Exception as e:
                error_msg = str(e)
                print(f"Gemini Generation Attempt {attempt + 1} Failed: {error_msg}")
                if "429" in error_msg and attempt < max_retries - 1:
                    wait_time = 20 * (attempt + 1)
                    print(f"Rate limited. Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    raise e

# --- Email Tool ---
class EmailTool:
    def __init__(self):
        self.conf = ConnectionConfig(
            MAIL_USERNAME=os.getenv("SMTP_USERNAME"),
            MAIL_PASSWORD=os.getenv("SMTP_PASSWORD"),
            MAIL_FROM=os.getenv("SMTP_USERNAME", "no-reply@relaypost.com"),
            MAIL_PORT=int(os.getenv("SMTP_PORT", "587")),
            MAIL_SERVER=os.getenv("SMTP_SERVER", "smtp.gmail.com"),
            MAIL_FROM_NAME="RelayPost Intelligence Automation",
            MAIL_STARTTLS=True,
            MAIL_SSL_TLS=False,
            USE_CREDENTIALS=True,
            VALIDATE_CERTS=False
        )

    async def send_notification(self, recipients: List[str], subject: str, body_html: str):
        if not self.conf.MAIL_PASSWORD:
            print("SMTP_PASSWORD missing. Skipping email notification.")
            return False
            
        message = MessageSchema(
            subject=subject,
            recipients=recipients,
            body=body_html,
            subtype=MessageType.html
        )
        
        fm = FastMail(self.conf)
        try:
            await fm.send_message(message)
            return True
        except Exception as e:
            print(f"Email Notification Error: {e}")
            return False
# --- Unsplash Tool ---
class UnsplashTool:
    def __init__(self):
        self.access_key = os.getenv("UNSPLASH_ACCESS_KEY")
        self.base_url = "https://api.unsplash.com"

    async def search_image(self, query: str, orientation: str = "landscape") -> Optional[str]:
        if not self.access_key:
            print("UNSPLASH_ACCESS_KEY missing. Skipping image search.")
            return None
            
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/search/photos",
                    params={
                        "query": query,
                        "per_page": 1,
                        "orientation": orientation
                    },
                    headers={"Authorization": f"Client-ID {self.access_key}"},
                    timeout=10.0
                )
                if response.status_code == 200:
                    data = response.json()
                    results = data.get("results", [])
                    if results:
                        # Return the regular size URL with high quality params
                        return results[0]["urls"]["regular"] + "&auto=format&fit=crop&w=1200&q=80"
                else:
                    print(f"Unsplash API Error: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"Unsplash Tool Error: {e}")
            
        return None
    async def download_image(self, url: str) -> Optional[bytes]:
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=20.0, follow_redirects=True)
                if response.status_code == 200:
                    return response.content
                else:
                    print(f"Failed to download image: {response.status_code}")
        except Exception as e:
            print(f"Image Download Error: {e}")
            
        return None
